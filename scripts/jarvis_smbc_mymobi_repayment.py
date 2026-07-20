#!/usr/bin/env python3
"""三井住友カード プレミアムカードローン — Myモビで返済口座をOlive契約口座へ変更。

返済口座変更は Vpass ではなく会員専用サービス「Myモビ」で行います（三井住友カードFAQ id=2570）。

  python scripts/jarvis_smbc_mymobi_repayment.py --status
  python scripts/jarvis_smbc_mymobi_repayment.py --apply
  python scripts/jarvis_smbc_mymobi_repayment.py --open

.env.jarvis_private:
  MY_MOBI_USER_ID + MY_MOBI_PASSWORD
  または MY_MOBI_CARD_NUMBER + SMBC_CARD_PIN（+ PERSONAL_BIRTHDATE）
  Olive引落先: SMBC_OLIVE_BANK_BRANCH_CODE / SMBC_OLIVE_BANK_ACCOUNT（任意・画面選択でも可）
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

from car_loan.chrome_cdp import open_in_chrome, start_cdp_chrome  # noqa: E402
from car_loan.env_state import ENV_FILE, load_env  # noqa: E402

CDP_PORT = 9230
PROFILE = Path.home() / ".jarvis_state" / "chrome_smbc_mymobi"
MY_MOBI_TOP = "https://www.mobit.ne.jp/customers/mymobi/index.html"
MY_MOBI_LOGIN = "https://www.mobit.ne.jp/s/login/Login.do"


def _missing_mymobi(env: dict[str, str]) -> list[str]:
    user = env.get("MY_MOBI_USER_ID", "")
    pw = env.get("MY_MOBI_PASSWORD", "")
    card = env.get("MY_MOBI_CARD_NUMBER", "")
    pin = env.get("SMBC_CARD_PIN", "")
    if user and pw:
        return []
    if card and pin and env.get("PERSONAL_BIRTHDATE"):
        return []
    need = []
    if not (user and pw):
        need.append("MY_MOBI_USER_ID+MY_MOBI_PASSWORD または MY_MOBI_CARD_NUMBER+SMBC_CARD_PIN")
    if card and not pin:
        need.append("SMBC_CARD_PIN")
    if card and pin and not env.get("PERSONAL_BIRTHDATE"):
        need.append("PERSONAL_BIRTHDATE")
    return need


def _fill_birthdate(page: Page, birth: str) -> None:
    # YYYY-MM-DD or YYYYMMDD
    digits = re.sub(r"\D", "", birth)
    if len(digits) != 8:
        return
    y, m, d = digits[:4], digits[4:6], digits[6:8]
    for sel, val in [
        ("select[name*='year' i], #birthYear", y),
        ("select[name*='month' i], #birthMonth", str(int(m))),
        ("select[name*='day' i], #birthDay", str(int(d))),
    ]:
        loc = page.locator(sel)
        if loc.count():
            try:
                loc.first.select_option(value=val)
            except Exception:
                try:
                    loc.first.select_option(label=val)
                except Exception:
                    pass


def _mymobi_login(page: Page, env: dict[str, str]) -> bool:
    page.goto(MY_MOBI_LOGIN, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(2000)
    user = env.get("MY_MOBI_USER_ID", "")
    pw = env.get("MY_MOBI_PASSWORD", "")
    card = env.get("MY_MOBI_CARD_NUMBER", "")
    pin = env.get("SMBC_CARD_PIN", "")
    birth = env.get("PERSONAL_BIRTHDATE", "")

    if user and pw:
        for sel in ["input[name*='user' i]", "input[name*='login' i]", "#userId", "input[type='text']"]:
            loc = page.locator(sel)
            if loc.count() and loc.first.is_visible():
                loc.first.fill(user)
                break
        page.locator("input[type='password']").first.fill(pw)
    elif card and pin:
        tab = page.get_by_role("tab", name=re.compile(r"カード"))
        if tab.count():
            tab.first.click()
            page.wait_for_timeout(500)
        page.locator("input[type='text']").first.fill(card)
        page.locator("input[type='password']").first.fill(pin)
        _fill_birthdate(page, birth)
    else:
        return False

    btn = page.get_by_role("button", name=re.compile(r"ログイン"))
    if btn.count():
        btn.first.click()
    else:
        page.locator("input[type='submit'], button[type='submit']").first.click()
    page.wait_for_load_state("domcontentloaded", timeout=90000)
    page.wait_for_timeout(3000)

    if re.search(r"login|Login", page.url):
        print("📎 SMS認証コード入力が必要な場合があります。Chrome で完了してください。")
        deadline = time.time() + 180
        while time.time() < deadline and re.search(r"login|Login", page.url, re.I):
            time.sleep(2)
    return not re.search(r"login/Login", page.url, re.I)


def _goto_repayment_change(page: Page) -> bool:
    for pat in [
        r"返済方法変更",
        r"振替口座変更",
        r"返済時の振替口座",
        r"口座振替",
    ]:
        loc = page.get_by_role("link", name=re.compile(pat))
        if loc.count():
            loc.first.click()
            page.wait_for_timeout(2500)
            return True
        loc = page.locator(f"a:has-text('{pat}')")
        if loc.count():
            loc.first.click()
            page.wait_for_timeout(2500)
            return True
    return False


def _select_olive_account(page: Page, env: dict[str, str]) -> None:
    branch = env.get("SMBC_OLIVE_BANK_BRANCH_CODE", "")
    account = env.get("SMBC_OLIVE_BANK_ACCOUNT", "")
    body = page.inner_text("body")
    if "Olive" in body or "オリーブ" in body:
        for pat in [r"Olive", r"オリーブ", r"三井住友銀行"]:
            loc = page.get_by_label(re.compile(pat))
            if loc.count():
                loc.first.check(force=True)
                break
            loc = page.locator(f"label:has-text('{pat}')")
            if loc.count():
                loc.first.click()
                break
    if branch:
        for sel in ["input[name*='branch' i]", "input[name*='店' i]"]:
            loc = page.locator(sel)
            if loc.count() and loc.first.is_visible():
                loc.first.fill(branch)
                break
    if account:
        for sel in ["input[name*='account' i]", "input[name*='口座' i]"]:
            loc = page.locator(sel)
            if loc.count() and loc.first.is_visible():
                loc.first.fill(account)
                break


def run(mode: str, *, wait_sec: int, port: int) -> int:
    env = load_env(ENV_FILE)
    missing = _missing_mymobi(env)
    if missing and mode != "open":
        print("❌ Myモビログイン情報が不足しています:", file=sys.stderr)
        for m in missing:
            print(f"   - {m}", file=sys.stderr)
        print("   → .env.jarvis_private に追記後「保存した」と一声ください", file=sys.stderr)
        return 1

    start_cdp_chrome(port, PROFILE, MY_MOBI_TOP)
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        ctx = browser.contexts[0] if browser.contexts else browser.new_context(locale="ja-JP")
        page = ctx.new_page()

        if not _mymobi_login(page, env):
            print("⚠️ Myモビ ログイン未完了。SMS認証後に再実行してください。")
            time.sleep(wait_sec)
            return 1

        print(f"📎 ログイン後: {page.url[:90]}")
        if mode == "status":
            body = page.inner_text("body")
            for line in body.splitlines():
                s = line.strip()
                if any(k in s for k in ("返済", "振替", "口座", "Olive", "オリーブ", "引落")):
                    print(" ", s[:100])
        elif mode == "apply":
            if not _goto_repayment_change(page):
                print("📎 メニューから「返済方法変更・返済時の振替口座変更」を手動で開いてください")
            else:
                _select_olive_account(page, env)
                print("📎 Olive契約口座を選択し、確認画面まで Chrome で完了してください")
        print(f"\n📎 Chrome は {wait_sec} 秒間開いたままです（port {port}）")
        time.sleep(wait_sec)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Myモビ — カードローン返済口座をOlive口座へ")
    parser.add_argument("--status", action="store_true", help="ログイン後の返済・口座表示を確認")
    parser.add_argument("--apply", action="store_true", help="返済口座変更画面へ進む")
    parser.add_argument("--open", action="store_true", help="Myモビ案内URLのみ開く")
    parser.add_argument("--port", type=int, default=CDP_PORT)
    parser.add_argument("--wait-sec", type=int, default=600)
    args = parser.parse_args()

    if args.open:
        open_in_chrome(MY_MOBI_TOP)
        print("📎 ご契約中 → 会員専用サービス「Myモビ」→ 返済方法変更・返済時の振替口座変更")
        return 0

    mode = "apply" if args.apply else "status"
    try:
        return run(mode, wait_sec=args.wait_sec, port=args.port)
    except (PlaywrightTimeout, TimeoutError, RuntimeError) as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
