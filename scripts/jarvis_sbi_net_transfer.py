#!/usr/bin/env python3
"""ドコモSMTBネット銀行（旧住信SBIネット）→ SMBC刈谷 送金アシスト Wave1b。

最小ユーザー操作:
  Jarvis … ログイン / メール・SMS OTP / 振込入力 / 金額照合 / 実行クリック / 証跡
  ユーザー … スマート認証NEO・アプリ承認、および Jarvis が取れない OTP の提供のみ

  python scripts/jarvis_sbi_net_transfer.py --rail sbi_main_smbc --preview
  python scripts/jarvis_sbi_net_transfer.py --rail sbi_main_smbc --go --money-ops-id UUID
  # waiting_user 後（ブラウザは開いたまま）:
  python scripts/jarvis_sbi_net_transfer.py --rail sbi_main_smbc --resume --money-ops-id UUID

Terminal.app 必須。秘密は .env.jarvis_private の SBI_NET_*（証券と分離）。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, sync_playwright

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from car_loan.chrome_cdp import cdp_ready, start_cdp_chrome  # noqa: E402
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
SESSION_DIR = REPO / ".jarvis_state" / "transfer_session"
LOGIN_URL = "https://www.netbk.co.jp/contents/pages/wpl020601/i020601CT/DI02060100"
COTRA_LIMIT = 100_000
DEST_BANK = "0009"

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


def _session_path(rail_id: str) -> Path:
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    return SESSION_DIR / f"{rail_id}.json"


def _save_session(rail_id: str, data: dict[str, Any]) -> None:
    path = _session_path(rail_id)
    cur = {}
    if path.is_file():
        try:
            cur = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            cur = {}
    cur.update(data)
    cur["updated_at"] = time.time()
    # 秘密を書かない
    for banned in ("password", "otp", "code", "login_password"):
        cur.pop(banned, None)
    path.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_session(rail_id: str) -> dict[str, Any]:
    path = _session_path(rail_id)
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _body(page: Page, n: int = 8000) -> str:
    try:
        return page.inner_text("body")[:n]
    except Exception:
        return ""


def _looks_like_otp(page: Page) -> bool:
    t = _body(page, 2500)
    return any(k in t for k in ("ワンタイム", "認証コード", "確認コード", "パスコード", "OTP"))


def _looks_like_smart_auth(page: Page) -> bool:
    t = _body(page, 2500)
    return any(
        k in t for k in ("スマート認証", "NEO", "アプリで承認", "プッシュ通知", "生体認証", "承認してください")
    )


def _looks_like_done(page: Page) -> bool:
    t = _body(page, 4000)
    return any(
        k in t
        for k in (
            "振込を受け付けました",
            "ご依頼を受け付けました",
            "お手続きが完了",
            "送金が完了",
            "受付番号",
            "完了しました",
        )
    )


def _amount_visible(page: Page, amount: int) -> bool:
    text = _body(page)
    digits = re.sub(r"[^\d]", "", text)
    if str(amount) in digits:
        return True
    return f"{amount:,}" in text or f"{amount}" in text


def _dest_hints_visible(page: Page, branch: str, last4: str) -> bool:
    text = _body(page)
    ok_bank = ("三井住友" in text) or (DEST_BANK in text) or ("0009" in text)
    ok_br = (not branch) or (branch in text)
    ok_ac = (not last4) or (last4 in text)
    return ok_bank and (ok_br or ok_ac)


def _wait_user_handoff(*, prompt: str) -> str | None:
    """Terminal.app の /dev/tty で待機。

    Enter のみ → アプリ承認済みとして続行（OTPなし）
    数字行 → OTP として返す（ログに出さない）
    """
    print(prompt, flush=True)
    print(
        "👉 操作: (A) アプリ承認が終わったら Enter だけ"
        " / (B) Jarvis が取れない OTP ならコードを1行入力して Enter",
        flush=True,
    )
    try:
        with open("/dev/tty", "r", encoding="utf-8", errors="replace") as tty:
            line = tty.readline()
    except OSError:
        # フォールバック（Cursor 統合ターミナルでは Enter が壊れることがある）
        print("# /dev/tty 不可。stdin から読みます（Terminal.app 推奨）", file=sys.stderr)
        line = sys.stdin.readline()
    raw = (line or "").strip()
    if not raw:
        return None
    if re.fullmatch(r"\d{4,8}", raw):
        return raw
    print("# 数字以外は無視して承認済み扱いにします", file=sys.stderr)
    return None


def _fill_otp_code(page: Page, code: str) -> bool:
    otp_sels = (
        "input[autocomplete='one-time-code']",
        "input[name*='otp' i]",
        "input[id*='otp' i]",
        "input[name*='code' i]",
        "input[name*='pass' i]",
        "input[type='tel']",
        "input[type='password']",
    )
    for sel in otp_sels:
        loc = page.locator(sel)
        if loc.count():
            loc.first.fill(code)
            break
    else:
        return False
    for name in ("送信", "認証", "次へ", "確認", "OK"):
        btn = page.get_by_role("button", name=re.compile(name))
        if btn.count():
            btn.first.click()
            break
    page.wait_for_timeout(2000)
    return True


def _fill_login(page: Page, user: str, pw: str) -> None:
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(1500)
    user_sels = (
        "input[name*='user' i]",
        "input[id*='user' i]",
        "input[name*='loginId' i]",
        "input[type='text']",
    )
    pw_sels = ("input[type='password']", "input[name*='pass' i]", "input[id*='pass' i]")
    filled_u = filled_p = False
    for sel in user_sels:
        loc = page.locator(sel)
        if loc.count():
            loc.first.fill(user)
            filled_u = True
            break
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


def _try_otp_auto(page: Page, *, otp_channel: str, sender_hint: str) -> str:
    """ok | needs_user | failed"""
    if _looks_like_smart_auth(page) and not _looks_like_otp(page):
        return "needs_user"
    if not _looks_like_otp(page):
        return "ok"
    if otp_channel in ("app_onetime_pw", "passkey_or_bio"):
        return "needs_user"
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
        return "needs_user"  # Wave1b: 取れなければユーザー手渡しへ
    if not code:
        return "needs_user"
    return "ok" if _fill_otp_code(page, code) else "failed"


def _handle_user_gate(
    page: Page,
    *,
    rail_id: str,
    amount: int,
    dmask: str,
    money_ops_id: str,
    hold: bool,
) -> str:
    """needs_user ゲート。戻り値: ok | abort"""
    append_audit(
        {
            "rail_id": rail_id,
            "status": "waiting_user",
            "amount_jpy": amount,
            "dest_mask": dmask,
            "otp_channel": "passkey_or_bio",
            "otp_obtained": False,
            "money_ops_id": money_ops_id or None,
            "error": "awaiting_user_app_or_otp",
        }
    )
    _save_session(
        rail_id,
        {
            "phase": "waiting_user",
            "amount_jpy": amount,
            "dest_mask": dmask,
            "money_ops_id": money_ops_id,
            "cdp_port": CDP_PORT,
        },
    )
    print("📎 waiting_user（必要最小限の一手）")
    print("  - スマート認証NEO／アプリ承認 → 終わったら Enter")
    print("  - メール・SMS 以外でしか来ない OTP → コードを1行（チャットに貼らない）")
    if not hold:
        print("📎 --no-hold のため終了。承認後に --resume を実行してください。")
        return "abort"
    code = _wait_user_handoff(prompt="⏳ ユーザー操作待ち…")
    if code:
        if not _fill_otp_code(page, code):
            print("OTP 入力欄が見つかりません。画面で入力後 Enter で再待機します。", file=sys.stderr)
            _wait_user_handoff(prompt="⏳ 画面入力後 Enter…")
        else:
            append_audit(
                {
                    "rail_id": rail_id,
                    "status": "otp_submit",
                    "amount_jpy": amount,
                    "dest_mask": dmask,
                    "otp_channel": "user_provided",
                    "otp_obtained": True,
                    "money_ops_id": money_ops_id or None,
                }
            )
    page.wait_for_timeout(1500)
    return "ok"


def _goto_transfer_area(page: Page) -> bool:
    for pat in (r"ことら送金", r"振込・振替", r"^振込$", r"他行宛", r"振込"):
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


def _fill_amount_fields(page: Page, amount: int) -> bool:
    sels = (
        "input[name*='amount' i]",
        "input[id*='amount' i]",
        "input[name*='kingaku' i]",
        "input[name*='Amt' i]",
        "input[type='tel']",
        "input[inputmode='numeric']",
    )
    for sel in sels:
        loc = page.locator(sel)
        if not loc.count():
            continue
        for i in range(min(loc.count(), 4)):
            el = loc.nth(i)
            try:
                if not el.is_visible():
                    continue
                el.fill(str(amount))
                return True
            except Exception:
                continue
    return False


def _click_named(page: Page, names: tuple[str, ...]) -> bool:
    for name in names:
        btn = page.get_by_role("button", name=re.compile(name))
        if btn.count():
            btn.first.click()
            page.wait_for_timeout(1500)
            return True
        link = page.get_by_role("link", name=re.compile(name))
        if link.count():
            link.first.click()
            page.wait_for_timeout(1500)
            return True
    return False


def _try_execute_click(page: Page, *, amount: int, branch: str, last4: str) -> str:
    """clicked | blocked | not_found"""
    if not _amount_visible(page, amount):
        return "blocked"
    if not _dest_hints_visible(page, branch, last4):
        # 宛先がまだ確認画面に出ていない場合もあるので厳しめに止める
        return "blocked"
    if _click_named(
        page,
        ("実行する", "振込実行", "送金する", "^実行$", "確定", "申し込む"),
    ):
        return "clicked"
    return "not_found"


def _connect_page():
    start_cdp_chrome(port=CDP_PORT, profile_dir=PROFILE, start_url=LOGIN_URL)
    pw_api = sync_playwright().start()
    browser = pw_api.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
    ctx = browser.contexts[0] if browser.contexts else browser.new_context()
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    return pw_api, page


def _preview(rail_id: str, amount: int, money_ops_id: str, balance: int | None) -> str:
    branch = _env("PERSONAL_BANK_BRANCH_CODE")
    acct = _env("PERSONAL_BANK_ACCOUNT")
    dmask = dest_mask(acct, branch)
    key = make_idempotency_key(money_ops_id or "noid", rail_id, amount, dmask)
    parts = _split_cotra(amount)
    print(f"=== 送金アシスト Preview ({rail_id}) / Wave1b ===")
    print(f"ラベル: {RAILS[rail_id]['label']}")
    print(f"宛先: 三井住友銀行 刈谷 普通 {dmask}（銀行{DEST_BANK}）")
    print(f"金額: {amount:,}円 / keep下限目安: {RAILS[rail_id]['keep_floor_jpy']:,}円")
    if len(parts) > 1:
        print(f"ことら分割: {' + '.join(f'{p:,}' for p in parts)}（有料化しない）")
    else:
        print(f"ことら単発可: {amount:,}円")
    print("役割分担:")
    print("  Jarvis: ログイン・取得可能OTP・振込入力・照合・実行クリック・証跡")
    print("  あなた: アプリ承認／取れないOTPのみ（Terminal で Enter またはコード1行）")
    print(f"idempotency_key: {key}")
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
            "wave": "1b",
        }
    )
    _save_session(
        rail_id,
        {
            "phase": "previewed",
            "amount_jpy": amount,
            "dest_mask": dmask,
            "money_ops_id": money_ops_id,
            "idempotency_key": key,
        },
    )
    return key


def _post_auth_flow(
    page: Page,
    *,
    rail_id: str,
    amount: int,
    money_ops_id: str,
    dmask: str,
    branch: str,
    last4: str,
    chunk_amount: int,
    auto_execute: bool,
    hold: bool,
) -> int:
    if _looks_like_done(page):
        append_audit(
            {
                "rail_id": rail_id,
                "status": "done",
                "amount_jpy": amount,
                "dest_mask": dmask,
                "evidence": "completion_screen",
                "money_ops_id": money_ops_id or None,
            }
        )
        _save_session(rail_id, {"phase": "done", "evidence": "completion_screen"})
        print("✅ 完了画面を検出 → done（証跡: completion_screen）")
        return 0

    opened = _goto_transfer_area(page)
    print(f"📎 transfer_nav={'ok' if opened else 'manual_or_already'}")

    filled = _fill_amount_fields(page, chunk_amount)
    if filled:
        print(f"📎 金額入力: {chunk_amount:,}円")
        _click_named(page, ("次へ", "確認", "照会", "進む"))
    else:
        print("📎 金額欄を自動検出できません。画面で金額・宛先を合わせてください。")

    # 確認〜実行前に再度ユーザーゲートがあり得る
    if _looks_like_smart_auth(page) or (_looks_like_otp(page) and not filled):
        st = _handle_user_gate(
            page,
            rail_id=rail_id,
            amount=amount,
            dmask=dmask,
            money_ops_id=money_ops_id,
            hold=hold,
        )
        if st == "abort":
            return 2

    assert_amount_triple(amount if chunk_amount == amount else None, chunk_amount, None)
    if _amount_visible(page, chunk_amount):
        append_audit(
            {
                "rail_id": rail_id,
                "status": "verifying",
                "amount_jpy": chunk_amount,
                "dest_mask": dmask,
                "note": "amount_visible_on_page",
            }
        )
        print(f"📎 金額照合 OK（画面に {chunk_amount:,}）")
    else:
        print("⚠️ 画面に金額が見えません。照合できないため実行クリックはしません。")
        append_audit(
            {
                "rail_id": rail_id,
                "status": "waiting_user",
                "amount_jpy": chunk_amount,
                "dest_mask": dmask,
                "error": "amount_not_visible",
            }
        )
        _save_session(rail_id, {"phase": "waiting_user", "error": "amount_not_visible"})
        if hold:
            _wait_user_handoff(prompt="⏳ 確認画面まで進めたら Enter…")
        else:
            return 2

    if not auto_execute:
        print("📎 確認画面まで。実行は --execute（照合成功時のみ Jarvis がクリック）")
        _save_session(rail_id, {"phase": "confirm_ready"})
        append_audit(
            {
                "rail_id": rail_id,
                "status": "waiting_user",
                "amount_jpy": chunk_amount,
                "dest_mask": dmask,
                "error": "confirm_ready_await_execute_flag",
            }
        )
        return 0

    # 実行直前のアプリ承認
    if _looks_like_smart_auth(page):
        st = _handle_user_gate(
            page,
            rail_id=rail_id,
            amount=amount,
            dmask=dmask,
            money_ops_id=money_ops_id,
            hold=hold,
        )
        if st == "abort":
            return 2

    result = _try_execute_click(page, amount=chunk_amount, branch=branch, last4=last4)
    if result == "blocked":
        append_audit(
            {
                "rail_id": rail_id,
                "status": "failed",
                "amount_jpy": chunk_amount,
                "dest_mask": dmask,
                "error": "execute_blocked_amount_or_dest_mismatch",
            }
        )
        print("実行ブロック: 金額または宛先ヒントが画面と一致しません。", file=sys.stderr)
        return 1
    if result == "not_found":
        print("実行ボタンが見つかりません。画面のラベルを確認してください。", file=sys.stderr)
        append_audit(
            {
                "rail_id": rail_id,
                "status": "waiting_user",
                "amount_jpy": chunk_amount,
                "dest_mask": dmask,
                "error": "execute_button_not_found",
            }
        )
        return 2

    append_audit(
        {
            "rail_id": rail_id,
            "status": "executing_click",
            "amount_jpy": chunk_amount,
            "dest_mask": dmask,
            "money_ops_id": money_ops_id or None,
        }
    )
    page.wait_for_timeout(2500)

    # 実行後もアプリ承認が挟まることがある
    if _looks_like_smart_auth(page) or _looks_like_otp(page):
        st = _handle_user_gate(
            page,
            rail_id=rail_id,
            amount=amount,
            dmask=dmask,
            money_ops_id=money_ops_id,
            hold=hold,
        )
        if st == "abort":
            return 2
        page.wait_for_timeout(2000)

    if _looks_like_done(page):
        append_audit(
            {
                "rail_id": rail_id,
                "status": "done",
                "amount_jpy": chunk_amount,
                "dest_mask": dmask,
                "evidence": "completion_screen",
                "money_ops_id": money_ops_id or None,
            }
        )
        _save_session(rail_id, {"phase": "done", "evidence": "completion_screen"})
        print("✅ done（証跡: completion_screen）")
        return 0

    append_audit(
        {
            "rail_id": rail_id,
            "status": "verifying",
            "amount_jpy": chunk_amount,
            "dest_mask": dmask,
            "error": "awaiting_completion_evidence",
        }
    )
    _save_session(rail_id, {"phase": "verifying"})
    print("📎 verifying: 完了画面未検出。アプリ承認後に --resume で証跡確認してください。")
    return 0


def run_go(
    *,
    rail_id: str,
    amount: int,
    money_ops_id: str,
    balance: int | None,
    otp_channel: str,
    auto_execute: bool,
    hold: bool,
    chunk_index: int,
) -> int:
    user, pw = _require_creds()
    key = _preview(rail_id, amount, money_ops_id, balance)
    branch = _env("PERSONAL_BANK_BRANCH_CODE")
    acct = _env("PERSONAL_BANK_ACCOUNT")
    dmask = dest_mask(acct, branch)
    last4 = acct[-4:] if len(acct) >= 4 else ""
    parts = _split_cotra(amount)
    chunk_amount = parts[min(chunk_index, len(parts) - 1)]
    assert_amount_triple(amount if len(parts) == 1 else None, chunk_amount, None)

    lock = TransferLock(key if len(parts) == 1 else f"{key}:part{chunk_index}")
    if not lock.acquire():
        print("lock_busy", file=sys.stderr)
        return 3
    pw_api = None
    try:
        append_audit(
            {
                "rail_id": rail_id,
                "status": "running",
                "amount_jpy": chunk_amount,
                "dest_mask": dmask,
                "otp_channel": otp_channel,
                "money_ops_id": money_ops_id or None,
                "idempotency_key": key,
                "cotra_part": chunk_index,
                "cotra_parts": parts,
            }
        )
        pw_api, page = _connect_page()
        _fill_login(page, user, pw)
        otp_st = _try_otp_auto(
            page,
            otp_channel=otp_channel,
            sender_hint="ドコモSMTB|住信SBI|ネット銀行|NEOBANK|netbk",
        )
        if otp_st == "needs_user" or _looks_like_smart_auth(page):
            st = _handle_user_gate(
                page,
                rail_id=rail_id,
                amount=amount,
                dmask=dmask,
                money_ops_id=money_ops_id,
                hold=hold,
            )
            if st == "abort":
                return 2
        elif otp_st == "failed":
            append_audit(
                {
                    "rail_id": rail_id,
                    "status": "failed",
                    "amount_jpy": amount,
                    "dest_mask": dmask,
                    "error": "otp_fill_failed",
                }
            )
            return 1
        else:
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

        return _post_auth_flow(
            page,
            rail_id=rail_id,
            amount=amount,
            money_ops_id=money_ops_id,
            dmask=dmask,
            branch=branch,
            last4=last4,
            chunk_amount=chunk_amount,
            auto_execute=auto_execute,
            hold=hold,
        )
    finally:
        lock.release()
        if pw_api is not None:
            try:
                pw_api.stop()
            except Exception:
                pass


def run_resume(
    *,
    rail_id: str,
    amount: int,
    money_ops_id: str,
    otp_channel: str,
    auto_execute: bool,
    hold: bool,
    chunk_index: int,
) -> int:
    sess = _load_session(rail_id)
    branch = _env("PERSONAL_BANK_BRANCH_CODE")
    acct = _env("PERSONAL_BANK_ACCOUNT")
    dmask = dest_mask(acct, branch)
    last4 = acct[-4:] if len(acct) >= 4 else ""
    parts = _split_cotra(amount)
    chunk_amount = parts[min(chunk_index, len(parts) - 1)]
    if not cdp_ready(CDP_PORT):
        print(
            "CDP Chrome がありません。先に --go で起動するか、プロファイルを開いてください。",
            file=sys.stderr,
        )
        return 1
    print(f"📎 resume phase={sess.get('phase')} amount={chunk_amount}")
    append_audit(
        {
            "rail_id": rail_id,
            "status": "running",
            "amount_jpy": chunk_amount,
            "dest_mask": dmask,
            "note": "resume",
            "money_ops_id": money_ops_id or sess.get("money_ops_id"),
        }
    )
    pw_api = None
    try:
        pw_api, page = _connect_page()
        if _looks_like_otp(page) or _looks_like_smart_auth(page):
            # 自動再試行 → ダメならユーザー
            st_auto = _try_otp_auto(
                page,
                otp_channel=otp_channel,
                sender_hint="ドコモSMTB|住信SBI|ネット銀行|NEOBANK|netbk",
            )
            if st_auto != "ok":
                st = _handle_user_gate(
                    page,
                    rail_id=rail_id,
                    amount=amount,
                    dmask=dmask,
                    money_ops_id=money_ops_id or str(sess.get("money_ops_id") or ""),
                    hold=hold,
                )
                if st == "abort":
                    return 2
        return _post_auth_flow(
            page,
            rail_id=rail_id,
            amount=amount,
            money_ops_id=money_ops_id or str(sess.get("money_ops_id") or ""),
            dmask=dmask,
            branch=branch,
            last4=last4,
            chunk_amount=chunk_amount,
            auto_execute=auto_execute,
            hold=hold,
        )
    finally:
        if pw_api is not None:
            try:
                pw_api.stop()
            except Exception:
                pass


def main() -> int:
    load_env()
    p = argparse.ArgumentParser(description="SBIネット→SMBC Wave1b（最小ユーザー操作）")
    p.add_argument("--rail", required=True, choices=sorted(RAILS.keys()))
    p.add_argument("--preview", action="store_true")
    p.add_argument("--go", action="store_true")
    p.add_argument("--resume", action="store_true", help="waiting_user 後に続行")
    p.add_argument("--money-ops-id", default="")
    p.add_argument("--amount", type=int, default=None)
    p.add_argument("--balance", type=int, default=None)
    p.add_argument("--otp-channel", default="gmail_api")
    p.add_argument(
        "--execute",
        action="store_true",
        help="金額・宛先照合OKなら実行ボタンをクリック",
    )
    p.add_argument(
        "--no-hold",
        action="store_true",
        help="ユーザー待ちでプロセスを終え、後で --resume",
    )
    p.add_argument(
        "--chunk",
        type=int,
        default=0,
        help="ことら分割の何件目か（0始まり。副161kは 0=100k, 1=61k）",
    )
    args = p.parse_args()
    if not (args.preview or args.go or args.resume):
        p.error("--preview / --go / --resume のいずれかが必要です")
    meta = RAILS[args.rail]
    amount = int(args.amount if args.amount is not None else meta["amount_jpy"])
    hold = not args.no_hold
    if args.preview and not args.go and not args.resume:
        _preview(args.rail, amount, args.money_ops_id, args.balance)
        print("Preview のみ終了。次: --go （実行クリックまで進めるなら --execute）")
        return 0
    if args.resume:
        return run_resume(
            rail_id=args.rail,
            amount=amount,
            money_ops_id=args.money_ops_id,
            otp_channel=args.otp_channel,
            auto_execute=args.execute,
            hold=hold,
            chunk_index=args.chunk,
        )
    return run_go(
        rail_id=args.rail,
        amount=amount,
        money_ops_id=args.money_ops_id,
        balance=args.balance,
        otp_channel=args.otp_channel,
        auto_execute=args.execute,
        hold=hold,
        chunk_index=args.chunk,
    )


if __name__ == "__main__":
    raise SystemExit(main())
