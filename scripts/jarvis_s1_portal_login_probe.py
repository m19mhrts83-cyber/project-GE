#!/usr/bin/env python3
"""Try S1 portal logins with PORTAL_LOGIN_* candidates. Never prints secrets."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / ".env.jarvis_private"


def load_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def pick_creds(env: dict[str, str]) -> tuple[str, list[tuple[str, str]]]:
    email = (
        env.get("PORTAL_LOGIN_EMAIL")
        or env.get("KENBIYA_LOGIN_EMAIL")
        or env.get("RAKUMACHI_LOGIN_EMAIL")
        or ""
    ).strip()
    cands: list[tuple[str, str]] = []
    if env.get("PORTAL_LOGIN_PASSWORD"):
        cands.append(("PORTAL_LOGIN_PASSWORD", env["PORTAL_LOGIN_PASSWORD"]))
    for key in (
        "PORTAL_LOGIN_PASSWORD_CANDIDATE1",
        "PORTAL_LOGIN_PASSWORD_CANDIDATE2",
        "PORTAL_LOGIN_PASSWORD1",
        "PORTAL_LOGIN_PASSWORD2",
    ):
        if env.get(key):
            cands.append((key, env[key]))
    # dedupe by value
    seen: set[str] = set()
    uniq: list[tuple[str, str]] = []
    for k, v in cands:
        if v and v not in seen:
            seen.add(v)
            uniq.append((k, v))
    return email, uniq


def try_kenbiya(page, email: str, password: str) -> tuple[bool, str]:
    page.goto("https://www.kenbiya.com/", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(1200)
    if page.locator('a:has-text("会員ログイン")').count():
        page.locator('a:has-text("会員ログイン")').first.click()
        page.wait_for_timeout(2000)
    else:
        page.goto("https://www.kenbiya.com/app/exe/login", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(1500)
    if page.locator("#password, input[name='password']").count() == 0:
        if "ログアウト" in page.content():
            return True, "already_logged_in"
        return False, f"no_password_field url={page.url}"
    page.fill("#login_email, input[name='login_email']", email)
    page.fill("#password, input[name='password']", password)
    if page.locator('input[type="submit"][name="login"], input[name="login"]').count():
        page.locator('input[type="submit"][name="login"], input[name="login"]').first.click()
    else:
        page.locator('input[type="submit"]').first.click()
    page.wait_for_timeout(3500)
    html = page.content()
    url = page.url
    if any(
        x in html
        for x in (
            "パスワードが正しくありません",
            "ログインに失敗",
            "認証に失敗",
            "メールアドレスまたはパスワード",
            "一致しません",
            "正しくありません",
        )
    ):
        return False, "auth_failed"
    if page.locator("#password").count() and "/login" in url:
        return False, f"still_on_login url={url}"
    if "ログアウト" in html or "マイページ" in html or "/user/" in url:
        return True, f"ok url={url}"
    return False, f"ambiguous url={url}"


def try_rakumachi(page, email: str, password: str) -> tuple[bool, str]:
    page.goto("https://www.rakumachi.jp/", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(1500)
    # open login
    clicked = False
    for text in ("ログイン", "会員ログイン", "マイページ"):
        loc = page.locator(f'a:has-text("{text}"), button:has-text("{text}")')
        if loc.count():
            loc.first.click()
            clicked = True
            page.wait_for_timeout(2000)
            break
    if page.locator('input[type="password"]').count() == 0:
        for u in (
            "https://www.rakumachi.jp/user/login/",
            "https://www.rakumachi.jp/login/",
            "https://www.rakumachi.jp/members/login",
        ):
            page.goto(u, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(1500)
            if page.locator('input[type="password"]').count():
                break
    if page.locator('input[type="password"]').count() == 0:
        return False, f"no_password_field url={page.url} clicked={clicked}"
    # email field
    filled = False
    for sel in (
        'input[type="email"]',
        'input[name="email"]',
        'input[name="mail"]',
        'input[name="login_id"]',
        'input[name="user_id"]',
        'input[type="text"]',
    ):
        if page.locator(sel).count():
            page.locator(sel).first.fill(email)
            filled = True
            break
    if not filled:
        return False, f"no_email_field url={page.url}"
    page.locator('input[type="password"]').first.fill(password)
    for sel in (
        'button[type="submit"]',
        'input[type="submit"]',
        'button:has-text("ログイン")',
        'input[value*="ログイン"]',
    ):
        if page.locator(sel).count():
            page.locator(sel).first.click()
            break
    else:
        page.keyboard.press("Enter")
    page.wait_for_timeout(3500)
    html = page.content()
    url = page.url
    if any(
        x in html
        for x in (
            "パスワードが正しくありません",
            "ログインに失敗",
            "認証に失敗",
            "メールアドレスまたはパスワード",
            "一致しません",
            "正しくありません",
        )
    ):
        return False, "auth_failed"
    if page.locator('input[type="password"]').count() and "login" in url.lower():
        return False, f"still_on_login url={url}"
    if "ログアウト" in html or ("mypage" in url.lower()) or ("/user/" in url and "login" not in url.lower()):
        return True, f"ok url={url}"
    return False, f"ambiguous url={url}"


def main() -> int:
    if not ENV.exists():
        print("FAIL: no .env.jarvis_private")
        return 2
    env = load_env(ENV)
    email, cands = pick_creds(env)
    if not email:
        print("FAIL: PORTAL_LOGIN_EMAIL empty")
        return 2
    if not cands:
        print("FAIL: no password candidates")
        return 2
    print(f"email_set=yes domain=@{email.split('@',1)[-1]} candidates={len(cands)}")

    results: list[str] = []
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True, channel="chrome")
        except Exception:
            browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
            viewport={"width": 1280, "height": 900},
        )
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        page = context.new_page()
        winner_both: str | None = None
        winner_any: str | None = None
        for key, pw in cands:
            print(f"\n=== try {key} len={len(pw)} ===")
            ok_k, msg_k = try_kenbiya(page, email, pw)
            print(f"kenbiya: {'OK' if ok_k else 'NG'} · {msg_k}")
            results.append(f"kenbiya/{key}={'OK' if ok_k else 'NG'}:{msg_k}")
            context.clear_cookies()
            ok_r, msg_r = try_rakumachi(page, email, pw)
            print(f"rakumachi: {'OK' if ok_r else 'NG'} · {msg_r}")
            results.append(f"rakumachi/{key}={'OK' if ok_r else 'NG'}:{msg_r}")
            context.clear_cookies()
            if ok_k or ok_r:
                winner_any = key
            if ok_k and ok_r:
                winner_both = key
                print(f"WINNER_BOTH={key}")
                break
            if ok_k or ok_r:
                print(f"PARTIAL_WIN={key}")
        browser.close()

    print("\nSUMMARY")
    for r in results:
        print(r)
    if winner_both:
        print(f"SUGGEST_SET_PORTAL_LOGIN_PASSWORD_FROM={winner_both}")
        return 0
    if winner_any:
        print(f"SUGGEST_SET_PORTAL_LOGIN_PASSWORD_FROM={winner_any}")
        return 0
    print("NO_PASSWORD_WORKED")
    return 1


if __name__ == "__main__":
    sys.exit(main())
