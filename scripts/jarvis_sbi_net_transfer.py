#!/usr/bin/env python3
"""ドコモSMTBネット銀行（旧住信SBIネット）→ SMBC刈谷 送金アシスト Wave1。

プロトコル: Preview → Go / Terminal.app / 承認≠記帳
秘密: .env.jarvis_private の SBI_NET_*（証券 SBI_SEC_* と分離）

  # Previewのみ
  python scripts/jarvis_sbi_net_transfer.py --rail sbi_main_smbc --preview
  # ログイン〜振込画面（実行クリック既定オフ）
  python scripts/jarvis_sbi_net_transfer.py --rail sbi_main_smbc --go --money-ops-id UUID

ことら無料はおおむね1件10万まで。161k は分割（100k+61k）を提案する。
スマート認証NEO／アプリ承認が必要な場合は waiting_user。
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, sync_playwright

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from car_loan.chrome_cdp import start_cdp_chrome  # noqa: E402
from car_loan.env_state import load_env  # noqa: E402
from jarvis_transfer_audit import (  # noqa: E402
    TransferLock,
    append_audit,
    assert_amount_triple,
    assert_balance_keep,
    dest_mask,
    make_idempotency_key,
)
from jarvis_transfer_otp import NeedsUserOtp, OtpFetchError, fetch_otp  # noqa: E402

CDP_PORT = 9241
PROFILE = Path.home() / ".jarvis_state" / "chrome_sbi_net_transfer"
LOGIN_URL = "https://www.netbk.co.jp/contents/pages/wpl020601/i020601CT/DI02060100"
COTRA_LIMIT = 100_000

RAILS: dict[str, dict[str, Any]] = {
    "sbi_main_smbc": {
        "amount_jpy": 26_000,
        "keep_floor_jpy": 500_800,
        "from_account_id": "sbi_net_main",
        "label": "住信SBI本→SMBC刈谷",
        "account_hint_env": "SBI_NET_MAIN_ACCOUNT",
    },
    "sbi_sub_smbc": {
        "amount_jpy": 161_000,
        "keep_floor_jpy": 81_000,
        "from_account_id": "sbi_net_sub",
        "label": "住信SBI副→SMBC刈谷",
        "account_hint_env": "SBI_NET_SUB_ACCOUNT",
    },
}


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def _require_creds() -> tuple[str, str]:
    user = _env("SBI_NET_USER")
    pw = _env("SBI_NET_LOGIN_PASSWORD")
    if not user or not pw:
        raise SystemExit(
            "SBI_NET_USER / SBI_NET_LOGIN_PASSWORD が未設定です。"
            " .env.jarvis_private に追記してください（証券 SBI_SEC_* とは別）。"
            " 追記後『保存した』と一声ください。"
        )
    return user, pw


def _split_cotra(amount: int) -> list[int]:
    if amount <= COTRA_LIMIT:
        return [amount]
    parts: list[int] = []
    left = amount
    while left > 0:
        chunk = min(COTRA_LIMIT, left)
        parts.append(chunk)
        left -= chunk
    return parts


def _body(page: Page, n: int = 6000) -> str:
    try:
        return page.inner_text("body")[:n]
    except Exception:
        return ""


def _looks_like_otp(page: Page) -> bool:
    t = _body(page, 2500)
    keys = ("ワンタイム", "認証コード", "確認コード", "パスコード", "OTP")
    return any(k in t for k in keys)


def _looks_like_smart_auth(page: Page) -> bool:
    t = _body(page, 2500)
    keys = ("スマート認証", "NEO", "アプリで承認", "プッシュ通知", "生体認証")
    return any(k in t for k in keys)


def _fill_login(page: Page, user: str, pw: str) -> None:
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(1500)
    # フィールドは世代で変わるため広めに当てる
    user_sels = (
        "input[name*='user' i]",
        "input[id*='user' i]",
        "input[name*='loginId' i]",
        "input[type='text']",
    )
    pw_sels = (
        "input[type='password']",
        "input[name*='pass' i]",
        "input[id*='pass' i]",
    )
    filled_u = False
    for sel in user_sels:
        loc = page.locator(sel)
        if loc.count():
            loc.first.fill(user)
            filled_u = True
            break
    filled_p = False
    for sel in pw_sels:
        loc = page.locator(sel)
        if loc.count():
            loc.first.fill(pw)
            filled_p = True
            break
    if not (filled_u and filled_p):
        raise RuntimeError("login_fields_not_found")
    for name in ("ログイン", "Login"):
        btn = page.get_by_role("button", name=name)
        if btn.count():
            btn.first.click()
            break
        link = page.get_by_role("link", name=name)
        if link.count():
            link.first.click()
            break
    page.wait_for_load_state("domcontentloaded", timeout=90000)
    page.wait_for_timeout(2000)


def _try_otp(page: Page, *, otp_channel: str, sender_hint: str) -> str:
    """ok | needs_user | failed"""
    if _looks_like_smart_auth(page) and not _looks_like_otp(page):
        return "needs_user"
    if not _looks_like_otp(page):
        return "ok"
    try:
        code = fetch_otp(
            otp_channel=otp_channel,
            rail_id="sbi_net",
            sender_hint=sender_hint,
            gmail_account=_env("SBI_NET_GMAIL_ACCOUNT") or "m19m",
            after_ms=int(time.time() * 1000) - 60_000,
            timeout_sec=90,
        )
    except NeedsUserOtp:
        return "needs_user"
    except OtpFetchError as e:
        print(f"# otp_fetch_failed reason={e}", file=sys.stderr)
        return "failed"
    if not code:
        return "failed"
    otp_sels = (
        "input[autocomplete='one-time-code']",
        "input[name*='otp' i]",
        "input[id*='otp' i]",
        "input[name*='code' i]",
        "input[type='tel']",
    )
    for sel in otp_sels:
        loc = page.locator(sel)
        if loc.count():
            loc.first.fill(code)
            break
    else:
        return "failed"
    for name in ("送信", "認証", "次へ", "確認"):
        btn = page.get_by_role("button", name=re.compile(name))
        if btn.count():
            btn.first.click()
            break
    page.wait_for_timeout(2000)
    return "ok"


def _goto_transfer_area(page: Page) -> bool:
    body = _body(page)
    if "振込" in body or "ことら" in body:
        for pat in (r"^振込$", r"振込・振替", r"ことら送金", r"他行宛"):
            loc = page.get_by_role("link", name=re.compile(pat))
            if loc.count():
                loc.first.click()
                page.wait_for_timeout(2000)
                return True
            btn = page.get_by_role("button", name=re.compile(pat))
            if btn.count():
                btn.first.click()
                page.wait_for_timeout(2000)
                return True
    return False


def _preview(rail_id: str, amount: int, money_ops_id: str, balance: int | None) -> str:
    branch = _env("PERSONAL_BANK_BRANCH_CODE")
    acct = _env("PERSONAL_BANK_ACCOUNT")
    dmask = dest_mask(acct, branch)
    key = make_idempotency_key(money_ops_id or "noid", rail_id, amount, dmask)
    parts = _split_cotra(amount)
    print(f"=== 送金アシスト Preview ({rail_id}) ===")
    print(f"ラベル: {RAILS[rail_id]['label']}")
    print(f"宛先: 三井住友銀行 刈谷 普通 {dmask}（銀行0009）")
    print(f"金額: {amount:,}円 / keep下限目安: {RAILS[rail_id]['keep_floor_jpy']:,}円")
    if len(parts) > 1:
        print(
            f"ことら分割提案: {' + '.join(f'{p:,}' for p in parts)} "
            f"（1件≤{COTRA_LIMIT:,}）※有料化しない"
        )
    else:
        print(f"ことら単発可: {amount:,}円（≤{COTRA_LIMIT:,}）")
    print("OTP想定: メール/SMS→Jarvis / スマート認証NEO・アプリ承認→ユーザー")
    print(f"idempotency_key: {key}")
    print("実行環境: Terminal.app 必須 / CDP Chrome headed")
    if balance is not None:
        assert_balance_keep(balance, int(RAILS[rail_id]["keep_floor_jpy"]), amount)
        print("balance_keep: OK")
    append_audit(
        {
            "rail_id": rail_id,
            "status": "previewed",
            "amount_jpy": amount,
            "dest_mask": dmask,
            "otp_channel": "gmail_api",
            "money_ops_id": money_ops_id or None,
            "idempotency_key": key,
            "cotra_parts": parts,
        }
    )
    return key


def run_go(
    *,
    rail_id: str,
    amount: int,
    money_ops_id: str,
    balance: int | None,
    otp_channel: str,
    stop_at_confirm: bool,
    confirm_execute: bool,
) -> int:
    user, pw = _require_creds()
    key = _preview(rail_id, amount, money_ops_id, balance)
    branch = _env("PERSONAL_BANK_BRANCH_CODE")
    acct = _env("PERSONAL_BANK_ACCOUNT")
    dmask = dest_mask(acct, branch)
    assert_amount_triple(amount, amount, None)

    lock = TransferLock(key)
    if not lock.acquire():
        print("lock_busy: 同一レールが実行中です", file=sys.stderr)
        return 3
    try:
        append_audit(
            {
                "rail_id": rail_id,
                "status": "running",
                "amount_jpy": amount,
                "dest_mask": dmask,
                "otp_channel": otp_channel,
                "money_ops_id": money_ops_id or None,
                "idempotency_key": key,
            }
        )
        start_cdp_chrome(port=CDP_PORT, profile_dir=PROFILE, start_url=LOGIN_URL)
        with sync_playwright() as pw_api:
            browser = pw_api.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
            ctx = browser.contexts[0] if browser.contexts else browser.new_context()
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            _fill_login(page, user, pw)
            otp_st = _try_otp(
                page,
                otp_channel=otp_channel,
                sender_hint="ドコモSMTB|住信SBI|ネット銀行|NEOBANK|netbk",
            )
            if otp_st == "needs_user" or _looks_like_smart_auth(page):
                append_audit(
                    {
                        "rail_id": rail_id,
                        "status": "waiting_user",
                        "amount_jpy": amount,
                        "dest_mask": dmask,
                        "otp_channel": "passkey_or_bio",
                        "otp_obtained": False,
                        "money_ops_id": money_ops_id or None,
                        "error": "awaiting_smart_auth_neo_or_app",
                    }
                )
                print(
                    "📎 waiting_user: スマート認証NEO／アプリ承認を Chrome/アプリで完了してください。"
                    " 完了後、振込画面まで進んだら証跡を確認して rails status を更新します。"
                )
                print("（ブラウザは開いたまま。このプロセスは待機終了します）")
                return 2
            if otp_st == "failed":
                append_audit(
                    {
                        "rail_id": rail_id,
                        "status": "failed",
                        "amount_jpy": amount,
                        "dest_mask": dmask,
                        "otp_channel": otp_channel,
                        "otp_obtained": False,
                        "error": "otp_fetch_or_fill_failed",
                    }
                )
                return 1

            append_audit(
                {
                    "rail_id": rail_id,
                    "status": "otp_submit",
                    "amount_jpy": amount,
                    "dest_mask": dmask,
                    "otp_channel": otp_channel,
                    "otp_obtained": True,
                }
            )
            opened = _goto_transfer_area(page)
            parts = _split_cotra(amount)
            print(f"📎 transfer_nav={'ok' if opened else 'manual'} body_snip={_body(page, 400)!r}")
            print(
                "次の手: 画面で宛先=SMBC刈谷・金額照合。"
                f" ことら分割={parts}。"
                " 実行クリックは照合OKかつ --confirm-execute のときのみ（既定オフ）。"
            )
            if stop_at_confirm and not confirm_execute:
                append_audit(
                    {
                        "rail_id": rail_id,
                        "status": "waiting_user",
                        "amount_jpy": amount,
                        "dest_mask": dmask,
                        "otp_channel": otp_channel,
                        "error": "stop_at_confirm_no_execute",
                    }
                )
                print("📎 stop_at_confirm: 実行ボタンは押していません（資金未移動）。")
                return 0
            if confirm_execute:
                # 安全弁: DOM 金額一致が取れない限り押さない
                text = _body(page)
                amount_ok = (
                    f"{amount:,}" in text
                    or f"{amount}" in text
                    or str(amount) in re.sub(r"[^\d]", "", text)
                )
                if not amount_ok:
                    append_audit(
                        {
                            "rail_id": rail_id,
                            "status": "failed",
                            "amount_jpy": amount,
                            "dest_mask": dmask,
                            "error": "confirm_amount_not_found_in_dom",
                        }
                    )
                    print("金額照合失敗のため実行しません。", file=sys.stderr)
                    return 1
                append_audit(
                    {
                        "rail_id": rail_id,
                        "status": "executing_click",
                        "amount_jpy": amount,
                        "dest_mask": dmask,
                        "note": "confirm_execute_requested_but_click_not_automated_wave1",
                    }
                )
                print(
                    "Wave1: 実行ボタンの自動押下はまだ実装していません。"
                    " 照合OKなら画面でユーザーが実行／アプリ承認してください。"
                )
                return 0
        return 0
    finally:
        lock.release()


def main() -> int:
    load_env()
    p = argparse.ArgumentParser(description="SBIネット→SMBC 送金アシスト Wave1")
    p.add_argument("--rail", required=True, choices=sorted(RAILS.keys()))
    p.add_argument("--preview", action="store_true")
    p.add_argument("--go", action="store_true")
    p.add_argument("--money-ops-id", default="")
    p.add_argument("--amount", type=int, default=None)
    p.add_argument("--balance", type=int, default=None)
    p.add_argument(
        "--otp-channel",
        default="gmail_api",
        choices=["gmail_api", "sms_messages", "app_onetime_pw", "passkey_or_bio"],
    )
    p.add_argument(
        "--confirm-execute",
        action="store_true",
        help="確認画面で実行まで進める意図（Wave1は自動クリック未実装・照合のみ）",
    )
    args = p.parse_args()
    if not args.preview and not args.go:
        p.error("--preview または --go が必要です")
    meta = RAILS[args.rail]
    amount = int(args.amount if args.amount is not None else meta["amount_jpy"])
    if args.preview and not args.go:
        _preview(args.rail, amount, args.money_ops_id, args.balance)
        print("Preview のみ終了。実行するときは --go を付けて再実行してください。")
        return 0
    return run_go(
        rail_id=args.rail,
        amount=amount,
        money_ops_id=args.money_ops_id,
        balance=args.balance,
        otp_channel=args.otp_channel,
        stop_at_confirm=True,
        confirm_execute=args.confirm_execute,
    )


if __name__ == "__main__":
    raise SystemExit(main())
