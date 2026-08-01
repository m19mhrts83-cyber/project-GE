#!/usr/bin/env python3
"""周辺MAP 単独Web — Gemini連鎖 + Places + Static + C0（＋任意C1）.

秘密は環境変数のみ。キーを print しない。

  set -a && source .env.jarvis_private && set +a
  python scripts/shuhen_auto_pipeline.py --property Grandole志賀本通 \\
    --address '愛知県名古屋市北区杉栄町' --out /tmp/shuhen_job
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
import uuid
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
JOBS_DIR = ROOT / ".jarvis_state" / "shuhen_auto_jobs"
DEFAULT_MODEL = os.environ.get("GEMINI_MODEL") or "gemini-flash-latest"
IMAGE_MODEL = os.environ.get("GEMINI_IMAGE_MODEL") or "gemini-2.5-flash-image"

STYLE_PARAMS = [
    "feature:poi|visibility:off",
    "feature:poi.business|visibility:off",
    "feature:administrative|element:labels|visibility:off",
    "feature:administrative.neighborhood|element:labels|visibility:off",
    "feature:administrative.land_parcel|element:labels|visibility:off",
    "feature:administrative.locality|element:labels|visibility:off",
    "feature:landscape|element:labels|visibility:off",
    "feature:water|element:labels|visibility:off",
    "feature:road|element:labels|visibility:off",
    "feature:transit|element:labels|visibility:off",
    "feature:transit|element:labels.icon|visibility:off",
    "feature:transit.station|element:labels|visibility:off",
]

C1_PROMPT = """あなたは賃貸物件の周辺MAP用の地図下地を整える画像編集アシスタントです。
添付の地図画像（ピンなし・クリーン表示）の色味だけを、ベージュ／クリーム紙面のガイドマップ風に寄せてください。

厳守:
- 道路の形状・交差点・東西南北の配置を変えない（描き直し禁止）
- 番号ピン・店名・Access・吹き出し・人物を新たに描かない
- 文字ラベルを増やさない
- 出力は地図下地の画像のみ

タッチ: 標準（ベージュ紙面）。
物件名（ログ用・画像に大きく書かない）: {property_name}
"""


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def gemini_text(prompt: str, *, api_key: str, model: str = DEFAULT_MODEL) -> str:
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3},
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        data = json.load(r)
    parts = (data.get("candidates") or [{}])[0].get("content", {}).get("parts") or []
    texts = [p.get("text") or "" for p in parts if isinstance(p, dict)]
    out = "\n".join(t for t in texts if t).strip()
    if not out:
        raise RuntimeError("empty Gemini text response")
    return out


def gemini_json(prompt: str, *, api_key: str, model: str = DEFAULT_MODEL) -> dict[str, Any]:
    raw = gemini_text(
        prompt
        + "\n\n重要: 返答は JSON オブジェクトのみ。前後に説明文や ``` を付けない。",
        api_key=api_key,
        model=model,
    )
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


def build_wash_prompt(
    property_name: str, address: str, target: str, facility_count: int
) -> str:
    return f"""あなたは賃貸物件の空室対策用「周辺MAP」素材を作るアシスタントです。
存在しない店名を作らない。徒歩分は断定せず「約N分（要実測確認）」とする。

物件名: {property_name}
住所: {address}
ターゲット: {target}
施設数の目安: {facility_count}

次の JSON だけを返す:
{{
  "area_blurb": "エリア一言 1〜2行",
  "access": [{{"name":"施設名","kind":"駅|スーパー|ドラッグ|コンビニ|行政|その他","walk":"約N分（要実測確認）","note":"メモ"}}],
  "candidates": [{{"category":"駅|スーパー|ドラッグ|飲食|カフェ|公園|名所|娯楽|行政|その他","query":"Googleマップ検索クエリ（地名付き）","name":"短い表示名","blurb":"吹き出し一言20字前後","priority":"A|B|C"}}]
}}

制約:
- access は 6〜8 件。最寄り駅を必ず含める
- candidates は目安 {facility_count} 件。駅を1件以上。公園・緑地を可能な範囲で1件
- 物件自体は candidates に入れない
- query はマップでヒットしやすい表記
"""


def build_verify_prompt(
    property_name: str, address: str, target: str, wash: dict[str, Any]
) -> str:
    return f"""あなたは周辺MAP向けの実在検証アシスタントです。
候補リストを精査し、実在しそうな施設だけ最大8件（P1〜P8）に絞る。
不明・架空は落とす。駅は必ず残す（実在する最寄り）。

物件名: {property_name}
住所: {address}
ターゲット: {target}
候補JSON:
{json.dumps(wash, ensure_ascii=False)}

次の JSON だけを返す:
{{
  "area_blurb": "確定エリア一言",
  "access": [{{"name":"...","kind":"...","walk":"...","note":"..."}}],
  "facilities": [{{"id":"P1","category":"...","query":"...","name":"...","blurb":"...","needs_check":true}}]
}}

制約:
- facilities は最大8件（P1..P8）
- id は連番
- needs_check は徒歩・評判が未確定なら true
"""


def http_get_json(url: str) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": "ShuhenAuto/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def geocode(address: str, *, maps_key: str) -> dict[str, Any] | None:
    q = urllib.parse.urlencode(
        {"address": address, "language": "ja", "region": "jp", "key": maps_key}
    )
    data = http_get_json(f"https://maps.googleapis.com/maps/api/geocode/json?{q}")
    results = data.get("results") or []
    if not results:
        return None
    loc = results[0]["geometry"]["location"]
    return {
        "lat": loc["lat"],
        "lng": loc["lng"],
        "formatted": results[0].get("formatted_address") or address,
        "ok": True,
    }


def find_place(query: str, *, lat: float, lng: float, maps_key: str) -> dict[str, Any]:
    q = urllib.parse.urlencode(
        {
            "input": query,
            "inputtype": "textquery",
            "fields": "name,geometry,formatted_address,place_id",
            "locationbias": f"point:{lat},{lng}",
            "language": "ja",
            "key": maps_key,
        }
    )
    data = http_get_json(
        f"https://maps.googleapis.com/maps/api/place/findplacefromtext/json?{q}"
    )
    cands = data.get("candidates") or []
    if not cands:
        return {"ok": False, "status": data.get("status") or "ZERO"}
    c = cands[0]
    loc = c["geometry"]["location"]
    return {
        "ok": True,
        "name": c.get("name") or query,
        "lat": loc["lat"],
        "lng": loc["lng"],
        "formatted": c.get("formatted_address") or "",
        "place_id": c.get("place_id") or "",
    }


def static_map_png(
    pins: list[dict[str, Any]], *, maps_key: str, with_markers: bool, size: str = "900x700"
) -> bytes:
    ok = [p for p in pins if p.get("ok") and p.get("lat") is not None]
    if not ok:
        raise RuntimeError("no pins for static map")
    lats = [p["lat"] for p in ok]
    lngs = [p["lng"] for p in ok]
    pad = 0.002
    visible = f"{min(lats) - pad},{min(lngs) - pad}|{max(lats) + pad},{max(lngs) + pad}"
    params: list[tuple[str, str]] = [
        ("size", size),
        ("scale", "2"),
        ("maptype", "roadmap"),
        ("language", "ja"),
        ("visible", visible),
        ("key", maps_key),
    ]
    for s in STYLE_PARAMS:
        params.append(("style", s))
    if with_markers:
        for p in ok:
            color = "red" if p.get("id") == "P0" or p.get("isProperty") else "blue"
            lab = str(p.get("id", "X")).replace("P", "")[:1] or "X"
            params.append(
                ("markers", f"color:{color}|label:{lab}|{p['lat']},{p['lng']}")
            )
    url = "https://maps.googleapis.com/maps/api/staticmap?" + urllib.parse.urlencode(
        params
    )
    req = urllib.request.Request(url, headers={"User-Agent": "ShuhenAuto/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
        ctype = r.headers.get("Content-Type", "")
        if "image" not in ctype and data[:8] != b"\x89PNG\r\n\x1a\n":
            raise RuntimeError(f"static map failed: {ctype} {data[:80]!r}")
        return data


def tone_wash(base: Image.Image) -> Image.Image:
    img = base.convert("RGB")
    img = ImageEnhance.Color(img).enhance(0.32)
    img = ImageEnhance.Contrast(img).enhance(0.86)
    img = ImageEnhance.Brightness(img).enhance(1.10)
    paper = Image.new("RGB", img.size, (232, 218, 192))
    img = Image.blend(img, paper, 0.34)
    soft = img.filter(ImageFilter.SMOOTH_MORE)
    return Image.blend(img, soft, 0.40)


def latlng_to_xy(
    lat: float, lng: float, pins: list[dict], w: int, h: int, pad: float = 0.002
):
    lats = [p["lat"] for p in pins]
    lngs = [p["lng"] for p in pins]
    min_lat, max_lat = min(lats) - pad, max(lats) + pad
    min_lng, max_lng = min(lngs) - pad, max(lngs) + pad
    x = (lng - min_lng) / (max_lng - min_lng) * (w - 40) + 20
    y = (max_lat - lat) / (max_lat - min_lat) * (h - 40) + 20
    return x, y


def draw_pin(draw: ImageDraw.ImageDraw, x: float, y: float, label: str, is_property: bool):
    color = (192, 57, 43) if is_property else (41, 128, 185)
    r = 14
    draw.ellipse(
        (x - r, y - r - 6, x + r, y + r - 6),
        fill=color,
        outline=(255, 255, 255),
        width=2,
    )
    draw.polygon([(x - 7, y + 4), (x + 7, y + 4), (x, y + 16)], fill=color)
    text = label.replace("P", "")
    draw.text((x - 5, y - 12), text, fill=(255, 255, 255))


def recompose(base: Image.Image, pins: list[dict]) -> Image.Image:
    img = base.convert("RGBA")
    draw = ImageDraw.Draw(img)
    w, h = img.size
    ok = [p for p in pins if p.get("ok") and p.get("lat") is not None]
    for p in ok:
        x, y = latlng_to_xy(p["lat"], p["lng"], ok, w, h)
        draw_pin(
            draw,
            x,
            y,
            p.get("id", "?"),
            bool(p.get("isProperty") or p.get("id") == "P0"),
        )
    return img.convert("RGB")


def png_b64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def b64_to_image(b64: str) -> Image.Image:
    raw = base64.b64decode(b64)
    return Image.open(io.BytesIO(raw)).convert("RGB")


def places_list_text(facilities: list[dict[str, Any]]) -> str:
    lines = []
    for f in facilities:
        lines.append(f"{f['id']} | {f['query']} | {f['name']}")
    return "\n".join(lines)


def run_pipeline(
    *,
    property_name: str,
    address: str,
    target: str = "",
    facility_count: int = 15,
    job_id: str | None = None,
) -> dict[str, Any]:
    gemini_key = _env("GEMINI_API_KEY")
    maps_key = _env("GOOGLE_MAPS_API_KEY")
    if not gemini_key:
        raise RuntimeError("GEMINI_API_KEY 未設定")
    if not maps_key:
        raise RuntimeError("GOOGLE_MAPS_API_KEY 未設定")

    target = target.strip() or "単身〜カップル想定の一般向け"
    facility_count = max(8, min(int(facility_count or 15), 20))
    job_id = job_id or str(uuid.uuid4())
    steps: list[dict[str, Any]] = []
    errors: list[str] = []

    # 1) wash
    try:
        wash = gemini_json(
            build_wash_prompt(property_name, address, target, facility_count),
            api_key=gemini_key,
        )
        steps.append({"id": "wash", "ok": True, "detail": f"candidates={len(wash.get('candidates') or [])}"})
    except Exception as e:
        steps.append({"id": "wash", "ok": False, "detail": str(e)})
        raise

    # 2) verify
    try:
        verified = gemini_json(
            build_verify_prompt(property_name, address, target, wash),
            api_key=gemini_key,
        )
        facilities = verified.get("facilities") or []
        if not facilities:
            raise RuntimeError("検証後の施設が0件です")
        steps.append({"id": "verify", "ok": True, "detail": f"facilities={len(facilities)}"})
    except Exception as e:
        steps.append({"id": "verify", "ok": False, "detail": str(e)})
        raise

    # 3) geocode + places
    prop = geocode(address, maps_key=maps_key)
    if not prop:
        steps.append({"id": "places", "ok": False, "detail": "物件ジオコード失敗"})
        raise RuntimeError("物件住所のジオコードに失敗しました")

    property_pin = {
        "id": "P0",
        "name": property_name,
        "query": address,
        "lat": prop["lat"],
        "lng": prop["lng"],
        "formatted": prop.get("formatted") or address,
        "ok": True,
        "isProperty": True,
        "blurb": "",
        "category": "物件",
        "needs_check": False,
    }

    resolved: list[dict[str, Any]] = []
    for f in facilities[:8]:
        found = find_place(
            f.get("query") or f.get("name") or "",
            lat=prop["lat"],
            lng=prop["lng"],
            maps_key=maps_key,
        )
        row = {
            "id": f.get("id") or f"P{len(resolved)+1}",
            "query": f.get("query") or "",
            "name": f.get("name") or "",
            "blurb": f.get("blurb") or "",
            "category": f.get("category") or "",
            "needs_check": bool(f.get("needs_check", True)),
            "ok": bool(found.get("ok")),
            "lat": found.get("lat"),
            "lng": found.get("lng"),
            "formatted": found.get("formatted") or "",
            "resolvedName": found.get("name") or "",
            "isProperty": False,
        }
        if not row["ok"]:
            errors.append(f"{row['id']} Places未ヒット: {row['name']}")
        resolved.append(row)

    ok_count = sum(1 for r in resolved if r["ok"])
    steps.append({"id": "places", "ok": ok_count > 0, "detail": f"ok={ok_count}/{len(resolved)}"})
    if ok_count == 0:
        raise RuntimeError("施設の Places 確定が0件です")

    pins_for_map = [property_pin] + resolved

    # 4) static clean (no markers) + C0
    try:
        clean_bytes = static_map_png(pins_for_map, maps_key=maps_key, with_markers=False)
        clean_img = Image.open(io.BytesIO(clean_bytes)).convert("RGB")
        c0 = tone_wash(clean_img)
        c0_pins = recompose(c0, pins_for_map)
        steps.append({"id": "static", "ok": True, "detail": "clean+static ok"})
        steps.append({"id": "c0", "ok": True, "detail": "beige wash ok"})
    except Exception as e:
        steps.append({"id": "static", "ok": False, "detail": str(e)})
        steps.append({"id": "c0", "ok": False, "detail": str(e)})
        raise

    result = {
        "job_id": job_id,
        "property_name": property_name,
        "address": address,
        "target": target,
        "area_blurb": verified.get("area_blurb") or wash.get("area_blurb") or "",
        "access": verified.get("access") or wash.get("access") or [],
        "facilities": resolved,
        "property_pin": property_pin,
        "places_list_text": places_list_text(resolved),
        "images": {
            "c0_base_png_b64": png_b64(c0),
            "c0_with_pins_png_b64": png_b64(c0_pins),
        },
        "c1": {"status": "idle", "png_b64": None, "message": ""},
        "errors": errors,
        "steps": steps,
    }

    job_dir = JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "result.json").write_text(
        json.dumps({k: v for k, v in result.items() if k != "images"}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    c0.save(job_dir / "c0_base.png")
    c0_pins.save(job_dir / "c0_with_pins.png")
    clean_img.save(job_dir / "clean_base.png")
    # keep images path refs for C1
    meta = {
        "property_name": property_name,
        "clean_base": str(job_dir / "clean_base.png"),
        "c0_base": str(job_dir / "c0_base.png"),
    }
    (job_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def run_c1(job_id: str, *, timeout_sec: int = 120) -> dict[str, Any]:
    """Optional C1: Gemini image edit on pin-less C0/clean base. Human accepts/rejects in UI."""
    gemini_key = _env("GEMINI_API_KEY")
    if not gemini_key:
        raise RuntimeError("GEMINI_API_KEY 未設定")
    job_dir = JOBS_DIR / job_id
    meta_path = job_dir / "meta.json"
    if not meta_path.exists():
        raise RuntimeError("job が見つかりません。先に作成を実行してください")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    src = Path(meta.get("c0_base") or meta.get("clean_base") or "")
    if not src.exists():
        raise RuntimeError("下地画像がありません")

    img_bytes = src.read_bytes()
    b64 = base64.b64encode(img_bytes).decode("ascii")
    prompt = C1_PROMPT.format(property_name=meta.get("property_name") or "")

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{IMAGE_MODEL}:generateContent?key={gemini_key}"
    )
    body = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": "image/png", "data": b64}},
                ],
            }
        ],
        "generationConfig": {
            "temperature": 0.4,
            "responseModalities": ["TEXT", "IMAGE"],
        },
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        err = e.read()[:400].decode("utf-8", errors="replace")
        return {
            "status": "failed",
            "png_b64": None,
            "message": f"C1 APIエラー HTTP {e.code}: {err[:200]}",
        }
    except Exception as e:
        return {"status": "failed", "png_b64": None, "message": f"C1失敗: {e}"}

    parts = (data.get("candidates") or [{}])[0].get("content", {}).get("parts") or []
    out_b64 = None
    text_msg = ""
    for p in parts:
        if not isinstance(p, dict):
            continue
        if p.get("text"):
            text_msg = (text_msg + " " + p["text"]).strip()
        inline = p.get("inline_data") or p.get("inlineData")
        if inline and inline.get("data"):
            out_b64 = inline["data"]
    if not out_b64:
        return {
            "status": "failed",
            "png_b64": None,
            "message": text_msg or "画像が返りませんでした（モデル未対応の可能性）",
        }

    out_path = job_dir / "c1_base.png"
    out_path.write_bytes(base64.b64decode(out_b64))

    # recompose pins onto C1 if coords available
    result_path = job_dir / "result.json"
    pins_img_b64 = None
    if result_path.exists():
        try:
            prev = json.loads(result_path.read_text(encoding="utf-8"))
            pins = [prev.get("property_pin")] + (prev.get("facilities") or [])
            pins = [p for p in pins if p]
            c1_img = b64_to_image(out_b64)
            with_pins = recompose(c1_img, pins)
            with_pins.save(job_dir / "c1_with_pins.png")
            pins_img_b64 = png_b64(with_pins)
        except Exception:
            pins_img_b64 = None

    return {
        "status": "ready",
        "png_b64": out_b64,
        "with_pins_png_b64": pins_img_b64,
        "message": text_msg or "C1完了。道路が追えるか確認して採用／破棄してください。",
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--property", required=True)
    ap.add_argument("--address", required=True)
    ap.add_argument("--target", default="")
    ap.add_argument("--facility-count", type=int, default=15)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)
    result = run_pipeline(
        property_name=args.property,
        address=args.address,
        target=args.target,
        facility_count=args.facility_count,
    )
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        slim = {k: v for k, v in result.items() if k != "images"}
        (args.out / "result.json").write_text(
            json.dumps(slim, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"wrote {args.out / 'result.json'}")
        print(f"job_id={result['job_id']} facilities={len(result['facilities'])}")
    else:
        slim = {k: v for k, v in result.items() if k != "images"}
        print(json.dumps(slim, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
