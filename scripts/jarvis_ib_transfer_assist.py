#!/usr/bin/env python3
"""汎用 IB 送金アシスト（滋賀・京都）— Wave3。

東海労金と同型の最小ユーザー操作:
  Jarvis: ログイン・画面遷移・宛先ホワイトリスト照合・監査
  あなた: アプリ OTP／ワンタイムPWのみ

  python scripts/jarvis_ib_transfer_assist.py --bank shiga --preview
  python scripts/jarvis_ib_transfer_assist.py --bank kyoto --go --execute

設定: config/kurashift_ib_{shiga,kyoto}.yaml
秘密: SHIGA_IB_USER / SHIGA_IB_PASSWORD / SHIGA_IB_CONFIRM_PIN（任意）
      KYOTO_IB_USER / KYOTO_IB_PASSWORD

滋賀ログインPW失念: Web再設定不可。ヘルプデスク 0120-450-280（平日9–17）→ SMS eKYC →
会員カード郵送（1〜10日）。FAQ https://faq.shigagin.com/faq_detail.html?id=132
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import yaml
from playwright.sync_api import Page, sync_playwright

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from car_loan.chrome_cdp import start_cdp_chrome  # noqa: E402
from car_loan.env_state import load_env  # noqa: E402
from jarvis_transfer_audit import (  # noqa: E402
    TransferLock,
    append_audit,
    assert_balance_keep,
    dest_mask,
    make_idempotency_key,
)
from jarvis_transfer_otp import NeedsUserOtp, OtpFetchError, fetch_otp  # noqa: E402

BANKS: dict[str, dict[str, Any]] = {
    "shiga": {
        "rail_id": "shiga_smbc",
        "label": "滋賀銀行→SMBC刈谷",
        "amount_jpy": 62_000,
        "keep_floor_jpy": 300_000,
        "user_env": "SHIGA_IB_USER",
        "pass_env": "SHIGA_IB_PASSWORD",
        "confirm_pin_env": "SHIGA_IB_CONFIRM_PIN",
        "config": REPO / "config" / "kurashift_ib_shiga.yaml",
        "cdp_port": 9242,
        "profile": Path.home() / ".jarvis_state" / "chrome_ib_shiga",
        "otp_channel_default": "app_onetime_pw",
    },
    "kyoto": {
        "rail_id": "kyoto_smbc",
        "label": "京都銀行刈谷→SMBC刈谷",
        "amount_jpy": 50_000,
        "keep_floor_jpy": 51_000,
        "user_env": "KYOTO_IB_USER",
        "pass_env": "KYOTO_IB_PASSWORD",
        "config": REPO / "config" / "kurashift_ib_kyoto.yaml",
        "cdp_port": 9243,
        "profile": Path.home() / ".jarvis_state" / "chrome_ib_kyoto",
        "otp_channel_default": "app_onetime_pw",
    },
}


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def _load_cfg(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SystemExit(f"設定がありません: {path}（example をコピーしてください）")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _body(page: Page, n: int = 5000) -> str:
    try:
        return page.inner_text("body")[:n]
    except Exception:
        return ""


def _looks_otp(page: Page) -> bool:
    t = _body(page, 2000)
    return any(k in t for k in ("ワンタイム", "認証コード", "確認コード", "OTP", "スマート認証"))


def _wait_tty(prompt: str) -> str | None:
    print(prompt, flush=True)
    print("👉 アプリOTP入力後 Enter／またはコード1行（チャット禁止）", flush=True)
    try:
        with open("/dev/tty", "r", encoding="utf-8", errors="replace") as tty:
            line = tty.readline()
    except OSError:
        line = sys.stdin.readline()
    raw = (line or "").strip()
    if re.fullmatch(r"\d{4,8}", raw or ""):
        return raw
    return None


def _fill_login(page: Page, cfg: dict[str, Any], user: str, pw: str) -> None:
    url = cfg.get("login_url") or ""
    if not url:
        raise RuntimeError("login_url_missing")
    page.goto(url, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(1500)
    u_sels = cfg.get("username_selectors") or [
        "input[name*='user' i]",
        "input[id*='user' i]",
        "input[name*='login' i]",
        "input[type='text']",
    ]
    p_sels = cfg.get("password_selectors") or [
        "input[type='password']",
        "input[name*='pass' i]",
    ]
    for sel in u_sels:
        loc = page.locator(sel)
        if loc.count():
            loc.first.fill(user)
            break
    else:
        raise RuntimeError("username_field_not_found")
    for sel in p_sels:
        loc = page.locator(sel)
        if loc.count():
            loc.first.fill(pw)
            break
    else:
        raise RuntimeError("password_field_not_found")
    for name in cfg.get("login_button_names") or ["ログイン", "Login"]:
        btn = page.get_by_role("button", name=re.compile(name))
        if btn.count():
            btn.first.click()
            break
        link = page.get_by_role("link", name=re.compile(name))
        if link.count():
            link.first.click()
            break
    page.wait_for_load_state("domcontentloaded", timeout=90000)
    page.wait_for_timeout(2000)


def _fill_confirm_pin(page: Page, pin: str) -> bool:
    """振込実行画面の『確認用暗証番号』を埋める。"""
    if not pin:
        return False
    candidates = [
        page.get_by_label(re.compile(r"確認用暗証|暗証番号")),
        page.locator("input[name*='pin' i]"),
        page.locator("input[id*='pin' i]"),
        page.locator("input[name*='kakunin' i]"),
        page.locator("input[placeholder*='暗証' i]"),
    ]
    for loc in candidates:
        try:
            if loc.count():
                loc.first.fill(pin)
                print("📎 確認用暗証番号入力", file=sys.stderr)
                return True
        except Exception:
            continue
    body = _body(page, 4000)
    if "確認用暗証" in body or "暗証番号" in body:
        pw = page.locator("input[type='password']")
        try:
            if pw.count():
                pw.nth(pw.count() - 1).fill(pin)
                print("📎 確認用暗証番号入力（password末尾）", file=sys.stderr)
                return True
        except Exception:
            pass
    return False


def _handle_otp(page: Page, *, otp_channel: str, rail_id: str, hold: bool) -> str:
    if not _looks_otp(page):
        return "ok"
    if otp_channel in ("gmail_api", "sms_messages"):
        try:
            code = fetch_otp(
                otp_channel=otp_channel,
                rail_id=rail_id,
                sender_hint="滋賀|しがぎん|京都|京銀|認証|ワンタイム",
                timeout_sec=60,
            )
            if code:
                for sel in (
                    "input[autocomplete='one-time-code']",
                    "input[name*='otp' i]",
                    "input[type='tel']",
                    "input[type='password']",
                ):
                    loc = page.locator(sel)
                    if loc.count():
                        loc.first.fill(code)
                        break
                btn = page.get_by_role("button", name=re.compile("送信|認証|次へ|確認"))
                if btn.count():
                    btn.first.click()
                page.wait_for_timeout(1500)
                return "ok"
        except (NeedsUserOtp, OtpFetchError) as e:
            print(f"# otp_auto_skip {e}", file=sys.stderr)
    if not hold:
        return "needs_user"
    code = _wait_tty("⏳ ワンタイム／アプリ認証待ち…")
    if code:
        for sel in (
            "input[autocomplete='one-time-code']",
            "input[name*='otp' i]",
            "input[type='tel']",
            "input[type='password']",
        ):
            loc = page.locator(sel)
            if loc.count():
                loc.first.fill(code)
                break
        btn = page.get_by_role("button", name=re.compile("送信|認証|次へ|確認"))
        if btn.count():
            btn.first.click()
        page.wait_for_timeout(1500)
    return "ok"


def _goto_transfer(page: Page, cfg: dict[str, Any]) -> bool:
    for pat in cfg.get("transfer_link_patterns") or ["振込", "振替", "ことら"]:
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


def _amount_ok(page: Page, amount: int) -> bool:
    text = _body(page)
    digits = re.sub(r"[^\d]", "", text)
    return str(amount) in digits or f"{amount:,}" in text


def preview(bank: str, amount: int, money_ops_id: str, balance: int | None) -> str:
    meta = BANKS[bank]
    cfg_path = meta["config"]
    cfg = _load_cfg(cfg_path) if cfg_path.is_file() else {}
    branch = _env("PERSONAL_BANK_BRANCH_CODE")
    acct = _env("PERSONAL_BANK_ACCOUNT")
    dmask = dest_mask(acct, branch)
    key = make_idempotency_key(money_ops_id or "noid", meta["rail_id"], amount, dmask)
    print(f"=== 送金アシスト Preview ({meta['rail_id']}) / Wave3 ===")
    print(f"ラベル: {meta['label']}")
    print(f"ログイン: {cfg.get('login_url', '(config未作成)')}")
    print(f"金額: {amount:,}円 / keep下限目安: {meta['keep_floor_jpy']:,}円")
    print(f"宛先: 三井住友銀行 刈谷 普通 {dmask}")
    print("役割: Jarvis=ログイン〜照合・実行 / あなた=アプリOTPのみ")
    print(f"idempotency_key: {key}")
    if balance is not None:
        assert_balance_keep(balance, int(meta["keep_floor_jpy"]), amount)
        print("balance_keep: OK")
    append_audit(
        {
            "rail_id": meta["rail_id"],
            "status": "previewed",
            "amount_jpy": amount,
            "dest_mask": dmask,
            "otp_channel": cfg.get("otp_channel") or meta["otp_channel_default"],
            "money_ops_id": money_ops_id or None,
            "idempotency_key": key,
            "wave": "3",
        }
    )
    return key


def run_go(
    *,
    bank: str,
    amount: int,
    money_ops_id: str,
    balance: int | None,
    execute: bool,
    hold: bool,
) -> int:
    meta = BANKS[bank]
    cfg = _load_cfg(meta["config"])
    user = _env(meta["user_env"])
    pw = _env(meta["pass_env"])
    if not user or not pw:
        raise SystemExit(
            f"{meta['user_env']} / {meta['pass_env']} が未設定です。"
            " .env.jarvis_private に追記後『保存した』と一声ください。"
        )
    key = preview(bank, amount, money_ops_id, balance)
    branch = _env("PERSONAL_BANK_BRANCH_CODE")
    acct = _env("PERSONAL_BANK_ACCOUNT")
    dmask = dest_mask(acct, branch)
    otp_channel = cfg.get("otp_channel") or meta["otp_channel_default"]
    lock = TransferLock(key)
    if not lock.acquire():
        print("lock_busy", file=sys.stderr)
        return 3
    pw_api = None
    try:
        append_audit(
            {
                "rail_id": meta["rail_id"],
                "status": "running",
                "amount_jpy": amount,
                "dest_mask": dmask,
                "otp_channel": otp_channel,
                "money_ops_id": money_ops_id or None,
            }
        )
        start_cdp_chrome(
            port=int(meta["cdp_port"]),
            profile_dir=meta["profile"],
            start_url=cfg.get("login_url") or "about:blank",
        )
        pw_api = sync_playwright().start()
        browser = pw_api.chromium.connect_over_cdp(
            f"http://127.0.0.1:{meta['cdp_port']}"
        )
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        _fill_login(page, cfg, user, pw)
        st = _handle_otp(
            page, otp_channel=otp_channel, rail_id=meta["rail_id"], hold=hold
        )
        if st == "needs_user":
            append_audit(
                {
                    "rail_id": meta["rail_id"],
                    "status": "waiting_user",
                    "amount_jpy": amount,
                    "dest_mask": dmask,
                    "otp_channel": otp_channel,
                    "error": "awaiting_app_otp",
                }
            )
            print("📎 waiting_user: アプリOTP後に同コマンド再実行（--go）")
            return 2
        opened = _goto_transfer(page, cfg)
        print(f"📎 transfer_nav={'ok' if opened else 'manual'}")
        # 金額入力（見つかれば）
        for sel in ("input[name*='amount' i]", "input[id*='amount' i]", "input[type='tel']"):
            loc = page.locator(sel)
            if loc.count() and loc.first.is_visible():
                loc.first.fill(str(amount))
                print(f"📎 金額入力 {amount:,}")
                break
        btn = page.get_by_role("button", name=re.compile("次へ|確認"))
        if btn.count():
            btn.first.click()
            page.wait_for_timeout(1500)
        if _looks_otp(page):
            _handle_otp(page, otp_channel=otp_channel, rail_id=meta["rail_id"], hold=hold)
        if not _amount_ok(page, amount):
            print("⚠️ 金額照合不可 → 実行しません")
            append_audit(
                {
                    "rail_id": meta["rail_id"],
                    "status": "waiting_user",
                    "amount_jpy": amount,
                    "dest_mask": dmask,
                    "error": "amount_not_visible",
                }
            )
            return 2
        print("📎 金額照合 OK")
        if not execute:
            print("確認画面まで。実行は --execute")
            append_audit(
                {
                    "rail_id": meta["rail_id"],
                    "status": "waiting_user",
                    "amount_jpy": amount,
                    "dest_mask": dmask,
                    "error": "confirm_ready",
                }
            )
            return 0
        # 宛先ヒント
        text = _body(page)
        if "三井住友" not in text and "0009" not in text:
            print("宛先ヒント不一致のため実行しません", file=sys.stderr)
            append_audit(
                {
                    "rail_id": meta["rail_id"],
                    "status": "failed",
                    "amount_jpy": amount,
                    "dest_mask": dmask,
                    "error": "dest_hint_mismatch",
                }
            )
            return 1
        pin_env = meta.get("confirm_pin_env") or ""
        if pin_env:
            _fill_confirm_pin(page, _env(pin_env))
        exec_btn = page.get_by_role(
            "button", name=re.compile("実行|確定|振込する|申し込む")
        )
        if not exec_btn.count():
            print("実行ボタン未検出", file=sys.stderr)
            return 2
        exec_btn.first.click()
        append_audit(
            {
                "rail_id": meta["rail_id"],
                "status": "executing_click",
                "amount_jpy": amount,
                "dest_mask": dmask,
            }
        )
        page.wait_for_timeout(2500)
        if _looks_otp(page):
            _handle_otp(page, otp_channel=otp_channel, rail_id=meta["rail_id"], hold=hold)
        done = any(
            k in _body(page)
            for k in ("受け付けました", "完了", "受付番号", "お手続きが完了")
        )
        if done:
            append_audit(
                {
                    "rail_id": meta["rail_id"],
                    "status": "done",
                    "amount_jpy": amount,
                    "dest_mask": dmask,
                    "evidence": "completion_screen",
                }
            )
            print("✅ done")
            return 0
        append_audit(
            {
                "rail_id": meta["rail_id"],
                "status": "verifying",
                "amount_jpy": amount,
                "dest_mask": dmask,
            }
        )
        print("📎 verifying: 完了画面未検出。必要ならアプリ承認後に再確認")
        return 0
    finally:
        lock.release()
        if pw_api is not None:
            try:
                pw_api.stop()
            except Exception:
                pass


def main() -> int:
    load_env()
    p = argparse.ArgumentParser(description="滋賀・京都 IB 送金アシスト Wave3")
    p.add_argument("--bank", required=True, choices=sorted(BANKS.keys()))
    p.add_argument("--preview", action="store_true")
    p.add_argument("--go", action="store_true")
    p.add_argument("--execute", action="store_true")
    p.add_argument("--no-hold", action="store_true")
    p.add_argument("--money-ops-id", default="")
    p.add_argument("--amount", type=int, default=None)
    p.add_argument("--balance", type=int, default=None)
    args = p.parse_args()
    meta = BANKS[args.bank]
    amount = int(args.amount if args.amount is not None else meta["amount_jpy"])
    if args.preview and not args.go:
        preview(args.bank, amount, args.money_ops_id, args.balance)
        print("Preview のみ。次: --go [--execute]")
        return 0
    if args.go:
        return run_go(
            bank=args.bank,
            amount=amount,
            money_ops_id=args.money_ops_id,
            balance=args.balance,
            execute=args.execute,
            hold=not args.no_hold,
        )
    p.error("--preview または --go")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
