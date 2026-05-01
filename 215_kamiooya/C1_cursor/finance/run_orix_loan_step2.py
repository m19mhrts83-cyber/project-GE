#!/usr/bin/env python3
"""
ライフプラン自動化 Step2 実行ラッパー（オリックス銀行 借入残高）。
"""

from __future__ import annotations

import argparse
from pathlib import Path

from orix_loan_balance import DEFAULT_ENV_PATH, fetch_orix_loan_balances


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Step2: オリックス銀行の契約別借入残高取得")
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
        help="確認コード（必要時）。未指定時は必要になった段階で入力を促す",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    result = fetch_orix_loan_balances(
        headless=args.headless,
        timeout_ms=args.timeout_ms,
        save_debug=args.save_debug,
        env_file=Path(args.env_file).expanduser(),
        otp_code_override=(args.otp_code or "").strip() or None,
    )
    print("オリックス銀行 借入残高（契約別）")
    for x in result.items:
        contract = x.contract_no or "(契約番号不明)"
        date = f" / 借入日:{x.borrow_date}" if x.borrow_date else ""
        src = f"  [{x.extraction_mode}]" if x.extraction_mode else ""
        print(f"- {contract}{date}: {x.balance_jpy:,}円{src}")
    print(f"取得URL: {result.source_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
