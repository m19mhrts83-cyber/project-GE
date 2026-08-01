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

# A4横（297×210mm）・300dpi 相当。Static API は 640x453×scale=2 取得後にリサイズ。
A4_LANDSCAPE_PX = (3508, 2480)
STATIC_MAP_SIZE = "640x453"  # ≈ A4 横比率（Google Static 上限 640）
WALK_M_PER_MIN = 80.0  # 不動産慣例の目安
WALK_PREFER_MIN = 7
WALK_SOFT_MAX_MIN = 20
WALK_HARD_MAX_MIN = 30

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
  "candidates": [{{"category":"駅|スーパー|ドラッグ|飲食|カフェ|公園|名所|娯楽|行政|その他","query":"Googleマップ検索クエリ（地名付き）","name":"短い表示名","blurb":"吹き出し一言20字前後","priority":"A|B|C","why":"選んだ理由1行"}}]
}}

制約:
- access は 6〜8 件。最寄り駅を必ず含める
- candidates は目安 {facility_count} 件。駅を1件以上。公園・緑地を可能な範囲で1件
- **徒歩圏を厳守**: 優先は徒歩約{WALK_PREFER_MIN}分以内、次に約{WALK_SOFT_MAX_MIN}分以内。徒歩約{WALK_HARD_MAX_MIN}分超は候補に入れない（魅力が薄れる）
- 物件自体は candidates に入れない
- query はマップでヒットしやすい表記
- candidates の各要素に "why":"選んだ理由1行" を付ける
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
  "facilities": [{{"id":"P1","category":"...","query":"...","name":"...","blurb":"...","why":"採用理由","needs_check":true}}],
  "rejected": [{{"name":"...","query":"...","reason":"落とした理由"}}]
}}

制約:
- facilities は最大8件（P1..P8）
- id は連番
- needs_check は徒歩・評判が未確定なら true
- **徒歩約{WALK_HARD_MAX_MIN}分超は落とす**（優先は約{WALK_PREFER_MIN}〜{WALK_SOFT_MAX_MIN}分）。rejected に理由を書く
- 落とした候補は rejected に残す（後で人が見直せるように）
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


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    import math

    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def walk_min_from_m(meters: float) -> float:
    return round(meters / WALK_M_PER_MIN, 1)


def looks_like_station(row: dict[str, Any]) -> bool:
    blob = f"{row.get('category') or ''} {row.get('name') or ''} {row.get('query') or ''}"
    return "駅" in blob


def annotate_distance(
    rows: list[dict[str, Any]], *, prop_lat: float, prop_lng: float
) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        row = dict(r)
        if row.get("ok") and row.get("lat") is not None and row.get("lng") is not None:
            dm = haversine_m(prop_lat, prop_lng, float(row["lat"]), float(row["lng"]))
            row["distance_m"] = int(round(dm))
            row["walk_min_approx"] = walk_min_from_m(dm)
            row["walk_band"] = (
                "prefer"
                if row["walk_min_approx"] <= WALK_PREFER_MIN
                else "soft"
                if row["walk_min_approx"] <= WALK_SOFT_MAX_MIN
                else "hard"
                if row["walk_min_approx"] <= WALK_HARD_MAX_MIN
                else "far"
            )
        else:
            row["distance_m"] = None
            row["walk_min_approx"] = None
            row["walk_band"] = "unknown"
        out.append(row)
    return out


def filter_by_walk_radius(
    rows: list[dict[str, Any]], *, max_keep: int = 8
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """徒歩圏で絞る。戻り値: (採用, 距離などで除外)."""
    ok_rows = [r for r in rows if r.get("ok") and r.get("walk_min_approx") is not None]
    failed = [r for r in rows if not r.get("ok")]
    dropped: list[dict[str, Any]] = []
    for r in failed:
        d = dict(r)
        d["drop_reason"] = "Places未ヒット"
        dropped.append(d)

    near = [r for r in ok_rows if (r.get("walk_min_approx") or 999) <= WALK_HARD_MAX_MIN]
    far = [r for r in ok_rows if (r.get("walk_min_approx") or 999) > WALK_HARD_MAX_MIN]
    for r in far:
        d = dict(r)
        d["drop_reason"] = f"徒歩約{r.get('walk_min_approx')}分（上限{WALK_HARD_MAX_MIN}分超・直線換算）"
        dropped.append(d)

    # 駅は近いものを最低1件確保（near に無ければ far の最寄りを例外採用）
    stations_near = [r for r in near if looks_like_station(r)]
    if not stations_near:
        stations_far = sorted(
            [r for r in far if looks_like_station(r)],
            key=lambda x: x.get("walk_min_approx") or 999,
        )
        if stations_far:
            keep_st = dict(stations_far[0])
            keep_st["drop_reason"] = None
            keep_st["walk_exception"] = True
            near.append(keep_st)
            dropped = [
                d
                for d in dropped
                if not (
                    d.get("id") == keep_st.get("id")
                    and d.get("drop_reason", "").startswith("徒歩約")
                )
            ]

    def sort_key(r: dict[str, Any]) -> tuple:
        band = {"prefer": 0, "soft": 1, "hard": 2, "far": 3}.get(r.get("walk_band") or "", 9)
        is_st = 0 if looks_like_station(r) else 1
        return (band, is_st, r.get("walk_min_approx") or 999)

    near_sorted = sorted(near, key=sort_key)
    kept = near_sorted[:max_keep]
    for r in near_sorted[max_keep:]:
        d = dict(r)
        d["drop_reason"] = "件数上限のため保留（近い施設を優先）"
        dropped.append(d)

    # 再採番 P1..
    for i, r in enumerate(kept, start=1):
        r["id"] = f"P{i}"
    return kept, dropped


def upscale_to_a4(img: Image.Image) -> Image.Image:
    return img.convert("RGB").resize(A4_LANDSCAPE_PX, Image.Resampling.LANCZOS)


def static_map_png(
    pins: list[dict[str, Any]],
    *,
    maps_key: str,
    with_markers: bool,
    size: str = STATIC_MAP_SIZE,
) -> bytes:
    ok = [p for p in pins if p.get("ok") and p.get("lat") is not None]
    if not ok:
        raise RuntimeError("no pins for static map")
    # 徒歩圏に寄せた余白（遠すぎる1点が全体を引き伸ばさないよう pad は控えめ）
    lats = [p["lat"] for p in ok]
    lngs = [p["lng"] for p in ok]
    pad = 0.0015
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


def render_c0_pair(
    pins_for_map: list[dict[str, Any]], *, maps_key: str
) -> tuple[Image.Image, Image.Image, Image.Image]:
    """Returns (clean_a4, c0_a4, c0_with_pins_a4)."""
    clean_bytes = static_map_png(pins_for_map, maps_key=maps_key, with_markers=False)
    clean_img = upscale_to_a4(Image.open(io.BytesIO(clean_bytes)).convert("RGB"))
    c0 = tone_wash(clean_img)
    c0_pins = recompose(c0, pins_for_map)
    return clean_img, c0, c0_pins


def research_policy() -> dict[str, Any]:
    return {
        "walk_prefer_min": WALK_PREFER_MIN,
        "walk_soft_max_min": WALK_SOFT_MAX_MIN,
        "walk_hard_max_min": WALK_HARD_MAX_MIN,
        "walk_m_per_min": WALK_M_PER_MIN,
        "output_size_px": list(A4_LANDSCAPE_PX),
        "output_note": "A4横 300dpi相当（297×210mm）",
        "distance_note": "徒歩分は直線距離÷80m/分の概算（要実測）",
    }


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
            "why": f.get("why") or "",
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

    resolved = annotate_distance(resolved, prop_lat=prop["lat"], prop_lng=prop["lng"])
    kept, walk_dropped = filter_by_walk_radius(resolved, max_keep=8)
    for d in walk_dropped:
        if d.get("drop_reason"):
            errors.append(f"{d.get('id') or '?'} {d['drop_reason']}: {d.get('name') or ''}")

    ok_count = sum(1 for r in kept if r["ok"])
    steps.append(
        {
            "id": "places",
            "ok": ok_count > 0,
            "detail": f"ok={ok_count}/{len(resolved)} kept={len(kept)} walk_drop={len(walk_dropped)}",
        }
    )
    if ok_count == 0:
        raise RuntimeError("施設の Places 確定が0件です（徒歩圏フィルタ後）")

    pins_for_map = [property_pin] + kept

    # 4) static clean (no markers) + C0（A4横）
    try:
        clean_img, c0, c0_pins = render_c0_pair(pins_for_map, maps_key=maps_key)
        steps.append({"id": "static", "ok": True, "detail": f"A4 {A4_LANDSCAPE_PX[0]}x{A4_LANDSCAPE_PX[1]}"})
        steps.append({"id": "c0", "ok": True, "detail": "beige wash ok"})
    except Exception as e:
        steps.append({"id": "static", "ok": False, "detail": str(e)})
        steps.append({"id": "c0", "ok": False, "detail": str(e)})
        raise

    research = {
        "policy": research_policy(),
        "wash": {
            "area_blurb": wash.get("area_blurb") or "",
            "access": wash.get("access") or [],
            "candidates": wash.get("candidates") or [],
        },
        "verify": {
            "area_blurb": verified.get("area_blurb") or "",
            "access": verified.get("access") or [],
            "facilities": verified.get("facilities") or [],
            "rejected": verified.get("rejected") or [],
        },
        "places_all": resolved,
        "walk_dropped": walk_dropped,
        "user_excluded": [],
    }

    result = {
        "job_id": job_id,
        "property_name": property_name,
        "address": address,
        "target": target,
        "area_blurb": verified.get("area_blurb") or wash.get("area_blurb") or "",
        "access": verified.get("access") or wash.get("access") or [],
        "facilities": kept,
        "property_pin": property_pin,
        "places_list_text": places_list_text(kept),
        "research": research,
        "images": {
            "c0_base_png_b64": png_b64(c0),
            "c0_with_pins_png_b64": png_b64(c0_pins),
            "width": A4_LANDSCAPE_PX[0],
            "height": A4_LANDSCAPE_PX[1],
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


def rebuild_from_exclusions(
    job_id: str, *, exclude_ids: list[str] | None = None
) -> dict[str, Any]:
    """ユーザー除外を反映して地図・C0を再生成（Geminiは再実行しない）."""
    maps_key = _env("GOOGLE_MAPS_API_KEY")
    if not maps_key:
        raise RuntimeError("GOOGLE_MAPS_API_KEY 未設定")
    job_dir = JOBS_DIR / job_id
    result_path = job_dir / "result.json"
    if not result_path.exists():
        raise RuntimeError("job が見つかりません")
    prev = json.loads(result_path.read_text(encoding="utf-8"))
    exclude = {str(x) for x in (exclude_ids or [])}
    property_pin = prev.get("property_pin")
    if not property_pin:
        raise RuntimeError("物件ピンがありません")

    # 直前の採用＋距離落ち＋ユーザー除外済みをプールから再構成
    research = prev.get("research") or {}
    pool = list(prev.get("facilities") or [])
    for d in research.get("walk_dropped") or []:
        if d.get("ok") and d.get("lat") is not None:
            pool.append(d)
    for d in research.get("user_excluded") or []:
        if d.get("ok") and d.get("lat") is not None:
            pool.append(d)

    # id 重複除去（先勝ち＝現採用優先）
    seen: set[str] = set()
    uniq: list[dict[str, Any]] = []
    for r in pool:
        rid = str(r.get("id") or "")
        key = rid or f"{r.get('name')}|{r.get('lat')}"
        if key in seen:
            continue
        seen.add(key)
        uniq.append(r)

    kept = [r for r in uniq if str(r.get("id") or "") not in exclude]
    user_excluded = [r for r in uniq if str(r.get("id") or "") in exclude]
    # 徒歩圏を再適用
    kept = annotate_distance(
        kept,
        prop_lat=float(property_pin["lat"]),
        prop_lng=float(property_pin["lng"]),
    )
    kept, walk_dropped = filter_by_walk_radius(kept, max_keep=8)
    if not any(r.get("ok") for r in kept):
        raise RuntimeError("除外後に掲載できる施設がありません")

    pins_for_map = [property_pin] + kept
    clean_img, c0, c0_pins = render_c0_pair(pins_for_map, maps_key=maps_key)

    research = dict(research)
    research["policy"] = research_policy()
    research["walk_dropped"] = walk_dropped
    research["user_excluded"] = user_excluded

    result = {
        **prev,
        "facilities": kept,
        "places_list_text": places_list_text(kept),
        "research": research,
        "images": {
            "c0_base_png_b64": png_b64(c0),
            "c0_with_pins_png_b64": png_b64(c0_pins),
            "width": A4_LANDSCAPE_PX[0],
            "height": A4_LANDSCAPE_PX[1],
        },
        "c1": {"status": "idle", "png_b64": None, "message": ""},
        "steps": (prev.get("steps") or [])
        + [{"id": "rebuild", "ok": True, "detail": f"exclude={len(exclude)} kept={len(kept)}"}],
    }

    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "result.json").write_text(
        json.dumps({k: v for k, v in result.items() if k != "images"}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    c0.save(job_dir / "c0_base.png")
    c0_pins.save(job_dir / "c0_with_pins.png")
    clean_img.save(job_dir / "clean_base.png")
    meta = {
        "property_name": prev.get("property_name") or "",
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
