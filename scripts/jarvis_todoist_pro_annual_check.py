#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Todoist Pro 月額→年額切替の促し（初月更新前）.

  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_pro_annual_check.py
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_pro_annual_check.py --mark-prompted
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_pro_annual_check.py --mark-done
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
STATE = REPO / ".jarvis_state" / "todoist_pro_annual_switch.json"
JST = timezone(timedelta(hours=9))


def _today() -> date:
    return datetime.now(JST).date()


def _load() -> dict:
    if not STATE.is_file():
        return {"disabled": True}
    return json.loads(STATE.read_text(encoding="utf-8"))


def _save(data: dict) -> None:
    STATE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _parse(s: str | None) -> date | None:
    if not s:
        return None
    return date.fromisoformat(str(s)[:10])


def level_for(today: date, data: dict) -> str | None:
    if data.get("disabled") or data.get("completed_at"):
        return None
    deadline = _parse(data.get("switch_deadline_jst"))
    propose_from = _parse(data.get("propose_from_jst")) or (
        deadline - timedelta(days=21) if deadline else None
    )
    ask_from = _parse(data.get("ask_from_jst")) or (
        deadline - timedelta(days=7) if deadline else None
    )
    if not deadline or not propose_from:
        return None
    if today > deadline:
        return "ask"
    if ask_from and today >= ask_from:
        return "ask"
    if today >= propose_from:
        return "soon"
    # まだ窓前でも、ユーザーが Todoist/Pro/課金に触れたときは info を出してよい（呼び出し側）
    return None


def format_block(data: dict, level: str) -> str:
    deadline = data.get("switch_deadline_jst") or "?"
    until = (data.get("premium_until_utc") or "")[:10] or "?"
    lines = [
        "📎 Todoist Pro 年額切替",
        f"- レベル: {level}",
        f"- 意向: 月額→年額（初月更新前）",
        f"- 目安期限: {deadline}（現 premium_until 付近 {until}）",
        "- 操作: Todoist Settings → Subscription → 年額へ変更（admin）",
        "- 切替済みなら「年額にした」→ Jarvis が state を閉じます",
    ]
    if level == "ask":
        lines.append("- 今日やる／延期／もうやらない？")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mark-prompted", action="store_true")
    ap.add_argument("--mark-done", action="store_true")
    ap.add_argument("--force", action="store_true", help="窓外でも soon 相当で出す")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    data = _load()
    if args.mark_done:
        data["completed_at"] = datetime.now(JST).isoformat(timespec="seconds")
        data["disabled"] = True
        _save(data)
        print("marked done / disabled")
        return 0

    today = _today()
    level = level_for(today, data)
    if args.force and not level and not data.get("disabled") and not data.get("completed_at"):
        level = "soon"

    # 促しすぎ防止: 同レベルは3日以内再掲しない（ask は1日）
    if level and data.get("last_prompted_at") and data.get("last_prompt_level") == level:
        try:
            last = datetime.fromisoformat(str(data["last_prompted_at"]).replace("Z", "+00:00"))
            if last.tzinfo is None:
                last = last.replace(tzinfo=JST)
            gap = (datetime.now(JST) - last.astimezone(JST)).days
            min_gap = 1 if level == "ask" else 3
            if gap < min_gap and not args.force:
                if args.json:
                    print(json.dumps({"level": None, "suppressed": True}))
                return 0
        except Exception:
            pass

    if args.json:
        print(json.dumps({"level": level, "deadline": data.get("switch_deadline_jst")}, ensure_ascii=False))
        return 0

    if not level:
        return 0

    print(format_block(data, level))
    if args.mark_prompted:
        data["last_prompted_at"] = datetime.now(JST).isoformat(timespec="seconds")
        data["last_prompt_level"] = level
        _save(data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
