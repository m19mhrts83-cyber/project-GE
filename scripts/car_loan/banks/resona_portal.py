"""りそな Web手続きポータル（Salesforce）— ログイン・本申込フォーム。"""
from __future__ import annotations

import re
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

from ..chrome_cdp import start_cdp_chrome
from ..env_state import load_env, load_state, receipt_from_state
from .registry import expand_path, load_bank_config

PORTAL = "https://loan-resona-gr.my.site.com"
CASE_PATH = "/s/detail/a01fQ00000T1SHvQAN"


def _init_password(env: dict) -> str:
    bd = re.sub(r"[^0-9]", "", env.get("PERSONAL_BIRTHDATE", ""))
    ph = re.sub(r"[^0-9]", "", env.get("PERSONAL_PHONE", ""))
    return f"r{bd}{ph}"


def _login(page: Page, env: dict) -> None:
    email = env.get("RESONA_MYCAR_APPLICATION_EMAIL") or env.get("PERSONAL_EMAIL", "")
    password = _init_password(env)
    if "SiteLogin" not in page.url:
        page.goto(f"{PORTAL}/SiteLogin", wait_until="domcontentloaded", timeout=90000)
    page.locator('input[name="loginPage:siteLogin:loginComponent:loginForm:username"]').fill(email)
    page.locator('input[name="loginPage:siteLogin:loginComponent:loginForm:password"]').fill(password)
    page.locator('input[name="loginPage:siteLogin:loginComponent:loginForm:loginButton"]').click()
    page.wait_for_load_state("domcontentloaded", timeout=60000)
    time.sleep(1.5)
    if "SiteLogin" in page.url and "失敗" in page.inner_text("body"):
        raise RuntimeError("りそなポータルへのログインに失敗しました（初期パスワードを確認）")


def _fill_visible_by_index(page: Page, idx: int, value: str) -> None:
    inp = page.locator("input:visible").nth(idx)
    if inp.count():
        inp.fill(value)


def _click_edit_if_needed(page: Page) -> None:
    if page.locator("input:visible").count() >= 20:
        return
    edit = page.locator('button[title*="編集"], button:has-text("編集")')
    for i in range(edit.count()):
        title = edit.nth(i).get_attribute("title") or ""
        if "お問い合わせ" in title:
            continue
        try:
            edit.nth(i).click(force=True, timeout=5000)
            time.sleep(2)
            if page.locator("input:visible").count() >= 20:
                return
        except Exception:
            continue


def _select_deposit_type(page: Page, label: str = "普通預金") -> bool:
    """お振込先預金種目（index=1）をプルダウンから選択。"""
    try:
        trigger = page.locator('a.select[role=button]').nth(1)
        if trigger.count() and label not in (trigger.inner_text(timeout=2000) or ""):
            trigger.click(force=True)
            time.sleep(0.6)
            page.locator("a").filter(has_text=label).last.click(force=True)
            time.sleep(0.4)
        return True
    except Exception:
        return False


def _dealer_transfer_name(state: dict) -> str:
    transfer = state.get("dealer_transfer") or {}
    return transfer.get("account_name_halfwidth") or "ｶ)ﾒｲﾃﾂｱｵﾄ"


def _dealer_account_for_form(state: dict) -> str:
    transfer = state.get("dealer_transfer") or {}
    acct = str(transfer.get("account_number", ""))
    if transfer.get("account_number_form"):
        return str(transfer["account_number_form"])
    # りそなフォームは7桁ゼロ埋めを要求することがある
    if acct.isdigit() and len(acct) < 7:
        return acct.zfill(7)
    return acct


def _save_application(page: Page) -> bool:
    """申込内容入力完了チェック → 保存。"""
    try:
        cb = page.locator("input[type=checkbox]").first
        if cb.count() and not cb.is_checked():
            cb.click(force=True)
        time.sleep(0.4)
        save = page.locator('button:has-text("保存"):visible').last
        if save.count():
            save.click()
            page.wait_for_load_state("networkidle", timeout=60000)
            time.sleep(2)
            body = page.inner_text("body")
            if "次の項目を確認" in body:
                return False
            return page.locator('button:has-text("キャンセル"):visible').count() == 0
    except Exception:
        pass
    return False


def fill_main_application(page: Page, env: dict, state: dict) -> list[str]:
    """編集画面で入力可能な項目を埋める。未入力の必須は warnings に返す。"""
    warnings: list[str] = []
    home_addr = (
        env.get("HOME_PREF", "")
        + env.get("HOME_ADDRESS_STREET", "")
        + env.get("HOME_ADDRESS_BANTI", "")
    )
    postal = re.sub(r"[^0-9]", "", env.get("HOME_POSTAL_CODE", ""))
    phone = env.get("PERSONAL_PHONE", "")

    _click_edit_if_needed(page)

    # 編集時のみ空になる連絡先（インデックスは探索時に確定）
    fields = {
        2: postal,
        3: home_addr,
        4: phone,
        5: phone,
        8: state.get("loan_desired_date", "2026/07/15"),
    }
    for idx, val in fields.items():
        if val:
            _fill_visible_by_index(page, idx, val)

    amount = str(state.get("loan_amount_requested", 5489025))
    # 振込金額（円）
    _fill_visible_by_index(page, 22, amount)

    bonus_months = state.get("loan_bonus_months") or [1, 7]
    if isinstance(bonus_months, str):
        bonus_months = [int(x) for x in re.findall(r"\d+", bonus_months)]
    if len(bonus_months) >= 2:
        _fill_visible_by_index(page, 10, str(bonus_months[0]))
        _fill_visible_by_index(page, 12, str(bonus_months[1]))

    transfer = state.get("dealer_transfer") or {}
    mapping = {
        18: transfer.get("bank_name", ""),
        19: _dealer_account_for_form(state),
        20: transfer.get("branch_name", ""),
        21: _dealer_transfer_name(state),
    }
    for idx, val in mapping.items():
        if val:
            _fill_visible_by_index(page, idx, val)
        elif idx in (18, 19, 20, 21):
            warnings.append(f"振込先情報（input index {idx}）が未設定です")

    acct = env.get("RESONA_REPAYMENT_ACCOUNT_NUMBER") or env.get("RESONA_ACCOUNT", "")
    if acct and acct not in ("未定", ""):
        _fill_visible_by_index(page, 16, acct)
    else:
        warnings.append("返済口座番号（RESONA_REPAYMENT_ACCOUNT_NUMBER）が未設定です（口座開設完了メール待ち）")

    if not _select_deposit_type(page):
        warnings.append("お振込先預金種目（普通預金）の選択に失敗しました")

    return warnings


def complete_main_application(page: Page, env: dict, state: dict) -> tuple[list[str], bool]:
    """本申込フォーム入力 → 保存まで。"""
    warnings = fill_main_application(page, env, state)
    if any("返済口座" in w or "振込先" in w for w in warnings):
        return warnings, False
    saved = _save_application(page)
    return warnings, saved


def open_and_prepare(*, port: int | None = None, dry_run: bool = False, save: bool = False) -> str:
    cfg = load_bank_config("resona")
    env = load_env()
    state = load_state()
    cdp_port = port or int(cfg.get("cdp_port", 9224))
    profile = expand_path(cfg["chrome_profile"])
    url = f"{PORTAL}{CASE_PATH}"

    if dry_run:
        print(f"portal={PORTAL}")
        print(f"case={receipt_from_state('resona_mycar', env, state) or '26-300487525'}")
        print(f"login_user={env.get('RESONA_MYCAR_APPLICATION_EMAIL')}")
        return url

    start_cdp_chrome(cdp_port, profile, url)
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{cdp_port}")
        ctx = browser.contexts[0] if browser.contexts else browser.new_context(locale="ja-JP")
        page = ctx.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=90000)
        if "SiteLogin" in page.url:
            _login(page, env)
            page.goto(url, wait_until="domcontentloaded", timeout=90000)
        if save:
            warnings, saved = complete_main_application(page, env, state)
            for w in warnings:
                print(f"⚠️  {w}")
            if saved:
                print("✅ 本申込フォームを保存しました")
            else:
                print("❌ 本申込フォームの保存に失敗しました（画面を確認してください）")
        else:
            warnings = fill_main_application(page, env, state)
            for w in warnings:
                print(f"⚠️  {w}")
            print(f"📎 りそな本申込フォームを開きました: {page.url}")
            print("📎 「申込内容入力完了」→「保存」後、書類提出に進んでください。")
        return page.url
