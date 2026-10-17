#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI社員の二重起動防止（ローカル JSON ロック）。

  cd ~/git-repos && ~/selenium_env/venv/bin/python scripts/jarvis_agent_run_lock.py acquire \\
    --task-id 6hmr… --agent-id 114 --folder 'docs/AIエージェントチーム/…/114_…'
  … release / status / stale-clear

正本設計: docs/AIエージェントチーム/31_作業ロック_二重起動防止_20261017.md
state: .jarvis_state/agent_run_locks.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
STATE_PATH = REPO / ".jarvis_state" / "agent_run_locks.json"
JST = timezone(timedelta(hours=9))


def _now_iso() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def _key(task_id: str) -> str:
    tid = (task_id or "").strip()
    if not tid:
        raise SystemExit("task_id が空です")
    if tid.startswith("todoist:"):
        return tid
    return f"todoist:{tid}"


def _load() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        return {"locks": {}, "updated_at": None}
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"locks": {}, "updated_at": None}
    if not isinstance(data, dict):
        return {"locks": {}, "updated_at": None}
    locks = data.get("locks")
    if not isinstance(locks, dict):
        data["locks"] = {}
    return data


def _save(data: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = _now_iso()
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(STATE_PATH)


def cmd_acquire(args: argparse.Namespace) -> int:
    data = _load()
    locks: dict[str, Any] = data["locks"]
    k = _key(args.task_id)
    existing = locks.get(k)
    if isinstance(existing, dict) and existing.get("status") == "running":
        print(
            f"LOCKED: {k} agent={existing.get('agent_id')} "
            f"executor={existing.get('executor')} started={existing.get('started_at')}",
            file=sys.stderr,
        )
        return 2
    locks[k] = {
        "agent_id": args.agent_id or "",
        "folder": args.folder or "",
        "executor": args.executor or "unknown",
        "pid": os.getpid(),
        "started_at": _now_iso(),
        "status": "running",
        "note": args.note or "",
    }
    _save(data)
    print(f"ACQUIRED: {k}")
    return 0


def cmd_release(args: argparse.Namespace) -> int:
    data = _load()
    locks: dict[str, Any] = data["locks"]
    k = _key(args.task_id)
    if k not in locks:
        print(f"NO_LOCK: {k}")
        return 0
    if args.keep:
        locks[k]["status"] = args.final_status
        locks[k]["finished_at"] = _now_iso()
    else:
        del locks[k]
    _save(data)
    print(f"RELEASED: {k} final={args.final_status}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    data = _load()
    locks: dict[str, Any] = data.get("locks") or {}
    if args.task_id:
        k = _key(args.task_id)
        row = locks.get(k)
        print(json.dumps({k: row}, ensure_ascii=False, indent=2))
        return 0 if row else 1
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def cmd_stale_clear(args: argparse.Namespace) -> int:
    data = _load()
    locks: dict[str, Any] = data["locks"]
    cutoff = datetime.now(JST) - timedelta(hours=max(1, int(args.hours)))
    removed = []
    for k, row in list(locks.items()):
        if not isinstance(row, dict) or row.get("status") != "running":
            continue
        started = row.get("started_at") or ""
        try:
            ts = datetime.fromisoformat(started)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=JST)
        except ValueError:
            removed.append(k)
            del locks[k]
            continue
        if ts < cutoff:
            removed.append(k)
            del locks[k]
    _save(data)
    print(f"STALE_CLEARED: {len(removed)} {removed}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="AI agent run lock (local JSON)")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("acquire", help="実行開始前にロック取得")
    a.add_argument("--task-id", required=True)
    a.add_argument("--agent-id", default="")
    a.add_argument("--folder", default="")
    a.add_argument("--executor", default="cursor")
    a.add_argument("--note", default="")
    a.set_defaults(func=cmd_acquire)

    r = sub.add_parser("release", help="実行終了でロック解放")
    r.add_argument("--task-id", required=True)
    r.add_argument("--final-status", default="done", choices=["done", "failed", "blocked"])
    r.add_argument("--keep", action="store_true", help="削除せず status だけ更新")
    r.set_defaults(func=cmd_release)

    s = sub.add_parser("status", help="ロック状態")
    s.add_argument("--task-id", default="")
    s.set_defaults(func=cmd_status)

    c = sub.add_parser("stale-clear", help="古い running を掃除")
    c.add_argument("--hours", type=int, default=6)
    c.set_defaults(func=cmd_stale_clear)

    args = p.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
