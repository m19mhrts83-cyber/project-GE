#!/usr/bin/env python3
"""
Step4: 滋賀銀行ローン残高確認の手動実行ラッパー。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from shiga_loan_balance import fetch_shiga_loan_balance


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_ENV_PATH = SCRIPT_DIR / ".env.lifeplan"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="滋賀銀行ローン残高を確認")
    parser.add_argument("--headless", action="store_true", help="ヘッドレスで実行する")
    parser.add_argument("--timeout-ms", type=int, default=60000, help="Playwright タイムアウト（ms）")
    parser.add_argument("--save-debug", action="store_true", help="最終ページのHTML/PNGを保存")
    parser.add_argument(
        "--env-file",
        default=str(DEFAULT_ENV_PATH),
        help="環境変数ファイル（既定: finance/.env.lifeplan）",
    )
    parser.add_argument(
        "--otp-code",
        default="",
        help="ワンタイムパスワード。未指定で対話実行時は入力を促す",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        result = fetch_shiga_loan_balance(
            headless=args.headless,
            timeout_ms=args.timeout_ms,
            save_debug=args.save_debug,
            env_file=Path(args.env_file).expanduser(),
            otp_code_override=(args.otp_code or "").strip() or None,
        )
    except PlaywrightTimeoutError as exc:
        print(f"タイムアウト: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"取得失敗: {exc}", file=sys.stderr)
        return 1
    print(f"滋賀銀行ローン残高（合計）: {result.amount_jpy:,}円")
    for p in result.products:
        print(f"  - {p.kind}: {p.amount_jpy:,}円  ({p.amount_detail})")
    print(result.amount_text)
    print(f"PDF保存先: {result.pdf_path}")
    print(f"抽出方式: {result.parser_mode}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
