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
    # Web で閉じた行（sent/skipped/snoozed/done）を Mac push で pending に戻さない。
    # Web で保存した draft_text / payload メタも潰さない。
    PROTECTED = {"sent", "skipped", "snoozed", "done"}
    KEEP_PAYLOAD = (
        "sent_at",
        "gmail_sent_id",
        "gmail_sent_thread_id",
        "yoritoori_appended",
        "yoritoori_appended_at",
        "web_draft_saved_at",
    )
    remote_by_id: dict[str, dict[str, Any]] = {}
    ids = [str(it.get("id") or "").strip() for it in items if str(it.get("id") or "").strip()]
    try:
        for i in range(0, len(ids), 80):
            chunk_ids = ids[i : i + 80]
            r = (
                sb.table("triage_items")
                .select("id,status,draft_text,payload,updated_at")
                .in_("id", chunk_ids)
                .execute()
            )
            for x in r.data or []:
                remote_by_id[str(x["id"])] = x
    except Exception as e:
        print(f"# triage protected merge skipped: {e}", file=sys.stderr)
    rows: list[dict[str, Any]] = []
    for it in items:
        iid = str(it.get("id") or "").strip()
        if not iid:
            continue
        st = it.get("status") or "pending"
        remote = remote_by_id.get(iid) or {}
        remote_st = str(remote.get("status") or "")
        if st == "pending" and remote_st in PROTECTED:
            st = remote_st
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
        remote_payload = remote.get("payload") if isinstance(remote.get("payload"), dict) else {}
        for k in KEEP_PAYLOAD:
            if remote_payload.get(k) is not None:
                payload[k] = remote_payload[k]
        draft_text = it.get("draft_text") or None
        if remote_payload.get("web_draft_saved_at") and remote.get("draft_text"):
            draft_text = remote.get("draft_text")
        rows.append(
            {
                "id": iid,
                "lane": it.get("lane") or "partner",
                "kind": it.get("kind") or "mail",
                "status": st,
                "partner": it.get("partner") or None,
                "folder": it.get("folder") or None,
                "subject": it.get("subject") or None,
                "received_at": it.get("received_at") or None,
                "summary": it.get("summary") or None,
                "draft_text": draft_text,
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
    sb.table("sync_meta").upsert(
        [
            {"key": "mac_triage_pushed_at", "value": now_iso(), "updated_at": now_iso()},
            {"key": "triage_source", "value": "mac", "updated_at": now_iso()},
        ],
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
    # Web アーカイブを Mac push で潰さない（ローカル archived は優先）
    remote_arch: dict[str, Any] = {}
    try:
        r = (
            sb.table("watch_status")
            .select("id,status,archived_at")
            .eq("status", "archived")
            .execute()
        )
        remote_arch = {x["id"]: x for x in (r.data or [])}
    except Exception as e:
        print(f"# watch archive merge skipped: {e}", file=sys.stderr)
    rows = []
    for it in items:
        iid = str(it.get("id") or "").strip()
        if not iid:
            continue
        st = it.get("status") or "active"
        arch_at = it.get("archived_at")
        if st != "archived" and iid in remote_arch:
            st = "archived"
            arch_at = remote_arch[iid].get("archived_at")
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
                "status": st,
                "archived_at": arch_at,
                "checked_at": it.get("checked_at"),
                "payload": it.get("payload")
                if isinstance(it.get("payload"), dict)
                else {},
                "updated_at": now_iso(),
            }
        )
    if not rows:
        return 0
    sb.table("watch_status").upsert(rows, on_conflict="id").execute()
    sb.table("sync_meta").upsert(
        [
            {"key": "watch_pushed_at", "value": now_iso(), "updated_at": now_iso()},
            {"key": "watch_source", "value": "mac", "updated_at": now_iso()},
        ],
        on_conflict="key",
    ).execute()
    print(f"# watch upserted {len(rows)}", file=sys.stderr)
    return len(rows)


def push_other_mail_digest(sb=None) -> int:
    """パートナー以外メールのダイジェストを sync_meta へ。失敗しても 0。"""
    import subprocess

    py = Path.home() / "selenium_env" / "venv" / "bin" / "python"
    exe = str(py) if py.is_file() else sys.executable
    try:
        r = subprocess.run(
            [exe, str(REPO / "scripts" / "jarvis_other_mail_digest.py"), "--push"],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=120,
            env=os.environ.copy(),
        )
        print(r.stderr or "", file=sys.stderr, end="")
        if r.returncode == 0:
            return 1
        print(f"# other_mail_digest failed rc={r.returncode}", file=sys.stderr)
    except Exception as e:
        print(f"# other_mail_digest failed: {e}", file=sys.stderr)
    return 0


def push_openchat_digest() -> int:
    """815 オプチャ有益ダイジェスト。失敗しても 0。"""
    import subprocess

    py = Path.home() / "selenium_env" / "venv" / "bin" / "python"
    exe = str(py) if py.is_file() else sys.executable
    try:
        r = subprocess.run(
            [exe, str(REPO / "scripts" / "jarvis_openchat_digest.py"), "--push"],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=180,
            env=os.environ.copy(),
        )
        print(r.stderr or "", file=sys.stderr, end="")
        print(r.stdout or "", file=sys.stderr, end="")
        if r.returncode == 0:
            return 1
        print(f"# openchat_digest failed rc={r.returncode}", file=sys.stderr)
    except Exception as e:
        print(f"# openchat_digest failed: {e}", file=sys.stderr)
    return 0


def push_lanes_finance_subscriptions() -> tuple[int, int, int, int]:
    """サブプロセスで lanes / finance / subscriptions / occupancy を集約＋push。失敗しても 0。"""
    import subprocess

    py = Path.home() / "selenium_env" / "venv" / "bin" / "python"
    exe = str(py) if py.is_file() else sys.executable
    cards_n = fin_n = sub_n = occ_n = 0
    try:
        # 機械的大量カードは出さない。要約確認テーマのみ push
        r = subprocess.run(
            [exe, str(REPO / "scripts" / "jarvis_lane_digest.py"), "--push"],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=180,
        )
        print(r.stderr or "", file=sys.stderr, end="")
        if r.returncode == 0:
            cards_n = 1
    except Exception as e:
        print(f"# lane digest push failed: {e}", file=sys.stderr)
    try:
        r = subprocess.run(
            [exe, str(REPO / "scripts" / "jarvis_lane_log_flush.py")],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=60,
        )
        print(r.stderr or "", file=sys.stderr, end="")
        print(r.stdout or "", file=sys.stderr, end="")
    except Exception as e:
        print(f"# lane log flush failed: {e}", file=sys.stderr)
    try:
        r = subprocess.run(
            [exe, str(REPO / "scripts" / "jarvis_finance_metrics.py"), "--push"],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=120,
        )
        print(r.stderr or "", file=sys.stderr, end="")
        if r.returncode == 0:
            fin_n = 1
    except Exception as e:
        print(f"# finance push failed: {e}", file=sys.stderr)
    try:
        r = subprocess.run(
            [exe, str(REPO / "scripts" / "jarvis_subscriptions_push.py"), "--push"],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=60,
        )
        print(r.stderr or "", file=sys.stderr, end="")
        if r.returncode == 0:
            sub_n = 1
    except Exception as e:
        print(f"# subscriptions push failed: {e}", file=sys.stderr)
    try:
        r = subprocess.run(
            [
                exe,
                str(REPO / "scripts" / "jarvis_property_occupancy_from_mail.py"),
                "--push",
            ],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=120,
        )
        print(r.stderr or "", file=sys.stderr, end="")
        if r.returncode == 0:
            occ_n = 1
            print(r.stdout or "", file=sys.stderr, end="")
    except Exception as e:
        print(f"# occupancy mail failed: {e}", file=sys.stderr)
    return cards_n, fin_n, sub_n, occ_n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--triage-only", action="store_true")
    ap.add_argument("--watch-only", action="store_true")
    ap.add_argument("--full", action="store_true", help="lanes/finance/subscriptions も含めて push")
    args = ap.parse_args(argv)

    sb = client()
    t = w = digest = oc_digest = 0
    if not args.watch_only:
        t = push_triage(sb)
        digest = push_other_mail_digest(sb)
        oc_digest = push_openchat_digest()
    if not args.triage_only:
        w = push_watch(sb)
    cards = finance = subscriptions = occupancy = 0
    if args.full or (not args.triage_only and not args.watch_only):
        cards, finance, subscriptions, occupancy = push_lanes_finance_subscriptions()
    print(
        json.dumps(
            {
                "triage": t,
                "watch": w,
                "other_mail_digest": digest,
                "openchat_digest": oc_digest,
                "lanes": cards,
                "finance": finance,
                "subscriptions": subscriptions,
                "occupancy_mail": occupancy,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())