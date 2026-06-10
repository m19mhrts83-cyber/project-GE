#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LIMO（Raimo）アプリに管理者ログインし、CSV取込を自動実行する。

必須環境変数:
  LIMO_APP_URL
  1段目（ライモBiz等のポータル）:
    LIMO_PORTAL_EMAIL / LIMO_PORTAL_PASSWORD（推奨）
    または LIMO_ADMIN_EMAIL / LIMO_ADMIN_PASSWORD（後方互換。PORTAL 未設定時に1段目へ使用）
  2段目（ミニアプリのログイン）:
    LIMO_APP_EMAIL / LIMO_APP_PASSWORD（ポータル通過後にアプリのログイン画面が出る場合に必須）

任意環境変数:
  LIMO_HEADLESS=1/0 (既定: 1)
  LIMO_UPLOAD_TIMEOUT_SEC (既定: 1800)
  LIMO_SLOW_MO_MS (既定: 0)
  LIMO_LOGIN_WAIT_MS (ログイン画面の要素待ち ms、既定: 120000)
  LIMO_POST_LOGIN_WAIT_MS (ラッパーログイン後〜#mainView 表示まで ms、既定: 180000)
  LIMO_TRY_COMMUNITY_REFRESH=1/0 (既定: 1) CSV取込後に「コミュニティ情報の最新化」相当の操作を試す
  LIMO_COMMUNITY_REFRESH_TIMEOUT_SEC (既定: 300) 上記の完了待ち秒
  LIMO_NOTIFY_MACOS=1/0 (既定: 1) macOS のみ終了時に通知センターへ表示（osascript）

使い方:
  python3 upload_csv_to_limo.py --csv /path/to/delta.csv
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

try:
    from playwright.sync_api import TimeoutError as PwTimeoutError
    from playwright.sync_api import sync_playwright
except Exception as e:  # pragma: no cover
    print(
        "playwright が見つかりません。`pip install playwright` と "
        "`playwright install chromium` を実行してください。\n"
        f"detail: {e}",
        file=sys.stderr,
    )
    raise SystemExit(2)


def get_required_env(key: str) -> str:
    value = os.environ.get(key, "").strip()
    if not value:
        raise RuntimeError(f"環境変数 {key} が未設定です")
    return value


def get_env_bool(key: str, default: bool) -> bool:
    raw = os.environ.get(key)
    if raw is None:
        return default
    return raw.strip().lower() not in ("0", "false", "no")


def _applescript_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def maybe_macos_notify_done(exit_code: int, detail: str) -> None:
    """
    処理終了時に macOS の通知センターへ表示する。
    Linux 等では何もしない。LIMO_NOTIFY_MACOS=0 で無効。
    """
    if sys.platform != "darwin":
        return
    if not get_env_bool("LIMO_NOTIFY_MACOS", True):
        return
    d = (detail or "").strip()
    if len(d) > 280:
        d = d[:277] + "..."
    d_esc = _applescript_escape(d)
    if exit_code == 0:
        title = "LIMO CSV取込 完了"
    elif exit_code == 1:
        title = "LIMO CSV取込 完了（NGあり）"
    else:
        title = "LIMO CSV取込 失敗"
    title_esc = _applescript_escape(title)
    try:
        subprocess.run(
            [
                "osascript",
                "-e",
                f'display notification "{d_esc}" with title "{title_esc}"',
            ],
            check=False,
            timeout=15,
            capture_output=True,
        )
    except Exception:
        pass


def _login_error_markers() -> tuple[str, ...]:
    return (
        "メールアドレス、または、パスワードが違います",
        "パスワードが違います",
        "パスワードが間違っています",
        "メールアドレスまたはパスワードが間違っています",
        "invalid_credentials",
    )


def _email_selectors() -> list[str]:
    return [
        "#loginEmail",
        'input[placeholder="メールアドレス"]',
        'input[placeholder="ユーザー名"]',
        "input[placeholder*='メール']",
        "input[placeholder*='ユーザー']",
        'input[type="email"]',
        'input[name="email"]',
        'input[name="username"]',
        'input[name*="mail"]',
        'input[id="username"]',
        'input[id*="mail"]',
        'input[id*="user"]',
        'input[autocomplete="username"]',
        'input[type="text"]',
    ]


def _password_selectors() -> list[str]:
    return [
        "#loginPassword",
        'input[placeholder="パスワード"]',
        'input[type="password"]',
        'input[name="password"]',
        'input[name="passwd"]',
        'input[id="password"]',
        'input[id="passwd"]',
        'input[autocomplete="current-password"]',
    ]


def _all_frames(page):
    """メインフレーム優先。iframe 内のミニアプリにも対応。"""
    main = page.main_frame
    out = [main]
    for fr in page.frames:
        if fr != main:
            out.append(fr)
    return out


def _body_text_joined(page) -> str:
    parts: list[str] = []
    for fr in _all_frames(page):
        try:
            parts.append(fr.locator("body").inner_text(timeout=1500))
        except Exception:
            pass
    return "\n".join(parts)


def _main_view_visible(page) -> bool:
    for fr in _all_frames(page):
        try:
            if fr.locator("#mainView").first.is_visible():
                return True
        except Exception:
            pass
    return False


def _login_email_field_visible_in_frame(fr) -> bool:
    for sel in _email_selectors():
        loc = fr.locator(sel).first
        try:
            if loc.is_visible():
                return True
        except Exception:
            pass
    return False


def _app_login_form_visible(page) -> bool:
    """#mainView ではなく、どこかのフレームにログインフォームが見えている。"""
    if _main_view_visible(page):
        return False
    for fr in _all_frames(page):
        if _login_email_field_visible_in_frame(fr):
            return True
    return False


def _fill_limo_login_on_frame(fr, email: str, password: str, timeout_ms: int) -> None:
    """単一フレーム上のログインフォームを埋めて送信する。"""

    def _first_working_locator(selectors: list[str], per_try_ms: int = 8000):
        for sel in selectors:
            loc = fr.locator(sel).first
            try:
                loc.wait_for(state="visible", timeout=per_try_ms)
                return loc
            except Exception:
                continue
        return None

    per = min(30000, max(5000, timeout_ms // 4))
    email_loc = _first_working_locator(
        _email_selectors(),
        per_try_ms=per,
    )
    if email_loc is None:
        # 一部画面では「ログイン」導線を押して初めて入力欄が出る
        for sel in (
            "button:has-text('ログイン')",
            "a:has-text('ログイン')",
            "button:has-text('Sign in')",
            "a:has-text('Sign in')",
        ):
            try:
                btn = fr.locator(sel).first
                if btn.count() and btn.is_visible():
                    btn.click(timeout=5000)
                    fr.wait_for_timeout(600)
                    email_loc = _first_working_locator(_email_selectors(), per_try_ms=per)
                    if email_loc is not None:
                        break
            except Exception:
                continue
    if email_loc is None:
        try:
            email_loc = fr.get_by_placeholder("メールアドレス").first
            email_loc.wait_for(state="visible", timeout=per)
        except Exception:
            email_loc = None
    if email_loc is None:
        # パスワード欄だけ先に見つかるUIでは、可視な text/email をID欄として使う
        try:
            pw_probe = _first_working_locator(_password_selectors(), per_try_ms=1500)
            if pw_probe is not None:
                candidate = fr.locator(
                    "input[type='text'],input[type='email'],input[autocomplete='username']"
                ).first
                if candidate.count() and candidate.is_visible():
                    email_loc = candidate
        except Exception:
            email_loc = None
    if email_loc is None:
        raise PwTimeoutError("メール入力欄（#loginEmail / プレースホルダー）が見つかりません")

    email_loc.fill(email, timeout=timeout_ms)

    pw_loc = _first_working_locator(
        _password_selectors(),
        per_try_ms=per,
    )
    if pw_loc is None:
        try:
            pw_loc = fr.get_by_placeholder("パスワード").first
            pw_loc.wait_for(state="visible", timeout=per)
        except Exception:
            pw_loc = None
    if pw_loc is None:
        raise PwTimeoutError("パスワード入力欄が見つかりません")
    pw_loc.fill(password, timeout=timeout_ms)

    clicked = False
    for sel in ("#loginSubmitBtn", "button:has-text('ログイン')"):
        btn = fr.locator(sel).first
        try:
            if btn.count() and btn.is_visible():
                btn.click(timeout=timeout_ms)
                clicked = True
                break
        except Exception:
            continue
    if not clicked:
        try:
            fr.get_by_role("button", name="ログイン").click(timeout=timeout_ms)
        except Exception:
            pw_loc.press("Enter")


def _fill_limo_login(page, email: str, password: str, timeout_ms: int) -> None:
    """表示中のログインフォームを検出して埋める（iframe 対応）。"""
    per = min(8000, max(2000, timeout_ms // 8))
    deadline = time.time() + timeout_ms / 1000.0
    last_err: Exception | None = None
    login_surface_retry = 0
    while time.time() < deadline:
        for fr in _all_frames(page):
            if not _login_email_field_visible_in_frame(fr):
                continue
            try:
                _fill_limo_login_on_frame(fr, email, password, timeout_ms)
                return
            except Exception as e:
                last_err = e
        # どのフレームにも入力欄が見えない場合、ログイン導線を押して再試行
        login_surface_retry += 1
        if login_surface_retry % 4 == 0:
            for fr in _all_frames(page):
                for sel in (
                    "button:has-text('ログイン')",
                    "a:has-text('ログイン')",
                    "button:has-text('Sign in')",
                    "a:has-text('Sign in')",
                ):
                    try:
                        btn = fr.locator(sel).first
                        if btn.count() and btn.is_visible():
                            btn.click(timeout=3000)
                            page.wait_for_timeout(500)
                            break
                    except Exception:
                        continue
        page.wait_for_timeout(300)
    if last_err is not None:
        raise last_err
    raise PwTimeoutError("ログインフォーム（メール入力欄）がどのフレームにも見つかりません")


def wait_initial_auth_state(page, timeout_ms: int) -> str:
    """
    初期表示で、以下のどれが先に出るかを判定する。
    - main: すでに #mainView が表示されている
    - login_form: ログインフォームが表示されている
    """
    deadline = time.time() + timeout_ms / 1000.0
    while time.time() < deadline:
        if _main_view_visible(page):
            return "main"
        if _app_login_form_visible(page):
            return "login_form"
        page.wait_for_timeout(300)
    raise PwTimeoutError(
        f"初期認証状態の判定がタイムアウトしました（{timeout_ms}ms）。"
        "#mainView もログインフォームも確認できませんでした。"
    )


def _login_in_progress(body: str) -> bool:
    return any(x in body for x in ("処理中です", "ログイン中", "読み込み中"))


def _check_login_errors_in_page(body: str, stage_hint: str) -> None:
    if _login_in_progress(body):
        return
    for m in _login_error_markers():
        if m in body:
            raise RuntimeError(
                f"{stage_hint}ログインに失敗しました（{m}）。"
                "該当段のメール・パスワードを .env で確認してください。"
            )


def wait_until_main_or_app_login(page, timeout_ms: int, *, stage_hint: str) -> str:
    """
    ログイン送信後、#mainView まで行くか、2段目のアプリログイン画面が出るまで待つ。
    戻り値: 'main' | 'app_login'
    """
    deadline = time.time() + timeout_ms / 1000.0
    while time.time() < deadline:
        if _main_view_visible(page):
            return "main"
        body = _body_text_joined(page)
        _check_login_errors_in_page(body, stage_hint)
        if _app_login_form_visible(page):
            return "app_login"
        page.wait_for_timeout(400)
    raise PwTimeoutError(
        f"{stage_hint}: タイムアウト（{timeout_ms}ms）。"
        "#mainView も 2段目ログイン画面も確認できませんでした。"
    )


def resolve_app_frame(page, timeout_ms: int = 120000):
    """#mainView が表示されているフレームを返す（iframe 内アプリ対応）。"""
    deadline = time.time() + timeout_ms / 1000.0
    while time.time() < deadline:
        for fr in _all_frames(page):
            try:
                if fr.locator("#mainView").first.is_visible(timeout=800):
                    return fr
            except Exception:
                pass
        page.wait_for_timeout(250)
    raise PwTimeoutError(
        f"#mainView を含むフレームを特定できません（{timeout_ms}ms）。"
    )


def wait_until_main_view_only(page, timeout_ms: int, *, stage_hint: str) -> None:
    """2段目ログイン後、アプリ本体 (#mainView) まで待つ。"""
    deadline = time.time() + timeout_ms / 1000.0
    while time.time() < deadline:
        if _main_view_visible(page):
            return
        body = _body_text_joined(page)
        _check_login_errors_in_page(body, stage_hint)
        page.wait_for_timeout(400)
    raise PwTimeoutError(
        f"{stage_hint}: #mainView が表示されません（{timeout_ms}ms）。"
        "アプリ側のアカウント・公開設定を確認してください。"
    )


def try_resolve_portal_credentials() -> tuple[str, str] | None:
    """ポータル（1段目）認証。未設定なら None（公開URLの1段ログイン運用）。"""
    pe = os.environ.get("LIMO_PORTAL_EMAIL", "").strip()
    pp = os.environ.get("LIMO_PORTAL_PASSWORD", "").strip()
    if pe or pp:
        if not pe or not pp:
            raise RuntimeError(
                "LIMO_PORTAL_EMAIL と LIMO_PORTAL_PASSWORD は、どちらも設定するか、"
                "どちらも空にしてください（片方だけは不可）。"
            )
        return pe, pp
    ae = os.environ.get("LIMO_ADMIN_EMAIL", "").strip()
    ap = os.environ.get("LIMO_ADMIN_PASSWORD", "").strip()
    if ae or ap:
        if not ae or not ap:
            raise RuntimeError(
                "LIMO_ADMIN_EMAIL と LIMO_ADMIN_PASSWORD は、どちらも設定するか、"
                "どちらも空にしてください（片方だけは不可）。"
            )
        return ae, ap
    return None


def resolve_portal_credentials() -> tuple[str, str]:
    creds = try_resolve_portal_credentials()
    if creds is None:
        raise RuntimeError(
            "ポータル認証が未設定です。"
            "LIMO_PORTAL_* / LIMO_ADMIN_* を設定するか、"
            "LIMO_APP_EMAIL / LIMO_APP_PASSWORD で公開URLに直接ログインしてください。"
        )
    return creds


def authenticate_limo_page(
    page,
    *,
    app_email: str,
    app_password: str,
    portal_creds: tuple[str, str] | None,
    login_wait_ms: int,
    post_login_wait_ms: int,
) -> None:
    """
    公開URL（1段）とポータル経由（2段）の両方に対応する認証。
    初期表示がミニアプリのログイン画面のときは LIMO_APP_* を優先する。
    """
    initial_state = wait_initial_auth_state(page, login_wait_ms)
    if initial_state == "main":
        print("初期表示で #mainView を検出。ログインをスキップします", flush=True)
        return

    if app_email and app_password:
        print("1段（ミニアプリ公開URL）ログインを実行します", flush=True)
        _fill_limo_login(page, app_email, app_password, login_wait_ms)
        wait_until_main_view_only(
            page,
            post_login_wait_ms,
            stage_hint="ミニアプリ",
        )
        return

    if portal_creds is None:
        raise RuntimeError(
            "ログインが必要ですが、LIMO_APP_EMAIL / LIMO_APP_PASSWORD が未設定です。"
            "公開URL用のアカウントを scripts/.env に設定してください。"
        )

    print("1段目（ポータル）ログインを実行します", flush=True)
    portal_email, portal_password = portal_creds
    _fill_limo_login(page, portal_email, portal_password, login_wait_ms)
    after_first = wait_until_main_or_app_login(
        page,
        post_login_wait_ms,
        stage_hint="1段目（ポータル）",
    )
    if after_first == "main":
        return
    if not app_email or not app_password:
        raise RuntimeError(
            "2段目（ミニアプリ）のログイン画面が表示されましたが、"
            "LIMO_APP_EMAIL / LIMO_APP_PASSWORD が未設定です。"
        )
    print("2段目（ミニアプリ）ログインを実行します", flush=True)
    _fill_limo_login(page, app_email, app_password, login_wait_ms)
    wait_until_main_view_only(
        page,
        post_login_wait_ms,
        stage_hint="2段目（ミニアプリ）",
    )


def ensure_csv_file(path: str) -> Path:
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        raise RuntimeError(f"CSVファイルが見つかりません: {p}")
    return p


def _safe_inner_text(locator, timeout_ms: int) -> str:
    try:
        if locator.count() == 0:
            return ""
        return locator.inner_text(timeout=timeout_ms).strip()
    except Exception:
        return ""


def wait_import_finished(ctx, timeout_sec: int) -> str:
    """
    importResult のテキストが一定時間変化しなくなるまで待つ。
    ctx: Page または #mainView を含む Frame。
    """
    deadline = time.time() + timeout_sec
    last_text = ""
    stable_rounds = 0
    started = False
    while time.time() < deadline:
        current = _safe_inner_text(ctx.locator("#importResult"), 5000)
        if current:
            started = True
        if current != last_text:
            last_text = current
            stable_rounds = 0
        else:
            stable_rounds += 1

        toast = _safe_inner_text(ctx.locator("#toast"), 2000)
        # 完了トーストを優先（文言変更時は LIMO 側確認）
        if toast and ("CSV取込完了" in toast or "取込完了" in toast):
            return current

        # ログが出始めてから 3 回連続で不変なら完了扱い
        if started and stable_rounds >= 3:
            return current
        # Frame には wait_for_timeout がないため、常に親 Page で待つ
        getattr(ctx, "page", ctx).wait_for_timeout(2000)
    raise PwTimeoutError(f"CSV取込の完了待ちがタイムアウトしました（{timeout_sec}秒）")


def parse_result_stats(result_text: str) -> dict:
    ok_count = len(re.findall(r"^OK row=", result_text, flags=re.MULTILINE))
    skip_count = len(re.findall(r"^SKIP dup row=", result_text, flags=re.MULTILINE))
    ng_count = len(re.findall(r"^NG row=", result_text, flags=re.MULTILINE))
    return {"ok": ok_count, "skip": skip_count, "ng": ng_count}


def _all_page_like(page):
    """メインページと子フレーム（Raimo シェルが iframe の場合）。"""
    seen = set()
    out = []
    for fr in [page] + list(page.frames):
        key = id(fr)
        if key in seen:
            continue
        seen.add(key)
        out.append(fr)
    return out


def try_community_info_refresh(page, timeout_sec: int) -> tuple[bool, str]:
    """
    アプリ本体 HTML には無いが、LIMO 管理シェル等に「コミュニティ情報の最新化」ボタンがある場合にクリックする。
    見つからなければ (False, 理由)。
    """
    if not get_env_bool("LIMO_TRY_COMMUNITY_REFRESH", True):
        return False, "LIMO_TRY_COMMUNITY_REFRESH=0 のためスキップ"

    # 誤クリックを避け、まずは明示ラベルのみ（部分一致は最小限）
    name_res = [
        re.compile(r"コミュニティ情報の最新化"),
        re.compile(r"コミュニティ情報を最新化"),
    ]
    roles = ("button", "link")

    target = None
    target_frame = None
    for fr in _all_page_like(page):
        for role in roles:
            for pat in name_res:
                try:
                    loc = fr.get_by_role(role, name=pat)
                    if loc.count() == 0:
                        continue
                    first = loc.first
                    if first.is_visible():
                        target = first
                        target_frame = fr
                        break
                except Exception:
                    continue
            if target is not None:
                break
        if target is not None:
            break

    if target is None:
        return (
            False,
            "「コミュニティ情報の最新化」に一致するボタン/リンクが見つかりません（別タブ・別画面の可能性）",
        )

    try:
        target.click(timeout=15000)
    except Exception as e:
        return False, f"クリック失敗: {e}"

    deadline = time.time() + timeout_sec
    last_toast = ""
    while time.time() < deadline:
        # メインの #toast とシェル側の汎用トーストの両方をざっと見る
        for fr in _all_page_like(page):
            try:
                for sel in ("#toast", "[role='alert']", ".toast", "[class*='toast']"):
                    t = _safe_inner_text(fr.locator(sel), 1500)
                    if t and t != last_toast:
                        last_toast = t
                    if t and any(
                        k in t
                        for k in ("完了", "成功", "最新化", "更新", "処理", "取込")
                    ):
                        return True, t.strip()[:500]
            except Exception:
                continue
        page.wait_for_timeout(2000)

    return True, f"最新化操作はクリック済み（{timeout_sec}s 以内に完了トーストは未取得） frame={target_frame}"


def main() -> int:
    ap = argparse.ArgumentParser(description="LIMO管理画面でCSV取込を自動実行")
    ap.add_argument("--csv", required=True, help="アップロードするCSVパス")
    ap.add_argument(
        "--timeout-sec",
        type=int,
        default=int(os.environ.get("LIMO_UPLOAD_TIMEOUT_SEC", "1800")),
        help="CSV取込の完了待ちタイムアウト秒",
    )
    ap.add_argument(
        "--screenshot-dir",
        default=None,
        help="失敗時/完了時スクリーンショット保存先（任意）",
    )
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(line_buffering=True)
        sys.stderr.reconfigure(line_buffering=True)
    except Exception:
        pass

    csv_path = ensure_csv_file(args.csv)
    app_url = get_required_env("LIMO_APP_URL")
    portal_creds = try_resolve_portal_credentials()
    app_email = os.environ.get("LIMO_APP_EMAIL", "").strip()
    app_password = os.environ.get("LIMO_APP_PASSWORD", "").strip()
    if not ((app_email and app_password) or portal_creds):
        raise RuntimeError(
            "LIMO 認証情報が不足しています。"
            "公開URL運用: LIMO_APP_EMAIL / LIMO_APP_PASSWORD。"
            "従来の2段: LIMO_PORTAL_*（+ 必要なら LIMO_APP_*）。"
        )
    headless = get_env_bool("LIMO_HEADLESS", True)
    slow_mo = int(os.environ.get("LIMO_SLOW_MO_MS", "0"))
    user_agent = os.environ.get(
        "LIMO_USER_AGENT",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6_0) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    ).strip()
    shot_dir = (
        Path(args.screenshot_dir).expanduser().resolve()
        if args.screenshot_dir
        else None
    )
    if shot_dir:
        shot_dir.mkdir(parents=True, exist_ok=True)

    login_wait_ms = int(os.environ.get("LIMO_LOGIN_WAIT_MS", "120000"))
    post_login_wait_ms = int(os.environ.get("LIMO_POST_LOGIN_WAIT_MS", "180000"))

    print(f"LIMO自動取込開始: csv={csv_path}", flush=True)

    exit_code = 2
    notify_detail = "処理が完了しませんでした。"

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            slow_mo=slow_mo,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent=user_agent,
            locale="ja-JP",
            viewport={"width": 1440, "height": 900},
        )
        context.add_init_script(
            """
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'platform', {get: () => 'MacIntel'});
            Object.defineProperty(navigator, 'language', {get: () => 'ja-JP'});
            Object.defineProperty(navigator, 'languages', {get: () => ['ja-JP', 'ja', 'en-US']});
            """
        )
        page = context.new_page()
        try:
            page.goto(app_url, wait_until="domcontentloaded", timeout=120000)

            authenticate_limo_page(
                page,
                app_email=app_email,
                app_password=app_password,
                portal_creds=portal_creds,
                login_wait_ms=login_wait_ms,
                post_login_wait_ms=post_login_wait_ms,
            )

            app_fr = resolve_app_frame(page, timeout_ms=120000)

            # 管理者タブ（CSV取込）へ（iframe 内でも操作）
            admin_tab = app_fr.locator("#adminDataTabBtn")
            admin_tab.wait_for(state="visible", timeout=120000)
            admin_tab.click()

            # タブ切り替え後に file input が差し込まれるまで待つ
            file_input = app_fr.locator("#csvFileInput")
            file_input.wait_for(state="attached", timeout=120000)

            # CSV ファイル選択と取込実行
            file_input.set_input_files(str(csv_path))
            app_fr.locator("#importCsvBtn").click()
            print(
                "ブラウザでCSV取込を実行中（行数が多いと完了まで時間がかかります）…",
                flush=True,
            )

            result_text = wait_import_finished(app_fr, timeout_sec=args.timeout_sec)
            stats = parse_result_stats(result_text)
            toast_text = _safe_inner_text(app_fr.locator("#toast"), 3000)

            refresh_timeout = int(
                os.environ.get("LIMO_COMMUNITY_REFRESH_TIMEOUT_SEC", "300")
            )
            ok_refresh, refresh_msg = try_community_info_refresh(
                page, timeout_sec=max(30, refresh_timeout)
            )
            if ok_refresh:
                print(f"コミュニティ最新化: {refresh_msg}", flush=True)
            else:
                print(f"コミュニティ最新化: {refresh_msg}", flush=True)

            if shot_dir:
                ok_shot = shot_dir / f"limo_import_ok_{int(time.time())}.png"
                page.screenshot(path=str(ok_shot), full_page=True)
                print(f"スクリーンショット保存: {ok_shot}", flush=True)

            print(
                "LIMO取込完了: "
                f"OK={stats['ok']} / SKIP={stats['skip']} / NG={stats['ng']}",
                flush=True,
            )
            if toast_text:
                print(f"トースト: {toast_text}", flush=True)

            summary_bits = [
                f'importResult行カウント OK={stats["ok"]} SKIP={stats["skip"]} NG={stats["ng"]}',
            ]
            if toast_text:
                summary_bits.append(toast_text.strip()[:220])
            notify_detail = " ".join(summary_bits)

            if stats["ng"] > 0:
                print("NG行があるため終了コード1を返します", file=sys.stderr)
                exit_code = 1
            else:
                exit_code = 0
        except PwTimeoutError as e:
            if shot_dir:
                ng_shot = shot_dir / f"limo_import_ng_{int(time.time())}.png"
                try:
                    page.screenshot(path=str(ng_shot), full_page=True)
                    print(f"失敗時スクリーンショット: {ng_shot}", file=sys.stderr)
                except Exception:
                    pass
            print(f"LIMO取込失敗(タイムアウト): {e}", file=sys.stderr)
            notify_detail = str(e)
            exit_code = 2
        except Exception as e:
            if shot_dir:
                ng_shot = shot_dir / f"limo_import_ng_{int(time.time())}.png"
                try:
                    page.screenshot(path=str(ng_shot), full_page=True)
                    print(f"失敗時スクリーンショット: {ng_shot}", file=sys.stderr)
                except Exception:
                    pass
            print(f"LIMO取込失敗: {e}", file=sys.stderr)
            notify_detail = str(e)
            exit_code = 2
        finally:
            context.close()
            browser.close()

    maybe_macos_notify_done(exit_code, notify_detail)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
