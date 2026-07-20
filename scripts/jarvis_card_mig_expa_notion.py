#!/usr/bin/env python3
"""エキスパ(exp-t.jp)・Notion 課金の支払カードを Olive Infinite(6777)へ切替（Chrome CDP）。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  python scripts/jarvis_card_mig_expa_notion.py --expa --status
  python scripts/jarvis_card_mig_expa_notion.py --notion --status
  python scripts/jarvis_card_mig_expa_notion.py --expa --wait-sec 900
  python scripts/jarvis_card_mig_expa_notion.py --notion --wait-sec 900

.env.jarvis_private:
  EXPA_USER / EXPA_PASSWORD（未設定時は PERSONAL_EMAIL=m19m.hrts83@gmail.com のみ使用）
  OLIVE_FLEXIBLE_PAY_CREDIT_* （6777）
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

CDP_PORT = 9229
PROFILE = Path.home() / ".jarvis_state" / "chrome_card_mig"
EXPA_LOGIN = "https://exp-t.jp/account/login/expa"
NOTION_BILLING = "https://www.notion.so/my-account/billing"


def _body(page: Page) -> str:
    try:
        return page.inner_text("body")
    except Exception:
        return ""


def _dump(page: Page, label: str = "") -> None:
    print(f"\n📎 {label} URL: {page.url}")
    body = _body(page)
    for kw in ["7887", "6777", "3402", "1002", "American", "Amex", "Visa", "三井", "クレジット", "カード", "Billing", "請求", "ログイン", "エラー"]:
        if kw.lower() in body.lower() or kw in body:
            print(f"   本文に「{kw}」あり")
    links = page.eval_on_selector_all(
        "a, button",
        """els => els.map(e => ({
            text: (e.innerText || e.value || '').trim().slice(0, 80),
            href: e.href || '',
            visible: !!(e.offsetWidth || e.offsetHeight)
        })).filter(x => x.visible && /カード|クレジット|Billing|請求|編集|変更|Edit|Update|管理者|契約|登録|payment/i.test(x.text))""",
    )
    for a in links[:25]:
        print("  NAV:", a)


def _login_expa(page: Page, user: str, password: str) -> bool:
    page.goto(EXPA_LOGIN, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(2000)
    body = _body(page)
    if any(x in body for x in ("ログアウト", "マイページ", "管理者メニュー")):
        print("📎 エキスパ: 既にログイン済み")
        return True
    if page.locator("#MasterCustomerMail").count():
        page.locator("#MasterCustomerMail").fill(user)
        page.locator("#MasterCustomerPassword").fill(password)
        page.get_by_role("button", name="会員ログインする").click()
    else:
        page.locator('input[type="email"]').first.fill(user)
        page.locator('input[type="password"]').first.fill(password)
        page.get_by_role("button", name=re.compile("ログイン")).first.click()
    page.wait_for_timeout(5000)
    body = _body(page)
    if any(x in body for x in ("ログアウト", "マイページ", "管理者メニュー")):
        print("📎 エキスパ: ログイン成功")
        return True
    if "誤" in body:
        print("📎 エキスパ: ログイン失敗（メールまたはパスワード不一致）")
    elif password:
        print("📎 エキスパ: ログイン未確認")
    else:
        print("📎 エキスパ: EXPA_PASSWORD 未設定 — 手動ログインしてください")
    _dump(page, "エキスパ login")
    return False


def _open_expa_card_settings(page: Page) -> None:
    """管理者メニュー → 契約情報 / クレジットカード登録 を探索。"""
    for pat in [r"管理者メニュー", r"クレジットカード", r"カード登録", r"契約情報", r"登録情報"]:
        loc = page.get_by_role("link", name=re.compile(pat))
        if loc.count() and loc.first.is_visible():
            print(f"📎 エキスパ: 「{pat}」をクリック")
            loc.first.click()
            page.wait_for_timeout(3000)
            _dump(page, f"エキスパ after {pat}")
            if re.search(pat, r"管理者|契約|カード|登録"):
                break
    # 直接URL候補
    for url in [
        "https://exp-t.jp/c/card/edit",
        "https://exp-t.jp/c/card",
        "https://exp-t.jp/c/contract",
        "https://exp-t.jp/c/admin/contract",
    ]:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(1500)
        body = _body(page)
        if "404" not in body and "見つかりません" not in body and "ログイン" not in page.url:
            if any(k in body for k in ["カード", "クレジット", "Visa", "有効期限"]):
                print(f"📎 エキスパ: カード設定候補 {url}")
                _dump(page, "エキスパ card page")
                return


def _open_notion_billing(page: Page) -> None:
    page.goto(NOTION_BILLING, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(3000)
    _dump(page, "Notion billing")
    for pat in [r"Edit method", r"編集", r"Update", r"更新", r"Continue with Google", r"Googleで続行"]:
        loc = page.get_by_role("button", name=re.compile(pat, re.I))
        if not loc.count():
            loc = page.get_by_role("link", name=re.compile(pat, re.I))
        if loc.count() and loc.first.is_visible():
            print(f"📎 Notion: 「{pat}」ボタンあり（手動/Google SSO）")
            break


def run_expa(env: dict, wait_sec: int, port: int, status_only: bool) -> int:
    user = env.get("EXPA_USER") or env.get("PERSONAL_EMAIL") or env.get("ZAIM_LOGIN_EMAIL", "")
    password = env.get("EXPA_PASSWORD", "")
    last4 = env.get("OLIVE_FLEXIBLE_PAY_CREDIT_LAST4", "6777")

    start_cdp_chrome(port, PROFILE, EXPA_LOGIN)
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        ctx = browser.contexts[0] if browser.contexts else browser.new_context(locale="ja-JP")
        page = ctx.new_page()
        logged_in = _login_expa(page, user, password)
        if logged_in or not status_only:
            _open_expa_card_settings(page)
        print("")
        print("=" * 60)
        print(f"📎 エキスパ — カード切替（目標: Visa ****{last4}）")
        print(f"   ログインID: {user}")
        print("   手順: 管理者メニュー → 契約情報/クレジットカード登録 → 7887へ更新")
        print("   参考: help.ex-pa.jp 「クレジットカード登録（商品/セミナー購入用）」")
        if not password:
            print("   ⚠ EXPA_PASSWORD を .env.jarvis_private に追記すると自動ログイン可")
        if not status_only:
            print(f"   Chrome は {wait_sec} 秒開いたまま（3Dセキュアは手入力）")
        print("=" * 60)
        if not status_only:
            time.sleep(wait_sec)
    return 0 if logged_in else 2


def run_notion(env: dict, wait_sec: int, port: int, status_only: bool) -> int:
    last4 = env.get("OLIVE_FLEXIBLE_PAY_CREDIT_LAST4", "6777")
    start_cdp_chrome(port, PROFILE, NOTION_BILLING)
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        ctx = browser.contexts[0] if browser.contexts else browser.new_context(locale="ja-JP")
        page = ctx.new_page()
        _open_notion_billing(page)
        print("")
        print("=" * 60)
        print(f"📎 Notion — カード切替（目標: Visa ****{last4}）")
        print("   Settings → Billing → Edit method → Stripeで7887更新")
        print("   明細: LEMSQZY* NOTIONSENDE（Notion有料プラン）")
        print("   Google SSO (matsuno.estate@gmail.com 等) が必要な場合あり")
        if not status_only:
            print(f"   Chrome は {wait_sec} 秒開いたまま")
        print("=" * 60)
        if not status_only:
            time.sleep(wait_sec)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="エキスパ・Notion 支払カード切替（Olive 6777）")
    parser.add_argument("--expa", action="store_true")
    parser.add_argument("--notion", action="store_true")
    parser.add_argument("--status", action="store_true", help="画面状態のみ確認（短時間）")
    parser.add_argument("--open-expa", action="store_true")
    parser.add_argument("--open-notion", action="store_true")
    parser.add_argument("--port", type=int, default=CDP_PORT)
    parser.add_argument("--wait-sec", type=int, default=600)
    args = parser.parse_args()

    if args.open_expa:
        open_in_chrome(EXPA_LOGIN)
        return 0
    if args.open_notion:
        open_in_chrome(NOTION_BILLING)
        return 0

    if not args.expa and not args.notion:
        parser.error("--expa または --notion を指定")

    env = load_env(ENV_FILE)
    wait = 30 if args.status else args.wait_sec
    rc = 0
    try:
        if args.expa:
            r = run_expa(env, wait, args.port, args.status)
            rc = max(rc, r)
        if args.notion:
            # Expa 後に同じ Chrome で続行
            run_notion(env, wait, args.port, args.status)
    except (PlaywrightTimeout, TimeoutError, RuntimeError) as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
