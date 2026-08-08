#!/usr/bin/env python3
"""Glucon: queued 下書きを WeStudy フォーラムへ投稿（Playwright）.

Dashboard で確認後 status=queued になった行を処理する。
対外投稿のため既定は確認付き。自動実行時は --i-confirm-post 必須。

例:
  python scripts/jarvis_westudy_forum_post_worker.py --dry-run
  python scripts/jarvis_westudy_forum_post_worker.py --i-confirm-post
  python scripts/jarvis_westudy_forum_post_worker.py --i-confirm-post --show
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env.jarvis_private"
WESTUDY_AUTH = ROOT / "215_kamiooya/C1_cursor/westudy_common"

FORUM_URL = {
    "activity": "https://westudy.co.jp/forum/monthly_output",
    "result": "https://westudy.co.jp/forum/results",
}


def load_env() -> None:
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    sys.path.insert(0, str(WESTUDY_AUTH))
    try:
        from auth import load_westudy_env  # type: ignore

        load_westudy_env(force=False)
    except Exception as e:
        print(f"# westudy env warn: {e}", file=sys.stderr)


def supabase_client():
    from supabase import create_client

    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        raise RuntimeError("JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY required")
    return create_client(url, key)


def mark(sb, row_id: str, **fields) -> None:
    fields["updated_at"] = datetime.now(timezone.utc).isoformat()
    sb.table("glucon_report_drafts").update(fields).eq("id", row_id).execute()


def login_page(page) -> None:
    user = os.environ.get("WESTUDY_USER") or ""
    password = os.environ.get("WESTUDY_PASS") or ""
    if not user or not password:
        raise RuntimeError("WESTUDY_USER / WESTUDY_PASS missing")
    login_url = (os.environ.get("WESTUDY_LOGIN_URL") or "https://westudy.co.jp/login").strip()
    page.goto(login_url, wait_until="domcontentloaded", timeout=120_000)
    if page.locator("#user_login").count():
        page.fill("#user_login", user)
        page.fill("#user_pass", password)
        try:
            if page.locator("#rememberme").count() and page.locator("#rememberme").is_visible():
                page.check("#rememberme")
        except Exception:
            pass
        page.click("#wp-submit")
        page.wait_for_load_state("networkidle", timeout=90_000)
        time.sleep(1.0)
    if "wp-login.php" in page.url.lower() or page.url.rstrip("/").endswith("/login"):
        raise RuntimeError(f"login failed: {page.url}")


def find_comment_box(page):
    selectors = [
        "textarea#comment",
        "textarea[name='comment']",
        "#respond textarea",
        ".comment-form textarea",
        "textarea.wp-editor-area",
        "div.ProseMirror",
        "[contenteditable='true']",
    ]
    for sel in selectors:
        loc = page.locator(sel)
        if loc.count() and loc.first.is_visible():
            return sel, loc.first
    return None, None


def submit_comment(page, body: str, *, dry_run: bool) -> str | None:
    sel, box = find_comment_box(page)
    if not box:
        raise RuntimeError("コメント入力欄が見つかりません（DOM変更の可能性）")

    tag = box.evaluate("el => el.tagName.toLowerCase()")
    if tag == "textarea":
        box.fill(body)
    else:
        box.click()
        page.keyboard.press("Meta+A")
        page.keyboard.type(body, delay=5)

    if dry_run:
        print(f"# dry-run: focused {sel}, body_chars={len(body)}")
        return None

    submit_sels = [
        "#submit",
        "input[name='submit']",
        "button[type='submit']",
        "#respond input[type='submit']",
        ".form-submit input",
        "button:has-text('投稿')",
        "input[value*='投稿']",
    ]
    clicked = False
    for s in submit_sels:
        loc = page.locator(s)
        if loc.count() and loc.first.is_visible():
            loc.first.click()
            clicked = True
            break
    if not clicked:
        raise RuntimeError("投稿ボタンが見つかりません")

    page.wait_for_load_state("networkidle", timeout=90_000)
    time.sleep(1.5)

    # best-effort comment id from URL hash or newest comment
    comment_id = None
    if "#comment-" in page.url:
        comment_id = page.url.split("#comment-")[-1].split("&")[0]
    return comment_id


def process_row(page, sb, row: dict, *, dry_run: bool) -> None:
    kind = row.get("kind")
    url = FORUM_URL.get(kind)
    if not url:
        raise RuntimeError(f"unknown kind: {kind}")
    body = (row.get("body") or "").strip()
    if not body:
        raise RuntimeError("empty body")

    print(f"# post {row.get('period_key')} {kind} → {url}")
    page.goto(url, wait_until="domcontentloaded", timeout=120_000)
    time.sleep(1.0)
    try:
        cid = submit_comment(page, body, dry_run=dry_run)
        if dry_run:
            return
        mark(
            sb,
            row["id"],
            status="posted",
            posted_at=datetime.now(timezone.utc).isoformat(),
            westudy_comment_id=cid,
            post_error=None,
        )
        print(f"# posted ok id={row['id']} comment_id={cid}")
    except Exception as e:
        if not dry_run:
            mark(sb, row["id"], status="failed", post_error=str(e)[:500])
        raise


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="ログイン〜入力まで（投稿しない）")
    ap.add_argument(
        "--i-confirm-post",
        action="store_true",
        help="本番投稿を実行する明示フラグ（dry-run 以外で必須）",
    )
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--limit", type=int, default=5)
    args = ap.parse_args()

    if not args.dry_run and not args.i_confirm_post:
        print(
            "本番投稿には --i-confirm-post が必要です。まず --dry-run で確認してください。",
            file=sys.stderr,
        )
        return 2

    load_env()
    sb = supabase_client()
    res = (
        sb.table("glucon_report_drafts")
        .select("*")
        .eq("status", "queued")
        .order("updated_at")
        .limit(args.limit)
        .execute()
    )
    rows = res.data or []
    if not rows:
        print("# no queued drafts")
        return 0

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.show)
        page = browser.new_page()
        try:
            login_page(page)
            for row in rows:
                try:
                    process_row(page, sb, row, dry_run=args.dry_run)
                except Exception as e:
                    print(f"# fail {row.get('id')}: {e}", file=sys.stderr)
        finally:
            if args.show:
                print("--show: 10秒後に閉じます")
                time.sleep(10)
            browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
