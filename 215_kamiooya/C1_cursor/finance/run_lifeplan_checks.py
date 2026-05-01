#!/usr/bin/env python3
"""
ライフプラン確認のまとめ実行:
1) 太陽光発電ローン残高
2) オリックス銀行 借入残高（契約別）
3) ソニー生命 解約返戻金
4) 滋賀銀行 ローン残高
5) プルデンシャル生命 解約返戻金
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from orix_loan_balance import fetch_orix_loan_balances
from shiga_loan_balance import fetch_shiga_loan_balance
from solar_loan_balance import fetch_solar_loan_amount
from prudential_life_surrender_value import PrudentialOtpPausedAtScreen
from prudential_life_surrender_value import PrudentialOtpPausedBeforeSubmit
from prudential_life_surrender_value import PrudentialPausedAtContractList
from prudential_life_surrender_value import fetch_prudential_surrender_value
from prudential_life_surrender_value import prudential_step_configured
from sony_life_surrender_value import fetch_sony_surrender_value


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_ENV_PATH = SCRIPT_DIR / ".env.lifeplan"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ライフプラン確認をまとめて実行")
    parser.add_argument("--headless", action="store_true", help="ヘッドレスで実行する")
    parser.add_argument("--timeout-ms", type=int, default=45000, help="Playwright タイムアウト（ms）")
    parser.add_argument("--save-debug", action="store_true", help="各処理の最終ページHTML/PNGを保存")
    parser.add_argument(
        "--env-file",
        default=str(DEFAULT_ENV_PATH),
        help="環境変数ファイル（既定: finance/.env.lifeplan）",
    )
    parser.add_argument("--solar-otp-code", default="", help="太陽光ローン OTP（必要時）")
    parser.add_argument("--orix-otp-code", default="", help="オリックス OTP（必要時）")
    parser.add_argument("--sony-otp-code", default="", help="ソニー生命 OTP（必要時）")
    parser.add_argument("--shiga-otp-code", default="", help="滋賀銀行 OTP（必要時）")
    parser.add_argument(
        "--prudential-otp-code",
        default="",
        help="プルデンシャル生命の確認番号（1人目・必要時）。チャットで受け取った番号を渡す想定",
    )
    parser.add_argument(
        "--fetch-prudential-otp-gmail",
        action="store_true",
        help="プルデンシャル確認番号を Gmail で取得（既定でオン・明示用）",
    )
    parser.add_argument(
        "--no-fetch-prudential-otp-gmail",
        action="store_true",
        help="プルデンシャル確認番号を Gmail で取得しない",
    )
    parser.add_argument(
        "--prudential-dump-login-form-fail",
        action="store_true",
        help="プルデンシャルでログイン欄が見つからないとき finance/debug/ へ HTML・PNG を保存",
    )
    parser.add_argument(
        "--prudential-resume-otp",
        action="store_true",
        help="プルデンシャルを保存済みセッションで確認番号画面から再開（ログインを繰り返さない）",
    )
    parser.add_argument("--json", action="store_true", help="JSONで結果を出力する")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    env_file = Path(args.env_file).expanduser()

    out: dict[str, object] = {}

    # 1) 太陽光発電
    try:
        solar = fetch_solar_loan_amount(
            headless=args.headless,
            timeout_ms=args.timeout_ms,
            save_debug=args.save_debug,
            env_file=env_file,
            otp_code_override=(args.solar_otp_code or "").strip() or None,
        )
        out["solar_loan"] = {
            "ok": True,
            "amount_jpy": solar.amount_jpy,
            "amount_text": solar.amount_text,
            "source_url": solar.source_url,
        }
    except Exception as exc:
        out["solar_loan"] = {"ok": False, "error": str(exc)}

    # 2) オリックス銀行（契約別）
    try:
        orix = fetch_orix_loan_balances(
            headless=args.headless,
            timeout_ms=args.timeout_ms,
            save_debug=args.save_debug,
            env_file=env_file,
            otp_code_override=(args.orix_otp_code or "").strip() or None,
        )
        out["orix_loans"] = {
            "ok": True,
            "items": [
                {
                    "contract_no": x.contract_no,
                    "borrow_date": x.borrow_date,
                    "balance_jpy": x.balance_jpy,
                    "balance_text": x.balance_text,
                    "extraction_mode": x.extraction_mode,
                }
                for x in orix.items
            ],
            "source_url": orix.source_url,
        }
    except Exception as exc:
        out["orix_loans"] = {"ok": False, "error": str(exc)}

    # 3) ソニー生命（解約返戻金）
    try:
        sony = fetch_sony_surrender_value(
            headless=args.headless,
            timeout_ms=args.timeout_ms,
            save_debug=args.save_debug,
            env_file=env_file,
            otp_code_override=(args.sony_otp_code or "").strip() or None,
        )
        out["sony_surrender"] = {
            "ok": True,
            "value_jpy": sony.value_jpy,
            "value_text": sony.value_text,
            "source_url": sony.source_url,
            "items": [
                {
                    "account_index": x.account_index,
                    "username": x.username,
                    "value_jpy": x.value_jpy,
                    "value_text": x.value_text,
                    "source_url": x.source_url,
                    "parser_mode": x.parser_mode,
                }
                for x in sony.items
            ],
        }
    except Exception as exc:
        out["sony_surrender"] = {"ok": False, "error": str(exc)}

    # 4) 滋賀銀行（ローン残高）
    try:
        shiga = fetch_shiga_loan_balance(
            headless=args.headless,
            timeout_ms=args.timeout_ms,
            save_debug=args.save_debug,
            env_file=env_file,
            otp_code_override=(args.shiga_otp_code or "").strip() or None,
        )
        out["shiga_loan"] = {
            "ok": True,
            "amount_jpy": shiga.amount_jpy,
            "amount_text": shiga.amount_text,
            "source_url": shiga.source_url,
            "pdf_path": shiga.pdf_path,
            "products": [
                {
                    "kind": p.kind,
                    "amount_jpy": p.amount_jpy,
                    "amount_detail": p.amount_detail,
                    "pdf_path": p.pdf_path,
                }
                for p in shiga.products
            ],
        }
    except Exception as exc:
        out["shiga_loan"] = {"ok": False, "error": str(exc)}

    # 5) プルデンシャル生命（解約返戻金、未設定時はスキップ）
    if not prudential_step_configured(env_file):
        out["prudential_surrender"] = {
            "ok": True,
            "skipped": True,
            "reason": "PRUDENTIAL_LOGIN_URL 未設定",
        }
    else:
        if args.fetch_prudential_otp_gmail and args.no_fetch_prudential_otp_gmail:
            out["prudential_surrender"] = {
                "ok": False,
                "error": "--fetch-prudential-otp-gmail と --no-fetch-prudential-otp-gmail は同時指定不可",
            }
        else:
            try:
                if args.no_fetch_prudential_otp_gmail:
                    pru_fetch = False
                elif args.fetch_prudential_otp_gmail:
                    pru_fetch = True
                else:
                    pru_fetch = None
                pru = fetch_prudential_surrender_value(
                    headless=args.headless,
                    timeout_ms=args.timeout_ms,
                    save_debug=args.save_debug,
                    env_file=env_file,
                    otp_code_override=(args.prudential_otp_code or "").strip() or None,
                    fetch_otp_from_gmail=pru_fetch,
                    debug_login_form_fail=True if args.prudential_dump_login_form_fail else None,
                    resume_otp_only=True if args.prudential_resume_otp else None,
                )
                out["prudential_surrender"] = {
                    "ok": True,
                    "value_jpy": pru.value_jpy,
                    "value_text": pru.value_text,
                    "source_url": pru.source_url,
                    "items": [
                        {
                            "account_index": x.account_index,
                            "username": x.username,
                            "value_jpy": x.value_jpy,
                            "value_text": x.value_text,
                            "source_url": x.source_url,
                            "parser_mode": x.parser_mode,
                        }
                        for x in pru.items
                    ],
                }
            except PrudentialOtpPausedAtScreen as exc:
                out["prudential_surrender"] = {
                    "ok": True,
                    "paused_at_otp_screen": True,
                    "message": str(exc),
                }
            except PrudentialOtpPausedBeforeSubmit as exc:
                out["prudential_surrender"] = {
                    "ok": True,
                    "paused_before_otp_submit": True,
                    "message": str(exc),
                }
            except PrudentialPausedAtContractList as exc:
                out["prudential_surrender"] = {
                    "ok": True,
                    "paused_at_contract_list": True,
                    "message": str(exc),
                }
            except Exception as exc:
                out["prudential_surrender"] = {"ok": False, "error": str(exc)}

    if args.json:
        print(json.dumps(out, ensure_ascii=False))
        return 0

    print("ライフプラン確認結果")

    s = out["solar_loan"]
    if isinstance(s, dict) and s.get("ok"):
        print(f"1. 太陽光発電: {int(s['amount_jpy']):,}円")
    else:
        print(f"1. 太陽光発電: 取得失敗 ({s.get('error') if isinstance(s, dict) else 'unknown'})")

    o = out["orix_loans"]
    if isinstance(o, dict) and o.get("ok"):
        print("2. オリックス銀行の返済残高（契約別）:")
        items = o.get("items") if isinstance(o.get("items"), list) else []
        if items:
            for item in items:
                if not isinstance(item, dict):
                    continue
                c = item.get("contract_no") or "(契約番号不明)"
                d = item.get("borrow_date") or ""
                b = item.get("balance_jpy")
                date = f" / 借入日:{d}" if d else ""
                try:
                    b_int = int(b)
                except Exception:
                    b_int = 0
                mode = item.get("extraction_mode") or ""
                src = f"  [{mode}]" if mode else ""
                print(f"   - {c}{date}: {b_int:,}円{src}")
        else:
            print("   - 契約が見つかりませんでした")
    else:
        print(f"2. オリックス銀行の返済残高: 取得失敗 ({o.get('error') if isinstance(o, dict) else 'unknown'})")

    y = out["sony_surrender"]
    if isinstance(y, dict) and y.get("ok"):
        print(f"3. ソニー生命 解約返戻金（合計）: {int(y['value_jpy']):,}円")
        sitems = y.get("items") if isinstance(y.get("items"), list) else []
        for item in sitems:
            if not isinstance(item, dict):
                continue
            ai = item.get("account_index") or ""
            u = item.get("username") or ""
            vj = item.get("value_jpy")
            try:
                vji = int(vj)
            except Exception:
                vji = 0
            print(f"   - アカウント{ai}（{u}）: {vji:,}円")
    else:
        print(f"3. ソニー生命 解約返戻金: 取得失敗 ({y.get('error') if isinstance(y, dict) else 'unknown'})")

    g = out["shiga_loan"]
    if isinstance(g, dict) and g.get("ok"):
        print(f"4. 滋賀銀行 ローン残高（合計）: {int(g['amount_jpy']):,}円")
        prods = g.get("products") if isinstance(g.get("products"), list) else []
        for item in prods:
            if not isinstance(item, dict):
                continue
            k = item.get("kind") or ""
            aj = item.get("amount_jpy")
            try:
                aj_i = int(aj)
            except Exception:
                aj_i = 0
            print(f"   - {k}: {aj_i:,}円")
        print(f"   - PDF: {g.get('pdf_path')}")
    else:
        print(f"4. 滋賀銀行 ローン残高: 取得失敗 ({g.get('error') if isinstance(g, dict) else 'unknown'})")

    pr = out["prudential_surrender"]
    if isinstance(pr, dict) and pr.get("skipped"):
        print(f"5. プルデンシャル生命 解約返戻金: {pr.get('reason') or 'スキップ'}")
    elif isinstance(pr, dict) and pr.get("ok"):
        print(f"5. プルデンシャル生命 解約返戻金（合計）: {int(pr['value_jpy']):,}円")
        pritems = pr.get("items") if isinstance(pr.get("items"), list) else []
        for item in pritems:
            if not isinstance(item, dict):
                continue
            ai = item.get("account_index") or ""
            u = item.get("username") or ""
            vj = item.get("value_jpy")
            try:
                vji = int(vj)
            except Exception:
                vji = 0
            print(f"   - アカウント{ai}（{u}）: {vji:,}円")
    else:
        print(f"5. プルデンシャル生命 解約返戻金: 取得失敗 ({pr.get('error') if isinstance(pr, dict) else 'unknown'})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
