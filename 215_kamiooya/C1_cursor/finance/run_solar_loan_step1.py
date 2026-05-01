#!/usr/bin/env python3
"""
ライフプラン自動化 Step1 実行ラッパー。
"""

from __future__ import annotations

import argparse
from pathlib import Path

from solar_loan_balance import DEFAULT_ENV_PATH, fetch_solar_loan_amount


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Step1: 太陽光発電ローン金額の取得")
    parser.add_argument("--headless", action="store_true", help="ヘッドレスで実行する")
    parser.add_argument("--timeout-ms", type=int, default=45000, help="Playwright タイムアウト（ms）")
    parser.add_argument("--save-debug", action="store_true", help="最終ページのHTML/PNGを保存")
    parser.add_argument(
        "--env-file",
        default=str(DEFAULT_ENV_PATH),
        help="環境変数ファイル（既定: finance/.env.lifeplan）",
    )
    parser.add_argument(
        "--otp-code",
        default="",
        help="確認コード（6桁）。未指定時は必要になった段階で入力を促す",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    result = fetch_solar_loan_amount(
        headless=args.headless,
        timeout_ms=args.timeout_ms,
        save_debug=args.save_debug,
        env_file=Path(args.env_file).expanduser(),
        otp_code_override=(args.otp_code or "").strip() or None,
    )
    print(f"太陽光ローン金額: {result.amount_jpy:,}円")
    print(f"抽出方法: {result.parser_mode}")
    print(f"取得URL: {result.source_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
