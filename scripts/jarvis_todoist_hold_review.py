#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Todoist HOLD 1ヶ月レビュー（会話トリガー）。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_hold_review.py
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_hold_review.py --force
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_hold_review.py --mark-prompted
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_hold_review.py --force --mark-prompted

促し: 毎月1〜8日（JST）の未実施月、または --force（明示「HOLD確認して」）。
無効化: state disabled / JARVIS_TODOIST_HOLD_REVIEW_DISABLE=1
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
STATE_PATH = REPO / ".jarvis_state" / "todoist_hold_review.json"
EXAMPLE_PATH = REPO / ".jarvis_state" / "todoist_hold_review.example.json"
JST = ZoneInfo("Asia/Tokyo")
WINDOW_START = 1
WINDOW_END = 8


def _now() -> datetime:
    return datetime.now(JST)


def _load_state() -> dict:
    if STATE_PATH.is_file():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8")) or {}
        except json.JSONDecodeError:
            return {}
    return {}


def _save_state(data: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _disabled(state: dict) -> bool:
    if os.environ.get("JARVIS_TODOIST_HOLD_REVIEW_DISABLE", "").strip() in (
        "1",
        "true",
        "yes",
    ):
        return True
    return bool(state.get("disabled"))


def _in_window(day: int) -> bool:
    return WINDOW_START <= day <= WINDOW_END


def main() -> int:
    p = argparse.ArgumentParser(description="Todoist HOLD 1ヶ月レビュー")
    p.add_argument(
        "--force",
        action="store_true",
        help="窓外・当月実施済でも実行（明示依頼）",
    )
    p.add_argument(
        "--mark-prompted",
        action="store_true",
        help="実行後に last_check / last_prompted_at を記録",
    )
    p.add_argument("--min-days", type=int, default=None)
    p.add_argument("--json", action="store_true")
    p.add_argument(
        "--due-only",
        action="store_true",
        help="対象0件なら何も出さない",
    )
    args = p.parse_args()

    state = _load_state()
    if _disabled(state):
        return 0

    now = _now()
    ym = now.strftime("%Y-%m")
    in_win = _in_window(now.day)
    already = str(state.get("last_check") or "") == ym

    if not args.force:
        if not in_win:
            return 0
        if already:
            return 0

    # 本体は jarvis_todoist_api hold-review
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import jarvis_todoist_api as api  # noqa: E402

    ns = argparse.Namespace(
        min_days=args.min_days,
        json=args.json,
        due_only=args.due_only or (in_win and not args.force),
    )
    rc = api.cmd_hold_review(ns)

    if args.mark_prompted:
        state["last_check"] = ym
        state["last_prompted_at"] = now.isoformat()
        state.setdefault("disabled", False)
        _save_state(state)

    return rc


if __name__ == "__main__":
    raise SystemExit(main())
