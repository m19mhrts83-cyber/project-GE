#!/usr/bin/env python3
"""SBI証券 クレカ積立3件の再設定（Google Chrome + CDP）。

前提: クレジットカード（Olive INF / 6777）登録済み。
  ~/git-repos/scripts/jarvis_sbi_tsumitate_setup.py
  ~/git-repos/scripts/jarvis_sbi_tsumitate_setup.py --dry-run
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout, sync_playwright

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from car_loan.chrome_cdp import start_cdp_chrome  # noqa: E402
from car_loan.env_state import ENV_FILE, load_env  # noqa: E402

CDP_PORT = 9225
PROFILE = Path.home() / ".jarvis_state" / "chrome_sbi_card"

ACCUMULATION_URL = (
    "https://www.sbisec.co.jp/ETGate/?_ControlID=WPLETsmR001Control"
    "&_PageID=WPLETsmR001Sdtl23&_ActionID=NoActionID&_DataStoreID=DSWPLETsmR001Control"
    "&OutSide=on&getFlg=on&path=fund%2Faccount%2Faccumulation"
)
SBI_LOGIN = (
    "https://login.sbisec.co.jp/login/entry"
    "?_ReturnPageInfo=WPLETsmR001Control%2FWPLETsmR001Sdtl23%2FNoActionID%2FDSWPLETsmR001Control"
    "&_ALLPARAM_JSON=%7B%22getFlg%22%3A%22on%22%2C%22path%22%3A%22fund%2Faccount%2Faccumulation%22%7D"
    "&eventCode=&channel=main-site-user"
)
RESERVE_INIT = "https://site0.sbisec.co.jp/marble/trade/fund/reserve/reserveInit.do?param_fund_cd={code}"


@dataclass(frozen=True)
class FundPlan:
    code: str
    name: str
    amount: int


PLANS = (
    FundPlan("03319172", "eMAXIS Slim 先進国（除く日本）", 70000),
    FundPlan("2931517A", "ニッセイ新興国", 10000),
    FundPlan("7931211C", "三井住友 DC NISA 日本株", 10000),
)


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


def _wait_login(page: Page, wait_sec: int) -> bool:
    if "login.sbisec.co.jp" not in page.url:
        return True
    print("📎 OTP・追加認証があれば Chrome で入力してください（最大5分待機）…")
    deadline = time.time() + 300
    while time.time() < deadline and "login.sbisec.co.jp" in page.url:
        time.sleep(2)
    if "login.sbisec.co.jp" in page.url:
        print("⚠️ まだログイン画面です。Chrome でログイン完了後、同コマンドを再実行してください。")
        time.sleep(wait_sec)
        return False
    return True


def _select_nisa_tsumitate(page: Page) -> None:
    for label in ("NISA（つみたて投資枠）", "NISA(つみたて投資枠)", "つみたて投資枠"):
        loc = page.get_by_label(label)
        if loc.count():
            loc.first.check(force=True)
            return
        loc = page.locator(f"input[type='radio'][value*='tsumitate'], input[type='radio']").filter(
            has_text=re.compile("つみたて")
        )
        if loc.count():
            loc.first.check(force=True)
            return
    # fallback: radio near つみたて text
    page.locator("label").filter(has_text=re.compile("つみたて")).first.click(timeout=5000)


def _select_credit_card(page: Page) -> None:
    for label in ("クレジットカード", "クレジットカード決済"):
        loc = page.get_by_label(label)
        if loc.count():
            loc.first.check(force=True)
            return
    page.locator("label").filter(has_text=re.compile("クレジット")).first.click(timeout=5000)


def _fill_monthly_course(page: Page, amount: int, day: int = 9) -> None:
    # 金額
    for sel in ("input[name*='amount']", "input[name*='kingaku']", "#amount", "input[type='tel']"):
        loc = page.locator(sel)
        if loc.count():
            loc.first.fill(str(amount))
            break
    # 申込日
    for sel in ("select[name*='day']", "select[name*='Day']", "select[name*='date']"):
        loc = page.locator(sel)
        if loc.count():
            try:
                loc.first.select_option(label=str(day))
            except Exception:
                loc.first.select_option(value=str(day))
            break


def _submit_to_confirm(page: Page, trade_pw: str) -> None:
    pw = page.locator("input[type='password']").last
    if pw.count():
        pw.fill(trade_pw)
    for name in ("設定確認画面へ", "確認画面へ", "確認する", "次へ"):
        btn = page.get_by_role("button", name=name)
        if btn.count():
            btn.first.click()
            page.wait_for_load_state("domcontentloaded", timeout=60000)
            time.sleep(1)
            return
    page.locator("input[type='submit'], button[type='submit']").first.click()
    page.wait_for_load_state("domcontentloaded", timeout=60000)
    time.sleep(1)


def _final_confirm(page: Page) -> bool:
    for name in ("設定", "設定する", "確定", "申込"):
        btn = page.get_by_role("button", name=name)
        if btn.count():
            btn.first.click()
            page.wait_for_load_state("domcontentloaded", timeout=60000)
            time.sleep(2)
            body = page.inner_text("body")[:800]
            return any(k in body for k in ("受け付け", "完了", "設定しました", "積立設定"))
    return False


def _setup_one(page: Page, plan: FundPlan, trade_pw: str, dry_run: bool) -> bool:
    url = RESERVE_INIT.format(code=plan.code)
    print(f"📎 {plan.name} ({plan.code}) ¥{plan.amount:,} …")
    page.goto(url, wait_until="domcontentloaded", timeout=90000)
    time.sleep(2)
    if "login.sbisec.co.jp" in page.url:
        raise RuntimeError("積立設定画面遷移でログアウトしました")
    body = page.inner_text("body")[:500]
    if "積立" not in body and "買付" not in body:
        print(f"   ⚠️ 想定外画面: {page.url[:100]}")
        return False
    if dry_run:
        print("   dry-run: 入力スキップ")
        return True
    _select_nisa_tsumitate(page)
    _select_credit_card(page)
    _fill_monthly_course(page, plan.amount, day=9)
    _submit_to_confirm(page, trade_pw)
    ok = _final_confirm(page)
    print(f"   {'✅ 設定完了' if ok else '⚠️ 確認画面まで（最終確定要確認）'}")
    return ok


def run_flow(dry_run: bool, wait_sec: int, port: int) -> int:
    env = load_env(ENV_FILE)
    user = env.get("SBI_SEC_USER", "")
    login_pw = env.get("SBI_SEC_LOGIN_PASSWORD", "")
    trade_pw = env.get("SBI_SEC_TRADE_PASSWORD", "")
    missing = [k for k, v in [("SBI_SEC_USER", user), ("SBI_SEC_LOGIN_PASSWORD", login_pw), ("SBI_SEC_TRADE_PASSWORD", trade_pw)] if not v]
    if missing:
        print(f"未設定: {', '.join(missing)} (.env.jarvis_private)", file=sys.stderr)
        return 1

    start_cdp_chrome(port, PROFILE, SBI_LOGIN)
    results: list[tuple[str, bool]] = []

    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        ctx = browser.contexts[0] if browser.contexts else browser.new_context(locale="ja-JP")
        page = ctx.new_page()
        page.goto(SBI_LOGIN, wait_until="domcontentloaded", timeout=90000)

        print("📎 SBI ログイン…")
        _sbi_login_if_needed(page, user, login_pw)
        if not _wait_login(page, wait_sec):
            return 0

        print("📎 積立設定一覧へ…")
        page.goto(ACCUMULATION_URL, wait_until="domcontentloaded", timeout=90000)
        time.sleep(2)
        if "login.sbisec.co.jp" in page.url:
            print("⚠️ 積立一覧へ遷移できませんでした（ログイン要）")
            time.sleep(wait_sec)
            return 0

        existing = page.inner_text("body")
        if "03319172" in existing or "eMAXIS" in existing:
            print("📎 既存の積立設定が見つかりました。重複登録に注意してください。")

        for plan in PLANS:
            try:
                ok = _setup_one(page, plan, trade_pw, dry_run)
                results.append((plan.name, ok))
            except (PlaywrightTimeout, RuntimeError) as e:
                print(f"   ❌ {e}")
                results.append((plan.name, False))

        print("")
        print("=" * 60)
        for name, ok in results:
            print(f"{'✅' if ok else '❌'} {name}")
        print(f"   Chrome は {wait_sec} 秒間開いたままです（port {port}）")
        print("=" * 60)
        time.sleep(wait_sec)

    return 0 if all(ok for _, ok in results) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="SBI クレカ積立3件 再設定")
    parser.add_argument("--dry-run", action="store_true", help="画面遷移のみ")
    parser.add_argument("--port", type=int, default=CDP_PORT)
    parser.add_argument("--wait-sec", type=int, default=600)
    args = parser.parse_args()
    try:
        return run_flow(args.dry_run, args.wait_sec, args.port)
    except (PlaywrightTimeout, RuntimeError) as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
