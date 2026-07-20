#!/usr/bin/env python3
"""三菱UFJネットDEローン（JACCS）— Chrome で確実に開く・書類提出。

Cursor 内蔵ブラウザでは「書類提出」が window.open のため _ESY0C020 になりやすい。
Google Chrome + CDP を正とする。

使い方:
  # 手動: 通常 Chrome でログイン画面
  ~/git-repos/scripts/jarvis_mufg_jaccs_open.py --open

  # 書類提出案内まで開く
  ~/git-repos/scripts/jarvis_mufg_jaccs_open.py --documents

  # 4点セット自動アップロード（推奨・今回の知見を反映）
  ~/git-repos/scripts/jarvis_mufg_jaccs_open.py --upload
  ~/git-repos/scripts/jarvis_mufg_jaccs_open.py --upload --folder /path/to/submit --dry-run

  # 銀行共通CLI（りそな等）: jarvis_car_loan_upload.py --bank mufg_jaccs --upload

正本: scripts/car_loan/configs/mufg_jaccs.yaml
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from car_loan.banks import mufg_jaccs  # noqa: E402
from car_loan.banks.registry import expand_path, load_bank_config  # noqa: E402
from car_loan.chrome_cdp import open_in_chrome, start_cdp_chrome  # noqa: E402
from car_loan.env_state import ENV_FILE, load_env, load_state, receipt_from_state  # noqa: E402

LOGIN_URL = "https://ecredit.jaccs.co.jp/bank/Service?_TRANID=BWFLoginDL"
DEFAULT_CDP_PORT = 9223


def receipt_number(env: dict) -> str:
    if env.get("MUFG_JACCS_RECEIPT_NUMBER"):
        return env["MUFG_JACCS_RECEIPT_NUMBER"]
    return receipt_from_state("mufg_net_de_mycar", env, load_state())


def main() -> int:
    parser = argparse.ArgumentParser(description="MUFG/JACCS ポータル・書類提出")
    parser.add_argument("--open", action="store_true", help="通常 Chrome でログインURLを開く")
    parser.add_argument("--cdp-start", action="store_true", help="CDP Chrome を起動")
    parser.add_argument("--login", action="store_true", help="CDP Chrome で自動ログイン")
    parser.add_argument("--documents", action="store_true", help="書類提出案内を開く")
    parser.add_argument("--upload", action="store_true", help="提出フォルダから4点を自動アップロード")
    parser.add_argument(
        "--resubmit-deficiency",
        action="store_true",
        help="書類不備の再提出（免許証表のみ。他は不要）",
    )
    parser.add_argument(
        "--post-approval",
        action="store_true",
        help="本審査承認後の追加提出（振込先・注文書/契約書等）",
    )
    parser.add_argument("--folder", type=Path, help="提出書類フォルダ")
    parser.add_argument("--dry-run", action="store_true", help="アップロードせずファイル・URL確認")
    parser.add_argument("--port", type=int, default=DEFAULT_CDP_PORT)
    parser.add_argument("--print-info", action="store_true")
    args = parser.parse_args()

    env = load_env(ENV_FILE)
    rcpt = receipt_number(env)
    password = env.get("MUFG_JACCS_LOGIN_PASSWORD", "")
    cfg = load_bank_config("mufg_jaccs")
    profile = expand_path(cfg["chrome_profile"])

    if args.print_info or not any(
        [
            args.open,
            args.cdp_start,
            args.login,
            args.documents,
            args.upload,
            args.resubmit_deficiency,
            args.post_approval,
        ]
    ):
        print("=== MUFG/JACCS ネットDEローン ===")
        print(f"LOGIN_URL={LOGIN_URL}")
        print(f"RECEIPT_NUMBER={rcpt or '（未設定）'}")
        print(f"PASSWORD={'（.env.jarvis_private に設定済み）' if password else '（未設定）'}")
        print()
        print("推奨: --upload（自動提出） / --open（手動） / --documents（案内のみ）")
        if not any(
            [
                args.open,
                args.cdp_start,
                args.login,
                args.documents,
                args.upload,
                args.resubmit_deficiency,
                args.post_approval,
            ]
        ):
            return 0

    if args.post_approval:
        folder = args.folder or expand_path(cfg.get("default_submit_folder", ""))
        if not folder.is_dir():
            print(f"提出フォルダが見つかりません: {folder}", file=sys.stderr)
            return 1
        mufg_jaccs.run_post_approval(
            folder,
            port=args.port,
            dry_run=args.dry_run,
            update_state=not args.dry_run,
        )
        return 0

    if args.resubmit_deficiency:
        folder = args.folder or expand_path(cfg.get("default_submit_folder", ""))
        if not folder.is_dir():
            print(f"提出フォルダが見つかりません: {folder}", file=sys.stderr)
            return 1
        mufg_jaccs.run_resubmit_deficiency(
            folder,
            port=args.port,
            dry_run=args.dry_run,
            update_state=not args.dry_run,
        )
        return 0

    if args.upload:
        folder = args.folder or expand_path(cfg.get("default_submit_folder", ""))
        if not folder.is_dir():
            print(f"提出フォルダが見つかりません: {folder}", file=sys.stderr)
            return 1
        mufg_jaccs.run_upload(
            folder,
            port=args.port,
            dry_run=args.dry_run,
            update_state=not args.dry_run,
        )
        return 0

    if args.open:
        open_in_chrome(LOGIN_URL)
        if rcpt:
            print(f"📎 受付番号: {rcpt}")
        return 0

    if args.cdp_start or args.login or args.documents:
        start_cdp_chrome(args.port, profile, LOGIN_URL)

    if args.login or args.documents:
        if not rcpt or not password:
            print("受付番号または MUFG_JACCS_LOGIN_PASSWORD が未設定です。", file=sys.stderr)
            return 1
        if args.documents:
            mufg_jaccs.open_jaccs_documents_guide(args.port, rcpt, password)
        else:
            from playwright.sync_api import sync_playwright
            import time

            with sync_playwright() as pw:
                browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{args.port}")
                ctx = browser.contexts[0]
                page = ctx.pages[0] if ctx.pages else ctx.new_page()
                if LOGIN_URL not in page.url:
                    page.goto(LOGIN_URL, wait_until="domcontentloaded")
                page.locator('input[name="IUSERID"]').fill(rcpt)
                page.locator('input[name="IPASSWORD"]').fill(password)
                page.locator('img[alt="ログイン"]').click()
                page.wait_for_load_state("domcontentloaded")
                time.sleep(1)
                print(f"📎 ログイン後: {page.title()} / {page.url}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
