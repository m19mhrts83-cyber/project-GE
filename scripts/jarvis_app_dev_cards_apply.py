#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""アプリ開発統括カード → Drive inbox `action: app_dev_cards` を Todoist へ。

並行期（〜2026-10-25）: estate 件名 [Grok開発] と並立。
本経路が安定したらメール必須を外せる。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_app_dev_cards_apply.py --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_app_dev_cards_apply.py --apply
  ~/selenium_env/venv/bin/python scripts/jarvis_app_dev_cards_apply.py --apply --archive-done

Inbox 例:

---
action: app_dev_cards
source: app_dev
title: カード 2026-10-18
---

📎 Jarvis向け（実装）
- アプリ: …
- やりたいこと: …
- リスク: 低
- 完了条件: …

無効化: JARVIS_APP_DEV_CARDS_DRIVE_APPLY_DISABLE=1
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from jarvis_bucho_bridge_lib import folder, list_queue_files  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import jarvis_app_dev_cards_morning as cards  # noqa: E402
import jarvis_app_dev_todoist_sync as sync  # noqa: E402

ACTION = "app_dev_cards"


def env_disabled() -> bool:
    return (os.environ.get("JARVIS_APP_DEV_CARDS_DRIVE_APPLY_DISABLE") or "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end < 0:
        return {}, text
    raw = text[3:end].strip()
    meta: dict[str, str] = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        meta[k.strip()] = v.strip().strip("\"'")
    return meta, text[end + 4 :].lstrip("\n")


def list_app_dev_card_files() -> list[Path]:
    inbox = folder("inbox_from_grok")
    out: list[Path] = []
    for p in list_queue_files(inbox):
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        meta, _ = parse_frontmatter(text)
        if (meta.get("action") or "").strip() == ACTION:
            out.append(p)
    return out


def archive_file(path: Path) -> Path:
    arch = folder("archive")
    dest = arch / path.name
    if dest.exists():
        stem, suf = path.stem, path.suffix
        dest = arch / f"{stem}_archived{suf}"
    shutil.move(str(path), str(dest))
    return dest


def process_file(
    path: Path,
    state: dict[str, Any],
    *,
    apply: bool,
    dry_run: bool,
    max_cards: int,
) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    meta, body = parse_frontmatter(text)
    parsed = cards.parse_cards(body, source="drive", source_id=path.name)
    done_map = state.setdefault("todoist_by_card_id", {})
    if not isinstance(done_map, dict):
        done_map = {}
        state["todoist_by_card_id"] = done_map

    pending: list[dict[str, Any]] = []
    for c in parsed:
        cid = c.get("id")
        if not cid:
            continue
        prev = done_map.get(cid)
        if isinstance(prev, dict) and (prev.get("task_id") or prev.get("skipped")):
            continue
        if isinstance(prev, str) and prev.strip():
            continue
        pending.append(c)

    created = 0
    errors = 0
    results: list[dict[str, Any]] = []
    for card in pending[: max(0, max_cards)]:
        res = sync.create_todoist(card, dry_run=dry_run or not apply)
        results.append({"card_id": card.get("id"), **res})
        if not res.get("ok"):
            errors += 1
            continue
        created += 1
        if apply and not dry_run and res.get("id"):
            done_map[card["id"]] = {
                "task_id": res["id"],
                "url": res.get("url") or "",
                "at": cards.now_iso(),
                "status": res.get("status") or "",
                "source": "drive",
                "source_file": path.name,
            }

    return {
        "name": path.name,
        "title": meta.get("title") or path.stem,
        "cards_parsed": len(parsed),
        "pending": len(pending),
        "created": created,
        "errors": errors,
        "dry_run": dry_run or not apply,
        "results": results,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Drive action:app_dev_cards → Todoist")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument(
        "--archive-done",
        action="store_true",
        help="カード0件 or 起票エラー0のファイルを archive",
    )
    ap.add_argument("--max", type=int, default=10)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if env_disabled():
        msg = {"ok": True, "skipped": True, "reason": "JARVIS_APP_DEV_CARDS_DRIVE_APPLY_DISABLE"}
        print(json.dumps(msg, ensure_ascii=False) if args.json else f"# skip: {msg['reason']}")
        return 0

    if not args.apply and not args.dry_run:
        args.dry_run = True

    files = list_app_dev_card_files()
    state = sync.load_state()
    file_results: list[dict[str, Any]] = []
    archived: list[str] = []
    total_created = 0
    total_errors = 0

    for path in files:
        fr = process_file(
            path,
            state,
            apply=args.apply,
            dry_run=args.dry_run,
            max_cards=args.max,
        )
        file_results.append(fr)
        total_created += int(fr.get("created") or 0)
        total_errors += int(fr.get("errors") or 0)
        # archive: パース0（空）またはエラーなしで処理完了
        can_archive = (
            args.apply
            and args.archive_done
            and not args.dry_run
            and int(fr.get("errors") or 0) == 0
            and (
                int(fr.get("cards_parsed") or 0) == 0
                or int(fr.get("pending") or 0) == int(fr.get("created") or 0)
            )
        )
        if can_archive:
            dest = archive_file(path)
            archived.append(dest.name)
            fr["archived"] = dest.name

    if args.apply and not args.dry_run:
        state["last_drive_cards_apply_at"] = cards.now_iso()
        sync.save_state(state)

    out = {
        "ok": total_errors == 0,
        "count": len(files),
        "created": total_created,
        "errors": total_errors,
        "archived": archived,
        "files": [
            {
                "name": f.get("name"),
                "cards_parsed": f.get("cards_parsed"),
                "pending": f.get("pending"),
                "created": f.get("created"),
                "errors": f.get("errors"),
                "archived": f.get("archived"),
            }
            for f in file_results
        ],
    }

    if args.json:
        print(json.dumps(out, ensure_ascii=False))
    else:
        print("📎 アプリ開発カード Drive apply")
        print(f"- files: {len(files)}")
        for f in file_results:
            print(
                f"  · {f.get('name')}: parsed={f.get('cards_parsed')} "
                f"pending={f.get('pending')} created={f.get('created')} "
                f"errors={f.get('errors')}"
                + (f" archived={f.get('archived')}" if f.get("archived") else "")
            )
        print(f"- created={total_created} errors={total_errors} dry_run={args.dry_run}")
    return 1 if total_errors and not total_created else 0


if __name__ == "__main__":
    raise SystemExit(main())
