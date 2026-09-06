#!/usr/bin/env python3
"""神大家AI不動産 スプレッドシート・アダプター (dx_spreadsheet_adapter.py)

【目的】
KURASHIFT（独自Webアプリ）を持たない一般のDX互助会メンバー向けに、
GoogleスプレッドシートやExcel/CSVを正本として、AI社員（Grok Bot/Cursor）
と以下の3大業務データを双方向連携するための軽量アダプター。

1. 物件案件一覧 (Deals)       : 物件名、住所、価格、利回り、ステータス、担当Bot、次のアクション
2. 業者開拓一覧 (Vendors)     : 会社名、地域、フォームURL、送信フェーズ、返信メモ、担当Bot
3. 募集クリエイティブ (Creative): 物件名、周辺MAP作成状況、マイソク、POP設置メモ、担当Bot

【使い方】
# 1. 全テンプレートの初期化（Deals, Vendors, Creative）
python scripts/dx_spreadsheet_adapter.py --init-all

# 2. 一覧表示
python scripts/dx_spreadsheet_adapter.py --sheet deals --list
python scripts/dx_spreadsheet_adapter.py --sheet vendors --list
python scripts/dx_spreadsheet_adapter.py --sheet creative --list

# 3. 案件・業者の追加
python scripts/dx_spreadsheet_adapter.py --sheet deals --add \
  --name "岡崎市戸建" --address "愛知県岡崎市..." --price 350 --yield-rate 16.0

python scripts/dx_spreadsheet_adapter.py --sheet vendors --add \
  --company "ニッショー一宮店" --area "愛知県一宮市" --url "https://example.com/form"

# 4. ステータス・担当Botの更新
python scripts/dx_spreadsheet_adapter.py --sheet deals --update \
  --id P002 --status "買付交渉中" --bot "S6買付・価格交渉" --action "指値250万打診"
"""

import sys
import os
import csv
import argparse
import json
from datetime import datetime
from pathlib import Path

DATA_DIR = Path.cwd() / "data"

SHEET_CONFIGS = {
    "deals": {
        "file": DATA_DIR / "神大家AI不動産_案件管理.csv",
        "template": DATA_DIR / "dx_kamiooya_property_sheet_template.csv",
        "title": "物件案件一覧 (Deals)",
        "id_prefix": "P",
        "fieldnames": [
            "案件ID", "物件名", "所在地", "価格(万円)", "想定利回り(%)",
            "構造", "築年", "ステータス", "担当Bot", "次のアクション", "神大家メモ", "最終更新日時"
        ]
    },
    "vendors": {
        "file": DATA_DIR / "神大家AI不動産_業者開拓.csv",
        "template": DATA_DIR / "dx_kamiooya_vendor_sheet_template.csv",
        "title": "業者開拓一覧 (Vendors)",
        "id_prefix": "V",
        "fieldnames": [
            "業者ID", "会社名", "地域", "WebフォームURL", "送信フェーズ", "返信メモ", "担当Bot", "最終更新日時"
        ]
    },
    "creative": {
        "file": DATA_DIR / "神大家AI不動産_募集クリエイティブ.csv",
        "template": DATA_DIR / "dx_kamiooya_creative_sheet_template.csv",
        "title": "募集クリエイティブ一覧 (Creative)",
        "id_prefix": "C",
        "fieldnames": [
            "クリエイティブID", "物件名", "周辺MAP作成状況", "マイソク作成状況", "POP設置メモ", "担当Bot", "最終更新日時"
        ]
    }
}

def ensure_data_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

def init_sheet(sheet_key: str):
    ensure_data_dir()
    cfg = SHEET_CONFIGS[sheet_key]
    target_path = cfg["file"]
    tpl_path = cfg["template"]

    if target_path.exists():
        print(f"⚠️ 既にファイルが存在します: {target_path.name}")
        return

    if tpl_path.exists():
        with open(tpl_path, "r", encoding="utf-8") as f_src:
            content = f_src.read()
    else:
        content = ",".join(cfg["fieldnames"]) + "\n"

    with open(target_path, "w", encoding="utf-8") as f_dst:
        f_dst.write(content)
    print(f"✅ 【{cfg['title']}】CSVを初期化しました: {target_path.name}")

def init_all():
    ensure_data_dir()
    for k in SHEET_CONFIGS:
        init_sheet(k)
    print("👉 これらのCSVをGoogleドライブに保存して「Googleスプレッドシートとして開く」ことで、共同編集可能です。")

def load_rows(sheet_key: str) -> list:
    cfg = SHEET_CONFIGS[sheet_key]
    path = cfg["file"]
    if not path.exists():
        if cfg["template"].exists():
            path = cfg["template"]
        else:
            return []
    rows = []
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)
    return rows

def save_rows(sheet_key: str, rows: list):
    ensure_data_dir()
    cfg = SHEET_CONFIGS[sheet_key]
    path = cfg["file"]
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=cfg["fieldnames"])
        writer.writeheader()
        for r in rows:
            row = {k: r.get(k, "") for k in cfg["fieldnames"]}
            writer.writerow(row)

def list_sheet(sheet_key: str):
    cfg = SHEET_CONFIGS[sheet_key]
    rows = load_rows(sheet_key)
    print(f"\n【神大家AI不動産：{cfg['title']}】 (全{len(rows)}件) - {cfg['file'].name}")
    print("=" * 105)

    if sheet_key == "deals":
        print(f"{'ID':<6} | {'ステータス':<10} | {'物件名':<22} | {'利回り':<7} | {'担当Bot':<14} | {'次のアクション'}")
        print("-" * 105)
        for d in rows:
            y_val = d.get('想定利回り(%)', d.get('想定利回り', ''))
            y_str = f"{y_val}%" if y_val else "-"
            print(f"{d.get('案件ID',''):<6} | {d.get('ステータス',''):<10} | {d.get('物件名','')[:20]:<22} | {y_str:<7} | {d.get('担当Bot',''):<14} | {d.get('次のアクション','')}")

    elif sheet_key == "vendors":
        print(f"{'ID':<6} | {'送信フェーズ':<14} | {'会社名':<24} | {'地域':<14} | {'担当Bot':<12} | {'返信メモ'}")
        print("-" * 105)
        for v in rows:
            print(f"{v.get('業者ID',''):<6} | {v.get('送信フェーズ',''):<14} | {v.get('会社名','')[:22]:<24} | {v.get('地域',''):<14} | {v.get('担当Bot',''):<12} | {v.get('返信メモ','')}")

    elif sheet_key == "creative":
        print(f"{'ID':<6} | {'物件名':<24} | {'周辺MAP状況':<20} | {'マイソク状況':<16} | {'POP設置メモ'}")
        print("-" * 105)
        for c in rows:
            print(f"{c.get('クリエイティブID',''):<6} | {c.get('物件名','')[:22]:<24} | {c.get('周辺MAP作成状況',''):<20} | {c.get('マイソク作成状況',''):<16} | {c.get('POP設置メモ','')}")

    print("=" * 105 + "\n")

def add_entry(sheet_key: str, args):
    cfg = SHEET_CONFIGS[sheet_key]
    rows = load_rows(sheet_key)
    id_field = cfg["fieldnames"][0]
    pfx = cfg["id_prefix"]

    # 採番
    existing = [r.get(id_field, "") for r in rows if r.get(id_field, "").startswith(pfx)]
    nums = [int(i[1:]) for i in existing if i[1:].isdigit()]
    next_num = max(nums) + 1 if nums else 1
    new_id = f"{pfx}{next_num:03d}"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    new_row = {id_field: new_id, "最終更新日時": now_str}

    if sheet_key == "deals":
        new_row.update({
            "物件名": args.name or "",
            "所在地": args.address or "",
            "価格(万円)": str(args.price or ""),
            "想定利回り(%)": str(args.yield_rate or ""),
            "構造": args.structure or "",
            "築年": args.built_year or "",
            "ステータス": args.status or "新着",
            "担当Bot": args.bot or "S1物件調査",
            "次のアクション": args.action or "初動調査開始",
            "神大家メモ": args.memo or "",
        })
    elif sheet_key == "vendors":
        new_row.update({
            "会社名": args.company or args.name or "",
            "地域": args.area or args.address or "",
            "WebフォームURL": args.url or "",
            "送信フェーズ": args.phase or args.status or "送信準備中",
            "返信メモ": args.memo or "",
            "担当Bot": args.bot or "S2業者開拓",
        })
    elif sheet_key == "creative":
        new_row.update({
            "物件名": args.name or "",
            "周辺MAP作成状況": args.map_status or "未着手",
            "マイソク作成状況": args.maisoku_status or "未着手",
            "POP設置メモ": args.memo or "",
            "担当Bot": args.bot or "S10周辺マップ職人",
        })

    rows.append(new_row)
    save_rows(sheet_key, rows)
    print(f"✅ 【{cfg['title']}】に新規追加しました: [{new_id}] ({now_str})")

def update_entry(sheet_key: str, args):
    cfg = SHEET_CONFIGS[sheet_key]
    rows = load_rows(sheet_key)
    id_field = cfg["fieldnames"][0]

    target = None
    for r in rows:
        if r.get(id_field) == args.id:
            target = r
            break
    if not target:
        print(f"❌ ID '{args.id}' が【{cfg['title']}】に見つかりません。")
        return

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    target["最終更新日時"] = now_str

    if sheet_key == "deals":
        if args.status: target["ステータス"] = args.status
        if args.bot: target["担当Bot"] = args.bot
        if args.action: target["次のアクション"] = args.action
        if args.memo: target["神大家メモ"] = args.memo
    elif sheet_key == "vendors":
        if args.phase or args.status: target["送信フェーズ"] = args.phase or args.status
        if args.memo: target["返信メモ"] = args.memo
        if args.bot: target["担当Bot"] = args.bot
    elif sheet_key == "creative":
        if args.map_status: target["周辺MAP作成状況"] = args.map_status
        if args.maisoku_status: target["マイソク作成状況"] = args.maisoku_status
        if args.memo: target["POP設置メモ"] = args.memo
        if args.bot: target["担当Bot"] = args.bot

    save_rows(sheet_key, rows)
    print(f"✅ 【{cfg['title']}】 [{args.id}] を更新しました ({now_str})")

def main():
    parser = argparse.ArgumentParser(description="神大家AI不動産 スプレッドシート・アダプター")
    parser.add_argument("--sheet", choices=["deals", "vendors", "creative"], default="deals", help="対象シート種別 (既定: deals)")
    parser.add_argument("--init", action="store_true", help="指定シートのCSVを初期配置")
    parser.add_argument("--init-all", action="store_true", help="全3シートのCSVを初期配置")
    parser.add_argument("--list", action="store_true", help="指定シートの一覧を表示")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")

    # 追加用
    parser.add_argument("--add", action="store_true", help="データを追加")
    parser.add_argument("--name", type=str, help="物件名 (deals/creative)")
    parser.add_argument("--address", type=str, help="所在地 (deals)")
    parser.add_argument("--price", type=float, help="価格(万円) (deals)")
    parser.add_argument("--yield-rate", type=float, help="想定利回り(%) (deals)")
    parser.add_argument("--structure", type=str, help="構造 (deals)")
    parser.add_argument("--built-year", type=str, help="築年 (deals)")
    parser.add_argument("--company", type=str, help="会社名 (vendors)")
    parser.add_argument("--area", type=str, help="地域 (vendors)")
    parser.add_argument("--url", type=str, help="WebフォームURL (vendors)")
    parser.add_argument("--phase", type=str, help="送信フェーズ (vendors)")
    parser.add_argument("--map-status", type=str, help="周辺MAP状況 (creative)")
    parser.add_argument("--maisoku-status", type=str, help="マイソク状況 (creative)")

    # 共通更新・追加項目
    parser.add_argument("--status", type=str, help="ステータス")
    parser.add_argument("--bot", type=str, help="担当Bot")
    parser.add_argument("--action", type=str, help="次のアクション (deals)")
    parser.add_argument("--memo", type=str, help="メモ")

    # 更新用
    parser.add_argument("--update", action="store_true", help="データを更新")
    parser.add_argument("--id", type=str, help="更新対象ID (例: P001, V001, C001)")

    args = parser.parse_args()

    if args.init_all:
        init_all()
    elif args.init:
        init_sheet(args.sheet)
    elif args.list:
        list_sheet(args.sheet)
    elif args.json:
        rows = load_rows(args.sheet)
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    elif args.add:
        add_entry(args.sheet, args)
    elif args.update:
        if not args.id:
            print("❌ --id を指定してください。")
            return
        update_entry(args.sheet, args)
    else:
        # デフォルトはdeals一覧を表示
        list_sheet(args.sheet)

if __name__ == "__main__":
    main()
