#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WeStudy コースページから lesson メタを取り、Raimo comments に backfill する。

コースタブ / 目次 / レッスンタイトル / URL を埋め、本文先頭の「目次 [非表示]…」を除去する。

  python3 backfill_lesson_meta_to_raimo.py --dry-run
  python3 backfill_lesson_meta_to_raimo.py
  python3 backfill_lesson_meta_to_raimo.py --limit 10
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
CHATBOT = SCRIPTS.parent
API_PREFIX = "/miniAppApi/be_nXbcTm3EumRbotHtAwGGXb45raHz0"
ALFRED = Path.home() / "git-repos" / "ProgramCode" / "alfred_python"


def load_env() -> None:
    for p in (
        Path.home() / "git-repos" / ".env.jarvis_private",
        CHATBOT / "scripts" / ".env",
        Path.home()
        / "Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部"
        / "C1_cursor/1c_神・大家さん倶楽部_AI推進"
        / "神・大家さん倶楽部情報Q&Aチャットボット/scripts/.env",
    ):
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    for a, b in [
        ("RAIMO_APP_URL", "LIMO_APP_URL"),
        ("RAIMO_ADMIN_EMAIL", "LIMO_ADMIN_EMAIL"),
        ("RAIMO_ADMIN_PASSWORD", "LIMO_ADMIN_PASSWORD"),
        ("RAIMO_APP_EMAIL", "LIMO_APP_EMAIL"),
        ("RAIMO_APP_PASSWORD", "LIMO_APP_PASSWORD"),
    ]:
        if not os.environ.get(a) and os.environ.get(b):
            os.environ[a] = os.environ[b]


def strip_mokuji_prefix(text: str) -> str:
    t = (text or "").strip()
    if not t.startswith("目次"):
        return t
    lines = t.split("\n")
    i = 0
    while i < len(lines) and (
        lines[i].strip().startswith("目次")
        or (i == 0 and "目次" in lines[i][:20] and "[非表示]" in lines[i])
    ):
        i += 1
    return "\n".join(lines[i:]).strip() or t


def slug_from_url(url: str) -> str:
    m = re.search(r"/lesson/([^/?#]+)", url or "")
    return m.group(1) if m else (url or "").rstrip("/").split("/")[-1]


def collect_meta_map() -> dict[str, dict[str, str]]:
    if not ALFRED.is_dir():
        raise SystemExit(f"westudy scraper が見つかりません: {ALFRED}")
    sys.path.insert(0, str(ALFRED))
    import westudy_lesson_pages as wlp  # noqa: E402

    wlp.driver = wlp.create_driver(headless=True)
    meta: dict[str, dict[str, str]] = {}
    try:
        wlp.login_westudy()
        for tab in wlp.COURSE_TABS:
            lessons = wlp.collect_sections_and_lessons(tab)
            for lesson in lessons:
                url = (lesson.get("url") or "").strip()
                slug = slug_from_url(url)
                if not slug:
                    continue
                cid = f"lesson_desc_{slug}"
                title = (lesson.get("title") or slug).strip()
                # リンク文言が長すぎる／ノイズのときは slug を優先しない
                if len(title) > 200:
                    title = slug
                meta[cid] = {
                    "course_tab": tab["label"],
                    "section_name": (lesson.get("section") or "").strip(),
                    "lesson_title": title,
                    "lesson_url": url,
                }
    finally:
        try:
            wlp.driver.quit()
        except Exception:
            pass
        wlp.driver = None
    return meta


def main() -> int:
    load_env()
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-scrape", action="store_true", help="WeStudy 取得をスキップ（本文の目次除去のみ）")
    args = ap.parse_args()

    meta_map: dict[str, dict[str, str]] = {}
    if not args.skip_scrape:
        print("WeStudy コースページからメタ収集中…", flush=True)
        meta_map = collect_meta_map()
        print(f"meta_map={len(meta_map)}", flush=True)

    app_url = (os.environ.get("RAIMO_APP_URL") or "").rstrip("/")
    email = (
        os.environ.get("RAIMO_ADMIN_EMAIL")
        or os.environ.get("RAIMO_APP_EMAIL")
        or ""
    )
    password = (
        os.environ.get("RAIMO_ADMIN_PASSWORD")
        or os.environ.get("RAIMO_APP_PASSWORD")
        or ""
    )
    if not app_url or not email or not password:
        print("RAIMO_APP_URL / ADMIN or APP credentials が必要です", file=sys.stderr)
        return 2

    from playwright.sync_api import sync_playwright

    ok = 0
    fail = 0
    skip = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(app_url + "/", wait_until="domcontentloaded", timeout=120000)
        page.wait_for_timeout(2000)
        if page.locator("#loginEmail").count():
            page.fill("#loginEmail", email)
            page.fill("#loginPassword", password)
            page.click("#loginSubmitBtn")
            page.wait_for_timeout(4000)

        resp = page.request.get(app_url + API_PREFIX + "/comments", timeout=120000)
        if resp.status >= 400:
            print(f"comments fetch failed: {resp.status} {resp.text()[:200]}", file=sys.stderr)
            browser.close()
            return 1
        data = resp.json()
        comments = data.get("comments") if isinstance(data, dict) else data
        if not isinstance(comments, list):
            print("unexpected comments payload", file=sys.stderr)
            browser.close()
            return 1

        lessons = [
            c
            for c in comments
            if str(c.get("comment_id") or "").startswith("lesson_desc_")
            or str(c.get("source_system") or "") == "lesson"
        ]
        if args.limit > 0:
            lessons = lessons[: args.limit]
        print(f"lesson_rows={len(lessons)}", flush=True)

        if args.dry_run:
            for c in lessons[:5]:
                cid = str(c.get("comment_id") or "")
                m = meta_map.get(cid) or {}
                print(
                    "sample",
                    cid,
                    "course=",
                    m.get("course_tab"),
                    "section=",
                    (m.get("section_name") or "")[:40],
                    "title=",
                    (m.get("lesson_title") or "")[:40],
                )
            browser.close()
            return 0

        for i, c in enumerate(lessons, 1):
            cid = str(c.get("comment_id") or "").strip()
            m = meta_map.get(cid) or {}
            content = strip_mokuji_prefix(str(c.get("content") or ""))
            payload = {
                "comment_id": cid,
                "content": content,
                "posted_at": c.get("posted_at"),
                "author_name": c.get("author_name") or "WeStudy",
                "author_email": c.get("author_email") or "",
                "source_type": c.get("source_type") or "WeStudy",
                "source_system": "lesson",
                "source_kind": "lesson_desc",
                "forum_category": m.get("course_tab") or c.get("forum_category") or "",
                "topic_title": m.get("lesson_title") or c.get("topic_title") or "",
                "parent_comment_id": c.get("parent_comment_id") or "",
                "course_tab": m.get("course_tab") or c.get("course_tab") or "",
                "section_name": m.get("section_name") or c.get("section_name") or "",
                "lesson_title": m.get("lesson_title") or c.get("lesson_title") or "",
                "lesson_url": m.get("lesson_url") or c.get("lesson_url") or "",
                "content_hash": c.get("content_hash") or "",
            }
            if not payload["course_tab"] and not payload["lesson_title"] and content == str(
                c.get("content") or ""
            ).strip():
                skip += 1
                continue
            try:
                r = page.request.post(
                    app_url + API_PREFIX + "/admin/comments/update-content",
                    data=json.dumps(payload),
                    headers={"Content-Type": "application/json"},
                    timeout=60000,
                )
                if 200 <= r.status < 300:
                    ok += 1
                else:
                    fail += 1
                    if fail <= 5:
                        print(f"[ERR] {cid} HTTP {r.status} {r.text()[:180]}", file=sys.stderr)
            except Exception as e:
                fail += 1
                if fail <= 5:
                    print(f"[ERR] {cid}: {e}", file=sys.stderr)
            if i % 50 == 0:
                print(f"  progress {i}/{len(lessons)} ok={ok} fail={fail} skip={skip}", flush=True)
                time.sleep(0.15)

        browser.close()

    print(f"lesson meta backfill done: ok={ok} fail={fail} skip={skip}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
