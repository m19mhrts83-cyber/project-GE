#!/usr/bin/env python3
"""部長 → Jarvis: 部長ボックス（10_inbox_from_grok）をポーリング。

未処理 MD を検知し .jarvis_state/grok_bridge_inbox.json を更新。
situation_watch（id: grok_bridge_inbox）→ dashboard に載る。

  cd ~/git-repos
  ~/selenium_env/venv/bin/python scripts/jarvis_bucho_inbox_poll.py
  ~/selenium_env/venv/bin/python scripts/jarvis_bucho_inbox_poll.py --push
  ~/selenium_env/venv/bin/python scripts/jarvis_bucho_inbox_poll.py --mark-seen FILE.md
  ~/selenium_env/venv/bin/python scripts/jarvis_bucho_inbox_poll.py --archive FILE.md
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from jarvis_bucho_bridge_lib import (  # noqa: E402
    INBOX_STATE_PATH,
    STATE_DIR,
    folder,
    list_queue_files,
)

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
PY = Path.home() / "selenium_env" / "venv" / "bin" / "python"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_state() -> dict[str, Any]:
    if not INBOX_STATE_PATH.is_file():
        return {
            "level": "ok",
            "summary": "部長ボックス: 未処理なし",
            "detail": "",
            "pending": [],
            "seen": {},
            "last_poll_at": None,
        }
    try:
        data = json.loads(INBOX_STATE_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("not dict")
        data.setdefault("seen", {})
        data.setdefault("pending", [])
        return data
    except Exception:
        return {
            "level": "ok",
            "summary": "部長ボックス: state 読取失敗のためリセット",
            "detail": "",
            "pending": [],
            "seen": {},
            "last_poll_at": None,
        }


def save_state(state: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state["last_poll_at"] = now_iso()
    INBOX_STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def preview(path: Path, limit: int = 240) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""
    text = " ".join(text.split())
    return text[:limit] + ("…" if len(text) > limit else "")


def poll() -> dict[str, Any]:
    state = load_state()
    seen: dict[str, Any] = dict(state.get("seen") or {})
    inbox = folder("inbox_from_grok")
    pending: list[dict[str, Any]] = []
    for p in list_queue_files(inbox):
        key = p.name
        if key in seen:
            continue
        st = p.stat()
        mtime = datetime.fromtimestamp(st.st_mtime, tz=JST).isoformat()
        pending.append(
            {
                "name": key,
                "path": str(p),
                "mtime": mtime,
                "preview": preview(p),
            }
        )

    n = len(pending)
    if n == 0:
        level = "ok"
        summary = "部長ボックス: 未処理なし"
        detail = f"inbox={inbox}"
    elif n == 1:
        level = "warn"
        summary = f"部長ボックス未処理: {pending[0]['name']}"
        detail = pending[0].get("preview") or ""
    else:
        level = "attention" if n >= 3 else "warn"
        names = ", ".join(x["name"] for x in pending[:5])
        more = f" 他{n - 5}件" if n > 5 else ""
        summary = f"部長ボックス未処理 {n}件: {names}{more}"
        detail = "\n".join(
            f"- {x['name']}: {x.get('preview') or '(空)'}" for x in pending[:8]
        )

    state["level"] = level
    state["summary"] = summary
    state["detail"] = detail
    state["pending"] = pending
    state["inbox_dir"] = str(inbox)
    save_state(state)
    return state


def mark_seen(name: str) -> dict[str, Any]:
    state = load_state()
    seen = dict(state.get("seen") or {})
    seen[name] = now_iso()
    state["seen"] = seen
    save_state(state)
    return poll()


def archive_file(name: str) -> dict[str, Any]:
    inbox = folder("inbox_from_grok")
    arch = folder("archive")
    src = inbox / name
    if not src.is_file():
        raise FileNotFoundError(f"not in inbox: {src}")
    dest = arch / name
    if dest.exists():
        stem, suf = dest.stem, dest.suffix
        dest = arch / f"{stem}_archived{suf}"
    src.rename(dest)
    state = load_state()
    seen = dict(state.get("seen") or {})
    seen[name] = now_iso()
    state["seen"] = seen
    save_state(state)
    print(f"📎 archive: {dest}")
    return poll()


def push_dashboard() -> int:
    if not PY.is_file():
        print("# push skip: python venv missing", file=sys.stderr)
        return 1
    # situation_watch 再集約 → watch-only push
    sw = REPO / "scripts" / "jarvis_situation_watch.py"
    push = REPO / "scripts" / "jarvis_dashboard_push.py"
    rc1 = subprocess.call([str(PY), str(sw)], cwd=str(REPO))
    rc2 = subprocess.call(
        [str(PY), str(push), "--watch-only"],
        cwd=str(REPO),
    )
    return 0 if rc1 == 0 and rc2 == 0 else 1


def print_block(state: dict[str, Any]) -> None:
    n = len(state.get("pending") or [])
    print("📎 部長ボックス（inbox poll）")
    print(f"- level: {state.get('level')}")
    print(f"- summary: {state.get('summary')}")
    print(f"- pending: {n}")
    for it in state.get("pending") or []:
        print(f"  - {it.get('name')}")
    print(f"- state: {INBOX_STATE_PATH}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Poll 部長ボックス → state / dashboard")
    ap.add_argument("--push", action="store_true", help="situation_watch + dashboard push")
    ap.add_argument(
        "--mark-seen",
        metavar="FILE",
        help="処理済みとして記録（ファイルは残す）",
    )
    ap.add_argument(
        "--archive",
        metavar="FILE",
        help="90_archive へ移して seen にする",
    )
    ap.add_argument("--json", action="store_true", help="state を JSON で stdout")
    args = ap.parse_args()

    try:
        if args.archive:
            state = archive_file(args.archive)
        elif args.mark_seen:
            state = mark_seen(args.mark_seen)
        else:
            state = poll()
    except Exception as e:
        print(f"# inbox poll error: {e}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(state, ensure_ascii=False, indent=2))
    else:
        print_block(state)

    if args.push:
        rc = push_dashboard()
        if rc != 0:
            print("# dashboard push soft-fail", file=sys.stderr)
            return rc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
