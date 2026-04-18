#!/usr/bin/env python3
"""
あかつき証券の債券残高を取得して LINE 通知する実行ラッパー。
"""

from __future__ import annotations

import argparse
from pathlib import Path

from akatsuki_bond_balance import fetch_bond_balance
from notify_line_balance import format_balance_message_with_pl, send_balance_with_pl_to_line


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_ENV_PATH = SCRIPT_DIR / ".env.akatsuki"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="あかつき証券の債券残高合計を取得してLINE通知")
    parser.add_argument("--headless", action="store_true", help="ヘッドレスでブラウザ実行")
    parser.add_argument("--timeout-ms", type=int, default=45000, help="Playwright タイムアウト（ms）")
    parser.add_argument("--save-debug", action="store_true", help="最終ページのHTML/PNGを保存")
    parser.add_argument("--allow-qr-login", action="store_true", help="CHRLINE送信でQR再ログインを許可")
    parser.add_argument("--print-only", action="store_true", help="LINE通知せず合計のみ表示")
    parser.add_argument(
        "--env-file",
        default=str(DEFAULT_ENV_PATH),
        help="環境変数ファイル（既定: finance/.env.akatsuki）",
    )
    parser.add_argument(
        "--allow-bond-nav-skip",
        action="store_true",
        help="ログイン後の債券ページ遷移をスキップ（ログイン直後に表示される場合）",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    result = fetch_bond_balance(
        headless=args.headless,
        timeout_ms=args.timeout_ms,
        save_debug=args.save_debug,
        allow_bond_nav_skip=args.allow_bond_nav_skip,
        env_file=Path(args.env_file).expanduser(),
    )
    message = format_balance_message_with_pl(
        eval_jpy=result.total_jpy,
        pl_jpy=result.pl_jpy,
        category=result.category,
    )
    print(message)

    if args.print_only:
        return 0

    backend = send_balance_with_pl_to_line(
        eval_jpy=result.total_jpy,
        pl_jpy=result.pl_jpy,
        category=result.category,
        allow_qr_login=args.allow_qr_login,
    )
    print(f"通知バックエンド: {backend}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
