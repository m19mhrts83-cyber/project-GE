#!/usr/bin/env python3
"""ホークアイ inbox → Notion タスク反映（create / done / archive）。

Drive `10_inbox_from_grok/` の MD で frontmatter `action: notion_tasks` を対象にする。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_hawk_notion_tasks_apply.py --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_hawk_notion_tasks_apply.py --apply
  ~/selenium_env/venv/bin/python scripts/jarvis_hawk_notion_tasks_apply.py --apply --archive-done

Inbox 例:

---
action: notion_tasks
priority: normal
target: jarvis
source: hawk
---

## create
- lane: kazoku
  title: 家族会議の宿題をNotionに
  due: 2026-09-06
  note: ミーティングメモ由来

## done
- lane: kodate
  page_id: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
  reason: タスク完了したよ（ホーク・週次で確認）・優先低下

## archive
- page_id: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
  reason: 重複
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from jarvis_bucho_bridge_lib import folder, list_queue_files  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
PY = Path.home() / "selenium_env" / "venv" / "bin" / "python"
API = REPO / "scripts" / "jarvis_notion_api.py"
YAML_PATH = REPO / "config" / "notion_task_dbs.yaml"


def _load_lanes() -> dict[str, Any]:
    import yaml  # type: ignore

    data = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8")) or {}
    return dict(data.get("lanes") or {})


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end < 0:
        return {}, text
    raw = text[3:end].strip()
    body = text[end + 4 :].lstrip("\n")
    meta: dict[str, str] = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        meta[k.strip()] = v.strip()
    return meta, body


def _parse_items(section: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    cur: dict[str, str] | None = None
    for line in section.splitlines():
        if re.match(r"^\s*-\s+\w+:", line):
            if cur:
                items.append(cur)
            cur = {}
            m = re.match(r"^\s*-\s+(\w+)\s*:\s*(.*)$", line)
            if m:
                cur[m.group(1)] = m.group(2).strip()
        elif cur is not None:
            m = re.match(r"^\s+(\w+)\s*:\s*(.*)$", line)
            if m:
                cur[m.group(1)] = m.group(2).strip()
    if cur:
        items.append(cur)
    return items


def _split_sections(body: str) -> dict[str, str]:
    parts = re.split(r"(?m)^##\s+", body)
    out: dict[str, str] = {}
    for part in parts:
        part = part.strip()
        if not part:
            continue
        lines = part.splitlines()
        key = lines[0].strip().lower()
        out[key] = "\n".join(lines[1:]).strip()
    return out


def _run_api(args: list[str], dry_run: bool) -> dict[str, Any]:
    cmd = [str(PY), str(API), *args]
    if dry_run:
        return {"ok": True, "dry_run": True, "cmd": cmd}
    r = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True)
    if r.returncode != 0:
        return {
            "ok": False,
            "stderr": (r.stderr or "")[:400],
            "stdout": (r.stdout or "")[:200],
            "cmd": cmd,
        }
    try:
        return json.loads((r.stdout or "").strip().splitlines()[-1])
    except Exception:
        return {"ok": True, "raw": (r.stdout or "")[:300]}


def apply_file(path: Path, *, dry_run: bool) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    meta, body = _parse_frontmatter(text)
    if (meta.get("action") or "").strip() != "notion_tasks":
        return {"file": path.name, "skipped": True, "reason": "not notion_tasks"}
    sections = _split_sections(body)
    lanes = _load_lanes()
    results: list[dict[str, Any]] = []

    for item in _parse_items(sections.get("create") or ""):
        lane = (item.get("lane") or "").strip()
        title = (item.get("title") or "").strip()
        if not lane or not title:
            results.append({"op": "create", "ok": False, "error": "lane/title required", "item": item})
            continue
        args = ["create-task", "--lane", lane, "--title", title]
        if item.get("due"):
            args += ["--due", item["due"]]
        if item.get("note"):
            args += ["--note", item["note"]]
        if item.get("status"):
            args += ["--status", item["status"]]
        results.append({"op": "create", **_run_api(args, dry_run), "title": title, "lane": lane})

    for item in _parse_items(sections.get("done") or ""):
        lane = (item.get("lane") or "").strip()
        page_id = (item.get("page_id") or "").strip()
        if not lane or not page_id:
            results.append({"op": "done", "ok": False, "error": "lane/page_id required", "item": item})
            continue
        cfg = lanes.get(lane) or {}
        done_list = list(cfg.get("done_statuses") or ["完了"])
        status = (item.get("to_status") or "").strip() or done_list[0]
        reason = (item.get("reason") or "").strip()
        comment = reason if reason.startswith("タスク完了したよ") else (
            f"タスク完了したよ（ホーク・週次で確認）{('・' + reason) if reason else ''}"
        )
        args = [
            "complete-task",
            "--lane",
            lane,
            "--page-id",
            page_id,
            "--status",
            status,
            "--who",
            "ホーク",
            "--comment",
            comment,
        ]
        results.append(
            {
                "op": "done",
                **_run_api(args, dry_run),
                "page_id": page_id,
                "status": status,
                "reason": reason,
                "comment": comment,
            }
        )

    for item in _parse_items(sections.get("archive") or ""):
        page_id = (item.get("page_id") or "").strip()
        if not page_id:
            results.append({"op": "archive", "ok": False, "error": "page_id required", "item": item})
            continue
        args = ["archive-page", "--page-id", page_id]
        results.append(
            {
                "op": "archive",
                **_run_api(args, dry_run),
                "page_id": page_id,
                "reason": item.get("reason") or "",
            }
        )

    ok = all(r.get("ok", True) for r in results if not r.get("skipped"))
    return {"file": path.name, "ok": ok, "results": results, "meta": meta}


def main() -> int:
    p = argparse.ArgumentParser(description="ホーク Notion タスク inbox 反映")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--apply", action="store_true")
    p.add_argument(
        "--archive-done",
        action="store_true",
        help="処理成功した inbox MD を 90_archive 相当へ移動（bridge archive）",
    )
    p.add_argument("--file", default="", help="特定ファイル名のみ")
    args = p.parse_args()
    if not args.dry_run and not args.apply:
        print("ERROR: --dry-run または --apply を指定", file=sys.stderr)
        return 2

    inbox = folder("inbox_from_grok")
    files = list_queue_files(inbox)
    if args.file:
        files = [f for f in files if f.name == args.file]
    reports = []
    for f in files:
        text = f.read_text(encoding="utf-8", errors="replace")
        meta, _ = _parse_frontmatter(text)
        if (meta.get("action") or "").strip() != "notion_tasks":
            continue
        report = apply_file(f, dry_run=args.dry_run)
        reports.append(report)
        if args.apply and args.archive_done and report.get("ok") and not report.get("skipped"):
            # 成功時のみ archive サブフォルダへ
            arch = inbox.parent / "90_archive" / "inbox_from_grok"
            arch.mkdir(parents=True, exist_ok=True)
            dest = arch / f.name
            if dest.exists():
                dest = arch / f"{f.stem}_{f.stat().st_mtime_ns}{f.suffix}"
            f.rename(dest)
            report["archived_to"] = str(dest)

    print(json.dumps({"ok": True, "count": len(reports), "reports": reports}, ensure_ascii=False, indent=2))
    if any(not r.get("ok", True) for r in reports):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
