#!/usr/bin/env python3
"""Prune Cursor globalStorage state.vscdb chat/agent cache (safe subset).

What this is
------------
~/Library/Application Support/Cursor/User/globalStorage/state.vscdb
is Cursor's SQLite app DB. Almost all bulk is chat/agent history in
cursorDiskKV (bubbleId / agentKv / checkpointId), not settings.

Business impact
---------------
- Keeps ItemTable (settings, UI prefs, privacy flags, MCP secret refs, etc.)
- Keeps composerData / bubbles for chats touched within --keep-days (default 30)
- Removes older chat bubbles + related composer rows + checkpoints
- Then deletes orphan agentKv blobs and VACUUMs

Preferred (Cursor still open)
-----------------------------
Command Palette:
  1) Developer: Delete Old Chats...  (keep 30 days)
  2) Developer: GC Agent KV Blobs

Use this script only when Cursor.app is fully quit
(otherwise the DB is locked / corruption risk).

Usage
-----
  # dry-run
  /Users/matsunomasaharu2/selenium_env/venv/bin/python \\
    scripts/jarvis_cursor_state_vscdb_prune.py --dry-run

  # apply (Cursor must be quit)
  /Users/matsunomasaharu2/selenium_env/venv/bin/python \\
    scripts/jarvis_cursor_state_vscdb_prune.py --apply --keep-days 30
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))
DEFAULT_DB = Path.home() / "Library/Application Support/Cursor/User/globalStorage/state.vscdb"


def human(n: int) -> str:
    for u in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} PB"


def cursor_running() -> bool:
    try:
        out = subprocess.check_output(["pgrep", "-x", "Cursor"], text=True).strip()
        return bool(out)
    except subprocess.CalledProcessError:
        return False


def composer_ts_ms(obj: dict) -> int | None:
    for k in ("lastUpdatedAt", "createdAt", "updatedAt"):
        v = obj.get(k)
        if isinstance(v, (int, float)) and v > 1e12:
            return int(v)
        if isinstance(v, (int, float)) and v > 1e9:
            return int(v * 1000)
    return None


def collect_keep_ids(con: sqlite3.Connection, keep_days: int) -> set[str]:
    cutoff_ms = int((datetime.now(JST) - timedelta(days=keep_days)).timestamp() * 1000)
    keep: set[str] = set()

    # composerHeaders (if present)
    try:
        for cid, created, updated in con.execute(
            "SELECT composerId, createdAt, lastUpdatedAt FROM composerHeaders"
        ):
            ts = updated or created
            if ts and int(ts) >= cutoff_ms:
                keep.add(str(cid))
    except sqlite3.Error:
        pass

    # composerData JSON
    for key, value in con.execute(
        "SELECT key, value FROM cursorDiskKV WHERE key LIKE 'composerData:%'"
    ):
        cid = key.split(":", 1)[1]
        try:
            if isinstance(value, bytes):
                text = value.decode("utf-8", errors="replace")
            else:
                text = str(value)
            obj = json.loads(text)
            ts = composer_ts_ms(obj) if isinstance(obj, dict) else None
            if ts is None or ts >= cutoff_ms:
                keep.add(cid)
        except Exception:
            # parse failure → keep (safer)
            keep.add(cid)
    return keep


def estimate(con: sqlite3.Connection, keep: set[str]) -> dict:
    stats = {
        "bubble_delete_rows": 0,
        "bubble_delete_bytes": 0,
        "composer_delete_rows": 0,
        "composer_delete_bytes": 0,
        "checkpoint_rows": 0,
        "checkpoint_bytes": 0,
        "agentkv_rows": 0,
        "agentkv_bytes": 0,
        "keep_composers": len(keep),
    }
    for key, n in con.execute(
        "SELECT key, LENGTH(value) FROM cursorDiskKV WHERE key LIKE 'bubbleId:%'"
    ):
        parts = key.split(":")
        cid = parts[1] if len(parts) >= 2 else ""
        if cid not in keep:
            stats["bubble_delete_rows"] += 1
            stats["bubble_delete_bytes"] += n
    for key, n in con.execute(
        "SELECT key, LENGTH(value) FROM cursorDiskKV WHERE key LIKE 'composerData:%'"
    ):
        cid = key.split(":", 1)[1]
        if cid not in keep:
            stats["composer_delete_rows"] += 1
            stats["composer_delete_bytes"] += n
    for n, in con.execute(
        "SELECT LENGTH(value) FROM cursorDiskKV WHERE key LIKE 'checkpointId:%'"
    ):
        stats["checkpoint_rows"] += 1
        stats["checkpoint_bytes"] += n
    for n, in con.execute(
        "SELECT LENGTH(value) FROM cursorDiskKV WHERE key LIKE 'agentKv:%'"
    ):
        stats["agentkv_rows"] += 1
        stats["agentkv_bytes"] += n
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--keep-days", type=int, default=30)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument(
        "--also-purge-agentkv",
        action="store_true",
        help="Also DELETE all agentKv:* (largest reclaim; chat UI may show Loading for purged chats)",
    )
    ap.add_argument(
        "--also-purge-checkpoints",
        action="store_true",
        default=True,
        help="DELETE checkpointId:* (default on)",
    )
    ap.add_argument("--no-purge-checkpoints", action="store_true")
    args = ap.parse_args()
    if args.no_purge_checkpoints:
        args.also_purge_checkpoints = False

    if not args.dry_run and not args.apply:
        print("Specify --dry-run or --apply", file=sys.stderr)
        return 2

    db: Path = args.db
    if not db.is_file():
        print(f"DB not found: {db}", file=sys.stderr)
        return 1

    size_before = db.stat().st_size
    print(f"DB: {db}")
    print(f"Size before: {human(size_before)}")
    print(f"Keep chats touched within: {args.keep_days} days")

    if args.apply and cursor_running():
        print(
            "ERROR: Cursor.app is running. Fully quit Cursor (Cmd+Q) before --apply.",
            file=sys.stderr,
        )
        return 3

    # Always open read-only first for plan
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    keep = collect_keep_ids(con, args.keep_days)
    stats = estimate(con, keep)
    con.close()

    reclaim_est = (
        stats["bubble_delete_bytes"]
        + stats["composer_delete_bytes"]
        + (stats["checkpoint_bytes"] if args.also_purge_checkpoints else 0)
        + (stats["agentkv_bytes"] if args.also_purge_agentkv else 0)
    )
    print("--- plan ---")
    print(f"keep composers: {stats['keep_composers']}")
    print(
        f"delete bubbleId: {stats['bubble_delete_rows']:,} rows / {human(stats['bubble_delete_bytes'])}"
    )
    print(
        f"delete composerData: {stats['composer_delete_rows']:,} rows / {human(stats['composer_delete_bytes'])}"
    )
    if args.also_purge_checkpoints:
        print(
            f"delete checkpointId: {stats['checkpoint_rows']:,} rows / {human(stats['checkpoint_bytes'])}"
        )
    if args.also_purge_agentkv:
        print(
            f"delete agentKv: {stats['agentkv_rows']:,} rows / {human(stats['agentkv_bytes'])}"
        )
    else:
        print(
            f"agentKv left in place: {stats['agentkv_rows']:,} rows / {human(stats['agentkv_bytes'])} "
            "(run Cursor 'Developer: GC Agent KV Blobs' afterward, or re-run with --also-purge-agentkv)"
        )
    print(f"estimated value bytes removed: {human(reclaim_est)} (+ VACUUM returns free pages)")

    if args.dry_run:
        print("dry-run only; no changes")
        return 0

    # Backup beside DB
    stamp = datetime.now(JST).strftime("%Y%m%d_%H%M%S")
    backup = db.with_name(f"state.vscdb.jarvis-prune-backup.{stamp}")
    print(f"Copying backup → {backup} (may take a few minutes)")
    shutil.copy2(db, backup)
    # also copy wal/shm if present so backup is consistent-ish when Cursor was quit
    for suf in ("-wal", "-shm"):
        p = Path(str(db) + suf)
        if p.exists():
            shutil.copy2(p, Path(str(backup) + suf))

    con = sqlite3.connect(str(db))
    con.execute("PRAGMA journal_mode=DELETE")
    con.execute("BEGIN IMMEDIATE")
    # Delete old bubbles
    # SQLite can't easily "NOT IN keep" for 30+ ids efficiently with LIKE; do per-composer or scan.
    cur = con.cursor()
    deleted_bubbles = 0
    deleted_composers = 0
    # materialize keys to delete
    bubble_keys = [
        k
        for (k,) in cur.execute("SELECT key FROM cursorDiskKV WHERE key LIKE 'bubbleId:%'")
        if (k.split(":")[1] if ":" in k else "") not in keep
    ]
    for i in range(0, len(bubble_keys), 500):
        chunk = bubble_keys[i : i + 500]
        cur.executemany("DELETE FROM cursorDiskKV WHERE key = ?", [(k,) for k in chunk])
        deleted_bubbles += len(chunk)

    composer_keys = [
        k
        for (k,) in cur.execute("SELECT key FROM cursorDiskKV WHERE key LIKE 'composerData:%'")
        if k.split(":", 1)[1] not in keep
    ]
    for i in range(0, len(composer_keys), 500):
        chunk = composer_keys[i : i + 500]
        cur.executemany("DELETE FROM cursorDiskKV WHERE key = ?", [(k,) for k in chunk])
        deleted_composers += len(chunk)

    # composerHeaders rows for old ids
    try:
        old_header_ids = [
            cid
            for (cid,) in cur.execute("SELECT composerId FROM composerHeaders")
            if str(cid) not in keep
        ]
        for i in range(0, len(old_header_ids), 500):
            chunk = old_header_ids[i : i + 500]
            cur.executemany("DELETE FROM composerHeaders WHERE composerId = ?", [(c,) for c in chunk])
    except sqlite3.Error:
        pass

    if args.also_purge_checkpoints:
        cur.execute("DELETE FROM cursorDiskKV WHERE key LIKE 'checkpointId:%'")
    if args.also_purge_agentkv:
        cur.execute("DELETE FROM cursorDiskKV WHERE key LIKE 'agentKv:%'")

    # ancillary caches tied to chats
    for pattern in (
        "codeBlockPartialInlineDiffFates:%",
        "ofsContent:%",
        "inlineDiff:%",
        "composerVirtualRowHeights:%",
        "patch-graph:%",
    ):
        cur.execute("DELETE FROM cursorDiskKV WHERE key LIKE ?", (pattern,))

    con.commit()
    print(f"deleted bubbles={deleted_bubbles:,} composerData={deleted_composers:,}")
    print("VACUUM (compacting; can take several minutes)...")
    t0 = time.time()
    con.execute("VACUUM")
    con.close()
    print(f"VACUUM done in {time.time() - t0:.1f}s")

    size_after = db.stat().st_size
    print(f"Size after:  {human(size_after)}")
    print(f"Freed:       {human(size_before - size_after)}")
    print(f"Backup kept: {backup}")
    print("Done. You can reopen Cursor.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
