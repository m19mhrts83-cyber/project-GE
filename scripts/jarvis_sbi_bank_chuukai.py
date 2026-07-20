#!/usr/bin/env python3
"""SBI証券 — 三井住友銀行仲介口座への切替補助（Chrome CDP）。

  ~/git-repos/scripts/jarvis_sbi_bank_chuukai.py --status     # 仲介業者確認
  ~/git-repos/scripts/jarvis_sbi_bank_chuukai.py --release    # カード仲介等の解除画面へ
  ~/git-repos/scripts/jarvis_sbi_bank_chuukai.py --apply      # 銀行仲介申込（SMBC経由）
  ~/git-repos/scripts/jarvis_sbi_bank_chuukai.py --open       # URLのみ

.env.jarvis_private: SBI_SEC_USER / SBI_SEC_LOGIN_PASSWORD
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from car_loan.chrome_cdp import cdp_ready, open_in_chrome, start_cdp_chrome  # noqa: E402
from car_loan.env_state import ENV_FILE, load_env  # noqa: E402

CDP_PORT = 9228
PROFILE = Path.home() / ".jarvis_state" / "chrome_sbi_chuukai"
SMBC_APPLY = "https://www.smbc.co.jp/kojin/asset-management/sbi/course_change/"
SBI_LOGIN_ENTRY = (
    "https://login.sbisec.co.jp/login/entry"
    "?channel=main-site-user&eventCode=LAR_000033"
)
# My設定 > お客さま情報 設定・変更
SBI_CUSTOMER_SETTING = (
    "https://www.sbisec.co.jp/ETGate/?_ControlID=WPLETsmR001Control"
    "&_DataStoreID=DSWPLETsmR001Control&OutSide=on&getFlg=on"
    "&sw_page=Regist&cat1=home&cat2=none"
)


def _sbi_login(page: Page, user: str, login_pw: str) -> None:
    page.goto(SBI_LOGIN_ENTRY, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(1500)
    if "login.sbisec.co.jp" not in page.url:
        return
    user_loc = page.locator("input[name='username']")
    if user_loc.count():
        user_loc.first.fill(user)
        page.locator("input[name='password']").first.fill(login_pw)
    else:
        page.locator("input[type='text']").first.fill(user)
        page.locator("input[type='password']").first.fill(login_pw)
    page.get_by_role("button", name="ログイン", exact=True).click()
    page.wait_for_load_state("domcontentloaded", timeout=90000)
    page.wait_for_timeout(2000)


def _wait_past_login(page: Page, wait_sec: int) -> bool:
    if "login.sbisec.co.jp" not in page.url:
        return True
    if "/otp/" in page.url:
        print(f"📎 ワンタイムパスワード入力画面です。SBIアプリ等で認証してください（最大{wait_sec}秒）…")
    else:
        print(f"📎 追加認証・パスキー選択があれば Chrome で完了してください（最大{wait_sec}秒）…")
    deadline = time.time() + wait_sec
    while time.time() < deadline and "login.sbisec.co.jp" in page.url:
        time.sleep(2)
    ok = "login.sbisec.co.jp" not in page.url
    if not ok:
        print("⚠️ ログイン未完了。Chrome でログイン後、同コマンドを再実行してください。")
    return ok


def _detect_intermediary(page: Page) -> str:
    html = page.content()
    text = page.inner_text("body")
    if "三井住友銀行" in html and "仲介" in text:
        return "三井住友銀行仲介口座"
    if "三井住友カード" in html:
        return "三井住友カード仲介口座"
    if "金融商品仲介業者" in text:
        m = re.search(r"金融商品仲介業者[^\n]*\n([^\n]+)", text)
        if m:
            return m.group(1).strip()
    if "仲介専用" in text or "mediation" in page.url:
        return "仲介口座（種類は画面で確認）"
    if "インターネットコース" in text and "仲介" not in text:
        return "通常インターネットコース（仲介なし）"
    return "不明（画面を確認）"


def _print_customer_info(page: Page) -> str:
    page.goto(SBI_CUSTOMER_SETTING, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(2500)
    if "login.sbisec.co.jp" in page.url:
        return "未ログイン"
    kind = _detect_intermediary(page)
    print(f"📎 仲介口座の推定: {kind}")
    for line in page.inner_text("body").splitlines():
        if any(k in line for k in ("仲介", "三井住友", "金融商品仲介", "コース")):
            s = line.strip()
            if s:
                print(f"   {s}")
    # お客さま基本情報リンク
    loc = page.get_by_role("link", name=re.compile("お客さま基本情報"))
    if loc.count():
        print("📎 「お客さま基本情報」リンクあり → --release で開きます")
    return kind


def _open_release_flow(page: Page) -> None:
    page.goto(SBI_CUSTOMER_SETTING, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(2000)
    for pat in [r"お客さま基本情報", r"基本情報"]:
        loc = page.get_by_role("link", name=re.compile(pat))
        if loc.count():
            loc.first.click()
            page.wait_for_timeout(2500)
            break
    body = page.inner_text("body")
    if "解除" in body:
        print("📎 「解除」ボタンを探してください（金融商品仲介業者の行）。")
        btn = page.get_by_role("button", name=re.compile("解除"))
        if not btn.count():
            btn = page.get_by_role("link", name=re.compile("解除"))
        if btn.count():
            print("   → 自動では押しません。内容確認後、Chrome で「解除」をクリックしてください。")
    print("📎 解除後は通常インターネットコースになります（1〜2営業日）。")
    print("📎 完了したら: python scripts/jarvis_sbi_bank_chuukai.py --apply")


def _open_apply_flow(page: Page) -> None:
    page.goto(SMBC_APPLY, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(2000)
    print("📎 三井住友銀行「仲介口座への変更」ページを開きました。")
    print("   留意事項を確認 → 「三井住友銀行仲介口座への変更のお申し込みへ進む」")
    for pat in [r"お申し込みへ進む", r"申し込みへ進む", r"変更のお申し込み"]:
        loc = page.get_by_role("link", name=re.compile(pat))
        if loc.count():
            print(f"   ボタン検出: {pat}")
            break
    print("📎 SBIログイン後に申込。完了は1〜2営業日。")
    print("📎 完了後: SBIでメインポイントをVポイントに / 銀行アプリでOlive資産運用サービス申込")


def run(mode: str, wait_sec: int, port: int) -> int:
    env = load_env(ENV_FILE)
    user = env.get("SBI_SEC_USER", "")
    pw = env.get("SBI_SEC_LOGIN_PASSWORD", "")
    if not user or not pw:
        print("SBI_SEC_USER / SBI_SEC_LOGIN_PASSWORD を .env.jarvis_private に設定してください。", file=sys.stderr)
        return 1

    start_cdp_chrome(port, PROFILE, SMBC_APPLY if mode == "apply" else SBI_LOGIN_ENTRY)
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        ctx = browser.contexts[0] if browser.contexts else browser.new_context(locale="ja-JP")
        page = ctx.new_page()
        if mode == "apply":
            _open_apply_flow(page)
        else:
            _sbi_login(page, user, pw)
            if not _wait_past_login(page, wait_sec):
                time.sleep(wait_sec)
                return 1
            if mode == "status":
                _print_customer_info(page)
            elif mode == "release":
                _open_release_flow(page)
        print(f"\n📎 Chrome は {wait_sec} 秒間開いたままです（port {port}）")
        time.sleep(wait_sec)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="SBI 銀行仲介口座切替補助")
    parser.add_argument("--status", action="store_true", help="仲介業者を確認")
    parser.add_argument("--release", action="store_true", help="仲介解除画面へ")
    parser.add_argument("--apply", action="store_true", help="銀行仲介申込ページへ")
    parser.add_argument("--open", action="store_true", help="SMBC申込URLのみ")
    parser.add_argument("--port", type=int, default=CDP_PORT)
    parser.add_argument("--wait-sec", type=int, default=600)
    args = parser.parse_args()
    if args.open:
        open_in_chrome(SMBC_APPLY)
        return 0
    mode = "status"
    if args.release:
        mode = "release"
    elif args.apply:
        mode = "apply"
    elif args.status:
        mode = "status"
    return run(mode, args.wait_sec, args.port)


if __name__ == "__main__":
    raise SystemExit(main())
