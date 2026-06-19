#!/usr/bin/env python3
"""
AMEX（アメリカン・エキスプレス）マイアカウントから利用履歴 Excel をダウンロードする。

使い方:
  python amex_statement.py \\
      --start-date 2025-06-01 --end-date 2025-06-30 \\
      --output-dir ".../00_元ファイル_サイト取得/AMEX/"

認証情報: .env.tax_docs に AMEX_LOGIN_ID / AMEX_PASSWORD を設定する。

ログイン:
  初回は手動ブラウザで ID/パスワード入力 → ログイン（amex_login_session.py 既定）。
  2FA 画面が出たら「Eメール」→「次へ」→ Gmail API で確認コード取得・入力を自動実行。
  完了後 .amex_storage_state.json にセッション保存 → 次回以降 --headless 可。

取得元:
  ログイン → 全カードを列挙 → カードごとに期間検索 → Excel ダウンロード
  （activity.xlsx 相当。カード識別子付きファイル名で保存、上書きしない）

注意: AMEX サイトは CSP で page.evaluate が無効なため、Playwright locator のみ使用。
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from datetime import date, datetime
from pathlib import Path

from playwright.sync_api import Frame, TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import Page, sync_playwright

UiContext = Page | Frame

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_ENV_PATH = SCRIPT_DIR / ".env.tax_docs"

AMEX_LOGIN_URL = "https://www.americanexpress.com/ja-JP/account/login/"
ACTIVITY_SEARCH_URL = "https://global.americanexpress.com/activity/search"
DEFAULT_STORAGE_STATE = SCRIPT_DIR / ".amex_storage_state.json"

_NAV_OPTION_SKIP = re.compile(
    r"Cards and Banking|Membership Rewards|Merchant|@ Work|"
    r"マイ・アカウント|加盟店|@Work|選択|select|Choose",
    re.I,
)
_CARD_LABEL_HINT = re.compile(
    r"\d{4,5}|カード|Card|Business|Corporate|法人|個人|ｘ|X-|•|·|ゴールド|プラチナ",
    re.I,
)


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and value and key not in os.environ:
            os.environ[key] = value


def _wait_ready(page: Page, *, timeout_ms: int = 15000) -> None:
    page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
    try:
        page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 10000))
    except Exception:
        pass


def _sanitize_filename(s: str) -> str:
    s = re.sub(r'[\\/:*?"<>|]', "_", s.strip())
    return s[:80] if s else "card"


def _click_first_visible(page: Page, locator) -> bool:
    return _click_first_visible_ctx(page, locator)


def _click_first_visible_ctx(ctx: UiContext, locator) -> bool:
    for i in range(locator.count()):
        el = locator.nth(i)
        try:
            if el.is_visible():
                el.click()
                return True
        except Exception:
            continue
    return False


def _fill_user_id(page: Page, login_id: str) -> bool:
    selectors = (
        "#eliloUserID",
        'input[name="UserID"]',
        'input[name="userId"]',
        'input[id*="UserID" i]',
        'input[autocomplete="username"]',
    )
    for sel in selectors:
        loc = page.locator(sel)
        if loc.count() > 0 and loc.first.is_visible():
            loc.first.fill(login_id)
            return True
    # ラベル経由
    for label in ("ユーザーID", "User ID", "ユーザー ID"):
        try:
            page.get_by_label(label, exact=False).fill(login_id)
            return True
        except Exception:
            pass
    return False


def _fill_password(page: Page, password: str) -> bool:
    pw = page.locator('input[type="password"]')
    if pw.count() == 0:
        return False
    for i in range(pw.count()):
        el = pw.nth(i)
        try:
            if el.is_visible():
                el.fill(password)
                return True
        except Exception:
            continue
    pw.first.fill(password)
    return True


def _click_login_button(page: Page) -> None:
    patterns = [
        page.get_by_role("button", name=re.compile(r"ログイン|Login|Sign\s*in", re.I)),
        page.locator('button[type="submit"]'),
        page.locator('input[type="submit"]'),
        page.get_by_role("button", name=re.compile(r"次へ|Continue|続行", re.I)),
    ]
    for loc in patterns:
        if _click_first_visible(page, loc):
            return
    raise RuntimeError("ログインボタンが見つかりません")


def _storage_state_path() -> Path:
    raw = os.environ.get("AMEX_STORAGE_STATE", "").strip()
    return Path(raw) if raw else DEFAULT_STORAGE_STATE


def _is_login_url(url: str) -> bool:
    u = url.lower()
    return "/account/login" in u or u.rstrip("/").endswith("/login")


def _is_auth_flow_url(url: str) -> bool:
    """ログイン・2FA 認証中の URL（この間は page.goto で画面を壊さない）。"""
    u = url.lower()
    return _is_login_url(u) or "/reauth/" in u or "/account/reauth" in u


def _looks_logged_in_url(url: str) -> bool:
    u = url.lower()
    if _is_login_url(u):
        return False
    return "global.americanexpress.com" in u or (
        "americanexpress.com" in u and "destpage=" not in u
    )


def _select_account_type(page: Page) -> None:
    """ログイン画面のアカウントタイプを「マイ・アカウント」にする。"""
    sel = page.locator("select").first
    if sel.count() == 0:
        return
    try:
        if sel.is_visible():
            sel.select_option(value="account")
    except Exception:
        try:
            sel.select_option(label="マイ・アカウント")
        except Exception:
            pass


def _login_verified(page: Page) -> bool:
    if _is_auth_flow_url(page.url):
        return False
    try:
        page.goto("https://global.americanexpress.com/activity", wait_until="load", timeout=60000)
        _wait_ready(page, timeout_ms=30000)
        page.wait_for_timeout(2000)
    except Exception:
        pass
    return not _is_login_url(page.url)


def save_storage_state(context, path: Path | None = None) -> None:
    dest = path or _storage_state_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    context.storage_state(path=str(dest))
    print(f"  セッション保存: {dest}")


_2FA_BODY_HINTS = (
    "ワンタイム",
    "確認コード",
    "認証コード",
    "セキュリティコード",
    "二段階",
    "2段階",
    "two-step",
    "two factor",
    "verify your identity",
    "プッシュ通知",
    "SMS",
    "ご本人確認",
    "カード情報の認証",
    "送信先を指定",
    "認証コードを送信します",
)


def _is_2fa_screen(page: Page) -> bool:
    """二段階認証・本人確認画面かどうか。"""
    u = page.url.lower()
    if any(x in u for x in ("challenge", "twofa", "verification", "step-up", "mfa")):
        return True
    try:
        body = page.inner_text("body")
    except Exception:
        return False
    bl = body.lower()
    return any(h.lower() in bl for h in _2FA_BODY_HINTS)


def _login_form_visible(page: Page) -> bool:
    uid = page.locator("#eliloUserID")
    pwd = page.locator("#eliloPassword")
    try:
        return (
            uid.count() > 0
            and uid.first.is_visible()
            and pwd.count() > 0
            and pwd.first.is_visible()
        )
    except Exception:
        return False


def _wait_post_login_transition(page: Page, *, timeout_sec: int = 90) -> str:
    """パスワード送信後、ログイン完了 or 2FA 画面への遷移を待つ。"""
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if _login_verified(page):
            return "logged_in"
        if _is_2fa_method_selection(page):
            return "2fa_method"
        if _is_otp_entry_screen(page):
            return "2fa_otp"
        if _is_2fa_screen(page):
            return "2fa"
        if not _is_login_url(page.url) and not _login_form_visible(page):
            return "navigated"
        page.wait_for_timeout(1500)
    return "timeout"


def _open_login_page(page: Page, *, force: bool = False) -> None:
    """ログイン URL を開く。既にログイン画面なら再読み込みしない（入力が消えるのを防ぐ）。"""
    if not force and (_is_login_url(page.url) or _login_form_visible(page)):
        return
    page.goto(AMEX_LOGIN_URL, wait_until="load", timeout=60000)
    _wait_ready(page)
    page.wait_for_timeout(2000)


def _quiet_wait_for_manual(sec: int) -> None:
    """手動入力前にページを触らず待機する。"""
    if sec <= 0:
        return
    print(f"  [待機] ページ安定まで {sec} 秒お待ちください（入力はその後で構いません）…", flush=True)
    time.sleep(sec)


def _submit_credentials(page: Page, login_id: str, password: str) -> bool:
    """ID/パスワードを自動入力して送信する（2FA 画面には遷移しうる）。"""
    _open_login_page(page)
    _select_account_type(page)

    if not _login_form_visible(page):
        return False

    uid = page.locator("#eliloUserID")
    pwd = page.locator("#eliloPassword")
    uid.click()
    uid.fill("")
    uid.press_sequentially(login_id, delay=50)
    pwd.click()
    pwd.fill("")
    pwd.press_sequentially(password, delay=50)
    page.wait_for_timeout(800)

    def _click_submit() -> None:
        submit = page.locator("#loginSubmit")
        if submit.count() > 0 and submit.first.is_visible():
            submit.first.click()
        else:
            _click_login_button(page)

    _click_submit()
    _wait_ready(page, timeout_ms=45000)
    page.wait_for_timeout(3000)

    # 送信後もログインフォームのままなら再送信（AMEX は1回目が効かないことがある）
    for attempt in range(2):
        if not _login_form_visible(page):
            break
        if _is_2fa_method_selection(page) or _is_otp_entry_screen(page) or _is_2fa_screen(page):
            break
        print(f"  ログインフォームが残っています。再送信 ({attempt + 2}回目)…", flush=True)
        _click_submit()
        try:
            pwd.press("Enter")
        except Exception:
            pass
        _wait_ready(page, timeout_ms=30000)
        page.wait_for_timeout(4000)

    return True


def _focus_browser_window(page: Page) -> None:
    """手動ログイン用にブラウザウィンドウを前面へ。"""
    try:
        page.bring_to_front()
    except Exception:
        pass
    if sys.platform == "darwin":
        try:
            subprocess.run(
                ["osascript", "-e", 'tell application "Google Chrome" to activate'],
                check=False,
                capture_output=True,
            )
        except Exception:
            pass


def _iter_ui_contexts(page: Page):
    """メインページと iframe を走査（2FA UI が iframe 内のことがある）。"""
    yield page
    for fr in page.frames:
        if fr != page.main_frame:
            yield fr


def _ctx_body(ctx: UiContext) -> str:
    try:
        return ctx.inner_text("body", timeout=2000)
    except Exception:
        return ""


def _body_is_method_selection(body: str) -> bool:
    if "送信先を指定" in body or "認証コードを送信します" in body:
        return True
    if "カード情報の認証" in body and "Eメール" in body and "SMS" in body:
        return True
    return "Eメール" in body and "SMS" in body and "認証コード" in body


def _find_method_selection_ctx(page: Page) -> UiContext | None:
    for ctx in _iter_ui_contexts(page):
        if _body_is_method_selection(_ctx_body(ctx)):
            return ctx
    return None


def _is_2fa_method_selection(page: Page) -> bool:
    """2FA 送信先選択画面（SMS / Eメール ラジオ + 次へ）かどうか。"""
    return _find_method_selection_ctx(page) is not None


def _find_otp_entry_ctx(page: Page) -> UiContext | None:
    if _is_2fa_method_selection(page):
        return None
    for ctx in _iter_ui_contexts(page):
        body = _ctx_body(ctx)
        if not body:
            continue
        has_code_hint = any(
            k in body
            for k in ("確認コードを入力", "認証コードを入力", "コードを入力", "ワンタイムパスワード")
        )
        if not has_code_hint and "認証コード" not in body and "確認コード" not in body:
            continue
        if ctx.locator('input[autocomplete="one-time-code"]').count() > 0:
            return ctx
        if ctx.locator('input[type="radio"]').count() >= 2:
            continue
        inputs = ctx.locator(
            'input[type="text"], input[type="tel"], input[inputmode="numeric"], '
            'input[maxlength="1"], input[name*="code" i], input[id*="code" i]'
        )
        for i in range(inputs.count()):
            try:
                if inputs.nth(i).is_visible():
                    return ctx
            except Exception:
                continue
        if has_code_hint:
            return ctx
    return None


def _is_otp_entry_screen(page: Page) -> bool:
    """確認コード入力画面（送信先選択の次）かどうか。"""
    return _find_otp_entry_ctx(page) is not None


def _wait_for_2fa_method_selection(page: Page, *, timeout_sec: int = 120) -> bool:
    """2FA 送信先選択画面が出るまでポーリング待機。"""
    print(f"  [2FA] 送信先選択画面を待機（最大 {timeout_sec} 秒）…", flush=True)
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if _is_2fa_method_selection(page):
            print("  [2FA] 送信先選択画面を検出", flush=True)
            return True
        if _is_otp_entry_screen(page):
            print("  [2FA] 確認コード入力画面を検出（送信先選択をスキップ）", flush=True)
            return False
        page.wait_for_timeout(2000)
    print("  [2FA] 送信先選択画面がタイムアウト", file=sys.stderr)
    return False


def _wait_for_otp_entry_screen(page: Page, *, timeout_sec: int = 45) -> bool:
    """「次へ」後、確認コード入力欄が出るまで待機。"""
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if _is_otp_entry_screen(page):
            return True
        page.wait_for_timeout(1500)
    return _is_otp_entry_screen(page)


def _select_email_2fa_radio(ctx: UiContext, page: Page) -> bool:
    """
    AMEX「カード情報の認証:認証コード」画面で Eメール ラジオを選択する。
    （SMS ではなく Eメール側。マスク表示の @gmail.com 等を含む行）
    """
    # 0) Eメール 行全体をクリック（カスタム UI 対策）
    for loc in (
        ctx.locator("label").filter(has_text=re.compile(r"^Eメール$")),
        ctx.get_by_text(re.compile(r"^Eメール$"), exact=True),
    ):
        for i in range(loc.count()):
            el = loc.nth(i)
            try:
                if el.is_visible():
                    el.click()
                    page.wait_for_timeout(800)
                    print("  2FA: Eメール をクリックしました")
                    return True
            except Exception:
                continue

    # 1) 「Eメール」見出しと同じブロック内のラジオ
    for heading in ctx.get_by_text(re.compile(r"^Eメール$")).all():
        try:
            if not heading.is_visible():
                continue
            container = heading.locator(
                "xpath=ancestor::*[self::div or self::li or self::section or self::fieldset][1]"
            )
            radio = container.locator('input[type="radio"]').first
            if radio.count() > 0:
                radio.check(force=True)
                page.wait_for_timeout(800)
                print("  2FA: Eメール ラジオを選択しました")
                return True
        except Exception:
            continue

    # 2) アクセシブル名に @ / gmail を含むラジオ
    for loc in (
        ctx.get_by_role("radio", name=re.compile(r"gmail\.com|@", re.I)),
        ctx.get_by_role("radio", name=re.compile(r"Eメール|E-mail", re.I)),
    ):
        for i in range(loc.count()):
            r = loc.nth(i)
            try:
                if r.is_visible():
                    r.check(force=True)
                    page.wait_for_timeout(800)
                    print("  2FA: Eメール ラジオを選択しました（名前一致）")
                    return True
            except Exception:
                continue

    # 3) 可視ラジオの周辺テキストで Eメール / @ を判定
    radios = ctx.locator('input[type="radio"]')
    for i in range(radios.count()):
        r = radios.nth(i)
        try:
            if not r.is_visible():
                continue
            parent = r.locator("xpath=ancestor::*[self::div or self::li][1]")
            text = parent.inner_text(timeout=2000) if parent.count() else ""
            if "@" in text or "gmail" in text.lower() or "Eメール" in text:
                r.check(force=True)
                page.wait_for_timeout(800)
                print("  2FA: Eメール ラジオを選択しました（ブロック判定）")
                return True
        except Exception:
            continue

    # 4) フォールバック: 2番目のラジオ（AMEX 既定は SMS=1件目, Eメール=2件目）
    if radios.count() >= 2:
        r = radios.nth(1)
        try:
            if r.is_visible():
                r.check(force=True)
                page.wait_for_timeout(800)
                print("  2FA: Eメール ラジオを選択しました（2番目）")
                return True
        except Exception:
            pass
    return False


def _click_2fa_next(ctx: UiContext, page: Page) -> bool:
    """送信先選択後の「次へ」で認証コードのメール送信を開始する。"""
    for loc in (
        ctx.get_by_role("button", name=re.compile(r"^次へ$")),
        ctx.get_by_role("button", name=re.compile(r"^Next$", re.I)),
    ):
        if _click_first_visible_ctx(ctx, loc):
            page.wait_for_timeout(3500)
            print("  「次へ」をクリックしました（認証コードをメール送信）")
            return True
    return False


def _fill_otp_code(ctx: UiContext, code: str) -> bool:
    """確認コード入力欄に 6 桁を入力する。"""
    if len(code) != 6 or not code.isdigit():
        return False

    single = ctx.locator('input[maxlength="1"], input[aria-label*="digit" i]')
    if single.count() >= 6:
        for i, ch in enumerate(code):
            single.nth(i).fill(ch)
        print("  確認コードを入力しました（分割フィールド）")
        return True

    candidates = (
        'input[autocomplete="one-time-code"]',
        'input[name*="otp" i]',
        'input[name*="code" i]',
        'input[id*="otp" i]',
        'input[id*="code" i]',
        'input[type="tel"]',
        'input[inputmode="numeric"]',
    )
    for sel in candidates:
        loc = ctx.locator(sel)
        for i in range(loc.count()):
            el = loc.nth(i)
            try:
                if el.is_visible():
                    el.fill(code)
                    print("  確認コードを入力しました")
                    return True
            except Exception:
                continue

    # 汎用テキスト（2FA 画面のみ）
    for inp in ctx.locator('input[type="text"]').all():
        try:
            if inp.is_visible():
                inp.fill(code)
                print("  確認コードを入力しました（text）")
                return True
        except Exception:
            continue
    return False


def _submit_otp_code(ctx: UiContext, page: Page) -> bool:
    """確認コード送信ボタンをクリック。"""
    for loc in (
        ctx.get_by_role("button", name=re.compile(r"^次へ$|確認|送信|続行|Submit|Verify|ログイン", re.I)),
        ctx.locator('button[type="submit"]'),
    ):
        if _click_first_visible_ctx(ctx, loc):
            page.wait_for_timeout(3000)
            print("  確認コードを送信しました")
            return True
    return False


def _run_2fa_email_flow(page: Page, *, not_before_epoch: float) -> bool:
    """
    AMEX 2FA 自動化（4 ステップ）:
      1. 送信先選択画面で Eメール を選択
      2. 「次へ」でコード送信
      3. Gmail API で確認コード取得
      4. 確認コード入力 → 送信
    """
    from amex_gmail_2fa import fetch_amex_otp_from_gmail, gmail_2fa_enabled

    if not gmail_2fa_enabled():
        return False

    print("\n--- AMEX 2FA 自動化（Eメール → Gmail）---", flush=True)
    mail_since = not_before_epoch

    otp_ctx = _find_otp_entry_ctx(page)
    method_ctx = _find_method_selection_ctx(page) if not otp_ctx else None
    if not method_ctx and not otp_ctx:
        if _wait_for_2fa_method_selection(page, timeout_sec=120):
            method_ctx = _find_method_selection_ctx(page)
            otp_ctx = _find_otp_entry_ctx(page)

    # Step 1 & 2: Eメール → 次へ（コード入力画面のときはスキップ）
    if method_ctx and not otp_ctx:
        print("  [Step 1] Eメール を選択…", flush=True)
        if not _select_email_2fa_radio(method_ctx, page):
            print("  Eメール 選択に失敗。手動で選んでください。", file=sys.stderr)
            return False
        print("  [Step 2] 「次へ」をクリック…", flush=True)
        if not _click_2fa_next(method_ctx, page):
            print("  「次へ」が見つかりません。", file=sys.stderr)
            return False
        mail_since = time.time() - 3
        _wait_for_otp_entry_screen(page, timeout_sec=45)
        otp_ctx = _find_otp_entry_ctx(page)

    # Step 3: Gmail から確認コード取得
    print("  [Step 3] Gmail から確認コードを取得…", flush=True)
    code = fetch_amex_otp_from_gmail(not_before_epoch=mail_since, timeout_sec=180)
    if not code:
        return False

    # Step 4: 入力 → 送信
    print("  [Step 4] 確認コードを入力…", flush=True)
    if not otp_ctx:
        _wait_for_otp_entry_screen(page, timeout_sec=30)
        otp_ctx = _find_otp_entry_ctx(page) or page
    if not _fill_otp_code(otp_ctx, code):
        print("  確認コードの入力に失敗", file=sys.stderr)
        return False
    _submit_otp_code(otp_ctx, page)
    page.wait_for_timeout(5000)

    if _login_verified(page):
        print("  2FA 自動完了", flush=True)
        return True
    if not _is_2fa_screen(page) and not _is_login_url(page.url):
        return _login_verified(page)
    return False


def _complete_2fa_via_gmail(page: Page, *, not_before_epoch: float) -> bool:
    """後方互換ラッパー。"""
    return _run_2fa_email_flow(page, not_before_epoch=not_before_epoch)


def _print_auth_wait_banner(page: Page, *, manual_credentials: bool = False) -> None:
    print("\n" + "=" * 60)
    if _is_2fa_screen(page) or _is_2fa_method_selection(page) or _is_otp_entry_screen(page):
        print("  AMEX: 二段階認証（2FA）")
        print("  Eメール ラジオ →「次へ」→ Gmail API で確認コードを自動取得・入力します。")
        print("  自動取得に失敗した場合はブラウザで手動入力してください。")
    elif _is_login_url(page.url) and _login_form_visible(page):
        print("  AMEX: ブラウザで手動ログインしてください")
        print(f"  {AMEX_LOGIN_URL}")
        if manual_credentials:
            print("  ID・パスワードを入力し「ログイン」を押してください。")
        else:
            print("  （ID・パスワードは自動入力済みの場合があります）")
    else:
        print("  AMEX: ログイン完了を待機しています")
    print("  認証完了を自動検知して続行します（ブラウザは閉じないでください）")
    print("=" * 60 + "\n")


def _retry_login_submit_if_form_visible(page: Page) -> bool:
    """ログインフォームが残っているとき #loginSubmit を再クリック。"""
    if not _login_form_visible(page):
        return False
    if _is_2fa_method_selection(page) or _is_otp_entry_screen(page):
        return False
    try:
        submit = page.locator("#loginSubmit")
        if submit.count() > 0 and submit.first.is_visible():
            print("  [自動] ログインボタンを再クリック…", flush=True)
            submit.first.click()
            page.wait_for_timeout(4000)
            return True
    except Exception:
        pass
    return False


def _wait_auth_completion(
    page: Page,
    *,
    timeout_sec: int = 600,
    not_before_epoch: float | None = None,
    gmail_2fa_tried: bool = False,
    manual_credentials: bool = False,
    allow_login_retry: bool = True,
    quiet_sec: int = 0,
) -> bool:
    """2FA・手動ログイン完了まで待つ（現在の画面を維持。login URL へ戻さない）。"""
    _quiet_wait_for_manual(quiet_sec)
    if not manual_credentials:
        _focus_browser_window(page)
    _print_auth_wait_banner(page, manual_credentials=manual_credentials)

    last_url = ""
    last_2fa_notice = 0.0
    last_2fa_attempt = 0.0
    last_manual_hint = 0.0
    last_login_retry = 0.0
    deadline = time.time() + timeout_sec
    nb = not_before_epoch or (time.time() - 60)

    while time.time() < deadline:
        cur = page.url
        if cur != last_url:
            print(f"  [待機] URL: {cur[:100]}")
            last_url = cur

        on_2fa = (
            _is_2fa_method_selection(page) or _is_otp_entry_screen(page) or _is_2fa_screen(page)
        )

        # 2FA 画面はログイン URL 上でも先に判定（出たり消えたりするため繰り返し試行）
        if on_2fa:
            now = time.time()
            if not gmail_2fa_tried or (now - last_2fa_attempt > 60):
                gmail_2fa_tried = True
                last_2fa_attempt = now
                nb = time.time() - 5
                if _run_2fa_email_flow(page, not_before_epoch=nb):
                    return True
            if now - last_2fa_notice > 30:
                print("  → 二段階認証の完了をお待ちしています（手動でも可）…")
                last_2fa_notice = now
            page.wait_for_timeout(2000)
            continue

        if not on_2fa and not _is_auth_flow_url(cur):
            if _looks_logged_in_url(cur) or not _is_login_url(cur):
                if _login_verified(page):
                    print(f"  認証完了: {page.url}")
                    return True

        if _is_login_url(cur) and _login_form_visible(page) and not on_2fa:
            now = time.time()
            if allow_login_retry and now - last_login_retry > 20:
                _retry_login_submit_if_form_visible(page)
                last_login_retry = now
            if now - last_manual_hint > 90:
                if manual_credentials:
                    print(
                        "  → ブラウザで ID/パスワードを入力し「ログイン」を押してください。"
                        "2FA 画面が出たら Eメール → 次へ を自動実行します。",
                        flush=True,
                    )
                else:
                    print(
                        "  → Chrome で「ログイン」を押すと 2FA 画面が出る場合があります。"
                        "出たら Eメール → 次へ を自動実行します。",
                        flush=True,
                    )
                    _focus_browser_window(page)
                last_manual_hint = now
            page.wait_for_timeout(5000 if manual_credentials else 2000)
            continue

        page.wait_for_timeout(5000 if manual_credentials else 2000)

    return False


def _login(
    page: Page,
    login_id: str,
    password: str,
    *,
    headed: bool = False,
    manual_login: bool = False,
    manual_credentials: bool = False,
    auth_timeout_sec: int = 600,
    quiet_sec: int = 0,
) -> None:
    """AMEX マイアカウントにログインする（2FA 対応・evaluate 不使用）。"""
    page.on("dialog", lambda dialog: dialog.accept())

    if not manual_credentials and _login_verified(page):
        print(f"  既にログイン済み: {page.url}")
        return

    not_before = time.time()
    submitted = False
    transition = "manual"

    if manual_credentials:
        _open_login_page(page)
        _quiet_wait_for_manual(quiet_sec)
        _focus_browser_window(page)
        print("  [手動ログイン] ブラウザで ID/パスワードを入力し「ログイン」を押してください。", flush=True)
        print(f"  {AMEX_LOGIN_URL}", flush=True)
    else:
        submitted = _submit_credentials(page, login_id, password)
        if submitted:
            print("  ID/パスワードを送信しました。")
            not_before = time.time() - 5
            transition = _wait_post_login_transition(page, timeout_sec=90)
            print(f"  ログイン後の遷移: {transition}", flush=True)
        else:
            print("  ログインフォームが見つかりません。手動ログインに切り替えます。", file=sys.stderr)
            _open_login_page(page)
            manual_credentials = True

    if _login_verified(page):
        print(f"  ログイン成功（2FA 不要）: {page.url}")
        return

    gmail_tried = False
    needs_2fa = transition in ("2fa", "2fa_method", "2fa_otp", "navigated") or (
        _is_2fa_screen(page) or _is_2fa_method_selection(page) or _is_otp_entry_screen(page)
    )
    if needs_2fa:
        print("  二段階認証画面を検出（または待機中）", flush=True)
        gmail_tried = True
        if _run_2fa_email_flow(page, not_before_epoch=not_before):
            if _login_verified(page):
                print(f"  ログイン成功: {page.url}")
                return
    elif transition == "timeout" and submitted:
        print("  2FA 画面の出現を待機ループに委譲します（最大90秒経過済み）", flush=True)
    elif not submitted and not manual_credentials:
        print("  自動入力に失敗したため、ブラウザでログインを完了してください。", file=sys.stderr)

    if not (headed or manual_login):
        raise RuntimeError(
            "AMEX は二段階認証が必要です。初回は --headless を付けず実行するか、"
            " amex_login_session.py でセッション保存後に --headless を使ってください。"
        )

    if _wait_auth_completion(
        page,
        timeout_sec=auth_timeout_sec,
        not_before_epoch=not_before,
        gmail_2fa_tried=gmail_tried,
        manual_credentials=manual_credentials,
        allow_login_retry=not manual_credentials,
        quiet_sec=0,
    ):
        return

    raise RuntimeError(
        f"AMEX へのログインがタイムアウトしました（{auth_timeout_sec}秒）。"
        " 二段階認証を完了してから amex_login_session.py でセッション保存し、"
        " 再実行してください。"
    )


def _wait_manual_login(page: Page, *, timeout_sec: int = 600) -> bool:
    """後方互換: 手動ログイン／2FA 完了待ち。"""
    _open_login_page(page)
    return _wait_auth_completion(page, timeout_sec=timeout_sec)


def _list_cards(page: Page) -> list[dict]:
    """アカウント内のカード一覧を返す（利用履歴画面のカード切替のみ）。"""
    page.goto("https://global.americanexpress.com/activity", wait_until="load", timeout=60000)
    _wait_ready(page, timeout_ms=30000)
    page.wait_for_timeout(2000)

    cards: list[dict] = []
    seen: set[str] = set()

    visible_selects = []
    for sel in page.locator("select").all():
        try:
            if sel.is_visible():
                visible_selects.append(sel)
        except Exception:
            continue

    for si, sel in enumerate(visible_selects):
        for opt in sel.locator("option").all():
            try:
                label = (opt.inner_text() or "").strip()
                value = opt.get_attribute("value") or ""
            except Exception:
                continue
            if not label or len(label) < 3 or label in seen:
                continue
            if _NAV_OPTION_SKIP.search(label):
                continue
            if not _CARD_LABEL_HINT.search(label):
                continue
            seen.add(label)
            cards.append({
                "label": label,
                "kind": "select",
                "value": value,
                "select_index": si,
            })

    if not cards:
        return [{"label": "default", "kind": "default", "index": 0}]
    return [{**c, "index": i} for i, c in enumerate(cards)]


def _select_card(page: Page, card: dict) -> None:
    """指定カードに切り替える。"""
    if card.get("kind") == "default":
        return
    label = card["label"]
    if card.get("kind") == "select":
        visible_selects = []
        for sel in page.locator("select").all():
            try:
                if sel.is_visible():
                    visible_selects.append(sel)
            except Exception:
                continue
        idx = card.get("select_index", 0)
        targets = [visible_selects[idx]] if idx < len(visible_selects) else visible_selects
        for sel in targets:
            try:
                if not sel.is_visible():
                    continue
                if card.get("value"):
                    sel.select_option(value=card["value"])
                else:
                    sel.select_option(label=label)
                _wait_ready(page)
                page.wait_for_timeout(1500)
                return
            except Exception:
                continue
        raise RuntimeError(f"カード切替に失敗: {label}")


def _navigate_search(page: Page, start: date, end: date) -> None:
    """期間指定の利用履歴検索画面へ遷移する。"""
    url = f"{ACTIVITY_SEARCH_URL}?from={start.isoformat()}&to={end.isoformat()}"
    page.goto(url, wait_until="load", timeout=60000)
    _wait_ready(page, timeout_ms=30000)
    page.wait_for_timeout(2000)

    body = page.inner_text("body")
    if "ご利用" in body or "activity" in page.url.lower():
        return

    page.goto("https://global.americanexpress.com/activity", wait_until="load")
    _wait_ready(page)
    page.wait_for_timeout(1500)

    for text in ("絞り込み検索", "ご利用履歴の検索", "Search"):
        link = page.get_by_text(text, exact=False)
        if _click_first_visible(page, link):
            break
    page.wait_for_timeout(1000)

    date_inputs = page.locator('input[type="date"]')
    if date_inputs.count() >= 2:
        date_inputs.nth(0).fill(start.isoformat())
        date_inputs.nth(1).fill(end.isoformat())

    search_btn = page.get_by_role("button", name=re.compile(r"検索|Search", re.I))
    _click_first_visible(page, search_btn)
    _wait_ready(page, timeout_ms=30000)


def _download_excel(page: Page, dest_path: Path) -> None:
    """検索結果から Excel をダウンロードする。"""
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    dl_btn = page.get_by_text(re.compile(r"ダウンロード|Download", re.I))
    if not _click_first_visible(page, dl_btn):
        raise RuntimeError("ダウンロードボタンが見つかりません")

    page.wait_for_timeout(1500)

    with page.expect_download(timeout=120000) as dl_info:
        excel_btn = page.get_by_text(re.compile(r"^Excel$", re.I))
        if not _click_first_visible(page, excel_btn):
            excel_btn2 = page.get_by_text("Excel", exact=False)
            if not _click_first_visible(page, excel_btn2):
                raise RuntimeError("Excel 形式の選択肢が見つかりません")
        download = dl_info.value

    download.save_as(str(dest_path))


def _unique_dest(output_dir: Path, card_label: str, start: date, end: date) -> Path:
    safe = _sanitize_filename(card_label)
    base = f"activity_{start.isoformat()}_{end.isoformat()}_{safe}.xlsx"
    dest = output_dir / base
    if not dest.exists():
        return dest
    n = 1
    while True:
        alt = output_dir / f"activity_{start.isoformat()}_{end.isoformat()}_{safe}_{n}.xlsx"
        if not alt.exists():
            return alt
        n += 1


def download_period(
    page: Page,
    *,
    start_date: date,
    end_date: date,
    output_dir: Path,
    dry_run: bool = False,
) -> list[dict]:
    """ログイン済み page で指定期間の全カード分をダウンロード。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    period_label = f"{start_date.isoformat()}_{end_date.isoformat()}"
    results: list[dict] = []

    cards = _list_cards(page)
    print(f"  カード数: {len(cards)}")
    for c in cards:
        print(f"    - {c['label']}")

    for card in cards:
        label = card["label"]
        print(f"\n  --- カード: {label} ---")
        try:
            _select_card(page, card)
            _navigate_search(page, start_date, end_date)

            if dry_run:
                results.append({
                    "period": period_label,
                    "card": label,
                    "path": None,
                    "status": "dry-run",
                })
                continue

            dest = _unique_dest(output_dir, label, start_date, end_date)
            _download_excel(page, dest)
            print(f"  ✅ 保存: {dest.name}")
            results.append({
                "period": period_label,
                "card": label,
                "path": dest,
                "status": "ok",
            })
        except Exception as e:
            print(f"  ⚠ 失敗 ({label}): {e}", file=sys.stderr)
            results.append({
                "period": period_label,
                "card": label,
                "path": None,
                "status": f"error: {e}",
            })

    return results


def run(
    *,
    start_date: date,
    end_date: date,
    output_dir: Path,
    headed: bool = True,
    dry_run: bool = False,
    pause_on_error: bool = True,
    page: Page | None = None,
    own_browser: bool = True,
) -> list[dict]:
    """指定期間の AMEX 利用履歴 Excel を全カード分ダウンロードする。"""
    login_id = os.environ.get("AMEX_LOGIN_ID", "")
    password = os.environ.get("AMEX_PASSWORD", "")

    if page is None and not all([login_id, password]):
        print(
            "エラー: AMEX_LOGIN_ID / AMEX_PASSWORD が未設定です。\n"
            f"  → {DEFAULT_ENV_PATH} を編集してください",
            file=sys.stderr,
        )
        sys.exit(1)

    if page is not None:
        return download_period(
            page, start_date=start_date, end_date=end_date,
            output_dir=output_dir, dry_run=dry_run,
        )

    results: list[dict] = []
    with sync_playwright() as pw:
        launch_kw: dict = {"headless": not headed}
        try:
            launch_kw["channel"] = "chrome"
            launch_kw["args"] = ["--disable-blink-features=AutomationControlled"]
        except Exception:
            pass
        browser = pw.chromium.launch(**launch_kw)
        ctx_kw: dict = {"locale": "ja-JP", "accept_downloads": True}
        state_path = _storage_state_path()
        if state_path.exists():
            ctx_kw["storage_state"] = str(state_path)
        context = browser.new_context(**ctx_kw)
        pg = context.new_page()
        try:
            print("[1/3] AMEX ログイン中...")
            if state_path.exists() and _login_verified(pg):
                print(f"  保存済みセッションを使用: {state_path}")
            else:
                _login(pg, login_id, password, headed=headed, manual_login=headed)
                save_storage_state(context)
            print("[2/3] カード一覧を取得...")
            print(f"[3/3] 期間 {start_date} 〜 {end_date} をダウンロード...")
            results = download_period(
                pg, start_date=start_date, end_date=end_date,
                output_dir=output_dir, dry_run=dry_run,
            )
        except PlaywrightTimeoutError as e:
            print(f"タイムアウト: {e}", file=sys.stderr)
            if pause_on_error and headed:
                try:
                    pg.pause()
                except KeyboardInterrupt:
                    pass
        except Exception as e:
            print(f"エラー: {e}", file=sys.stderr)
            if pause_on_error and headed:
                try:
                    pg.pause()
                except KeyboardInterrupt:
                    pass
        finally:
            if own_browser:
                context.close()
                browser.close()

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="AMEX 利用履歴 Excel をダウンロード")
    parser.add_argument("--start-date", required=True, help="開始日 YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="終了日 YYYY-MM-DD")
    parser.add_argument("--output-dir", required=True, help="保存先（00_元ファイル_サイト取得/AMEX/）")
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_PATH))
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-pause", action="store_true")
    args = parser.parse_args()

    _load_env_file(Path(args.env_file))

    start = datetime.strptime(args.start_date, "%Y-%m-%d").date()
    end = datetime.strptime(args.end_date, "%Y-%m-%d").date()

    results = run(
        start_date=start,
        end_date=end,
        output_dir=Path(args.output_dir),
        headed=not args.headless,
        dry_run=args.dry_run,
        pause_on_error=not args.no_pause,
    )

    ok = sum(1 for r in results if r["status"] == "ok")
    print(f"\n完了: {ok}/{len(results)} 件")
    sys.exit(0 if ok > 0 else 1)


if __name__ == "__main__":
    main()
