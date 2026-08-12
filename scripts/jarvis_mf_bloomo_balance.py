#!/usr/bin/env python3
"""マネーフォワード ME 経由でブルーモ証券の評価額を取得する。

正本ログイン:
  - 推奨: Playwright storage_state（一度 --save-session で Google ログイン）
  - 任意: MONEYFORWARD_EMAIL / MONEYFORWARD_PASSWORD（ID+パスワード方式のとき）

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_mf_bloomo_balance.py --save-session
  ~/selenium_env/venv/bin/python scripts/jarvis_mf_bloomo_balance.py --json --headless
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEBUG = REPO / ".jarvis_state" / "mf_bloomo_debug"
DEFAULT_STATE = REPO / ".jarvis_state" / "mf_me_storage_state.json"
DEFAULT_PROFILE = REPO / ".jarvis_state" / "mf_me_browser_profile"
ACCOUNTS_URL = "https://moneyforward.com/accounts"
SIGN_IN = "https://id.moneyforward.com/sign_in"


def state_path() -> Path:
    raw = (os.environ.get("MONEYFORWARD_STORAGE_STATE") or "").strip()
    return Path(raw).expanduser() if raw else DEFAULT_STATE


def profile_path() -> Path:
    raw = (os.environ.get("MONEYFORWARD_BROWSER_PROFILE") or "").strip()
    return Path(raw).expanduser() if raw else DEFAULT_PROFILE


def show_url() -> str:
    return (os.environ.get("MONEYFORWARD_BLOOMO_SHOW_URL") or "").strip()


def creds() -> tuple[str, str]:
    email = (
        os.environ.get("MONEYFORWARD_EMAIL")
        or os.environ.get("MONEYFORWARD_USERNAME")
        or ""
    ).strip()
    password = (os.environ.get("MONEYFORWARD_PASSWORD") or "").strip()
    return email, password


def parse_yen(text: str) -> int | None:
    t = text.replace(",", "").replace("，", "")
    m = re.search(r"資産総額[：:]\s*([0-9]+)\s*円", t)
    if m:
        return int(m.group(1))
    m = re.search(r"([0-9]{4,})\s*円", t)
    if m:
        return int(m.group(1))
    return None


def save_debug(page, tag: str) -> None:
    DEBUG.mkdir(parents=True, exist_ok=True)
    (DEBUG / f"{tag}.html").write_text(page.content(), encoding="utf-8")
    page.screenshot(path=str(DEBUG / f"{tag}.png"), full_page=True)


def login_with_password(page, email: str, password: str) -> None:
    page.goto(SIGN_IN, wait_until="domcontentloaded", timeout=60000)
    page.locator('input[type="email"], input[name="email"], input[autocomplete="username"]').first.fill(
        email, timeout=10000
    )
    try:
        page.get_by_role("button", name=re.compile("ログイン")).first.click(timeout=5000)
    except Exception:
        pass
    page.wait_for_timeout(800)
    page.locator('input[type="password"]').first.fill(password, timeout=15000)
    page.get_by_role("button", name=re.compile("ログイン")).first.click(timeout=10000)
    page.wait_for_timeout(3000)


def ensure_logged_in(page) -> None:
    page.goto(ACCOUNTS_URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(1500)
    if "sign_in" in page.url or "id.moneyforward" in page.url:
        email, password = creds()
        if email and password:
            login_with_password(page, email, password)
            page.goto(ACCOUNTS_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(1500)
        if "sign_in" in page.url or "id.moneyforward" in page.url:
            raise RuntimeError(
                "MF 未ログイン。--save-session でブラウザプロファイルにログインするか、"
                "MONEYFORWARD_EMAIL/PASSWORD を .env.jarvis_private に設定してください"
            )


def fetch_bloomo_value(page) -> tuple[int, str]:
    target = show_url()
    if target:
        page.goto(target, wait_until="domcontentloaded", timeout=60000)
    else:
        ensure_logged_in(page)
        link = page.locator('a:has-text("ブルーモ証券")').first
        link.click(timeout=15000)
        page.wait_for_timeout(1500)
    page.wait_for_timeout(1000)
    body = page.inner_text("body")
    value = parse_yen(body)
    note = f"url={page.url}"
    if value is None:
        save_debug(page, "bloomo_fail")
        raise RuntimeError("ブルーモ資産総額が見つかりません（mf_bloomo_debug を確認）")
    if "/accounts/show/" in page.url:
        print(f"# MONEYFORWARD_BLOOMO_SHOW_URL={page.url}", file=sys.stderr)
    return value, note


def _logged_in_url(url: str) -> bool:
    return (
        "moneyforward.com/accounts" in (url or "")
        and "sign_in" not in (url or "")
        and "id.moneyforward" not in (url or "")
    )


def browser_channel() -> str | None:
    """Google OAuth 用。既定は実 Chrome（Playwright Chromium は Google に拒否されやすい）。"""
    raw = (os.environ.get("MONEYFORWARD_BROWSER_CHANNEL") or "chrome").strip().lower()
    if raw in ("", "chromium", "none", "0"):
        return None
    return raw  # chrome / chrome-beta / msedge 等


def cmd_save_session(*, headless: bool, wait_sec: int = 300) -> int:
    """永続プロファイルに Google ログインを保存（あかつき storage_state と同系統）。"""
    from playwright.sync_api import sync_playwright

    profile = profile_path()
    profile.mkdir(parents=True, exist_ok=True)
    st = state_path()
    st.parent.mkdir(parents=True, exist_ok=True)
    ch = browser_channel()
    print(
        f"{'Google Chrome' if ch == 'chrome' else 'ブラウザ'} が開きます。"
        " 表示ウィンドウで Google（m19m.hrts83@gmail.com）→ マネーフォワード にログインし、"
        f"口座一覧が出るまで待ってください（最大 {wait_sec} 秒）。",
        flush=True,
    )
    launch_kwargs: dict = {
        "user_data_dir": str(profile),
        "headless": headless,
        "viewport": {"width": 1280, "height": 900},
        "locale": "ja-JP",
        "args": ["--disable-blink-features=AutomationControlled"],
    }
    if ch:
        launch_kwargs["channel"] = ch
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(**launch_kwargs)
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(ACCOUNTS_URL, wait_until="domcontentloaded", timeout=60000)
        ok = False
        for i in range(max(1, wait_sec // 3)):
            page.wait_for_timeout(3000)
            if _logged_in_url(page.url or ""):
                ok = True
                break
            if i % 10 == 0:
                print(f"# waiting login... url={(page.url or '')[:100]}", flush=True)
        if not ok:
            save_debug(page, "save_session_timeout")
            context.close()
            print(json.dumps({"status": "error", "reason": "login timeout"}, ensure_ascii=False))
            return 1
        try:
            val, _ = fetch_bloomo_value(page)
            print(f"# bloomo check ok: {val:,}", flush=True)
        except Exception as exc:
            print(f"# bloomo check warn: {exc}", flush=True)
        context.storage_state(path=str(st))
        context.close()
    print(
        json.dumps(
            {
                "status": "ok",
                "storage_state": str(st),
                "browser_profile": str(profile),
                "channel": ch or "chromium",
            },
            ensure_ascii=False,
        )
    )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--save-debug", action="store_true")
    ap.add_argument(
        "--save-session",
        action="store_true",
        help="ブラウザでログインし profile + storage_state を保存（初回・期限切れ時）",
    )
    ap.add_argument("--wait-sec", type=int, default=300, help="--save-session の待機秒")
    args = ap.parse_args()

    if args.save_session:
        return cmd_save_session(headless=False, wait_sec=args.wait_sec)

    if args.dry_run:
        out = {
            "status": "ok",
            "value_jpy": 0,
            "note": "dry-run",
            "parser_mode": "dry_run",
            "source": "moneyforward",
        }
        print(json.dumps(out, ensure_ascii=False) if args.json else out["note"])
        return 0

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        out = {"status": "error", "reason": "playwright 未インストール"}
        print(json.dumps(out, ensure_ascii=False) if args.json else out["reason"])
        return 1

    st = state_path()
    profile = profile_path()
    email, password = creds()
    use_profile = profile.is_dir() and any(profile.iterdir())
    if not st.is_file() and not use_profile and not (email and password):
        out = {
            "status": "skipped",
            "reason": "MONEYFORWARD セッション未設定（--save-session を実行）",
        }
        print(json.dumps(out, ensure_ascii=False) if args.json else out["reason"])
        return 0

    value: int | None = None
    note = ""
    ch = browser_channel()
    # MF は headless（Chromium/Chrome とも）を Forbidden にするため、取得は常に headed。
    if args.headless:
        print(
            "# note: MoneyForward 取得は headed 強制（--headless は無視・403回避）",
            file=sys.stderr,
        )
    effective_headless = False
    # 永続プロファイルが正（storage_state だけでは Google セッションが足りないことが多い）
    with sync_playwright() as p:
        if use_profile:
            launch_kwargs: dict = {
                "user_data_dir": str(profile),
                "headless": effective_headless,
                "viewport": {"width": 1280, "height": 900},
                "locale": "ja-JP",
                "args": ["--disable-blink-features=AutomationControlled"],
            }
            if ch:
                launch_kwargs["channel"] = ch
            context = p.chromium.launch_persistent_context(**launch_kwargs)
            page = context.pages[0] if context.pages else context.new_page()
            browser = None
        else:
            launch_b: dict = {"headless": effective_headless}
            if ch:
                launch_b["channel"] = ch
            browser = p.chromium.launch(**launch_b)
            context = browser.new_context(
                storage_state=str(st) if st.is_file() else None,
                locale="ja-JP",
                viewport={"width": 1280, "height": 900},
            )
            page = context.new_page()
        try:
            ensure_logged_in(page)
            value, note = fetch_bloomo_value(page)
            if args.save_debug:
                save_debug(page, "bloomo_ok")
            try:
                context.storage_state(path=str(st))
            except Exception:
                pass
        except Exception as exc:
            save_debug(page, "error")
            out = {"status": "error", "reason": str(exc)[:400], "source": "moneyforward"}
            print(json.dumps(out, ensure_ascii=False) if args.json else out["reason"])
            context.close()
            if browser:
                browser.close()
            return 1
        context.close()
        if browser:
            browser.close()

    out = {
        "status": "ok",
        "value_jpy": int(value),
        "note": note,
        "parser_mode": "mf_accounts_show",
        "source": "moneyforward",
    }
    print(json.dumps(out, ensure_ascii=False) if args.json else f"{value:,}円")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
