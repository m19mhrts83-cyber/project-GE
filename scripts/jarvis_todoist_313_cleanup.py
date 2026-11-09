#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""313 片付け — 期日超過＋完了候補を1通の3択カードで #consult へ.

段階1本線。旧 20:00 の ✅／📅 2通に代わる。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_313_cleanup.py --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_313_cleanup.py
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
from jarvis_todoist_313_slack_blocks import (  # noqa: E402
    build_cleanup_blocks,
    prefer_url_mode,
    post_slack,
)

JST = ZoneInfo("Asia/Tokyo")
STATE = REPO / ".jarvis_state" / "todoist_313_cleanup.json"
MAX_TOP = 5
NEED_OWNER_RE = re.compile(
    r"(要ボス|検討|どうする|振込|解約|退会|資金|対外|方針)",
    re.I,
)
CONFIRM_RE = re.compile(r"(確認のみ|表確認|UI確認|launchd|resume)", re.I)


def _today() -> date:
    return datetime.now(JST).date()


def _token() -> str:
    return (
        os.environ.get("TODOIST_API_TOKEN_OWNER")
        or os.environ.get("TODOIST_API_TOKEN")
        or ""
    ).strip()


def _api(path: str) -> dict:
    tok = _token()
    if not tok:
        raise SystemExit("TODOIST_API_TOKEN がありません")
    req = urllib.request.Request(
        "https://api.todoist.com/api/v1" + path,
        headers={"Authorization": f"Bearer {tok}"},
    )
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode() or "{}")


def _propose_due(days_over: int, today: date) -> str:
    if days_over <= 7:
        d = today + timedelta(days=2)
    elif days_over <= 30:
        d = today + timedelta(days=7)
    else:
        d = today + timedelta(days=14)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d.isoformat()


def _star_for(title: str, days_over: int | None, confirm_only: bool) -> str:
    if NEED_OWNER_RE.search(title):
        return "reschedule"
    if confirm_only or (days_over is not None and days_over >= 21):
        return "close" if confirm_only else "reschedule"
    if days_over is not None and days_over >= 14:
        return "reschedule"
    return "reschedule"


def _fetch_active_tasks(page_limit: int = 200, max_pages: int = 20) -> list[dict]:
    """未完了タスクを全ページ取得（v1 は next_cursor でページ送り）。"""
    out: list[dict] = []
    cursor = ""
    for _ in range(max_pages):
        q = f"/tasks?limit={page_limit}" + (f"&cursor={cursor}" if cursor else "")
        d = _api(q)
        if isinstance(d, list):
            out.extend(d)
            break
        out.extend(d.get("results") or [])
        cursor = str(d.get("next_cursor") or "")
        if not cursor:
            break
    return out


def collect_items(limit: int = MAX_TOP) -> tuple[list[dict], int]:
    today = _today()
    tasks = _fetch_active_tasks()
    scored: list[tuple[int, dict]] = []
    for t in tasks or []:
        due = (t.get("due") or {}).get("date") or ""
        try:
            d0 = date.fromisoformat(due[:10])
        except ValueError:
            continue
        # API v1 の /tasks は filter を無視して全件を返すので、ここで超過だけに絞る
        if d0 >= today:
            continue
        days = (today - d0).days
        title = str(t.get("content") or "")
        if NEED_OWNER_RE.search(title) and "済んだ" not in title:
            # 要判断は「済んだ」推しにしない（star=reschedule）
            pass
        score = min(days, 60)
        labels = [str(x) for x in (t.get("labels") or [])]
        if "properties" in labels:
            score += 10
        scored.append((score, t))
    scored.sort(key=lambda x: -x[0])
    total = len(scored)
    items: list[dict] = []
    for i, (_, t) in enumerate(scored[:limit], start=1):
        due = (t.get("due") or {}).get("date") or ""
        d0 = date.fromisoformat(due[:10])
        days = (today - d0).days
        title = str(t.get("content") or "")
        confirm = bool(CONFIRM_RE.search(title))
        labels = [str(x) for x in (t.get("labels") or [])]
        lane = next((x for x in labels if x in (
            "ai_raimo", "apps", "properties", "kamiooya", "kazoku",
            "agent_team", "kodate", "kanji", "theme_stock",
        )), "")
        items.append({
            "n": i,
            "task_id": str(t.get("id") or ""),
            "title": title,
            "title_short": title[:70],
            "days_over": days,
            "new_due": _propose_due(days, today),
            "lane": lane,
            "kind": "confirm_only" if confirm else "overdue",
            "star": _star_for(title, days, confirm),
        })
    return items, total


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="313 片付け 3択 digest")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=MAX_TOP)
    ap.add_argument("--force-url-buttons", action="store_true")
    args = ap.parse_args(argv)

    if not _token():
        print("❌ TODOIST_API_TOKEN 未設定", file=sys.stderr)
        return 2

    items, total = collect_items(args.limit)
    if not items:
        print("📎 313片付け: 超過0件（投稿なし）")
        return 0

    url_mode = prefer_url_mode(force_url=args.force_url_buttons)
    payload = build_cleanup_blocks(
        items,
        header_text="【相談】313 片付け",
        fallback_text=f"313 片付け 上位{len(items)}/{total}",
        url_mode=url_mode,
        total_overdue=total,
    )
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(
        json.dumps(
            {
                "at": datetime.now(JST).isoformat(timespec="seconds"),
                "total": total,
                "items": items,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"📎 313片付け: {len(items)}件（超過合計 {total}）")
    for it in items:
        print(
            f"  #{it['n']} {it['star']} {it['days_over']}日 "
            f"{it['title_short'][:40]} → {it['new_due']}"
        )
    return post_slack(
        payload,
        dry_run=args.dry_run,
        force_url_buttons=args.force_url_buttons,
    )


if __name__ == "__main__":
    raise SystemExit(main())
