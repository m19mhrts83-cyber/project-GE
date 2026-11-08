#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""313 段階0 — 期日超過の棚卸し（提案→了承後のみ apply）.

目標: 超過を 10 件以下へ。要確認付きは断定 close しない。

  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_313_stage0_clear.py
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_313_stage0_clear.py --apply --select 1,3
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
JST = ZoneInfo("Asia/Tokyo")
STATE = REPO / ".jarvis_state" / "todoist_313_stage0.json"
NEED_CONFIRM_RE = re.compile(r"(要ボス|要確認|検討|どうする|振込|解約)", re.I)
PY = Path("/Users/matsunomasaharu2/selenium_env/venv/bin/python")
if not PY.is_file():
    PY = Path(sys.executable)


def _token() -> str:
    return (
        os.environ.get("TODOIST_API_TOKEN_OWNER")
        or os.environ.get("TODOIST_API_TOKEN")
        or ""
    ).strip()


def _api(method: str, path: str, body: dict | None = None) -> dict:
    tok = _token()
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        "https://api.todoist.com/api/v1" + path,
        data=data,
        headers={
            "Authorization": f"Bearer {tok}",
            "Content-Type": "application/json",
        },
        method=method,
    )
    with urllib.request.urlopen(req, timeout=40) as r:
        raw = r.read().decode()
        return json.loads(raw) if raw.strip() else {}


def _propose(days: int, title: str) -> dict:
    today = datetime.now(JST).date()
    need = bool(NEED_CONFIRM_RE.search(title))
    if need:
        return {
            "action": "ask",
            "label": "要確認（松野）",
            "new_due": (today + timedelta(days=7)).isoformat(),
        }
    if days >= 30:
        return {
            "action": "reschedule",
            "label": "長期超過→2週間後へ",
            "new_due": (today + timedelta(days=14)).isoformat(),
        }
    if days >= 14:
        return {
            "action": "reschedule",
            "label": "2週超→1週間後へ",
            "new_due": (today + timedelta(days=7)).isoformat(),
        }
    return {
        "action": "reschedule",
        "label": "短期超過→2営業日後",
        "new_due": (today + timedelta(days=2)).isoformat(),
    }


def inventory() -> list[dict]:
    today = datetime.now(JST).date()
    raw = _api("GET", "/tasks?filter=overdue&limit=200")
    tasks = raw.get("results", raw) if isinstance(raw, dict) else raw
    rows: list[dict] = []
    for i, t in enumerate(tasks or [], start=1):
        due = (t.get("due") or {}).get("date") or ""
        try:
            d0 = date.fromisoformat(due[:10])
        except ValueError:
            continue
        days = (today - d0).days
        title = str(t.get("content") or "")
        prop = _propose(days, title)
        rows.append({
            "n": i,
            "task_id": str(t.get("id") or ""),
            "title": title,
            "days_over": days,
            "due": due[:10],
            **prop,
        })
    rows.sort(key=lambda r: -int(r["days_over"]))
    for i, r in enumerate(rows, start=1):
        r["n"] = i
    return rows


def apply_one(row: dict, author: str) -> bool:
    tid = row["task_id"]
    if row["action"] == "ask":
        print(f"  skip #{row['n']} 要確認: {row['title'][:40]}")
        return False
    due = row["new_due"]
    comment = (
        f"【{author}】\nサマリ: 313段階0棚卸し — {row['label']}（due→{due}）\n"
        f"アウトプット:\n- [該当](https://app.todoist.com/app/task/{tid})\n"
    )
    _api("POST", "/comments", {"task_id": tid, "content": comment[:1900]})
    _api("POST", f"/tasks/{tid}", {"due_date": due})
    print(f"  ok #{row['n']} → {due} {row['title'][:40]}")
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--select", default="", help="番号 1,3 または all-safe")
    ap.add_argument("--author", default=os.environ.get("TODOIST_313_AUTHOR") or "Jarvis")
    args = ap.parse_args(argv)

    if not _token():
        print("❌ TODOIST_API_TOKEN 未設定", file=sys.stderr)
        return 2

    rows = inventory()
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(
        json.dumps(
            {"at": datetime.now(JST).isoformat(timespec="seconds"), "rows": rows},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"📎 313段階0棚卸し: 超過 {len(rows)} 件（目標≤10）")
    for r in rows[:40]:
        flag = "⚠要確認" if r["action"] == "ask" else r["action"]
        print(
            f"  #{r['n']:02d} {r['days_over']:2d}日 [{flag}] "
            f"{r['title'][:50]} → {r.get('new_due')}"
        )
    if len(rows) > 40:
        print(f"  …他 {len(rows) - 40} 件")

    if not args.apply:
        print("了承後: --apply --select 1,2,5 または --select all-safe（要確認以外）")
        return 0

    if args.select.strip().lower() == "all-safe":
        targets = [r for r in rows if r["action"] != "ask"]
    else:
        nums = {int(x) for x in re.findall(r"\d+", args.select)}
        targets = [r for r in rows if r["n"] in nums]

    if not targets:
        print("対象なし")
        return 1

    ok = 0
    for r in targets:
        if apply_one(r, args.author):
            ok += 1

    left = inventory()
    print(f"✅ 適用 {ok} 件 / 残り超過 {len(left)} 件")
    if len(left) > 10:
        print("⚠️ まだ10件超。要確認分は松野判断、または cleanup 3択へ")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
