#!/usr/bin/env python3
"""
Jarvis: ローカル queue / situation_watch を jarvis-dashboard（Supabase）へ upsert。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  python scripts/jarvis_dashboard_push.py
  python scripts/jarvis_dashboard_push.py --triage-only
  python scripts/jarvis_dashboard_push.py --watch-only

要: JARVIS_SUPABASE_URL + JARVIS_SUPABASE_SERVICE_ROLE_KEY
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from supabase import create_client

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
STATE = REPO / ".jarvis_state"
QUEUE_PATH = STATE / "night_triage" / "queue.json"
WATCH_PATH = STATE / "situation_watch.json"
WATCH_SCRIPT = REPO / "scripts" / "jarvis_situation_watch.py"


def now_iso() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S%z")


def client():
    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        raise SystemExit(
            "JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY が未設定です。"
            " .env.jarvis_private に追記してください（service_role は Dashboard → API）。"
        )
    return create_client(url, key)


def refresh_watch() -> None:
    py = Path.home() / "selenium_env" / "venv" / "bin" / "python"
    import subprocess

    exe = str(py) if py.is_file() else sys.executable
    subprocess.run([exe, str(WATCH_SCRIPT)], cwd=str(REPO), check=False, timeout=60)


def push_triage(sb) -> int:
    if not QUEUE_PATH.is_file():
        print("# triage: queue.json なし", file=sys.stderr)
        return 0
    data = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    items = data.get("items") or []
    rows: list[dict[str, Any]] = []
    for it in items:
        iid = str(it.get("id") or "").strip()
        if not iid:
            continue
        payload = {
            k: it.get(k)
            for k in (
                "reason",
                "draft_gemini",
                "draft_cursor",
                "message_id_header",
                "engine",
            )
            if it.get(k) is not None
        }
        rows.append(
            {
                "id": iid,
                "lane": it.get("lane") or "partner",
                "kind": it.get("kind") or "mail",
                "status": it.get("status") or "pending",
                "partner": it.get("partner") or None,
                "folder": it.get("folder") or None,
                "subject": it.get("subject") or None,
                "received_at": it.get("received_at") or None,
                "summary": it.get("summary") or None,
                "draft_text": it.get("draft_text") or None,
                "original_body": (str(it.get("original_body") or ""))[:8000] or None,
                "priority": it.get("priority") or None,
                "channel": it.get("channel") or None,
                "account": it.get("account") or None,
                "gmail_thread_id": it.get("gmail_thread_id") or None,
                "gmail_message_id": it.get("gmail_message_id") or None,
                "from_email": it.get("from_email") or None,
                "seq": it.get("seq"),
                "payload": payload,
                "updated_at": it.get("updated_at") or now_iso(),
            }
        )
    if not rows:
        print("# triage: 0 rows", file=sys.stderr)
        return 0
    # chunk upsert
    n = 0
    for i in range(0, len(rows), 50):
        chunk = rows[i : i + 50]
        sb.table("triage_items").upsert(chunk, on_conflict="id").execute()
        n += len(chunk)
    sb.table("sync_meta").upsert(
        {"key": "triage_pushed_at", "value": now_iso(), "updated_at": now_iso()},
        on_conflict="key",
    ).execute()
    print(f"# triage upserted {n}", file=sys.stderr)
    return n


def push_watch(sb) -> int:
    refresh_watch()
    if not WATCH_PATH.is_file():
        print("# watch: situation_watch.json なし", file=sys.stderr)
        return 0
    data = json.loads(WATCH_PATH.read_text(encoding="utf-8"))
    items = data.get("items") or []
    rows = []
    for it in items:
        iid = str(it.get("id") or "").strip()
        if not iid:
            continue
        rows.append(
            {
                "id": iid,
                "title": it.get("title") or iid,
                "category": it.get("category") or None,
                "level": it.get("level") or "info",
                "summary": it.get("summary") or None,
                "detail": it.get("detail") or None,
                "source": it.get("source") or None,
                "cursor_prompt": it.get("cursor_prompt") or None,
                "status": it.get("status") or "active",
                "archived_at": it.get("archived_at"),
                "checked_at": it.get("checked_at"),
                "payload": {},
                "updated_at": now_iso(),
            }
        )
    if not rows:
        return 0
    sb.table("watch_status").upsert(rows, on_conflict="id").execute()
    sb.table("sync_meta").upsert(
        {"key": "watch_pushed_at", "value": now_iso(), "updated_at": now_iso()},
        on_conflict="key",
    ).execute()
    print(f"# watch upserted {len(rows)}", file=sys.stderr)
    return len(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--triage-only", action="store_true")
    ap.add_argument("--watch-only", action="store_true")
    args = ap.parse_args(argv)

    sb = client()
    t = w = 0
    if not args.watch_only:
        t = push_triage(sb)
    if not args.triage_only:
        w = push_watch(sb)
    print(json.dumps({"triage": t, "watch": w}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
