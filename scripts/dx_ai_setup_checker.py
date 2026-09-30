#!/usr/bin/env python3
"""DX互助会向け AI社員組織 環境診断ツール (dx_ai_setup_checker.py)

【目的】
神大家さん倶楽部・東海DX互助会のメンバーが、自分自身のPCで
「Grok Bot × Cursor による不動産AI社員組織」を立ち上げるための
前提環境（Python, Grok Bot, Gmail API, クラウドストレージ, Maps等）
を自動診断し、不足項目とセットアップ手順を親切に案内する。

【実行方法】
python3 scripts/dx_ai_setup_checker.py
または
python scripts/dx_ai_setup_checker.py --json
"""

import sys
import os
import platform
import shutil
import subprocess
import urllib.request
import json
from pathlib import Path

# カラー表示用（Windows等非対応時は素直に表示）
USE_COLOR = sys.stdout.isatty() and platform.system() != "Windows"
GREEN = "\033[92m" if USE_COLOR else ""
YELLOW = "\033[93m" if USE_COLOR else ""
RED = "\033[91m" if USE_COLOR else ""
BLUE = "\033[94m" if USE_COLOR else ""
BOLD = "\033[1m" if USE_COLOR else ""
RESET = "\033[0m" if USE_COLOR else ""

def check_python():
    v = sys.version_info
    ok = v.major == 3 and v.minor >= 10
    ver_str = f"{v.major}.{v.minor}.{v.micro}"
    return {
        "name": "Pythonバージョン (3.10以上推奨)",
        "status": "OK" if ok else "WARN",
        "detail": f"現在: Python {ver_str}",
        "fix": "Python 3.10以上をインストールしてください（公式またはpyenv/brew）" if not ok else None
    }

def check_python_packages():
    required = {
        "websockets": "Grok Bot CDP操作用",
        "requests": "API通信・外部連携用",
        "google-api-python-client": "Gmail/Google連携用 (任意)",
    }
    missing = []
    installed = []
    for pkg, purpose in required.items():
        mod_name = pkg.replace("-", "_")
        try:
            __import__(mod_name)
            installed.append(pkg)
        except ImportError:
            # google-api-python-client is googleapiclient
            if pkg == "google-api-python-client":
                try:
                    __import__("googleapiclient")
                    installed.append(pkg)
                    continue
                except ImportError:
                    pass
            missing.append((pkg, purpose))

    if not missing:
        return {
            "name": "必須Pythonライブラリ",
            "status": "OK",
            "detail": f"導入済み: {', '.join(installed)}",
            "fix": None
        }
    else:
        miss_str = ", ".join([p[0] for p in missing])
        fix_cmd = f"pip install {' '.join([p[0] for p in missing])}"
        return {
            "name": "必須Pythonライブラリ",
            "status": "WARN",
            "detail": f"未導入: {miss_str}",
            "fix": f"ターミナルで実行: {fix_cmd}"
        }

def check_grok_bot_app():
    system = platform.system()
    app_found = False
    app_path = ""

    if system == "Darwin":
        candidates = [
            Path("/Applications/Grok Bot.app"),
            Path.home() / "Applications/Grok Bot.app",
        ]
        for c in candidates:
            if c.exists():
                app_found = True
                app_path = str(c)
                break
    elif system == "Windows":
        # Windowsの典型パス
        local_app = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Grok Bot"
        if local_app.exists():
            app_found = True
            app_path = str(local_app)

    return {
        "name": "Grok Bot デスクトップアプリ",
        "status": "OK" if app_found else "WARN",
        "detail": f"検出: {app_path}" if app_found else "未検出（/ApplicationsにGrok Bot.appがありません）",
        "fix": "Grok Bot（Electronアプリ）をインストールしてください" if not app_found else None
    }

def check_cdp_port():
    # 9222ポートでHTTP GET /json/list が通るか
    try:
        req = urllib.request.Request("http://127.0.0.1:9222/json/list", headers={"User-Agent": "DX-Checker"})
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return {
                "name": "Grok Bot CDPデバッグポート (9222)",
                "status": "OK",
                "detail": f"接続成功（稼働中タブ数: {len(data)}）",
                "fix": None
            }
    except Exception:
        return {
            "name": "Grok Bot CDPデバッグポート (9222)",
            "status": "INFO",
            "detail": "現在ポート9222は未開放です（アプリ未起動または通常起動中）",
            "fix": "自動設定時はスクリプトが自動でデバッグポート付きで起動します"
        }

def check_cloud_storage():
    home = Path.home()
    gdrive = False
    onedrive = False
    gdrive_path = ""
    onedrive_path = ""

    # Mac CloudStorage
    cloud_storage = home / "Library/CloudStorage"
    if cloud_storage.exists():
        for d in cloud_storage.iterdir():
            name = d.name
            if "GoogleDrive" in name and not gdrive:
                gdrive = True
                gdrive_path = str(d)
            elif "OneDrive" in name and not onedrive:
                onedrive = True
                onedrive_path = str(d)

    # Windows OneDrive / GDrive
    if not onedrive and os.environ.get("OneDrive"):
        onedrive = True
        onedrive_path = os.environ.get("OneDrive")

    found = []
    if gdrive:
        found.append("Google Drive")
    if onedrive:
        found.append("OneDrive")

    if found:
        return {
            "name": "クラウドストレージ連携 (Google Drive / OneDrive)",
            "status": "OK",
            "detail": f"検出: {', '.join(found)}",
            "fix": None
        }
    else:
        return {
            "name": "クラウドストレージ連携 (Google Drive / OneDrive)",
            "status": "INFO",
            "detail": "ローカル同期フォルダは未検出（ローカル完結またはWeb利用）",
            "fix": "PC用Google DriveまたはOneDriveをインストールするとファイル自動共有が容易になります"
        }

def check_gmail_credentials():
    # よくある置き場を探す
    candidates = [
        Path.home() / "git-repos/215_kamiooya/C1_cursor/1b_Cursorマニュアル/credentials.json",
        Path.cwd() / "credentials.json",
        Path.cwd() / "config/credentials.json",
    ]
    token_candidates = [
        Path.home() / "git-repos/215_kamiooya/C1_cursor/1b_Cursorマニュアル/token.json",
        Path.cwd() / "token.json",
    ]
    cred_found = any(c.exists() for c in candidates)
    token_path = next((t for t in token_candidates if t.exists()), None)

    if cred_found and token_path:
        detail = "OAuthクレデンシャル＆トークン検出（自動送受信可能）"
        try:
            with open(token_path, "r", encoding="utf-8") as f:
                token_data = json.load(f)
                expiry = token_data.get("expiry")
                if expiry:
                    detail += f" [有効期限情報: {expiry[:10]}]"
        except Exception:
            pass
        return {
            "name": "Gmail API 認証連携",
            "status": "OK",
            "detail": detail,
            "fix": None
        }
    elif cred_found:
        return {
            "name": "Gmail API 認証連携",
            "status": "WARN",
            "detail": "credentials.jsonあり / token.json未生成（初回認証が必要）",
            "fix": "認証スクリプトを実行してブラウザでログイン同意を行ってください"
        }
    else:
        return {
            "name": "Gmail API 認証連携",
            "status": "INFO",
            "detail": "未設定（Gmail自動連携パッケージを使用可能）",
            "fix": "Gmail自動送受信を行いたい場合は、Google CloudでAPI有効化とOAuth設定を行ってください"
        }

def check_spreadsheet_mode():
    # スプレッドシートまたはCSVによる案件管理ファイルの有無
    candidates = [
        Path.cwd() / "data/神大家AI不動産_案件管理.csv",
        Path.cwd() / "神大家AI不動産_案件管理.csv",
        Path.home() / "Downloads/神大家AI不動産_案件管理.csv",
    ]
    found = any(c.exists() for c in candidates)
    return {
        "name": "案件管理スプレッドシート（KURASHIFT代替）",
        "status": "OK" if found else "INFO",
        "detail": "案件管理CSVテンプレート検出済み" if found else "未配置（テンプレート生成可能）",
        "fix": "python scripts/dx_spreadsheet_adapter.py --init でテンプレートを作成できます" if not found else None
    }

def main():
    json_mode = "--json" in sys.argv

    results = [
        check_python(),
        check_python_packages(),
        check_grok_bot_app(),
        check_cdp_port(),
        check_cloud_storage(),
        check_gmail_credentials(),
        check_spreadsheet_mode(),
    ]

    if json_mode:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return

    print(f"\n{BOLD}{BLUE}===================================================={RESET}")
    print(f"{BOLD} 🚀 東海DX互助会 AI社員組織 セットアップ診断チェッカー{RESET}")
    print(f"{BOLD}{BLUE}===================================================={RESET}\n")

    ok_count = 0
    warn_count = 0
    info_count = 0

    for r in results:
        st = r["status"]
        if st == "OK":
            icon = f"{GREEN}[ OK ]{RESET}"
            ok_count += 1
        elif st == "WARN":
            icon = f"{YELLOW}[注意]{RESET}"
            warn_count += 1
        else:
            icon = f"{BLUE}[情報]{RESET}"
            info_count += 1

        print(f"{icon} {BOLD}{r['name']}{RESET}")
        print(f"     詳細: {r['detail']}")
        if r["fix"]:
            print(f"     👉 {YELLOW}対応:{RESET} {r['fix']}")
        print()

    # 総合判定（Lv.1: 未接続、Lv.2: メールOK、Lv.3: ストレージOK、Lv.4: Bot連携可能）
    print(f"{BOLD}----------------------------------------------------{RESET}")
    print(f"{BOLD}【総合診断結果】{RESET}")
    has_grok = results[2]["status"] == "OK"
    has_storage = results[4]["status"] == "OK" or results[6]["status"] == "OK"
    has_mail = results[5]["status"] == "OK"
    py_ok = results[0]["status"] == "OK" and results[1]["status"] == "OK"

    if py_ok and has_mail and has_storage and has_grok:
        level = "Lv.4: Bot連携・自走組織 フル稼働可能 (Full AI Organization)"
        msg = "おめでとうございます！Grok BotとCursorを連携させた10名のAI社員組織を即座に稼働できる最高水準の環境です。"
    elif py_ok and has_storage and has_grok:
        level = "Lv.3: ストレージ・台帳連携 稼働可能 (Storage & Deals Ready)"
        msg = "クラウドストレージまたは案件管理シートとGrok Botが連携可能です。Gmail APIを設定すると業者アプローチまで自動化できます。"
    elif py_ok and has_mail:
        level = "Lv.2: メール・API連携 稼働可能 (Mail & API Ready)"
        msg = "Gmail APIによる送受信基盤が整っています。案件管理シートの初期化とGrok Botの配属へ進みましょう。"
    else:
        level = "Lv.1: 未接続・セットアップ準備段階 (Initial Setup Needed)"
        msg = "まずはPythonライブラリのインストール、およびGrok Botアプリの導入からスタートしましょう。"

    color = GREEN if "Lv.4" in level else (BLUE if "Lv.3" in level else YELLOW)
    print(f"ステータス: {BOLD}{color}{level}{RESET}")
    print(f"解説: {msg}")
    print(f"{BOLD}----------------------------------------------------{RESET}\n")

if __name__ == "__main__":
    main()
