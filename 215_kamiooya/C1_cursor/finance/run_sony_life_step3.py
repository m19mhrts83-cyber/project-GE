#!/usr/bin/env python3
"""
ライフプラン自動化 Step3 実行ラッパー（ソニー生命 解約返戻金）。
複数の SONYLIFE_USERNAME_1/2/… があれば、順にログインし直して取得する。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from sony_life_surrender_value import DEFAULT_ENV_PATH, fetch_sony_surrender_value


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Step3: ソニー生命の解約返戻金取得")
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
        help="確認コード（1人目のログインで必要な場合）。2人目は SONYLIFE_OTP_CODE_2 等",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        result = fetch_sony_surrender_value(
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
    print(f"ソニー生命 解約返戻金（合計）: {result.value_jpy:,}円")
    for x in result.items:
        print(f"  - アカウント{x.account_index}（{x.username}）: {x.value_jpy:,}円")
    print(result.value_text)
    print(f"抽出方法: {result.parser_mode}")
    print(f"取得URL（最終）: {result.source_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
