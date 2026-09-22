#!/usr/bin/env python3
"""ホーク／部長 inbox → Todoist タスク反映（create / owner_confirm / done / comment）。

Drive `10_inbox_from_grok/` の MD で frontmatter `action: todoist_tasks` を対象にする。
サマリ・アウトプットは **Todoist コメント**にも残す。アウトプットは Markdown ハイパーリンク
（相対パスは GitHub／Pages 等の https に解決）。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_hawk_todoist_tasks_apply.py --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_hawk_todoist_tasks_apply.py --apply
  ~/selenium_env/venv/bin/python scripts/jarvis_hawk_todoist_tasks_apply.py --apply --archive-done

Inbox 例:

---
action: todoist_tasks
priority: normal
target: jarvis
source: hawk
---

## create
- lane: ai_raimo
  title: [L-12] 例タスク
  due: 2026-09-28
  status: 未着手
  note: 説明（description）
  summary: 週次で優先度を上げた
  links: https://example.com/out | docs/Todoist_タスク正本_設計_20260921.md

## owner_confirm
- lane: ai_raimo
  task_id: …
  reason: 実装完了候補
  summary: 受け入れ条件はダッシュボードで確認可
  links: https://jarvis-dashboard-amber.vercel.app/

## done
- lane: ai_raimo
  task_id: …
  reason: タスク完了したよ（ホーク・松野確認済）
  summary: 週次レビューで完了確認
  links: …

## comment
- task_id: …
  summary: 処置メモのみ
  links: …
  text: 任意の追記
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
from jarvis_todoist_comment_links import (  # noqa: E402
    enrich_comment_output_links,
    format_outputs_block,
    split_link_field,
)

REPO = Path(__file__).resolve().parents[1]
PY = Path.home() / "selenium_env" / "venv" / "bin" / "python"
API = REPO / "scripts" / "jarvis_todoist_api.py"
ACTION = "todoist_tasks"

# Title / field → extra Todoist labels
SIGNAL_LABELS = {
    "要ボス": "要ボス",
    "要jarvis連携": "要Jarvis連携",
    "要Jarvis連携": "要Jarvis連携",
    "要ホーク": "要ホーク",
    "quick": "quick",
}


def _extra_labels_from_item(item: dict[str, str], title: str) -> list[str]:
    out: list[str] = []
    raw = (item.get("labels") or item.get("label") or "").strip()
    if raw:
        out.extend([x.strip() for x in re.split(r"[,|]", raw) if x.strip()])
    for key, lab in SIGNAL_LABELS.items():
        if key.lower() in title.lower() or f"[{lab}]" in title or f"[{key}]" in title:
            out.append(lab)
    # dedupe preserve order
    seen: set[str] = set()
    uniq: list[str] = []
    for x in out:
        if x not in seen:
            seen.add(x)
            uniq.append(x)
    return uniq


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
                val = m.group(2).strip()
                if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
                    val = val[1:-1]
                cur[m.group(1)] = val
        elif cur is not None:
            m = re.match(r"^\s+(\w+)\s*:\s*(.*)$", line)
            if m:
                val = m.group(2).strip()
                if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
                    val = val[1:-1]
                cur[m.group(1)] = val
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


def _links_lines(item: dict[str, str]) -> list[str]:
    raw = (
        item.get("links")
        or item.get("output")
        or item.get("outputs")
        or item.get("url")
        or ""
    ).strip()
    return split_link_field(raw)


def _build_comment(
    item: dict[str, str],
    *,
    kind: str,
    source: str,
    inbox_file: str,
    extra_prefix: str = "",
) -> str:
    """サマリ・アウトプットをコメントにまとめる。アウトプットは Markdown ハイパーリンク。"""
    lines: list[str] = []
    if extra_prefix:
        lines.append(extra_prefix.rstrip())
    else:
        lines.append(f"[Jarvis適用/{kind}] source={source or '-'} file={inbox_file}")
    summary = (item.get("summary") or item.get("サマリ") or "").strip()
    if summary:
        lines.append(f"サマリ: {summary}")
    note = (item.get("note") or "").strip()
    if note and kind != "create":
        lines.append(f"note: {note}")
    elif note and kind == "create" and not summary:
        lines.append(f"note: {note}")
    link_raws = _links_lines(item)
    if link_raws:
        lines.append("アウトプット:")
        lines.extend(format_outputs_block(link_raws))
    reason = (item.get("reason") or "").strip()
    if reason and kind in ("owner_confirm", "done", "comment"):
        lines.append(f"reason: {reason}")
    text = (item.get("text") or item.get("comment") or "").strip()
    if text:
        lines.append(text)
    body = "\n".join(lines).strip()
    body = enrich_comment_output_links(body)
    return body[:1900] if body else ""


def _run_api(args: list[str], dry_run: bool) -> dict[str, Any]:
    cmd = [str(PY), str(API), *args]
    if dry_run:
        return {"ok": True, "dry_run": True, "cmd": cmd}
    r = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True)
    stdout = (r.stdout or "").strip()
    stderr = (r.stderr or "").strip()
    if r.returncode != 0:
        return {
            "ok": False,
            "stderr": stderr[:400],
            "stdout": stdout[:200],
            "cmd": cmd,
        }
    # Prefer JSON line if present
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                data = json.loads(line)
                if isinstance(data, dict):
                    return {"ok": True, **data, "raw": stdout[:300]}
            except json.JSONDecodeError:
                pass
    out: dict[str, Any] = {"ok": True, "raw": stdout[:400]}
    m = re.search(r"\bid=([A-Za-z0-9]+)", stdout)
    if m:
        out["id"] = m.group(1)
    if "url=" in stdout:
        um = re.search(r"url=(\S+)", stdout)
        if um:
            out["url"] = um.group(1)
    return out


def apply_file(path: Path, *, dry_run: bool) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    meta, body = _parse_frontmatter(text)
    if (meta.get("action") or "").strip() != ACTION:
        return {"file": path.name, "skipped": True, "reason": f"not {ACTION}"}
    sections = _split_sections(body)
    source = (meta.get("source") or "").strip()
    results: list[dict[str, Any]] = []

    for item in _parse_items(sections.get("create") or ""):
        lane = (item.get("lane") or "").strip() or "inbox"
        title = (item.get("title") or "").strip()
        if not title:
            results.append({"op": "create", "ok": False, "error": "title required", "item": item})
            continue
        args = ["create-task", "--lane", lane, "--title", title, "--url", "--json"]
        if item.get("due"):
            args += ["--due", item["due"]]
        if item.get("note"):
            args += ["--note", item["note"]]
        if item.get("status"):
            args += ["--status", item["status"]]
        extra = _extra_labels_from_item(item, title)
        if item.get("label"):
            # already in extra via labels field; keep --label for CLI
            pass
        if extra:
            args += ["--label", ",".join(extra)]
        comment = _build_comment(item, kind="create", source=source, inbox_file=path.name)
        if comment:
            args += ["--comment", comment]
        results.append({"op": "create", **_run_api(args, dry_run), "title": title, "lane": lane})

    for item in _parse_items(sections.get("owner_confirm") or ""):
        lane = (item.get("lane") or "").strip()
        task_id = (item.get("task_id") or "").strip()
        if not lane or not task_id:
            results.append(
                {"op": "owner_confirm", "ok": False, "error": "lane/task_id required", "item": item}
            )
            continue
        move = _run_api(
            ["update-status", "--task-id", task_id, "--lane", lane, "--status", "オーナー確認"],
            dry_run,
        )
        comment = _build_comment(
            item, kind="owner_confirm", source=source, inbox_file=path.name
        )
        c_res: dict[str, Any] = {"ok": True, "skipped": True}
        if comment:
            c_res = _run_api(["comment", "--task-id", task_id, "--text", comment], dry_run)
        results.append(
            {
                "op": "owner_confirm",
                "ok": bool(move.get("ok")) and bool(c_res.get("ok", True)),
                "task_id": task_id,
                "move": move,
                "comment": c_res,
            }
        )

    for item in _parse_items(sections.get("done") or ""):
        lane = (item.get("lane") or "").strip()
        task_id = (item.get("task_id") or "").strip()
        if not lane or not task_id:
            results.append({"op": "done", "ok": False, "error": "lane/task_id required", "item": item})
            continue
        reason = (item.get("reason") or "").strip()
        who = (item.get("who") or meta.get("source") or "ホーク").strip()
        # complete-task は定型先頭を付与。summary/links は別コメントで先に残す
        disposition = _build_comment(item, kind="done", source=source, inbox_file=path.name)
        pre: dict[str, Any] = {"ok": True, "skipped": True}
        if disposition and not dry_run:
            pre = _run_api(["comment", "--task-id", task_id, "--text", disposition], False)
        elif disposition and dry_run:
            pre = {"ok": True, "dry_run": True, "comment_preview": disposition[:200]}
        done_args = [
            "complete-task",
            "--lane",
            lane,
            "--task-id",
            task_id,
            "--who",
            who,
        ]
        if reason:
            done_args += ["--comment", reason]
        done_res = _run_api(done_args, dry_run)
        results.append(
            {
                "op": "done",
                "ok": bool(done_res.get("ok")) and bool(pre.get("ok", True)),
                "task_id": task_id,
                "disposition_comment": pre,
                "complete": done_res,
            }
        )

    for item in _parse_items(sections.get("comment") or ""):
        task_id = (item.get("task_id") or "").strip()
        if not task_id:
            results.append({"op": "comment", "ok": False, "error": "task_id required", "item": item})
            continue
        comment = _build_comment(item, kind="comment", source=source, inbox_file=path.name)
        if not comment:
            results.append({"op": "comment", "ok": False, "error": "empty comment", "item": item})
            continue
        results.append(
            {
                "op": "comment",
                **_run_api(["comment", "--task-id", task_id, "--text", comment], dry_run),
                "task_id": task_id,
            }
        )

    ok = all(r.get("ok", True) for r in results if not r.get("skipped"))
    if not results:
        ok = True
    return {"file": path.name, "ok": ok, "results": results, "meta": meta}


def main() -> int:
    p = argparse.ArgumentParser(description="ホーク／部長 Todoist タスク inbox 反映")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--apply", action="store_true")
    p.add_argument(
        "--archive-done",
        action="store_true",
        help="処理成功した inbox MD を 90_archive/inbox_from_grok へ移動",
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
        if (meta.get("action") or "").strip() != ACTION:
            continue
        report = apply_file(f, dry_run=args.dry_run)
        reports.append(report)
        if args.apply and args.archive_done and report.get("ok") and not report.get("skipped"):
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
