#!/usr/bin/env python3
"""Bloomo 残高取得（Web・Playwright）。

Phase2 骨格: ログイン〜残高抽出。セレクタは画面変更に合わせて直す。
秘密は .env.jarvis_private の BLOOMO_EMAIL / BLOOMO_PASSWORD（別名 BLOOMO_USERNAME 可）。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_bloomo_balance.py --json --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_bloomo_balance.py --json --headless
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEBUG = REPO / ".jarvis_state" / "bloomo_debug"
LOGIN_URL = os.environ.get("BLOOMO_LOGIN_URL", "https://bloomo.jp/").strip()


def creds() -> tuple[str, str]:
    email = (
        os.environ.get("BLOOMO_EMAIL")
        or os.environ.get("BLOOMO_USERNAME")
        or os.environ.get("BLOOMO_LOGIN_ID")
        or ""
    ).strip()
    password = (os.environ.get("BLOOMO_PASSWORD") or "").strip()
    return email, password


def parse_yen(text: str) -> int | None:
    t = text.replace(",", "").replace("，", "")
    m = re.search(r"([0-9]{4,})\s*円", t)
    if m:
        return int(m.group(1))
    m = re.search(r"¥\s*([0-9]{4,})", t)
    if m:
        return int(m.group(1))
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--save-debug", action="store_true")
    args = ap.parse_args()

    email, password = creds()
    if not email or not password:
        out = {
            "status": "skipped",
            "reason": "BLOOMO_EMAIL / BLOOMO_PASSWORD 未設定",
        }
        print(json.dumps(out, ensure_ascii=False) if args.json else out["reason"])
        return 0

    if args.dry_run:
        out = {
            "status": "ok",
            "value_jpy": 0,
            "note": "dry-run（ログイン未実施）",
            "parser_mode": "dry_run",
            "login_url": LOGIN_URL,
        }
        print(json.dumps(out, ensure_ascii=False))
        return 0

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        out = {"status": "error", "reason": "playwright 未インストール"}
        print(json.dumps(out, ensure_ascii=False) if args.json else out["reason"])
        return 1

    DEBUG.mkdir(parents=True, exist_ok=True)
    value: int | None = None
    note = ""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless)
        page = browser.new_page()
        try:
            page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
            # ログイン導線はサイト変更に弱いので複数候補
            for sel in (
                'a:has-text("ログイン")',
                'button:has-text("ログイン")',
                'text=ログイン',
            ):
                try:
                    page.locator(sel).first.click(timeout=3000)
                    break
                except Exception:
                    continue

            email_filled = False
            for sel in (
                'input[type="email"]',
                'input[name="email"]',
                'input[name="username"]',
                'input[autocomplete="username"]',
            ):
                try:
                    page.locator(sel).first.fill(email, timeout=3000)
                    email_filled = True
                    break
                except Exception:
                    continue
            if not email_filled:
                raise RuntimeError("メール入力欄が見つかりません")

            pw_filled = False
            for sel in (
                'input[type="password"]',
                'input[name="password"]',
            ):
                try:
                    page.locator(sel).first.fill(password, timeout=3000)
                    pw_filled = True
                    break
                except Exception:
                    continue
            if not pw_filled:
                raise RuntimeError("パスワード入力欄が見つかりません")

            for sel in (
                'button[type="submit"]',
                'button:has-text("ログイン")',
                'input[type="submit"]',
            ):
                try:
                    page.locator(sel).first.click(timeout=3000)
                    break
                except Exception:
                    continue

            page.wait_for_timeout(4000)
            body = page.inner_text("body")
            value = parse_yen(body)
            note = f"url={page.url}"
            if args.save_debug or value is None:
                (DEBUG / "last_page.html").write_text(page.content(), encoding="utf-8")
                page.screenshot(path=str(DEBUG / "last_page.png"), full_page=True)
            if value is None:
                raise RuntimeError(
                    "残高円が見つかりません。.jarvis_state/bloomo_debug を確認しセレクタを調整"
                )
        finally:
            browser.close()

    out = {
        "status": "ok",
        "value_jpy": int(value),
        "note": note,
        "parser_mode": "body_yen_regex",
    }
    print(json.dumps(out, ensure_ascii=False) if args.json else f"{value:,}円")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
