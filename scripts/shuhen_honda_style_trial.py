#!/usr/bin/env python3
"""本多さん型（DX互助会 2026-10-18）周辺MAP 試走。

Phase A: 確定済み施設表を埋めた状態から開始（空欄のまま本番に入らない）
Phase B: Geocode / Places / Static Map → HTML 組版 →（任意）PDF
Phase C: 見た目だけ触る前提（このスクリプトは B まで。描写は後段）

秘密は環境変数のみ。キーを print しない。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/shuhen_honda_style_trial.py
  ~/selenium_env/venv/bin/python scripts/shuhen_honda_style_trial.py --pdf
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT_DEFAULT = (
    ROOT
    / "215_kamiooya/C1_cursor/1c_神・大家さん倶楽部_AI推進/AI×周辺MAP/試走出力"
    / "honda_style_20261019_Grandole"
)

# 06_Canva組立シート（サキ向け）の確定分。Phase A 済みデータとして使う。
PROPERTY = {
    "name": "Grandole志賀本通",
    "address": "愛知県名古屋市北区長田町4丁目69番地5",
    "area_line": (
        "名城線と瀬戸線に挟まれた生活至便な立地。"
        "平日は栄へスマート通勤、休日はSAKUMACHI商店街でカフェ巡りを楽しめる街です。"
    ),
    "persona_note": "サキ向け（紙面には出さない）",
}

# 紙面用徒歩分は 06 確定値。座標は Places で取る。
FACILITIES: list[dict[str, Any]] = [
    {
        "n": 1,
        "name": "地下鉄名城線 志賀本通駅",
        "query": "志賀本通駅",
        "category": "駅",
        "walk_min_print": 7,
        "bubble": "栄まで地下鉄で直通。通勤に使いやすい駅です",
    },
    {
        "n": 2,
        "name": "名鉄瀬戸線 尼ケ坂駅／SAKUMACHI",
        "query": "尼ケ坂駅",
        "category": "駅・商店街",
        "walk_min_print": 8,
        "bubble": "高架下におしゃれな店が並ぶ休日の散策スポットです",
    },
    {
        "n": 3,
        "name": "ナフコトミダ杉栄店",
        "query": "ナフコトミダ杉栄店",
        "category": "スーパー",
        "walk_min_print": 3,
        "bubble": "徒歩3分で大抵の買い物が済みます",
    },
    {
        "n": 4,
        "name": "ドラッグスギヤマ杉栄店",
        "query": "ドラッグスギヤマ杉栄店",
        "category": "薬局",
        "walk_min_print": 3,
        "bubble": "日用品やコスメがすぐ揃います",
    },
    {
        "n": 5,
        "name": "つばめパン＆Milk 尼ケ坂本店",
        "query": "つばめパン＆Milk 尼ケ坂本店",
        "category": "飲食",
        "walk_min_print": 8,
        "bubble": "ふわもち食パンのモーニングが人気です",
    },
    {
        "n": 6,
        "name": "Cafe de Lyon Palette",
        "query": "Cafe de Lyon Palette 尼ケ坂",
        "category": "飲食",
        "walk_min_print": 8,
        "bubble": "旬のフルーツを使ったパフェが楽しめます",
    },
    {
        "n": 7,
        "name": "つけそば 神宮寺",
        "query": "つけそば神宮寺 北区",
        "category": "飲食",
        "walk_min_print": 9,
        "bubble": "仕事帰りに寄れる、評判のつけそば店です",
    },
    {
        "n": 8,
        "name": "コノズコーヒー 志賀本通駅前",
        "query": "コノズコーヒー 志賀本通",
        "category": "飲食",
        "walk_min_print": 9,
        "bubble": "駅前でモーニングやランチが取れます",
    },
]

ACCESS = [
    ("地下鉄名城線「志賀本通駅」", "約7分"),
    ("名鉄瀬戸線「尼ケ坂駅」", "約8分"),
    ("ナフコトミダ杉栄店（生鮮スーパー）", "約3分"),
    ("ドラッグスギヤマ杉栄店", "約3分"),
    ("名古屋市北区役所", "約18分"),
    ("ゲオ辻本通店", "約14分"),
]


def _maps_key() -> str:
    key = (os.environ.get("GOOGLE_MAPS_API_KEY") or "").strip()
    if not key:
        raise SystemExit("GOOGLE_MAPS_API_KEY が未設定です（.env.jarvis_private）")
    return key


def http_get_json(url: str) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": "ShuhenHondaTrial/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def http_get_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "ShuhenHondaTrial/1.0"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read()


def geocode(address: str, *, key: str) -> dict[str, Any]:
    q = urllib.parse.urlencode(
        {"address": address, "language": "ja", "region": "jp", "key": key}
    )
    data = http_get_json(f"https://maps.googleapis.com/maps/api/geocode/json?{q}")
    results = data.get("results") or []
    if not results:
        raise SystemExit(f"geocode失敗: {address} status={data.get('status')}")
    loc = results[0]["geometry"]["location"]
    return {"lat": loc["lat"], "lng": loc["lng"], "formatted": results[0].get("formatted_address")}


def find_place(query: str, *, lat: float, lng: float, key: str) -> dict[str, Any]:
    q = urllib.parse.urlencode(
        {
            "input": query,
            "inputtype": "textquery",
            "fields": "name,geometry,formatted_address,place_id",
            "locationbias": f"point:{lat},{lng}",
            "language": "ja",
            "key": key,
        }
    )
    data = http_get_json(
        f"https://maps.googleapis.com/maps/api/place/findplacefromtext/json?{q}"
    )
    cands = data.get("candidates") or []
    if not cands:
        return {"ok": False, "status": data.get("status") or "ZERO", "query": query}
    c = cands[0]
    loc = c["geometry"]["location"]
    return {
        "ok": True,
        "name": c.get("name") or query,
        "lat": loc["lat"],
        "lng": loc["lng"],
        "formatted": c.get("formatted_address") or "",
        "place_id": c.get("place_id") or "",
        "query": query,
    }


def fetch_static_map(
    *,
    prop_lat: float,
    prop_lng: float,
    pins: list[dict[str, Any]],
    key: str,
    out_png: Path,
) -> None:
    # クリーン寄りのスタイル（ラベル過多を抑える）
    styles = [
        "feature:poi|visibility:off",
        "feature:poi.business|visibility:off",
        "feature:administrative|element:labels|visibility:off",
        "feature:road|element:labels|visibility:off",
        "feature:transit|element:labels|visibility:off",
    ]
    markers = [f"color:0x0f766e|label:H|{prop_lat},{prop_lng}"]
    for p in pins:
        if not p.get("ok"):
            continue
        label = str(p["n"]) if p["n"] <= 9 else "•"
        markers.append(f"color:0xbe185d|label:{label}|{p['lat']},{p['lng']}")
    params: list[tuple[str, str]] = [
        ("size", "640x640"),
        ("scale", "2"),
        ("maptype", "roadmap"),
        ("language", "ja"),
        ("region", "jp"),
        ("center", f"{prop_lat},{prop_lng}"),
        ("zoom", "15"),
        ("key", key),
    ]
    for s in styles:
        params.append(("style", s))
    for m in markers:
        params.append(("markers", m))
    url = "https://maps.googleapis.com/maps/api/staticmap?" + urllib.parse.urlencode(params)
    out_png.write_bytes(http_get_bytes(url))


def phase_a_table(pins: list[dict[str, Any]]) -> str:
    lines = [
        "| # | 施設 | カテゴリ | 紙面徒歩 | Places | 座標 |",
        "|---|---|---|---|---|---|",
    ]
    for p in pins:
        coord = f"{p['lat']:.5f},{p['lng']:.5f}" if p.get("ok") else "—"
        hit = "OK" if p.get("ok") else f"NG({p.get('status')})"
        lines.append(
            f"| {p['n']} | {p['name']} | {p['category']} | 約{p['walk_min_print']}分 "
            f"| {hit} | {coord} |"
        )
    return "\n".join(lines)


def build_html(*, pins: list[dict[str, Any]], map_rel: str, note: str) -> str:
    access_rows = "".join(
        f"<tr><td>{i}</td><td>{name}</td><td>{walk}</td></tr>"
        for i, (name, walk) in enumerate(ACCESS, 1)
    )
    pin_rows = "".join(
        f"<tr><td>{p['n']}</td><td>{p['name']}</td>"
        f"<td>約{p['walk_min_print']}分</td><td>{p.get('bubble') or ''}</td></tr>"
        for p in pins
        if p.get("ok")
    )
    bubbles = "".join(
        f'<div class="bubble"><b>{p["n"]}. {p["name"]}</b><span>{p["bubble"]}</span></div>'
        for p in pins[:4]
        if p.get("ok") and p.get("bubble")
    )
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8" />
<title>{PROPERTY['name']} 周辺MAP（本多さん型試走）</title>
<style>
  @page {{ size: A4 portrait; margin: 12mm; }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; font-family: "Hiragino Sans", "Yu Gothic", sans-serif;
    color: #1e293b; background: #f8fafc;
  }}
  .sheet {{
    max-width: 210mm; margin: 0 auto; background: #fff;
    padding: 16px 18px 20px; border: 1px solid #e2e8f0;
  }}
  header {{
    border-bottom: 3px solid #0f766e; padding-bottom: 10px; margin-bottom: 12px;
  }}
  h1 {{ margin: 0 0 6px; font-size: 22px; font-weight: 900; color: #0f766e; }}
  .area {{ margin: 0; font-size: 13px; font-weight: 700; color: #475569; line-height: 1.45; }}
  .grid {{ display: grid; grid-template-columns: 1fr 1.15fr; gap: 12px; }}
  h2 {{ margin: 0 0 6px; font-size: 13px; font-weight: 900; color: #0f766e; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 11.5px; }}
  th, td {{ border: 1px solid #e2e8f0; padding: 4px 6px; text-align: left; vertical-align: top; }}
  th {{ background: #ecfdf5; font-weight: 900; }}
  .map-wrap {{
    border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden; background: #f1f5f9;
  }}
  .map-wrap img {{ display: block; width: 100%; height: auto; }}
  .here {{
    font-size: 11px; font-weight: 800; color: #0f766e; margin: 4px 0 0;
  }}
  .bubbles {{ display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-top: 10px; }}
  .bubble {{
    background: #f0fdfa; border: 1px solid #99f6e4; border-radius: 8px;
    padding: 6px 8px; font-size: 11px; line-height: 1.35;
  }}
  .bubble b {{ display: block; color: #115e59; margin-bottom: 2px; }}
  .note {{
    margin-top: 10px; font-size: 10.5px; color: #64748b; font-weight: 700;
  }}
  .pin-table {{ margin-top: 10px; }}
  @media print {{
    body {{ background: #fff; }}
    .sheet {{ border: none; max-width: none; }}
  }}
</style>
</head>
<body>
  <div class="sheet">
    <header>
      <h1>{PROPERTY['name']} 周辺MAP</h1>
      <p class="area">{PROPERTY['area_line']}</p>
    </header>
    <div class="grid">
      <section>
        <h2>Access（徒歩目安）</h2>
        <table>
          <tr><th>#</th><th>施設</th><th>徒歩</th></tr>
          {access_rows}
        </table>
        <p class="here">HERE = 物件位置（地図上の緑 H）</p>
      </section>
      <section>
        <h2>地図（実地図・番号ピン）</h2>
        <div class="map-wrap"><img src="{map_rel}" alt="周辺地図" /></div>
      </section>
    </div>
    <div class="bubbles">{bubbles}</div>
    <section class="pin-table">
      <h2>地図の番号（徒歩ピン）</h2>
      <table>
        <tr><th>#</th><th>施設</th><th>徒歩</th><th>ひとこと</th></tr>
        {pin_rows}
      </table>
    </section>
    <p class="note">{note}</p>
  </div>
</body>
</html>
"""


def try_pdf(html_path: Path, pdf_path: Path) -> bool:
    chrome = (
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        if Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome").exists()
        else shutil.which("google-chrome")
        or shutil.which("chromium")
    )
    if not chrome:
        return False
    cmd = [
        chrome,
        "--headless=new",
        "--disable-gpu",
        f"--print-to-pdf={pdf_path}",
        "--no-pdf-header-footer",
        html_path.resolve().as_uri(),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=60)
        return pdf_path.is_file()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description="本多さん型 周辺MAP 試走（Grandole）")
    ap.add_argument("--out", type=Path, default=OUT_DEFAULT)
    ap.add_argument("--pdf", action="store_true", help="Chrome headless で PDF も出す")
    ap.add_argument(
        "--oral",
        default="",
        help="口頭指示の模擬（例: 吹き出しをもっと短く）",
    )
    args = ap.parse_args()
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)

    key = _maps_key()
    print("Phase A: 確定表（06シート）を使用 — 空欄なしで本番へ")
    prop = geocode(PROPERTY["address"], key=key)
    print(f"  物件 geocode OK ({prop['formatted']})")

    pins: list[dict[str, Any]] = []
    for f in FACILITIES:
        hit = find_place(f["query"], lat=prop["lat"], lng=prop["lng"], key=key)
        row = {**f, **hit}
        pins.append(row)
        mark = "OK" if row.get("ok") else "NG"
        print(f"  Places {mark}: #{f['n']} {f['name']}")

    # 口頭指示の模擬（Phase C 手前の軽い修正）
    oral = (args.oral or "").strip()
    if "短く" in oral or "短文" in oral:
        for p in pins:
            if p.get("bubble") and len(p["bubble"]) > 18:
                p["bubble"] = p["bubble"][:18].rstrip("。") + "…"
        print(f"Oral apply: 吹き出し短縮 ({oral})")

    map_png = out / "map_static.png"
    fetch_static_map(
        prop_lat=prop["lat"],
        prop_lng=prop["lng"],
        pins=pins,
        key=key,
        out_png=map_png,
    )
    print(f"Phase B: Static Map → {map_png.name}")

    table_md = phase_a_table(pins)
    (out / "phase_a_table.md").write_text(
        f"# Phase A 表（Grandole・本多さん型試走）\n\n{table_md}\n",
        encoding="utf-8",
    )

    note = (
        f"試走 {datetime.now().strftime('%Y-%m-%d %H:%M')}｜"
        "本多さん型 Phase A/B（Cursor作業机）｜"
        "地図=Google Static／施設=Places｜紙面徒歩分は06確定値｜"
        "描写の作り込み（Phase C / Opus）は未実施"
    )
    if oral:
        note += f"｜口頭指示: {oral}"

    html = build_html(pins=pins, map_rel=map_png.name, note=note)
    html_path = out / "周辺MAP_本多さん型試走.html"
    html_path.write_text(html, encoding="utf-8")
    print(f"Phase B: HTML → {html_path}")

    meta = {
        "property": PROPERTY,
        "prop_geocode": prop,
        "pins": [
            {
                "n": p["n"],
                "name": p["name"],
                "ok": p.get("ok"),
                "lat": p.get("lat"),
                "lng": p.get("lng"),
                "walk_min_print": p.get("walk_min_print"),
                "places_name": p.get("name") if p.get("ok") else None,
            }
            for p in pins
        ],
        "oral": oral,
        "out": str(out),
    }
    (out / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    pdf_ok = False
    if args.pdf:
        pdf_path = out / "周辺MAP_本多さん型試走.pdf"
        pdf_ok = try_pdf(html_path, pdf_path)
        print(f"PDF: {'OK ' + pdf_path.name if pdf_ok else 'スキップ（Chrome未使用/失敗）'}")

    print("---")
    print(f"出力先: {out}")
    print("次: HTMLを開いて口頭指示→再実行（--oral '吹き出しをもっと短く' 等）")
    return 0 if all(p.get("ok") for p in pins) else 2


if __name__ == "__main__":
    sys.exit(main())
