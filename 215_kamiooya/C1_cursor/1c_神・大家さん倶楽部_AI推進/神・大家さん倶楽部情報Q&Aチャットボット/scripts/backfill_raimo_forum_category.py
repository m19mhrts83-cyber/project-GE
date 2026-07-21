#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Raimo comments の forum_category を raw/lookup から更新する。

  1) publish 後の API（POST /admin/comments/update-category）をアプリURL経由で呼ぶ
  2) 管理者でミニアプリにログインしてから実行

  python3 backfill_raimo_forum_category.py --lookup ../forum_category_lookup.json
  python3 backfill_raimo_forum_category.py --raw-dir ../../exports/raw/20260721-112905 --limit 20
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
CHATBOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))
from forum_category_map import enrich_comment_meta  # noqa: E402

API_PREFIX = "/miniAppApi/be_nXbcTm3EumRbotHtAwGGXb45raHz0"


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
    ]:
        if not os.environ.get(a) and os.environ.get(b):
            os.environ[a] = os.environ[b]


def collect_from_raw(raw_dir: Path) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for fp in raw_dir.rglob("*.csv"):
        try:
            with fp.open("r", encoding="utf-8-sig", newline="", errors="replace") as f:
                reader = csv.DictReader(f)
                if not reader.fieldnames or "comment_id" not in reader.fieldnames:
                    continue
                for row in reader:
                    cid = (row.get("comment_id") or "").strip().strip('"')
                    if cid.startswith("comment-"):
                        cid = cid[8:]
                    if not cid:
                        continue
                    meta = enrich_comment_meta(row.get("topic_title") or "", row.get("topic_url") or "")
                    if meta["forum_category"] == "未分類":
                        continue
                    out[cid] = meta
        except Exception as e:
            print(f"[WARN] {fp}: {e}", file=sys.stderr)
    return out


def collect_from_lookup(path: Path) -> dict[str, dict[str, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, dict[str, str]] = {}
    for cid, cat in data.items():
        cat_s = str(cat).strip()
        if not cat_s or cat_s == "未分類":
            continue
        out[str(cid)] = {
            "source_system": "WeStudy",
            "source_kind": "コミュニティ情報",
            "forum_category": cat_s,
            "topic_title": "",
        }
    return out


def main() -> int:
    load_env()
    ap = argparse.ArgumentParser()
    ap.add_argument("--lookup", default=str(CHATBOT / "forum_category_lookup.json"))
    ap.add_argument("--raw-dir", default="")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    mapping: dict[str, dict[str, str]] = {}
    if args.raw_dir:
        mapping.update(collect_from_raw(Path(args.raw_dir).expanduser()))
    lp = Path(args.lookup).expanduser()
    if lp.is_file():
        mapping.update(collect_from_lookup(lp))
    print(f"mapping size: {len(mapping)}")
    if args.limit > 0:
        mapping = dict(list(mapping.items())[: args.limit])

    if args.dry_run:
        print("dry-run sample:", list(mapping.items())[:3])
        return 0

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
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(app_url + "/", wait_until="domcontentloaded", timeout=120000)
        page.wait_for_timeout(2000)
        # ログインフォーム
        if page.locator("#loginEmail").count():
            page.fill("#loginEmail", email)
            page.fill("#loginPassword", password)
            page.click("#loginSubmitBtn")
            page.wait_for_timeout(4000)

        for i, (cid, meta) in enumerate(mapping.items(), 1):
            payload = {
                "comment_id": cid,
                "source_system": meta.get("source_system") or "WeStudy",
                "source_kind": meta.get("source_kind") or "コミュニティ情報",
                "forum_category": meta["forum_category"],
                "topic_title": meta.get("topic_title") or "",
            }
            try:
                resp = page.request.post(
                    app_url + API_PREFIX + "/admin/comments/update-category",
                    data=json.dumps(payload),
                    headers={"Content-Type": "application/json"},
                    timeout=60000,
                )
                if resp.status >= 200 and resp.status < 300:
                    ok += 1
                else:
                    fail += 1
                    if fail <= 5:
                        print(f"[ERR] {cid} HTTP {resp.status} {resp.text()[:160]}", file=sys.stderr)
            except Exception as e:
                fail += 1
                if fail <= 5:
                    print(f"[ERR] {cid}: {e}", file=sys.stderr)
            if i % 200 == 0:
                print(f"  progress {i}/{len(mapping)} ok={ok} fail={fail}", flush=True)
                time.sleep(0.2)
        browser.close()

    print(f"raimo backfill done: ok={ok} fail={fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
