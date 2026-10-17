#!/usr/bin/env python3
"""Grok／ホーク → 311: Drive inbox `action: send_gate_311` を input/ へ enqueue。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_hawk_send_gate_311_apply.py --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_hawk_send_gate_311_apply.py --apply --archive-done

Inbox 例:

---
action: send_gate_311
target: jarvis
source: hawk
draft_path: /絶対パス/4.送信下書き.txt
partner_or_thread: 103_Tcell
---
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
from jarvis_send_gate_311 import enqueue_request  # noqa: E402

ACTION = "send_gate_311"


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.lstrip().startswith("---"):
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
        meta[k.strip().lower()] = v.strip().strip("\"'")
    return meta, text[end + 4 :].lstrip("\n")


def archive_file(path: Path) -> None:
    dest_dir = folder("archive")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / path.name
    if dest.exists():
        stem, suf = path.stem, path.suffix
        n = 1
        while True:
            cand = dest_dir / f"{stem}_{n}{suf}"
            if not cand.exists():
                dest = cand
                break
            n += 1
    shutil.move(str(path), str(dest))


def collect_targets() -> list[Path]:
    out: list[Path] = []
    inbox = folder("inbox_from_grok")
    for p in list_queue_files(inbox):
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        meta, _ = parse_frontmatter(text)
        if (meta.get("action") or "").strip() == ACTION:
            out.append(p)
    return out


def apply_one(path: Path, *, dry_run: bool) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    meta, _ = parse_frontmatter(text)
    draft = (meta.get("draft_path") or meta.get("draft") or "").strip()
    source = (meta.get("source") or "hawk").strip() or "hawk"
    partner = (meta.get("partner_or_thread") or meta.get("partner") or "").strip()
    if not draft:
        return {"ok": False, "file": path.name, "error": "draft_path missing"}
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "file": path.name,
            "draft_path": draft,
            "source": source,
        }
    try:
        written = enqueue_request(
            draft,
            source=source,
            partner_or_thread=partner,
            note=f"hawk inbox apply ({path.name})",
        )
    except Exception as e:
        return {"ok": False, "file": path.name, "error": str(e)[:200]}
    return {
        "ok": True,
        "file": path.name,
        "draft_path": draft,
        "source": source,
        "enqueued": str(written),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--archive-done", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    if not args.dry_run and not args.apply:
        ap.error("--dry-run または --apply を指定")

    if (os.environ.get("JARVIS_SEND_GATE_311_HAWK_APPLY_DISABLE") or "").strip() in (
        "1",
        "true",
        "yes",
    ):
        result = {"ok": True, "skipped": True, "reason": "disabled", "count": 0}
        print(json.dumps(result, ensure_ascii=False) if args.json else result)
        return 0

    targets = collect_targets()
    results: list[dict[str, Any]] = []
    for p in targets:
        r = apply_one(p, dry_run=bool(args.dry_run))
        results.append(r)
        if (
            args.apply
            and args.archive_done
            and r.get("ok")
            and not r.get("dry_run")
        ):
            try:
                archive_file(p)
                r["archived"] = True
            except Exception as e:
                r["archive_error"] = str(e)[:120]

    summary = {
        "ok": all(x.get("ok") for x in results) if results else True,
        "count": len(results),
        "results": results,
    }
    if args.json:
        print(json.dumps(summary, ensure_ascii=False))
    else:
        print(f"send_gate_311 apply count={summary['count']} ok={summary['ok']}")
        for r in results:
            print(f"  - {r}")
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
