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

BUY_PLAN_PRESETS = {
    "1": {
        "buy_plan_type": "築古戸建て",
        "target_asset_types": "木造築古戸建（平屋・2階建て）",
        "target_price_max_man": 500,
        "target_min_yield_pct": 15.0,
        "land_ratio_target_pct": 70,
        "financing_strategy": "現金購入またはリフォームローン",
        "summary": "200〜600万円 / 利回り15〜20%以上 / 土地値70%以上 / 手堅いCF構築・自己資金保全"
    },
    "2": {
        "buy_plan_type": "築古アパート",
        "target_asset_types": "木造または軽量鉄骨中古アパート（1棟）",
        "target_price_max_man": 3000,
        "target_min_yield_pct": 12.0,
        "land_ratio_target_pct": 65,
        "financing_strategy": "地銀・信金・信販（セゾン・トラスト等）",
        "summary": "1,500〜4,000万円 / 利回り11〜15%前後 / 土地値60〜70%以上 / まとまったCF加速"
    },
    "3": {
        "buy_plan_type": "新築アパート",
        "target_asset_types": "木造新築アパート（建売・建築）",
        "target_price_max_man": 10000,
        "target_min_yield_pct": 7.5,
        "land_ratio_target_pct": 15,
        "financing_strategy": "アパートローン・提携ローン（フルローン活用）",
        "summary": "6,000万〜1.5億円 / 利回り7.0〜8.5%前後 / 土地値12〜15%以上 / 規模一気拡大"
    }
}

def load_member_config():
    target = CONFIG_PATH if CONFIG_PATH.exists() else EXAMPLE_CONFIG_PATH
    if not target.exists():
        return {}
    if yaml is None:
        # 簡易フォールバック
        return {
            "owner": {"name": "松野", "company": "リビングサポート松", "email": "admin@livingsupport-matsu.co.jp", "phone": ""},
            "strategy": {
                "buy_plan_type": "築古戸建て",
                "target_area": "愛知県・岐阜県",
                "target_asset_types": "木造築古戸建",
                "target_price_max_man": 500,
                "target_min_yield_pct": 15.0,
                "land_ratio_target_pct": 70,
                "financing_strategy": "現金購入またはリフォームローン",
                "parking_requirement": "1台以上"
            }
        }
    with open(target, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def save_member_config(cfg: dict):
    if yaml is None:
        print("❌ PyYAMLがインストールされていないため保存できません。pip install pyyaml を実行してください。")
        return False
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    return True

def prompt_buy_plan_selection(cfg: dict) -> dict:
    strategy = cfg.setdefault("strategy", {})
    current_plan = strategy.get("buy_plan_type", "築古戸建て")
    
    print("\n" + "=" * 60)
    print("【神大家 STEP3連動】買い進めプラン選定ヒアリング（質問形式）")
    print("=" * 60)
    print("物件調査フェーズに入る前に、現在狙う「買い進めプラン」を選択してください。\n")
    print(" [1] 築古戸建て (現金・小額融資 / 手堅いCF構築)")
    print("     ・価格帯: 200〜600万円 (指値前提)")
    print("     ・目標利回り: 15%〜20%以上")
    print("     ・土地値割合目安: 70%以上 (路線価重視)")
    print("     ・融資戦略: 現金またはリフォームローン (自己資金保全・共同担保原資)\n")
    print(" [2] 築古アパート (地銀・信販活用 / CF加速)")
    print("     ・価格帯: 1,500〜4,000万円")
    print("     ・目標利回り: 11%〜15%前後")
    print("     ・土地値割合目安: 60%〜70%以上")
    print("     ・融資戦略: 地銀・信金・信販（セゾン・トラスト等 / 修繕再生バリューアップ)\n")
    print(" [3] 新築アパート (フルローン・規模拡大)")
    print("     ・価格帯: 6,000万〜1.5億円")
    print("     ・目標利回り: 7.0%〜8.5%前後")
    print("     ・土地値割合目安: 12%〜15%以上")
    print("     ・融資戦略: アパートローン・提携ローン (高属性を活かした規模一気拡大)\n")
    print("-" * 60)
    
    current_key = "1"
    for k, v in BUY_PLAN_PRESETS.items():
        if v["buy_plan_type"] == current_plan:
            current_key = k
            break
            
    choice = input(f"買い進めプランを選択してください [1-3] (現在: {current_key} {current_plan}): ").strip()
    if not choice:
        choice = current_key
        
    preset = BUY_PLAN_PRESETS.get(choice, BUY_PLAN_PRESETS["1"])
    print(f"\n✅ 選択されたプラン: 【{preset['buy_plan_type']}】")
    print(f"   基準概要: {preset['summary']}")
    
    # プリセット値を反映
    strategy["buy_plan_type"] = preset["buy_plan_type"]
    strategy["target_asset_types"] = preset["target_asset_types"]
    strategy["target_price_max_man"] = preset["target_price_max_man"]
    strategy["target_min_yield_pct"] = preset["target_min_yield_pct"]
    strategy["land_ratio_target_pct"] = preset["land_ratio_target_pct"]
    strategy["financing_strategy"] = preset["financing_strategy"]
    
    save_member_config(cfg)
    print(f"💾 設定ファイル ({CONFIG_PATH}) を更新しました！\n")
    return cfg

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
        "{{BUY_PLAN_TYPE}}": str(strategy.get("buy_plan_type", "築古戸建て")),
        "{{TARGET_AREA}}": str(strategy.get("target_area", "愛知県・岐阜県周辺")),
        "{{TARGET_ASSET_TYPES}}": str(strategy.get("target_asset_types", "木造戸建またはアパート")),
        "{{TARGET_PRICE_MAX_MAN}}": str(strategy.get("target_price_max_man", 500)),
        "{{TARGET_MIN_YIELD_PCT}}": str(strategy.get("target_min_yield_pct", 15.0)),
        "{{LAND_RATIO_TARGET_PCT}}": str(strategy.get("land_ratio_target_pct", 70)),
        "{{FINANCING_STRATEGY}}": str(strategy.get("financing_strategy", "現金購入またはリフォームローン")),
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

    if getattr(args, "set_plan", None):
        plan_choice = str(args.set_plan).strip()
        if plan_choice in BUY_PLAN_PRESETS:
            preset = BUY_PLAN_PRESETS[plan_choice]
            strategy = cfg.setdefault("strategy", {})
            strategy["buy_plan_type"] = preset["buy_plan_type"]
            strategy["target_asset_types"] = preset["target_asset_types"]
            strategy["target_price_max_man"] = preset["target_price_max_man"]
            strategy["target_min_yield_pct"] = preset["target_min_yield_pct"]
            strategy["land_ratio_target_pct"] = preset["land_ratio_target_pct"]
            strategy["financing_strategy"] = preset["financing_strategy"]
            save_member_config(cfg)
            print(f"✅ 買い進めプランを【{preset['buy_plan_type']}】に更新しました。({preset['summary']})\n")
        else:
            print(f"❌ 無効なプラン番号です。1: 築古戸建て, 2: 築古アパート, 3: 新築アパート から選んでください。\n")

    if getattr(args, "interactive_plan", False):
        cfg = prompt_buy_plan_selection(cfg)
        if not args.apply and not args.dry_run:
            print("👉 このプランでGrok Botへ反映するには: python scripts/dx_grok_bot_setup.py --apply")
            return

    owner_name = cfg.get("owner", {}).get("name", "未設定")
    area = cfg.get("strategy", {}).get("target_area", "未設定")
    current_plan = cfg.get("strategy", {}).get("buy_plan_type", "築古戸建て")
    print(f"オーナー: {owner_name} | プラン: 【{current_plan}】 | 対象エリア: {area}\n")

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
    parser.add_argument("--interactive-plan", action="store_true", help="対話形式で買い進めプラン（築古戸建て/築古AP/新築AP）を選択・設定")
    parser.add_argument("--set-plan", type=str, choices=["1", "2", "3"], help="買い進めプランを番号で指定設定 (1: 築古戸建て, 2: 築古アパート, 3: 新築アパート)")
    parser.add_argument("--dry-run", action="store_true", help="反映せず置換プレビューを表示")
    parser.add_argument("--apply", action="store_true", help="実際にGrok Botへ反映")
    parser.add_argument("--bot", type=str, help="特定Botのみ対象 (例: bucho, S01, S10)")
    args = parser.parse_args()

    asyncio.run(run_setup(args))

if __name__ == "__main__":
    main()
