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
    err_ask["retry_count"] = int(err_ask.get("retry_count") or 0) + 1
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
        err_ask["retry_count"] = int(err_ask.get("retry_count") or 0) + 1
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


def recover_stale_running(sb: Any, *, timeout_minutes: int = 10) -> int:
    """running のまま放置されたゾンビを queued に戻す"""
    recovered = 0
    cutoff = datetime.now(timezone.utc).timestamp() - (timeout_minutes * 60)
    for table, id_f, title_f in [
        ("cards", "id", "title"),
        ("watch_status", "id", "title"),
        ("triage_items", "id", "subject"),
    ]:
        try:
            r = (
                sb.table(table)
                .select(f"{id_f},{title_f},payload")
                .filter("payload->cursor_ask->>status", "eq", "running")
                .execute()
            )
            for row in r.data or []:
                payload = row.get("payload") or {}
                ask = payload.get("cursor_ask") or {}
                started = ask.get("started_at")
                if not started:
                    continue
                try:
                    st_ts = datetime.fromisoformat(started.replace("Z", "+00:00")).timestamp()
                except Exception:
                    st_ts = 0
                if st_ts < cutoff:
                    item_id = row[id_f]
                    print(f"# recover stale running {table} id={item_id}")
                    ask["status"] = "queued"
                    ask["recovered_at"] = now_iso()
                    ask["retry_count"] = int(ask.get("retry_count") or 0) + 1
                    payload["cursor_ask"] = ask
                    sb.table(table).update({"payload": payload, "updated_at": now_iso()}).eq(
                        id_f, item_id
                    ).execute()
                    recovered += 1
        except Exception as e:
            print(f"# error recover_stale_running {table}: {e}", file=sys.stderr)
    return recovered


def auto_retry_errors(sb: Any, *, max_retries: int = 2, within_minutes: int = 15) -> int:
    """直近のエラータスクで retry_count 未満のものを自動再試行"""
    retried = 0
    cutoff = datetime.now(timezone.utc).timestamp() - (within_minutes * 60)
    for table, id_f, title_f in [
        ("cards", "id", "title"),
        ("watch_status", "id", "title"),
        ("triage_items", "id", "subject"),
    ]:
        try:
            r = (
                sb.table(table)
                .select(f"{id_f},{title_f},payload")
                .filter("payload->cursor_ask->>status", "eq", "error")
                .execute()
            )
            for row in r.data or []:
                payload = row.get("payload") or {}
                ask = payload.get("cursor_ask") or {}
                retries = int(ask.get("retry_count") or 0)
                if retries >= max_retries:
                    continue
                finished = ask.get("finished_at")
                if not finished:
                    continue
                try:
                    fn_ts = datetime.fromisoformat(finished.replace("Z", "+00:00")).timestamp()
                except Exception:
                    fn_ts = 0
                if fn_ts >= cutoff:
                    item_id = row[id_f]
                    print(f"# auto-retry {table} id={item_id} (attempt {retries + 1})")
                    ask["status"] = "queued"
                    ask["last_retry_at"] = now_iso()
                    payload["cursor_ask"] = ask
                    sb.table(table).update({"payload": payload, "updated_at": now_iso()}).eq(
                        id_f, item_id
                    ).execute()
                    retried += 1
        except Exception as e:
            print(f"# error auto_retry_errors {table}: {e}", file=sys.stderr)
    return retried


def sync_worker_status_json(sb: Any) -> dict[str, Any]:
    """現在の Supabase 状態を集計して .jarvis_state/cursor_worker_status.json に書き出す"""
    import json
    state_file = REPO / ".jarvis_state" / "cursor_worker_status.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)

    status_data: dict[str, Any] = {
        "updated_at": now_iso(),
        "worker_alive": True,
        "last_heartbeat": now_iso(),
        "queued_items": [],
        "running_items": [],
        "error_items": [],
        "recent_done": [],
        "counts": {
            "queued": 0,
            "running": 0,
            "error": 0,
            "done_recent": 0,
        },
    }

    recent_cutoff = datetime.now(timezone.utc).timestamp() - (24 * 3600)

    for table, id_f, title_f, kind in [
        ("cards", "id", "title", "card"),
        ("watch_status", "id", "title", "watch"),
        ("triage_items", "id", "subject", "triage"),
    ]:
        try:
            r = (
                sb.table(table)
                .select(f"{id_f},{title_f},payload,updated_at")
                .filter("payload->cursor_ask->>status", "neq", "null")
                .execute()
            )
            for row in r.data or []:
                payload = row.get("payload") or {}
                ask = payload.get("cursor_ask") or {}
                st = ask.get("status")
                item_id = str(row[id_f])
                title = str(row.get(title_f) or item_id)
                href = f"/situation?watch={item_id}" if kind == "watch" else "/"

                item_info = {
                    "id": item_id,
                    "kind": kind,
                    "title": title,
                    "status": st,
                    "via": ask.get("via"),
                    "href": href,
                }

                if st == "queued":
                    item_info["requested_at"] = ask.get("requested_at")
                    status_data["queued_items"].append(item_info)
                elif st == "running":
                    item_info["started_at"] = ask.get("started_at")
                    status_data["running_items"].append(item_info)
                elif st == "error":
                    item_info["error"] = ask.get("error")
                    item_info["finished_at"] = ask.get("finished_at")
                    item_info["retry_count"] = ask.get("retry_count")
                    status_data["error_items"].append(item_info)
                elif st == "done":
                    finished = ask.get("finished_at")
                    fn_ts = 0
                    if finished:
                        try:
                            fn_ts = datetime.fromisoformat(finished.replace("Z", "+00:00")).timestamp()
                        except Exception:
                            pass
                    if fn_ts >= recent_cutoff:
                        item_info["finished_at"] = finished
                        status_data["recent_done"].append(item_info)
        except Exception as e:
            print(f"# error sync_worker_status_json {table}: {e}", file=sys.stderr)

    # ソート
    status_data["recent_done"].sort(key=lambda x: str(x.get("finished_at") or ""), reverse=True)
    status_data["recent_done"] = status_data["recent_done"][:10]

    status_data["counts"]["queued"] = len(status_data["queued_items"])
    status_data["counts"]["running"] = len(status_data["running_items"])
    status_data["counts"]["error"] = len(status_data["error_items"])
    status_data["counts"]["done_recent"] = len(status_data["recent_done"])

    try:
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(status_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"# error write {state_file}: {e}", file=sys.stderr)

    return status_data


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Process Cursor ask queue from dashboard cards/watch")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=3)
    ap.add_argument("--status-only", action="store_true", help="キュー処理せず状態JSONのみ同期")
    ap.add_argument("--retry-all-failed", action="store_true", help="失敗した全タスクを再試行キューに戻す")
    args = ap.parse_args(argv)

    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        print("# JARVIS_SUPABASE_* 未設定", file=sys.stderr)
        return 1

    from supabase import create_client

    sb = create_client(url, key)

    if args.retry_all_failed:
        print("# retrying all failed tasks...")
        for table, id_f in [("cards", "id"), ("watch_status", "id"), ("triage_items", "id")]:
            r = sb.table(table).select(f"{id_f},payload").filter("payload->cursor_ask->>status", "eq", "error").execute()
            for row in r.data or []:
                payload = row.get("payload") or {}
                ask = payload.get("cursor_ask") or {}
                ask["status"] = "queued"
                ask["manual_retry_at"] = now_iso()
                payload["cursor_ask"] = ask
                sb.table(table).update({"payload": payload, "updated_at": now_iso()}).eq(id_f, row[id_f]).execute()
                print(f"# reset {table} id={row[id_f]} to queued")

    if args.status_only:
        st = sync_worker_status_json(sb)
        print(f"# status synced: queued={st['counts']['queued']} running={st['counts']['running']} error={st['counts']['error']}")
        return 0

    # ゾンビ回収と自動リトライ
    recover_stale_running(sb)
    auto_retry_errors(sb)

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

    # 最新状態JSONを保存
    if not args.dry_run:
        sync_worker_status_json(sb)

    print(f"# cursor ask done={done} failed={failed} scanned={scanned}")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
