#!/usr/bin/env python3
"""東海DX互助会 汎用Grok Bot AI社員インストーラー (dx_grok_bot_setup.py)

【目的】
Cursorを使っているDX互助会メンバーが、コマンド1発で
Grok Bot（デスクトップアプリ）内に自分専用の「不動産AI社員組織」
（部長、S1物件調査、S2業者開拓、S6買付交渉、S10周辺マップ等）
を自動セットアップ・Instructions更新するためのツール。

【実行方法】
# 1. プレビュー（反映せず置換結果を確認）
python scripts/dx_grok_bot_setup.py --dry-run

# 2. 実際にGrok Botアプリへ反映（自動起動・CDP設定）
python scripts/dx_grok_bot_setup.py --apply

# 特定の社員だけセットアップする場合
python scripts/dx_grok_bot_setup.py --apply --bot S10
"""

import sys
import os
import time
import json
import asyncio
import argparse
import subprocess
import urllib.request
from pathlib import Path

try:
    import websockets
except ImportError:
    websockets = None

try:
    import yaml
except ImportError:
    yaml = None

CONFIG_PATH = Path.cwd() / "config/dx_member_config.yaml"
EXAMPLE_CONFIG_PATH = Path.cwd() / "config/dx_member_config.example.yaml"
TEMPLATES_DIR = Path.cwd() / "config/dx_grok_templates"

BOT_DEFS = [
    {
        "id": "bucho",
        "name": "不動産賃貸・部長",
        "label": "不動産賃貸・部長",
        "template": "00_不動産賃貸部長_template.md"
    },
    {
        "id": "S01",
        "name": "S1 物件調査",
        "label": "S1 物件調査",
        "template": "S01_物件調査_template.md"
    },
    {
        "id": "S02",
        "name": "S2 業者開拓",
        "label": "S2 業者開拓",
        "template": "S02_業者開拓_template.md"
    },
    {
        "id": "S03",
        "name": "S3 需給三次判断",
        "label": "S3 需給三次判断",
        "template": "S03_需給判断_template.md"
    },
    {
        "id": "S04",
        "name": "S4 修繕業者開拓",
        "label": "S4 修繕業者開拓",
        "template": "S04_修繕業者_template.md"
    },
    {
        "id": "S05",
        "name": "S5 ペルソナ二次判断",
        "label": "S5 ペルソナ二次判断",
        "template": "S05_ペルソナ_template.md"
    },
    {
        "id": "S06",
        "name": "S6 買付・価格交渉",
        "label": "S6 買付・価格交渉",
        "template": "S06_買付交渉_template.md"
    },
    {
        "id": "S07",
        "name": "S7 融資相談",
        "label": "S7 融資相談",
        "template": "S07_融資相談_template.md"
    },
    {
        "id": "S08",
        "name": "S8 物件ライフライン",
        "label": "S8 物件ライフライン",
        "template": "S08_ライフライン_template.md"
    },
    {
        "id": "S09",
        "name": "S9 管理会社開拓",
        "label": "S9 管理会社開拓",
        "template": "S09_管理会社_template.md"
    },
    {
        "id": "S10",
        "name": "S10 周辺マップ作成職人",
        "label": "S10 周辺マップ作成職人",
        "template": "S10_周辺マップ作成職人_template.md"
    },
]

def load_member_config():
    target = CONFIG_PATH if CONFIG_PATH.exists() else EXAMPLE_CONFIG_PATH
    if not target.exists():
        return {}
    if yaml is None:
        # 簡易フォールバック
        return {
            "owner": {"name": "松野", "company": "リビングサポート松", "email": "admin@livingsupport-matsu.co.jp", "phone": ""},
            "strategy": {"target_area": "愛知県・岐阜県", "target_asset_types": "戸建・アパート", "target_price_max_man": 500, "target_min_yield_pct": 15.0, "parking_requirement": "1台以上"}
        }
    with open(target, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def render_template(template_filename: str, cfg: dict) -> str:
    path = TEMPLATES_DIR / template_filename
    if not path.exists():
        return ""
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    owner = cfg.get("owner", {})
    strategy = cfg.get("strategy", {})

    replacements = {
        "{{OWNER_NAME}}": str(owner.get("name", "オーナー")),
        "{{COMPANY_NAME}}": str(owner.get("company", "個人")),
        "{{OWNER_EMAIL}}": str(owner.get("email", "owner@example.com")),
        "{{OWNER_PHONE}}": str(owner.get("phone", "090-0000-0000")),
        "{{TARGET_AREA}}": str(strategy.get("target_area", "愛知県・岐阜県周辺")),
        "{{TARGET_ASSET_TYPES}}": str(strategy.get("target_asset_types", "木造戸建またはアパート")),
        "{{TARGET_PRICE_MAX_MAN}}": str(strategy.get("target_price_max_man", 500)),
        "{{TARGET_MIN_YIELD_PCT}}": str(strategy.get("target_min_yield_pct", 15.0)),
        "{{PARKING_REQUIREMENT}}": str(strategy.get("parking_requirement", "駐車場あり")),
    }

    for k, v in replacements.items():
        text = text.replace(k, v)
    return text

def ensure_grok_bot_cdp(port=9222):
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/json/list")
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            return True
    except Exception:
        pass

    if sys.platform == "darwin":
        print(f"🔄 Grok BotをCDPデバッグポート({port})付きで起動中...")
        cmd = [
            "open", "-a", "Grok Bot", "--args",
            f"--remote-debugging-port={port}",
            "--force-renderer-accessibility"
        ]
        subprocess.run(cmd, check=False)
        for _ in range(10):
            time.sleep(1.0)
            try:
                req = urllib.request.Request(f"http://127.0.0.1:{port}/json/list")
                with urllib.request.urlopen(req, timeout=1.0) as resp:
                    print("✅ Grok Botの起動とCDP接続を確認しました。")
                    return True
            except Exception:
                pass
    return False

async def get_grok_ws_url(port=9222):
    req = urllib.request.Request(f"http://127.0.0.1:{port}/json/list")
    with urllib.request.urlopen(req, timeout=2.0) as resp:
        tabs = json.loads(resp.read().decode("utf-8"))
    for t in tabs:
        if t.get("type") == "page" and "Grok" in t.get("title", ""):
            return t.get("webSocketDebuggerUrl")
    for t in tabs:
        if t.get("type") == "page" and t.get("webSocketDebuggerUrl"):
            return t.get("webSocketDebuggerUrl")
    return None

async def cdp_eval(ws, expr: str):
    msg_id = int(time.time() * 1000) % 1000000
    payload = {
        "id": msg_id,
        "method": "Runtime.evaluate",
        "params": {
            "expression": expr,
            "returnByValue": True,
            "awaitPromise": True
        }
    }
    await ws.send(json.dumps(payload))
    while True:
        resp = await ws.recv()
        data = json.loads(resp)
        if data.get("id") == msg_id:
            res = data.get("result", {}).get("result", {})
            return res.get("value")

async def run_setup(args):
    cfg = load_member_config()
    print("=====================================================")
    print(" 🤖 東海DX互助会 汎用Grok Bot AI社員インストーラー")
    print("=====================================================")
    owner_name = cfg.get("owner", {}).get("name", "未設定")
    area = cfg.get("strategy", {}).get("target_area", "未設定")
    print(f"オーナー: {owner_name} | 対象エリア: {area}\n")

    target_bots = BOT_DEFS
    if args.bot:
        target_bots = [b for b in BOT_DEFS if args.bot.lower() in b["id"].lower() or args.bot in b["name"]]
        if not target_bots:
            print(f"❌ 指定されたBot '{args.bot}' が見つかりません。")
            return

    if args.dry_run or not args.apply:
        print("【DRY-RUN プレビュー】（--apply を付けると実際にGrok Botに反映されます）\n")
        for b in target_bots:
            rendered = render_template(b["template"], cfg)
            print(f"-----------------------------------------------------")
            print(f"社員ID: {b['id']} | 名前: {b['name']}")
            print(f"指示書文字数: {len(rendered)}文字")
            print(f"冒頭抜粋:\n{rendered[:200]}...\n")
        print("-----------------------------------------------------")
        print("👉 反映するには: python scripts/dx_grok_bot_setup.py --apply")
        return

    # 実装反映 (--apply)
    if not websockets:
        print("❌ 'websockets' ライブラリが必要です。pip install websockets を実行してください。")
        return

    if not ensure_grok_bot_cdp():
        print("❌ Grok BotとCDP接続できませんでした。手動でアプリを起動してください。")
        return

    ws_url = await get_grok_ws_url()
    if not ws_url:
        print("❌ Grok BotのデバッグWebSocketが見つかりませんでした。")
        return

    print("🔌 Grok BotにCDP接続中...")
    async with websockets.connect(ws_url, max_size=10*1024*1024) as ws:
        # 現在のBotリスト取得
        existing = await cdp_eval(ws, "window.desktop ? window.desktop.agent.list() : []")
        print(f"📋 既存Bot検出数: {len(existing) if existing else '不明'}")

        for b in target_bots:
            rendered = render_template(b["template"], cfg)
            print(f"\n⚙️  設定中: {b['name']} ({len(rendered)}文字)...")
            
            # React state対応のInstructions更新スクリプト
            js_code = f"""
            (async () => {{
                if (!window.desktop || !window.desktop.agent) return {{ok: false, reason: 'NO_DESKTOP_API'}};
                const list = await window.desktop.agent.list();
                let target = list.find(x => x.name === {json.dumps(b['name'])} || x.label === {json.dumps(b['label'])});
                if (!target) {{
                    // 新規作成
                    target = await window.desktop.agent.create({{
                        name: {json.dumps(b['name'])},
                        label: {json.dumps(b['label'])},
                        instructions: {json.dumps(rendered)}
                    }});
                    return {{ok: true, action: 'created', id: target.id}};
                }} else {{
                    // 更新
                    await window.desktop.agent.update(target.id, {{
                        instructions: {json.dumps(rendered)}
                    }});
                    return {{ok: true, action: 'updated', id: target.id}};
                }}
            }})()
            """
            res = await cdp_eval(ws, js_code)
            if res and res.get("ok"):
                action_str = "新規作成" if res.get("action") == "created" else "指示書更新"
                print(f"   ✅ {action_str} 完了 (ID: {res.get('id')})")
            else:
                print(f"   ⚠️ API経由の更新結果: {res}")

        # サイドバーセクション「不動産賃貸」にまとめる
        section_js = f"""
        (async () => {{
            if (!window.desktop || !window.desktop.agent) return;
            const list = await window.desktop.agent.list();
            const names = {json.dumps([b['name'] for b in BOT_DEFS])};
            const ids = list.filter(x => names.includes(x.name)).map(x => x.id);
            if (ids.length && window.desktop.agent.setSidebarSections) {{
                await window.desktop.agent.setSidebarSections({{"不動産賃貸": ids}});
                return true;
            }}
            return false;
        }})()
        """
        await cdp_eval(ws, section_js)
        print("\n📁 サイドバーの「不動産賃貸」セクションに全AI社員を整理・配置しました。")
        print("🎉 すべてのAI社員のセットアップが完了しました！")

def main():
    parser = argparse.ArgumentParser(description="東海DX互助会 汎用Grok Bot AI社員インストーラー")
    parser.add_argument("--dry-run", action="store_true", help="反映せず置換プレビューを表示")
    parser.add_argument("--apply", action="store_true", help="実際にGrok Botへ反映")
    parser.add_argument("--bot", type=str, help="特定Botのみ対象 (例: bucho, S01, S10)")
    args = parser.parse_args()

    asyncio.run(run_setup(args))

if __name__ == "__main__":
    main()
