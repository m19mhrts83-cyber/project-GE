#!/usr/bin/env python3
"""
NotebookLM MCP 用 Chrome プロファイルへ Google ログインする。

要: .env.jarvis_private の NOTEBOOKLM_EMAIL / NOTEBOOKLM_PASSWORD
（未設定時は COMPANY_EMAIL をメール候補に使う）

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  python scripts/jarvis_notebooklm_mcp_login.py
  python scripts/jarvis_notebooklm_mcp_login.py --headed   # 既定は headed
  python scripts/jarvis_notebooklm_mcp_login.py --headless # 非対話（2FA 不可時は失敗）

成功後: Cursor の NotebookLM MCP で get_health → authenticated=true を確認。
"""
from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

PROFILE = (
    Path.home()
    / "Library/Application Support/notebooklm-mcp/chrome_profile"
)
STATE_DIR = (
    Path.home() / "Library/Application Support/notebooklm-mcp/browser_state"
)
STATE_JSON = STATE_DIR / "state.json"
MESSAGES_DB = Path.home() / "Library/Messages/chat.db"


def _env(*names: str) -> str:
    for n in names:
        v = (os.environ.get(n) or "").strip()
        if v:
            return v
    return ""


def _sms_otp(needle: str = "Google", minutes: int = 10) -> str | None:
    if not MESSAGES_DB.is_file():
        return None
    try:
        con = sqlite3.connect(f"file:{MESSAGES_DB}?mode=ro", uri=True)
        cur = con.cursor()
        cur.execute(
            """
            SELECT text FROM message
            WHERE text IS NOT NULL
              AND datetime(date/1000000000 + strftime('%s','2001-01-01'), 'unixepoch', 'localtime')
                  > datetime('now', 'localtime', ?)
            ORDER BY date DESC LIMIT 30
            """,
            (f"-{minutes} minutes",),
        )
        for (text,) in cur.fetchall():
            if not text:
                continue
            if needle.lower() not in text.lower() and "G-" not in text and "認証" not in text:
                # Google OTP often: "G-123456 is your Google verification code"
                if "google" not in text.lower() and "G-" not in text:
                    continue
            m = re.search(r"\bG-?(\d{6})\b", text) or re.search(r"\b(\d{6})\b", text)
            if m:
                return m.group(1)
    except Exception as e:
        print(f"# sms_otp skip: {e}", file=sys.stderr)
    return None


def _click_next(page) -> None:
    for sel in (
        'button:has-text("Next")',
        'button:has-text("次へ")',
        '#identifierNext',
        '#passwordNext',
        'button[type="submit"]',
    ):
        loc = page.locator(sel)
        if loc.count():
            try:
                loc.first.click(timeout=3000)
                return
            except Exception:
                continue


def _is_notebook_home(url: str) -> bool:
    if "accounts.google" in url or "ServiceLogin" in url:
        return False
    return "notebooklm.google.com" in url or "notebook.google.com" in url


def login(*, headed: bool = True, timeout_sec: int = 300) -> int:
    email = _env("NOTEBOOKLM_EMAIL", "COMPANY_EMAIL")
    password = _env("NOTEBOOKLM_PASSWORD", "GOOGLE_ADMIN_PASSWORD")
    if not email or not password:
        print(
            "missing NOTEBOOKLM_EMAIL / NOTEBOOKLM_PASSWORD "
            "(.env.jarvis_private に追記して『保存した』)",
            file=sys.stderr,
        )
        return 2

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright_not_installed", file=sys.stderr)
        return 1

    PROFILE.mkdir(parents=True, exist_ok=True)
    print(f"# profile={PROFILE}", file=sys.stderr)
    print(f"# email={email[:3]}…{email[-10:]}", file=sys.stderr)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE),
            headless=not headed,
            channel="chrome",
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1280, "height": 900},
            ignore_default_args=["--enable-automation"],
        )
        page = context.pages[0] if context.pages else context.new_page()
        try:
            page.goto(
                "https://accounts.google.com/ServiceLogin"
                "?continue=https%3A%2F%2Fnotebooklm.google.com%2F"
                "&flowName=GlifWebSignIn&flowEntry=ServiceLogin",
                wait_until="domcontentloaded",
                timeout=120000,
            )
            page.wait_for_timeout(1500)

            # already logged in?
            if _is_notebook_home(page.url):
                print("# already on notebooklm", file=sys.stderr)
            else:
                # email
                for sel in ('input[type="email"]', 'input[name="identifier"]', "#identifierId"):
                    if page.locator(sel).count():
                        page.fill(sel, email)
                        break
                _click_next(page)
                page.wait_for_timeout(2500)

                # password
                for sel in ('input[type="password"]', 'input[name="Passwd"]'):
                    if page.locator(sel).count():
                        page.fill(sel, password)
                        break
                else:
                    # challenge interstitial (account chooser etc.)
                    body = page.locator("body").inner_text()[:400]
                    print(f"# no password field yet; body[:120]={body[:120]!r}", file=sys.stderr)
                _click_next(page)
                page.wait_for_timeout(3000)

                # 2FA / challenge
                deadline = time.time() + timeout_sec
                while time.time() < deadline:
                    url = page.url
                    title = page.title()
                    try:
                        body = page.locator("body").inner_text(timeout=2000)
                    except Exception:
                        body = ""

                    if _is_notebook_home(url):
                        print("# landed notebooklm", file=sys.stderr)
                        break

                    # totp / sms code field
                    code_sel = (
                        'input[type="tel"]',
                        'input[name="totpPin"]',
                        'input[id="totpPin"]',
                        'input[aria-label*="code" i]',
                        'input[aria-label*="コード"]',
                    )
                    code_box = None
                    for sel in code_sel:
                        if page.locator(sel).count():
                            code_box = page.locator(sel).first
                            break
                    if code_box and ("challenge" in url or "検証" in body or "コード" in body or "2-Step" in body or "2 段階" in body):
                        otp = _sms_otp()
                        if otp:
                            print("# filling SMS OTP", file=sys.stderr)
                            code_box.fill(otp)
                            _click_next(page)
                            page.wait_for_timeout(3000)
                            continue
                        print(
                            "# 2FA 待ち: SMS/アプリのコードが必要です。"
                            "届いたらこのウィンドウに入力してください",
                            file=sys.stderr,
                        )
                        # wait for user to type
                        page.wait_for_timeout(5000)
                        continue

                    # "Try another way" / skip phone
                    print(f"# waiting auth… url={url[:90]} title={title[:40]}", file=sys.stderr)
                    page.wait_for_timeout(4000)
                else:
                    print("# timeout waiting for notebooklm", file=sys.stderr)
                    context.close()
                    return 1

            # ensure notebooklm
            if not _is_notebook_home(page.url):
                page.goto(
                    "https://notebooklm.google.com/",
                    wait_until="domcontentloaded",
                    timeout=120000,
                )
            page.wait_for_timeout(4000)
            body = page.locator("body").inner_text()[:600]
            ok = _is_notebook_home(page.url) and (
                "新しいノートブック" in body
                or "New notebook" in body
                or "ノートブック" in body
                or "NotebookLM" in page.title()
                or "Gemini Notebook" in page.title()
                or "pli=1" in page.url
            )
            print(f"# result ok={ok} url={page.url} title={page.title()}", file=sys.stderr)
            # MCP get_health は browser_state/state.json の有無で authenticated を判定
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            context.storage_state(path=str(STATE_JSON))
            print(f"# wrote {STATE_JSON}", file=sys.stderr)
            # let cookies settle
            page.wait_for_timeout(1000)
        finally:
            context.close()

    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--headed", action="store_true", default=True)
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--timeout", type=int, default=300)
    args = ap.parse_args(argv)
    headed = not args.headless
    return login(headed=headed, timeout_sec=args.timeout)


if __name__ == "__main__":
    raise SystemExit(main())
