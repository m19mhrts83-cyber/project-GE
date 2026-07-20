#!/usr/bin/env python3
"""SBI証券 クレカ登録 → Vpass「ログインカードの確認」まで（Google Chrome + CDP）。

Cursor 内蔵ブラウザで Vpass E01 になる場合、通常 Chrome で試す用。
既定: カード選択画面まで自動 → 「次へ進む」は手動。

  ~/git-repos/scripts/jarvis_sbi_card_vpass.py
  ~/git-repos/scripts/jarvis_sbi_card_vpass.py --open   # 通常 Chrome で URL のみ
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout, sync_playwright

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from car_loan.chrome_cdp import cdp_ready, open_in_chrome, start_cdp_chrome  # noqa: E402
from car_loan.env_state import ENV_FILE, load_env  # noqa: E402

CDP_PORT = 9224
PROFILE = Path.home() / ".jarvis_state" / "chrome_sbi_card"
CARD_SUMMARY = (
    "https://site2.sbisec.co.jp/ETGate/?_ControlID=WPLETsmR001Control"
    "&_PageID=WPLETsmR001Sdtl12&_DataStoreID=DSWPLETsmR001Control"
    "&OutSide=on&getFlg=on&sw_page=WNS001&sw_param1=trade&sw_param2=fund"
    "&sw_param3=reserve&sw_param4=cardSummary"
)
SBI_LOGIN = (
    "https://login.sbisec.co.jp/login/entry"
    "?_ReturnPageInfo=WPLETsmR001Control%2FWPLETsmR001Sdtl12%2FNoActionID%2FDSWPLETsmR001Control"
    "&_ALLPARAM_JSON=%7B%22cat2%22%3A%22none%22%2C%22getFlg%22%3A%22on%22%2C%22sw_param2%22%3A%22fund%22"
    "%2C%22sw_param3%22%3A%22reserve%22%2C%22cat1%22%3A%22home%22%2C%22sw_page%22%3A%22WNS001%22"
    "%2C%22sw_param4%22%3A%22cardSummary%22%2C%22sw_param1%22%3A%22trade%22%7D"
    "&eventCode=&channel=main-site-user"
)


def _find_page(ctx, pattern: str) -> Page | None:
    for p in ctx.pages:
        if re.search(pattern, p.url):
            return p
    return None


def _wait_vpass_page(ctx, timeout_sec: float = 45) -> Page:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        p = _find_page(ctx, r"smbc-card\.com/memx/tkauth")
        if p:
            return p
        time.sleep(0.5)
    raise TimeoutError("Vpass ページが開きませんでした")


def _sbi_login_if_needed(page: Page, user: str, login_pw: str) -> None:
    if "login.sbisec.co.jp" not in page.url:
        return
    page.wait_for_load_state("domcontentloaded", timeout=60000)
    user_loc = page.locator("input[name='username']")
    if user_loc.count():
        user_loc.first.fill(user)
        page.locator("input[name='password']").first.fill(login_pw)
    else:
        inputs = page.locator("input[type='text'], input:not([type])")
        if inputs.count() >= 1:
            inputs.first.fill(user)
        pw = page.locator("input[type='password']")
        if pw.count() >= 1:
            pw.first.fill(login_pw)
    page.get_by_role("button", name="ログイン", exact=True).click()
    page.wait_for_load_state("domcontentloaded", timeout=60000)
    time.sleep(2)


def _goto_card_summary(page: Page) -> None:
    page.goto(CARD_SUMMARY, wait_until="domcontentloaded", timeout=90000)
    time.sleep(2)
    if "login.sbisec.co.jp" in page.url:
        raise RuntimeError("cardSummary 遷移でログイン画面に戻りました")
    if "cardSummary" not in page.url and "cardregister" not in page.url:
        page.goto(
            "https://site0.sbisec.co.jp/marble/trade/fund/reserve/cardSummary.do?",
            wait_until="domcontentloaded",
            timeout=90000,
        )
        time.sleep(2)


def _start_card_register(page: Page) -> None:
    btn = page.get_by_role("button", name="カードを登録する")
    if btn.count() == 0:
        btn = page.get_by_role("link", name="カードを登録する")
    btn.first.click()
    page.wait_for_url(re.compile(r"agreementInit\.do"), timeout=60000)


def _agreement_to_vpass(page: Page, trade_pw: str) -> None:
    page.locator("#agree").check(force=True)
    page.locator("#trade-password").fill(trade_pw)
    page.locator("#btnAgree").click()


def _vpass_login(vpass: Page, vpass_id: str, vpass_pw: str) -> None:
    vpass.wait_for_load_state("domcontentloaded", timeout=60000)
    if "index2.html" in vpass.url:
        return
    id_box = vpass.locator("input[type='text'], input:not([type])").first
    id_box.fill(vpass_id)
    vpass.locator("input[type='password']").first.fill(vpass_pw)
    vpass.get_by_role("button", name="ログイン", exact=True).click()
    vpass.wait_for_load_state("domcontentloaded", timeout=60000)
    time.sleep(2)


def _wait_card_select(vpass: Page) -> None:
    deadline = time.time() + 60
    while time.time() < deadline:
        if "index2.html" in vpass.url and "error" not in vpass.url:
            body = vpass.inner_text("body")[:500]
            if "ログインカードの確認" in body:
                return
        if "error" in vpass.url:
            raise RuntimeError(f"Vpass エラー画面: {vpass.url}")
        time.sleep(0.5)
    raise TimeoutError(f"ログインカードの確認に到達できません: {vpass.url}")


def _select_olive_inf(vpass: Page) -> None:
    sel = vpass.locator("select").first
    if sel.count() == 0:
        return
    opts = sel.locator("option").all_inner_texts()
    target = next((o for o in opts if "ＩＮＦ" in o or "INF" in o), None)
    if target:
        sel.select_option(label=target)


def run_flow(wait_sec: int, port: int) -> int:
    env = load_env(ENV_FILE)
    user = env.get("SBI_SEC_USER", "")
    login_pw = env.get("SBI_SEC_LOGIN_PASSWORD", "")
    trade_pw = env.get("SBI_SEC_TRADE_PASSWORD", "")
    vpass_id = env.get("VPASS_ID", "")
    vpass_pw = env.get("VPASS_PASSWORD", "")

    missing = [
        k
        for k, v in [
            ("SBI_SEC_USER", user),
            ("SBI_SEC_LOGIN_PASSWORD", login_pw),
            ("SBI_SEC_TRADE_PASSWORD", trade_pw),
            ("VPASS_ID", vpass_id),
            ("VPASS_PASSWORD", vpass_pw),
        ]
        if not v
    ]
    if missing:
        print(f"未設定: {', '.join(missing)} (.env.jarvis_private)", file=sys.stderr)
        return 1

    start_cdp_chrome(port, PROFILE, SBI_LOGIN)

    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        ctx = browser.contexts[0] if browser.contexts else browser.new_context(locale="ja-JP")
        page = ctx.new_page()
        page.goto(SBI_LOGIN, wait_until="domcontentloaded", timeout=90000)

        print("📎 SBI ログイン…")
        _sbi_login_if_needed(page, user, login_pw)
        time.sleep(3)
        print(f"📎 現在: {page.url[:100]}…")

        print("📎 ログイン送信済み。OTP・追加認証があれば Chrome で入力してください（最大5分待機）…")
        deadline = time.time() + 300
        while time.time() < deadline and "login.sbisec.co.jp" in page.url:
            time.sleep(2)
        if "login.sbisec.co.jp" in page.url:
            print("⚠️ まだログイン画面です。Chrome でログイン完了後、同コマンドを再実行してください。")
            print(f"   CDP Chrome は port {port} で起動中です。")
            time.sleep(wait_sec)
            return 0

        print("📎 クレジットカード管理へ…")
        _goto_card_summary(page)
        print("📎 カードを登録する…")
        _start_card_register(page)

        print("📎 規約同意 → Vpass へ…")
        _agreement_to_vpass(page, trade_pw)
        vpass = _wait_vpass_page(ctx)
        print(f"📎 Vpass: {vpass.url}")

        print("📎 Vpass ログイン…")
        _vpass_login(vpass, vpass_id, vpass_pw)
        _wait_card_select(vpass)
        _select_olive_inf(vpass)

        print("")
        print("=" * 60)
        print("✅ Google Chrome — 「ログインカードの確認」表示済み")
        print("   Ｏｌｉｖｅ INF を選び 【次へ進む】 を手動でクリックしてください")
        print(f"   この Chrome は {wait_sec} 秒間開いたままです（port {port}）")
        print("=" * 60)
        time.sleep(wait_sec)

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="SBI クレカ登録 → Vpass カード選択（Chrome）")
    parser.add_argument("--open", action="store_true", help="通常 Chrome でログインURLのみ開く")
    parser.add_argument("--port", type=int, default=CDP_PORT)
    parser.add_argument("--wait-sec", type=int, default=600, help="カード選択後の待機秒")
    args = parser.parse_args()

    if args.open:
        open_in_chrome(SBI_LOGIN)
        print("📎 ログイン後: 入出金 → クレジットカード管理 → カードを登録する")
        return 0

    if not cdp_ready(args.port):
        pass  # start_cdp_chrome in run_flow
    try:
        return run_flow(args.wait_sec, args.port)
    except (PlaywrightTimeout, TimeoutError, RuntimeError) as e:
        print(f"❌ {e}", file=sys.stderr)
        print(f"📎 CDP Chrome は port {args.port} で起動中の可能性があります", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
