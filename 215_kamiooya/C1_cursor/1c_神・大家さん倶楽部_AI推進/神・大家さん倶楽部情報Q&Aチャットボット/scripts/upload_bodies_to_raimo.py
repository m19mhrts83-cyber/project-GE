#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""管理者CSVの本文を Raimo comments へ投入（欠落insert / 短い本文は update-content）。

  python3 upload_bodies_to_raimo.py --csv exports/full_bodies_*.csv
  python3 upload_bodies_to_raimo.py --csv ... --clean-junk
  python3 upload_bodies_to_raimo.py --csv ... --limit 50 --dry-run
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
CHATBOT = SCRIPTS.parent
API_PREFIX = "/miniAppApi/be_nXbcTm3EumRbotHtAwGGXb45raHz0"
JUNK_PREFIXES = ("trigger-", "edit-", "reply-", "test-")


def load_env() -> None:
    for p in (
        Path.home() / "git-repos" / ".env.jarvis_private",
        CHATBOT / "scripts" / ".env",
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
        ("RAIMO_PORTAL_EMAIL", "LIMO_PORTAL_EMAIL"),
        ("RAIMO_PORTAL_PASSWORD", "LIMO_PORTAL_PASSWORD"),
    ]:
        if not os.environ.get(a) and os.environ.get(b):
            os.environ[a] = os.environ[b]


def cell(row: dict[str, str], *keys: str) -> str:
    for k in keys:
        if k in row and row[k] is not None:
            v = str(row[k]).strip()
            if v:
                return v
    return ""


def read_csv_records(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig", newline="", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cid = cell(row, "コメントID", "comment_id", "commentId")
            if cid.startswith("comment-"):
                cid = cid[8:]
            if not cid.isdigit():
                continue
            content = cell(row, "コメント内容", "content", "本文")
            if not content:
                continue
            out.append(
                {
                    "comment_id": cid,
                    "content": content,
                    "posted_at": cell(row, "投稿日時", "posted_at") or None,
                    "author_name": cell(row, "投稿者名", "author_name") or None,
                    "author_email": cell(row, "投稿者メール", "author_email") or None,
                    "source_type": cell(row, "ソース", "source_type") or "WeStudy",
                    "parent_comment_id": cell(row, "親コメントID", "parent_comment_id") or None,
                    "ip_address": cell(row, "IP アドレス", "ip_address") or None,
                    "user_agent": cell(row, "ユーザーエージェント", "user_agent") or None,
                }
            )
    return out


def login_app(page, app_url: str) -> None:
    page.goto(app_url + "/", wait_until="domcontentloaded", timeout=180000)
    page.wait_for_timeout(2000)
    # ポータル経由の場合があるのでメール欄を待つ
    email = (
        os.environ.get("RAIMO_ADMIN_EMAIL")
        or os.environ.get("RAIMO_APP_EMAIL")
        or os.environ.get("RAIMO_PORTAL_EMAIL")
        or ""
    )
    password = (
        os.environ.get("RAIMO_ADMIN_PASSWORD")
        or os.environ.get("RAIMO_APP_PASSWORD")
        or os.environ.get("RAIMO_PORTAL_PASSWORD")
        or ""
    )
    if page.locator("#loginEmail").count():
        page.fill("#loginEmail", email)
        page.fill("#loginPassword", password)
        page.click("#loginSubmitBtn")
        page.wait_for_timeout(5000)
    elif page.locator('input[type="email"]').count():
        page.fill('input[type="email"]', email)
        page.fill('input[type="password"]', password)
        page.click('button:has-text("ログイン")')
        page.wait_for_timeout(5000)
        # アプリログインが続く場合
        if page.locator("#loginEmail").count():
            app_email = os.environ.get("RAIMO_APP_EMAIL") or email
            app_pass = os.environ.get("RAIMO_APP_PASSWORD") or password
            page.fill("#loginEmail", app_email)
            page.fill("#loginPassword", app_pass)
            page.click("#loginSubmitBtn")
            page.wait_for_timeout(5000)


def fetch_existing(page, app_url: str) -> dict[str, dict[str, Any]]:
    resp = page.request.get(app_url + API_PREFIX + "/comments", timeout=180000)
    if resp.status >= 400:
        raise RuntimeError(f"GET /comments HTTP {resp.status}: {resp.text()[:200]}")
    data = resp.json()
    rows = data.get("comments") or data.get("data") or []
    if isinstance(data, list):
        rows = data
    by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        cid = str(row.get("comment_id") or row.get("commentId") or "").strip()
        if cid:
            by_id[cid] = row
    return by_id


def main() -> int:
    load_env()
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--clean-junk", action="store_true")
    ap.add_argument("--dates-only", action="store_true", help="posted_at が空の既存行に日時だけ補完")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    csv_path = Path(args.csv).expanduser().resolve()
    records = read_csv_records(csv_path)
    print(f"csv_records={len(records)} file={csv_path}")
    if args.limit > 0:
        records = records[: args.limit]
        print(f"limit -> {len(records)}")

    app_url = (os.environ.get("RAIMO_APP_URL") or "").rstrip("/")
    if not app_url:
        print("RAIMO_APP_URL 未設定", file=sys.stderr)
        return 2

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        login_app(page, app_url)
        existing = fetch_existing(page, app_url)
        print(f"raimo_existing={len(existing)}")

        if args.clean_junk:
            junk = [
                row
                for cid, row in existing.items()
                if (not str(cid).isdigit())
                or any(str(cid).startswith(pref) for pref in JUNK_PREFIXES)
            ]
            print(f"junk_candidates={len(junk)}")
            deleted = 0
            for row in junk:
                rid = str(row.get("id") or "").strip()
                if not rid:
                    continue
                if args.dry_run:
                    deleted += 1
                    continue
                resp = page.request.post(
                    app_url + API_PREFIX + f"/admin/comments/{rid}/delete",
                    data=json.dumps({}),
                    headers={"Content-Type": "application/json"},
                    timeout=60000,
                )
                if 200 <= resp.status < 300:
                    deleted += 1
            print(f"junk_deleted={deleted}")
            existing = fetch_existing(page, app_url)
            print(f"raimo_existing_after_clean={len(existing)}")

        to_insert: list[dict[str, Any]] = []
        to_update: list[dict[str, Any]] = []
        to_date: list[dict[str, Any]] = []
        skip = 0
        for rec in records:
            cid = rec["comment_id"]
            old = existing.get(cid)
            if args.dates_only:
                if not rec.get("posted_at"):
                    skip += 1
                    continue
                if not old:
                    skip += 1
                    continue
                old_pa = str(old.get("posted_at") or old.get("postedAt") or "").strip()
                if old_pa:
                    skip += 1
                    continue
                to_date.append(rec)
                continue
            if not old:
                to_insert.append(rec)
                continue
            old_len = len(str(old.get("content") or "").strip())
            new_len = len(rec["content"])
            if new_len > old_len + 20:
                to_update.append(rec)
            else:
                skip += 1

        if args.dates_only:
            print(f"plan date_backfill={len(to_date)} skip={skip}")
        else:
            print(f"plan insert={len(to_insert)} update={len(to_update)} skip={skip}")
        if args.dry_run:
            browser.close()
            return 0

        def do_date_update(rec: dict[str, Any]) -> tuple[str, bool, str]:
            payload = {
                "comment_id": rec["comment_id"],
                "posted_at": rec.get("posted_at"),
            }
            payload = {k: v for k, v in payload.items() if v is not None and v != ""}
            resp = page.request.post(
                app_url + API_PREFIX + "/admin/comments/update-posted-at",
                data=json.dumps(payload),
                headers={"Content-Type": "application/json"},
                timeout=120000,
            )
            if 200 <= resp.status < 300:
                return rec["comment_id"], True, ""
            return rec["comment_id"], False, f"HTTP {resp.status} {resp.text()[:120]}"

        ok_i = fail_i = ok_u = fail_u = ok_d = fail_d = 0

        if args.dates_only:
            for i, rec in enumerate(to_date, 1):
                cid, ok, err = do_date_update(rec)
                if ok:
                    ok_d += 1
                else:
                    fail_d += 1
                    if fail_d <= 8:
                        print(f"[DATE ERR] {cid}: {err}", file=sys.stderr)
                if i % 200 == 0:
                    print(f"  date {i}/{len(to_date)} ok={ok_d} fail={fail_d}", flush=True)
                    time.sleep(0.15)
            browser.close()
            print(f"raimo dates done: ok={ok_d} fail={fail_d} skip={skip}")
            return 0 if fail_d == 0 else 1

        ok_i = fail_i = ok_u = fail_u = 0

        def do_update(rec: dict[str, Any]) -> tuple[str, bool, str]:
            payload = {
                "comment_id": rec["comment_id"],
                "content": rec["content"],
                "posted_at": rec.get("posted_at"),
                "author_name": rec.get("author_name"),
                "author_email": rec.get("author_email"),
                "source_type": rec.get("source_type"),
                "parent_comment_id": rec.get("parent_comment_id"),
            }
            # Raimo DSL は null で落ちることがあるため空は送らない
            payload = {k: v for k, v in payload.items() if v is not None and v != ""}
            resp = page.request.post(
                app_url + API_PREFIX + "/admin/comments/update-content",
                data=json.dumps(payload),
                headers={"Content-Type": "application/json"},
                timeout=120000,
            )
            if 200 <= resp.status < 300:
                return rec["comment_id"], True, ""
            return rec["comment_id"], False, f"HTTP {resp.status} {resp.text()[:120]}"

        def do_insert(rec: dict[str, Any]) -> tuple[str, bool, str]:
            payload = {k: v for k, v in rec.items() if v is not None and v != ""}
            resp = page.request.post(
                app_url + API_PREFIX + "/admin/comments",
                data=json.dumps(payload),
                headers={"Content-Type": "application/json"},
                timeout=120000,
            )
            if 200 <= resp.status < 300:
                return rec["comment_id"], True, ""
            return rec["comment_id"], False, f"HTTP {resp.status} {resp.text()[:120]}"

        # Playwright request は同一 page で直列が安全
        for i, rec in enumerate(to_insert, 1):
            cid, ok, err = do_insert(rec)
            if ok:
                ok_i += 1
            else:
                fail_i += 1
                if fail_i <= 8:
                    print(f"[INSERT ERR] {cid}: {err}", file=sys.stderr)
            if i % 200 == 0:
                print(f"  insert {i}/{len(to_insert)} ok={ok_i} fail={fail_i}", flush=True)
                time.sleep(0.15)

        for i, rec in enumerate(to_update, 1):
            cid, ok, err = do_update(rec)
            if ok:
                ok_u += 1
            else:
                fail_u += 1
                if fail_u <= 8:
                    print(f"[UPDATE ERR] {cid}: {err}", file=sys.stderr)
            if i % 200 == 0:
                print(f"  update {i}/{len(to_update)} ok={ok_u} fail={fail_u}", flush=True)
                time.sleep(0.15)

        browser.close()

    print(
        f"raimo bodies done: insert_ok={ok_i} insert_fail={fail_i} "
        f"update_ok={ok_u} update_fail={fail_u} skip={skip}"
    )
    return 0 if (fail_i + fail_u) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
