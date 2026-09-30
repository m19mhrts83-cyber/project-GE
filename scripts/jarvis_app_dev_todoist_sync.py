#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""アプリ開発カード → Todoist `#アプリ開発`（apps）へ起票。

入口は既存どおり estate 件名 [Grok開発]／ローカル inbox。
要ボス（Drive `todoist_tasks`）と同帯の launchd（起動時＋最大15分）で拾う。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_app_dev_todoist_sync.py --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_app_dev_todoist_sync.py --apply

無効化: JARVIS_APP_DEV_TODOIST_SYNC_DISABLE=1
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts"))

import jarvis_app_dev_cards_morning as cards  # noqa: E402

PY = Path.home() / "selenium_env" / "venv" / "bin" / "python"
API = REPO / "scripts" / "jarvis_todoist_api.py"
LANE = "apps"
MAX_PER_RUN = 10


def env_disabled() -> bool:
    return (os.environ.get("JARVIS_APP_DEV_TODOIST_SYNC_DISABLE") or "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def load_state() -> dict[str, Any]:
    state = cards.load_state()
    state.setdefault("todoist_by_card_id", {})
    if not isinstance(state["todoist_by_card_id"], dict):
        state["todoist_by_card_id"] = {}
    return state


def save_state(state: dict[str, Any]) -> None:
    cards.save_state(state)


def task_title(card: dict[str, Any]) -> str:
    kind = card.get("kind") or "実装"
    risk = card.get("risk") or "—"
    app = (card.get("app") or "（未記入）").strip()
    want = (card.get("want") or "（未記入）").strip()
    cid = card.get("id") or ""
    # card_id をタイトルに含め二重起票を避ける（再実行・Drive併用時）
    title = f"[app-dev][{kind}][{risk}][{cid}] {app}: {want}"
    return title[:200]


def task_status(card: dict[str, Any]) -> str:
    """高リスク実装はオーナー確認。それ以外は未着手。"""
    if card.get("kind") == "実装" and card.get("risk") == "高":
        return "オーナー確認"
    return "未着手"


def task_labels(card: dict[str, Any]) -> str:
    labs: list[str] = ["要Jarvis連携"]
    if card.get("kind") == "実装" and card.get("risk") == "高":
        labs.append("要ボス")
    if card.get("kind") == "実装" and card.get("risk") == "低":
        labs.append("quick")
    return ",".join(labs)


def task_note(card: dict[str, Any]) -> str:
    parts = [
        f"card_id: {card.get('id')}",
        f"kind: {card.get('kind')}",
        f"risk: {card.get('risk')}",
        f"source: {card.get('source')} / {card.get('source_id') or '-'}",
        f"where: {card.get('where') or '—'}",
        f"done: {card.get('done') or '—'}",
    ]
    return "\n".join(parts)[:1500]


def task_comment(card: dict[str, Any]) -> str:
    want = (card.get("want") or "").strip()
    done = (card.get("done") or "").strip()
    lines = [
        f"サマリ: アプリ開発統括カード（{card.get('kind')}／{card.get('risk')}）を Todoist 起票。",
        f"- やりたいこと: {want[:200]}",
    ]
    if done:
        lines.append(f"- 完了条件: {done[:200]}")
    lines.append("アウトプット:")
    lines.append("- docs/Grok_アプリ開発統括_設計_20260824.md")
    return "\n".join(lines)


def create_todoist(card: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
    title = task_title(card)
    status = task_status(card)
    labels = task_labels(card)
    note = task_note(card)
    comment = task_comment(card)
    if dry_run:
        print(f"# dry-run create lane={LANE} status={status} title={title}")
        return {"ok": True, "dry_run": True, "title": title}
    cmd = [
        str(PY),
        str(API),
        "create-task",
        "--lane",
        LANE,
        "--title",
        title,
        "--status",
        status,
        "--label",
        labels,
        "--note",
        note,
        "--comment",
        comment,
        "--json",
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=90,
        cwd=str(REPO),
    )
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    if proc.returncode != 0:
        return {"ok": False, "error": err or out or f"rc={proc.returncode}"}
    try:
        data = json.loads(out.splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        return {"ok": False, "error": f"bad json: {out[:200]}"}
    if not data.get("ok"):
        return {"ok": False, "error": out[:300]}
    return {
        "ok": True,
        "id": str(data.get("id") or ""),
        "url": data.get("url") or "",
        "title": title,
        "status": status,
    }


def pending_for_todoist(
    state: dict[str, Any], *, days: int, skip_gmail: bool
) -> tuple[list[dict[str, Any]], list[str]]:
    all_cards, notes = cards.collect_cards(
        days=days, skip_gmail=skip_gmail, state=state
    )
    done_map = state.get("todoist_by_card_id") or {}
    pending: list[dict[str, Any]] = []
    for c in all_cards:
        cid = c.get("id")
        if not cid:
            continue
        prev = done_map.get(cid)
        if isinstance(prev, dict) and (prev.get("task_id") or prev.get("skipped")):
            continue
        if isinstance(prev, str) and prev.strip():
            continue
        pending.append(c)
    return pending, notes


def bootstrap_skip_existing(
    state: dict[str, Any], pending: list[dict[str, Any]]
) -> int:
    """初回 apply: 既存カードは Todoist に流さずスキップ印だけ付ける。"""
    if state.get("last_todoist_sync_at"):
        return 0
    if state.get("todoist_by_card_id"):
        return 0
    n = 0
    m: dict[str, Any] = {}
    for c in pending:
        cid = c.get("id")
        if not cid:
            continue
        m[cid] = {
            "skipped": True,
            "reason": "bootstrap_existing",
            "at": cards.now_iso(),
        }
        n += 1
    state["todoist_by_card_id"] = m
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--skip-gmail", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--apply",
        action="store_true",
        help="実際に Todoist へ create-task（無いと dry-run 相当の一覧のみ）",
    )
    ap.add_argument(
        "--backfill",
        action="store_true",
        help="初回でも既存カードを起票する（既定は bootstrap スキップ）",
    )
    ap.add_argument("--max", type=int, default=MAX_PER_RUN)
    args = ap.parse_args()

    if env_disabled():
        print("# skip: JARVIS_APP_DEV_TODOIST_SYNC_DISABLE=1")
        return 0

    if not args.apply and not args.dry_run:
        args.dry_run = True

    state = load_state()
    pending, notes = pending_for_todoist(
        state, days=args.days, skip_gmail=args.skip_gmail
    )
    print("📎 アプリ開発 → Todoist")
    print(f"- 取得: {' / '.join(notes)}")
    print(f"- 未起票カード: {len(pending)}")

    if (
        args.apply
        and not args.dry_run
        and not args.backfill
        and not state.get("last_todoist_sync_at")
        and not state.get("todoist_by_card_id")
        and pending
    ):
        n = bootstrap_skip_existing(state, pending)
        state["last_todoist_sync_at"] = cards.now_iso()
        save_state(state)
        print(
            f"- 初回 bootstrap: 既存 {n} 件をスキップ印（今後の新規のみ起票）。"
            " 過去分も起票するなら --backfill"
        )
        print(f"- 今回: created=0 bootstrap_skip={n}")
        return 0

    created = 0
    errors = 0
    for card in pending[: max(0, args.max)]:
        res = create_todoist(card, dry_run=args.dry_run)
        if not res.get("ok"):
            errors += 1
            print(f"  · FAIL [{card.get('id')}] {res.get('error')}", file=sys.stderr)
            continue
        created += 1
        print(
            f"  · {'would create' if args.dry_run else 'created'}"
            f" [{card.get('id')}] {res.get('title')}"
            + (f" id={res.get('id')}" if res.get("id") else "")
        )
        if args.apply and not args.dry_run and res.get("id"):
            state.setdefault("todoist_by_card_id", {})[card["id"]] = {
                "task_id": res["id"],
                "url": res.get("url") or "",
                "at": cards.now_iso(),
                "status": res.get("status") or "",
            }

    if len(pending) > args.max:
        print(f"- 残り {len(pending) - args.max} 件は次回（max={args.max}/run）")

    if args.apply and not args.dry_run:
        state["last_todoist_sync_at"] = cards.now_iso()
        save_state(state)

    print(f"- 今回: created={created} errors={errors} dry_run={args.dry_run}")
    return 1 if errors and not created else 0


if __name__ == "__main__":
    raise SystemExit(main())
