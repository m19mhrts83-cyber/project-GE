#!/usr/bin/env python3
"""
ダッシュボード「聞く」の Mac Cursor キューを処理する。

cards / watch_status / triage_items の payload.cursor_ask.status=queued を拾い、
ローカル cursor_generate で返答する。

既存 revise worker と同じ launchd 間隔から呼ぶ想定:

  python scripts/jarvis_card_cursor_ask_worker.py
  python scripts/jarvis_card_cursor_ask_worker.py --dry-run
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from jarvis_night_triage import cursor_generate  # noqa: E402


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def strip_fences(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        lines = t.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        t = "\n".join(lines).strip()
    return t


def build_reply_prompt(handoff: str) -> str:
    return "\n".join(
        [
            "あなたは Jarvis（秘書 AI）です。ダッシュボードから引き継いだ相談に日本語で答えてください。",
            "手元のファイルやツールが必要なら使ってよい。推測で事実を捏造しない。",
            "出力は返答本文のみ。前置き・コードフェンスは付けない。8〜20行を目安。",
            "",
            handoff.strip(),
        ]
    )


def process_row(
    sb: Any,
    *,
    table: str,
    id_field: str,
    comment_table: str,
    comment_fk: str,
    row: dict[str, Any],
    dry_run: bool,
) -> str:
    item_id = row[id_field]
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    ask = payload.get("cursor_ask") if isinstance(payload.get("cursor_ask"), dict) else {}
    prompt = str(ask.get("prompt") or "").strip()
    if not prompt:
        return "skip_empty"

    print(f"# ask {table} id={item_id}")
    if dry_run:
        return "dry_run"

    running = dict(payload)
    running_ask = dict(ask)
    running_ask["status"] = "running"
    running_ask["started_at"] = now_iso()
    running["cursor_ask"] = running_ask
    sb.table(table).update({"payload": running, "updated_at": now_iso()}).eq(
        id_field, item_id
    ).execute()

    try:
        raw = cursor_generate(build_reply_prompt(prompt))
        reply = strip_fences(raw)
        if not reply:
            raise RuntimeError("Cursor Agent 応答が空")
        body = f"〔via: ローカル Cursor（Mac）〕\n\n{reply[:2000]}"
        sb.table(comment_table).insert(
            {comment_fk: item_id, "role": "jarvis", "body": body}
        ).execute()
    except Exception as e:
        err_payload = dict(payload)
        err_ask = dict(ask)
        err_ask["status"] = "error"
        err_ask["error"] = str(e)[:400]
        err_ask["finished_at"] = now_iso()
        err_payload["cursor_ask"] = err_ask
        sb.table(table).update(
            {"payload": err_payload, "updated_at": now_iso()}
        ).eq(id_field, item_id).execute()
        print(f"# error {table} id={item_id}: {e}", file=sys.stderr)
        return "error"

    ok_payload: dict[str, Any] = dict(payload)
    ok_ask = dict(ask)
    ok_ask["status"] = "done"
    ok_ask["finished_at"] = now_iso()
    ok_ask["via"] = "local_worker"
    ok_ask.pop("error", None)
    ok_payload["cursor_ask"] = ok_ask
    sb.table(table).update(
        {"payload": ok_payload, "updated_at": now_iso()}
    ).eq(id_field, item_id).execute()
    print(f"# done {table} id={item_id} chars={len(reply)}")
    return "done"


def process_triage_row(
    sb: Any,
    row: dict[str, Any],
    *,
    dry_run: bool,
) -> str:
    """triage_items は comments テーブルが無いので payload.cursor_ask.reply に書く。"""
    item_id = row["id"]
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    ask = payload.get("cursor_ask") if isinstance(payload.get("cursor_ask"), dict) else {}
    prompt = str(ask.get("prompt") or "").strip()
    if not prompt:
        return "skip_empty"

    print(f"# ask triage_items id={item_id}")
    if dry_run:
        return "dry_run"

    running = dict(payload)
    running_ask = dict(ask)
    running_ask["status"] = "running"
    running_ask["started_at"] = now_iso()
    running["cursor_ask"] = running_ask
    sb.table("triage_items").update({"payload": running, "updated_at": now_iso()}).eq(
        "id", item_id
    ).execute()

    try:
        raw = cursor_generate(build_reply_prompt(prompt))
        reply = strip_fences(raw)
        if not reply:
            raise RuntimeError("Cursor Agent 応答が空")
        body = f"〔via: ローカル Cursor（Mac）〕\n\n{reply[:4000]}"
    except Exception as e:
        err_payload = dict(payload)
        err_ask = dict(ask)
        err_ask["status"] = "error"
        err_ask["error"] = str(e)[:400]
        err_ask["finished_at"] = now_iso()
        err_payload["cursor_ask"] = err_ask
        sb.table("triage_items").update(
            {"payload": err_payload, "updated_at": now_iso()}
        ).eq("id", item_id).execute()
        print(f"# error triage_items id={item_id}: {e}", file=sys.stderr)
        return "error"

    ok_payload: dict[str, Any] = dict(payload)
    ok_ask = dict(ask)
    ok_ask["status"] = "done"
    ok_ask["finished_at"] = now_iso()
    ok_ask["via"] = "local_worker"
    ok_ask["reply"] = body
    ok_ask.pop("error", None)
    ok_payload["cursor_ask"] = ok_ask
    sb.table("triage_items").update(
        {"payload": ok_payload, "updated_at": now_iso()}
    ).eq("id", item_id).execute()
    print(f"# done triage_items id={item_id} chars={len(reply)}")
    return "done"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Process Cursor ask queue from dashboard cards/watch")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=3)
    args = ap.parse_args(argv)

    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        print("# JARVIS_SUPABASE_* 未設定", file=sys.stderr)
        return 1

    from supabase import create_client

    sb = create_client(url, key)
    done = 0
    failed = 0
    scanned = 0

    card_r = (
        sb.table("cards")
        .select("id,title,payload")
        .filter("payload->cursor_ask->>status", "eq", "queued")
        .order("updated_at", desc=False)
        .limit(args.limit)
        .execute()
    )
    for row in card_r.data or []:
        scanned += 1
        st = process_row(
            sb,
            table="cards",
            id_field="id",
            comment_table="card_comments",
            comment_fk="card_id",
            row=row,
            dry_run=args.dry_run,
        )
        if st in ("done", "dry_run"):
            done += 1
        elif st == "error":
            failed += 1

    watch_r = (
        sb.table("watch_status")
        .select("id,title,payload")
        .filter("payload->cursor_ask->>status", "eq", "queued")
        .order("updated_at", desc=False)
        .limit(args.limit)
        .execute()
    )
    for row in watch_r.data or []:
        scanned += 1
        st = process_row(
            sb,
            table="watch_status",
            id_field="id",
            comment_table="watch_comments",
            comment_fk="watch_id",
            row=row,
            dry_run=args.dry_run,
        )
        if st in ("done", "dry_run"):
            done += 1
        elif st == "error":
            failed += 1

    triage_r = (
        sb.table("triage_items")
        .select("id,subject,payload")
        .filter("payload->cursor_ask->>status", "eq", "queued")
        .order("updated_at", desc=False)
        .limit(args.limit)
        .execute()
    )
    for row in triage_r.data or []:
        scanned += 1
        st = process_triage_row(sb, row, dry_run=args.dry_run)
        if st in ("done", "dry_run"):
            done += 1
        elif st == "error":
            failed += 1

    print(f"# cursor ask done={done} failed={failed} scanned={scanned}")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
