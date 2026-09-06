#!/usr/bin/env python3
"""周辺マップ作成職人（S10）連携 — 地図素材＆Canva組立シート自動生成 CLI.

Grok Bot「周辺マップ作成職人」が出力した情報、または物件名・住所を渡すだけで、
A4横クリーン地図、ピン位置合わせ用ガイド地図、およびCanva組立シートを一括生成する。

使い方:
  # 1. 完全自動生成（Places APIで施設を自動選定＋地図生成）
  python scripts/jarvis_shuhen_map_gen.py --property "Grandole志賀本通Ⅰ" --address "愛知県名古屋市北区長田町4丁目69番地5"

  # 2. 施設名を指定して生成（Grok Botが厳選した8施設を反映）
  python scripts/jarvis_shuhen_map_gen.py --property "Grandole志賀本通Ⅰ" --address "愛知県名古屋市北区長田町4丁目69番地5" \\
    --facilities "志賀本通駅,尼ケ坂駅,ナフコトミダ杉栄店,ドラッグスギヤマ杉栄店,つばめパン＆Milk 尼ケ坂本店,Cafe de Lyon Palette,つけそば 神宮寺,コノズコーヒー 志賀本通駅前店"

  # 3. YAML/JSON ファイルから生成（Grok Botのカードをそのまま渡す）
  python scripts/jarvis_shuhen_map_gen.py --card card.yaml
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

# 環境変数読み込み（.env.jarvis_private）
env_path = ROOT / ".env.jarvis_private"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

import shuhen_auto_pipeline as sap

ONEDRIVE_BASE = Path(
    "/Users/matsunomasaharu2/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部"
    "/C1_cursor/1c_神・大家さん倶楽部_AI推進/AI×周辺MAP/生成マップ"
)


def _safe_name(name: str) -> str:
    return re.sub(r'[\\/*?:"<>| \t]', "_", name).strip("_")


def build_canva_markdown(
    property_name: str,
    address: str,
    target: str,
    property_pin: dict[str, Any],
    facilities: list[dict[str, Any]],
    job_id: str,
) -> str:
    today = datetime.date.today().strftime("%Y-%m-%d")

    # Access 候補
    access_rows = []
    pin_rows = []
    for i, f in enumerate(facilities, 1):
        name = f.get("name") or f.get("resolvedName") or "施設"
        walk = f.get("walk_min_approx")
        if walk is not None:
            # 端数切り上げ整数分（80m=1分不動産公取規約）
            import math
            walk_int = math.ceil(walk)
            walk_str = f"約{walk_int}分"
        else:
            walk_str = "徒歩圏内"
        cat = f.get("category") or "生活"
        blurb = f.get("blurb") or f.get("why") or f"{name}まで徒歩すぐ。毎日の生活に便利です。"
        
        access_rows.append(f"| {i} | {name} | {walk_str} | {cat} |")
        pin_rows.append(f"| {i} | {name} | {walk_str} | {cat} | {blurb} |")

    access_table = "\n".join(access_rows)
    pin_table = "\n".join(pin_rows)

    return f"""# Canva組立シート — {property_name} 周辺MAP

- 作成日: {today}
- 対象物件: {property_name}
- 住所: {address}
- 想定ターゲット: {target or "単身〜実需（スマート通勤・生活利便重視）"}
- ジョブID: `{job_id}`

---

## 1. タイトル ＆ エリア一言（Canva貼付用）

**タイトル**: {property_name} 周辺MAP  
**エリア一言**: 主要駅・生活インフラが徒歩圏内に充実した生活至便な立地。平日はスマート通勤、休日は街の散策を楽しめる環境です。

---

## 2. Access一覧（左欄掲載用）

| # | 施設・駅名 | 徒歩目安 | 分類 |
|---|---|---|---|
{access_table}

---

## 3. 地図ピン ＆ 吹き出しコメント（地図上配置用・最大8件）

| # | 施設名 | 徒歩 | 分類 | 吹き出し文言（誇大表現なし・30文字前後） |
|---|---|---|---|---|
{pin_table}

---

## 4. 人物コメント（いらすとや風・1〜2点）

- **人物A（平日・通勤・買い物）**: 「仕事帰りにスーパーに寄れて、毎日のお買い物もラクラクです♪」
- **人物B（休日・カフェ・散策）**: 「お休みの日は近所をお散歩したり、お気に入りのカフェで過ごしています！」

---

## 5. Canva作成クイックガイド（5分〜10分で仕上げ）

1. **Canva（無料版OK）** で「A4横」（幅 297mm × 高さ 210mm）を新規作成。
2. 同フォルダの **`01_クリーン地図_A4横.png`** をアップロードし、紙面いっぱいに配置して「ロック」。
3. 同フォルダの **`02_ピン位置合わせ用ガイド_A4横.png`** を同じ位置・サイズで重ね、**透明度40%** に設定。
4. ガイドに見えるピンの真上に、Canvaの「素材」からロケーションピンを配置（自宅位置は赤い家アイコン）。
5. 各ピンの横に白地のピル型ラベルで店名を配置。
6. 上記「3. 吹き出しコメント」をコピペして小さな吹き出し（薄クリーム色）を配置。
7. ピンの配置が終わったら、ガイド地図（`02`）を削除。
8. 左側に「Access一覧」、上部に「エリア一言」、余白に「人物イラスト」を置いてPDF出力！
"""


def generate_map(
    property_name: str,
    address: str,
    target: str = "",
    custom_facilities: list[str] | None = None,
    custom_blurbs: list[str] | None = None,
    out_dir: Path | None = None,
) -> dict[str, Any]:
    maps_key = sap._env("GOOGLE_MAPS_API_KEY")
    if not maps_key:
        raise RuntimeError("GOOGLE_MAPS_API_KEY が設定されていません。")

    print(f"# 開始: {property_name} ({address})")

    # 物件ジオコード
    prop_geo = sap.geocode(address, maps_key=maps_key)
    if not prop_geo:
        raise RuntimeError(f"住所のジオコードに失敗しました: {address}")

    prop_pin = {
        "id": "property",
        "name": property_name,
        "category": "自宅",
        "lat": prop_geo["lat"],
        "lng": prop_geo["lng"],
        "ok": True,
        "isProperty": True,
    }

    facilities = []
    job_id = "job_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    if custom_facilities:
        print(f"# 指定された施設 {len(custom_facilities)} 件をジオコード中...")
        for i, fname in enumerate(custom_facilities, 1):
            fname = fname.strip()
            if not fname:
                continue
            found = sap.find_place(
                fname,
                lat=prop_pin["lat"],
                lng=prop_pin["lng"],
                maps_key=maps_key,
            )
            if not found.get("ok"):
                print(f"  - ⚠️ 見つかりませんでした: {fname}")
                continue
            dist_m = sap.haversine_m(
                prop_pin["lat"], prop_pin["lng"],
                found["lat"], found["lng"]
            )
            walk_min = sap.walk_min_from_m(dist_m)
            blurb_text = (
                custom_blurbs[i - 1]
                if custom_blurbs and i - 1 < len(custom_blurbs) and custom_blurbs[i - 1].strip()
                else f"徒歩約{round(walk_min, 1)}分。毎日の生活に便利なスポットです。"
            )
            facilities.append({
                "id": str(i),
                "query": fname,
                "name": fname,
                "category": "周辺施設",
                "lat": found["lat"],
                "lng": found["lng"],
                "ok": True,
                "isProperty": False,
                "resolvedName": found.get("name") or fname,
                "formatted": found.get("formatted") or "",
                "distance_m": round(dist_m),
                "walk_min_approx": walk_min,
                "blurb": blurb_text,
            })
    else:
        print("# 施設自動選定パイプライン（Gemini + Places）を実行中...")
        res = sap.run_pipeline(property_name=property_name, address=address, target=target)
        job_id = res["job_id"]
        prop_pin = res["property_pin"]
        facilities = res["facilities"]

    # 地図画像ペアのレンダリング
    print("# A4横クリーン地図 ＆ ピン位置合わせ用ガイド地図をレンダリング中...")
    pins_for_map = [prop_pin] + facilities
    clean_img, c0_base, c0_with_pins = sap.render_c0_pair(pins_for_map, maps_key=maps_key)

    # 出力先決定
    date_str = datetime.date.today().strftime("%Y%m%d")
    folder_name = f"{_safe_name(property_name)}_{date_str}"
    target_dir = out_dir or (ONEDRIVE_BASE / folder_name)
    target_dir.mkdir(parents=True, exist_ok=True)

    # 保存
    clean_map_path = target_dir / "01_クリーン地図_A4横.png"
    pins_map_path = target_dir / "02_ピン位置合わせ用ガイド_A4横.png"
    assembly_sheet_path = target_dir / "03_Canva組立シート.md"
    result_json_path = target_dir / "result.json"

    c0_base.save(clean_map_path)
    c0_with_pins.save(pins_map_path)

    md_content = build_canva_markdown(
        property_name=property_name,
        address=address,
        target=target,
        property_pin=prop_pin,
        facilities=facilities,
        job_id=job_id,
    )
    assembly_sheet_path.write_text(md_content, encoding="utf-8")

    meta = {
        "job_id": job_id,
        "property_name": property_name,
        "address": address,
        "target": target,
        "property_pin": prop_pin,
        "facilities": facilities,
        "files": {
            "clean_map": str(clean_map_path),
            "pins_guide_map": str(pins_map_path),
            "canva_sheet": str(assembly_sheet_path),
        },
    }
    result_json_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n✅ 周辺MAP素材の生成が完了しました！")
    print(f"出力先: {target_dir}")
    print(f"  - 01_クリーン地図: {clean_map_path.name}")
    print(f"  - 02_ガイド地図: {pins_map_path.name}")
    print(f"  - 03_Canva組立シート: {assembly_sheet_path.name}")

    return meta


def main() -> int:
    parser = argparse.ArgumentParser(description="周辺マップ作成職人（S10）連携 地図素材生成 CLI")
    parser.add_argument("--property", help="物件名（例: Grandole志賀本通Ⅰ）")
    parser.add_argument("--address", help="物件住所")
    parser.add_argument("--target", default="", help="想定ターゲット（任意）")
    parser.add_argument("--facilities", default="", help="カンマ区切りの施設名リスト（任意）")
    parser.add_argument("--blurbs", default="", help="パイプ区切りの吹き出し文言リスト（任意）")
    parser.add_argument("--card", default="", help="Grok Botが出力したYAML/JSONカードファイル（任意）")
    parser.add_argument("--out", default="", help="出力ディレクトリ（任意）")

    args = parser.parse_args()

    prop = args.property
    addr = args.address
    target = args.target
    fac_list = None
    blurb_list = None

    if args.blurbs:
        blurb_list = [x.strip() for x in args.blurbs.split("|") if x.strip()]

    if args.card:
        card_p = Path(args.card)
        if card_p.exists():
            text = card_p.read_text(encoding="utf-8")
            # 簡易パース
            m_p = re.search(r'property_name[:：]\s*["\']?([^"\']+)["\']?', text)
            m_a = re.search(r'address[:：]\s*["\']?([^"\']+)["\']?', text)
            if m_p:
                prop = m_p.group(1).strip()
            if m_a:
                addr = m_a.group(1).strip()
            names = re.findall(r'-\s*name[:：]\s*["\']?([^"\']+)["\']?', text)
            if names:
                fac_list = names

    if args.facilities:
        fac_list = [x.strip() for x in args.facilities.split(",") if x.strip()]

    if not prop or not addr:
        print("エラー: --property と --address は必須です。（または --card を指定）", file=sys.stderr)
        return 1

    out_p = Path(args.out) if args.out else None
    generate_map(
        property_name=prop,
        address=addr,
        target=target,
        custom_facilities=fac_list,
        custom_blurbs=blurb_list,
        out_dir=out_p,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
