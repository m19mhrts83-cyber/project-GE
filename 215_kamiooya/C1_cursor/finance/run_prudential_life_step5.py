#!/usr/bin/env python3
"""
ライフプラン自動化 Step5 実行ラッパー（プルデンシャル生命 解約返戻金）。
複数の PRUDENTIAL_USERNAME_1/2/… があれば、順にログインし直して取得する。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from prudential_life_surrender_value import (
    DEFAULT_ENV_PATH,
    PrudentialPausedAtContractList,
    PrudentialOtpPausedAtScreen,
    PrudentialOtpPausedBeforeSubmit,
    fetch_prudential_surrender_value,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Step5: プルデンシャル生命の解約返戻金取得")
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
        help="確認番号（1人目）。メールで確認後チャットで受け取った番号を渡す。2人目は PRUDENTIAL_OTP_CODE_2 等",
    )
    parser.add_argument(
        "--fetch-otp-gmail",
        action="store_true",
        help="Gmail から確認番号を取得（既定でオン・明示用）",
    )
    parser.add_argument(
        "--no-fetch-otp-gmail",
        action="store_true",
        help="Gmail から確認番号を取得しない",
    )
    parser.add_argument(
        "--login-submit-debug",
        action="store_true",
        help="ログイン送信直後に finance/debug/ へ HTML・PNG を保存（ステップ1切り分け）",
    )
    parser.add_argument(
        "--dump-login-form-fail",
        action="store_true",
        help="ログイン入力欄が見つからないとき（ID/PW の fill より前）に finance/debug/ へ HTML・PNG を保存",
    )
    parser.add_argument(
        "--pause-before-login-sec",
        type=int,
        default=None,
        metavar="SEC",
        help="ログイン欄探索の直前に SEC 秒待つ（セレクタ確認用）",
    )
    parser.add_argument(
        "--pause-on-login-fail-sec",
        type=int,
        default=None,
        metavar="SEC",
        help="入力欄未検出で失敗した直後に SEC 秒待つ（ダンプ後）",
    )
    parser.add_argument(
        "--resume-otp",
        action="store_true",
        help="保存済みセッションで確認番号画面から再開（ログインを繰り返さない）",
    )
    parser.add_argument(
        "--pause-before-otp-submit",
        action="store_true",
        help="確認番号入力後に「次へ」を押さず停止（目視・セレクタ確認。PRUDENTIAL_OTP_PAUSE_BEFORE_SUBMIT と同効）",
    )
    parser.add_argument(
        "--pause-at-otp-screen",
        action="store_true",
        help="確認番号入力画面到達直後に停止（Gmail・入力の前。PRUDENTIAL_OTP_PAUSE_AT_SCREEN と同効）",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    if args.fetch_otp_gmail and args.no_fetch_otp_gmail:
        print("--fetch-otp-gmail と --no-fetch-otp-gmail は同時に指定できません。", file=sys.stderr)
        return 2
    if args.no_fetch_otp_gmail:
        fetch_otp_arg = False
    elif args.fetch_otp_gmail:
        fetch_otp_arg = True
    else:
        fetch_otp_arg = None
    try:
        result = fetch_prudential_surrender_value(
            headless=args.headless,
            timeout_ms=args.timeout_ms,
            save_debug=args.save_debug,
            env_file=Path(args.env_file).expanduser(),
            otp_code_override=(args.otp_code or "").strip() or None,
            fetch_otp_from_gmail=fetch_otp_arg,
            debug_login_submit=True if args.login_submit_debug else None,
            debug_login_form_fail=True if args.dump_login_form_fail else None,
            pause_before_login_ms=args.pause_before_login_sec * 1000
            if args.pause_before_login_sec is not None
            else None,
            pause_on_login_form_fail_ms=args.pause_on_login_fail_sec * 1000
            if args.pause_on_login_fail_sec is not None
            else None,
            resume_otp_only=True if args.resume_otp else None,
            otp_pause_before_submit=True if args.pause_before_otp_submit else None,
            otp_pause_at_screen=True if args.pause_at_otp_screen else None,
        )
    except PlaywrightTimeoutError as exc:
        print(f"タイムアウト: {exc}", file=sys.stderr)
        return 1
    except PrudentialOtpPausedAtScreen as exc:
        print(str(exc), file=sys.stderr)
        return 0
    except PrudentialOtpPausedBeforeSubmit as exc:
        print(str(exc), file=sys.stderr)
        return 0
    except PrudentialPausedAtContractList as exc:
        print(str(exc), file=sys.stderr)
        return 0
    except Exception as exc:
        print(f"取得失敗: {exc}", file=sys.stderr)
        return 1
    print(f"プルデンシャル生命 解約返戻金（合計）: {result.value_jpy:,}円")
    for x in result.items:
        print(f"  - アカウント{x.account_index}（{x.username}）: {x.value_jpy:,}円")
    print(result.value_text)
    print(f"抽出方法: {result.parser_mode}")
    print(f"取得URL（最終）: {result.source_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
