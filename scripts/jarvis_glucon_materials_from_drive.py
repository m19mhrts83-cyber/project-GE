#!/usr/bin/env python3
"""Grok Drive のグルコン材料 → jarvis-dashboard.glucon_material_items。

置き場（admin Drive）:
  【with Grok bot】/40_glucon_materials/inbox/*.md
  【with Grok bot】/40_glucon_materials/processed/

MD frontmatter 例:
---
kind: activity   # activity | result | either
title: ホーク週次の買い進め整理
for_result: false
period_key: 2026-08
tags: [grok, hawk]
recorded_at: 2026-08-30
---
本文…

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_glucon_materials_from_drive.py --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_glucon_materials_from_drive.py --apply
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from datetime import date
from pathlib import Path
from typing import Any

import urllib.error
import urllib.request
import yaml  # type: ignore

REPO = Path(__file__).resolve().parents[1]
BRIDGE = REPO / "config" / "kurashift_grok_bridge_folders.yaml"
CFG = REPO / "config" / "glucon_grok_materials.yaml"


def _bridge_root() -> Path:
    data = yaml.safe_load(BRIDGE.read_text(encoding="utf-8")) or {}
    return Path(data["local_root"])


def _materials_dirs() -> tuple[Path, Path]:
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8")) if CFG.is_file() else {}
    rel = (cfg or {}).get("drive_rel", "40_glucon_materials")
    root = _bridge_root() / rel
    inbox = root / "inbox"
    processed = root / "processed"
    return inbox, processed


def _parse_md(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end < 0:
        return {}, text
    meta = yaml.safe_load(text[3:end]) or {}
    body = text[end + 4 :].lstrip("\n")
    return dict(meta) if isinstance(meta, dict) else {}, body


def _sb() -> tuple[str, str]:
    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").rstrip("/")
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_* 未設定")
    return url, key


def _post(rows: list[dict[str, Any]]) -> None:
    url, key = _sb()
    data = json.dumps(rows, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{url}/rest/v1/glucon_material_items",
        data=data,
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            resp.read()
    except urllib.error.HTTPError as e:
        raise SystemExit(f"HTTP {e.code}: {e.read().decode('utf-8','replace')[:400]}") from e


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()
    if not args.dry_run and not args.apply:
        print("ERROR: --dry-run または --apply", file=sys.stderr)
        return 2

    inbox, processed = _materials_dirs()
    inbox.mkdir(parents=True, exist_ok=True)
    processed.mkdir(parents=True, exist_ok=True)

    files = sorted(
        [f for f in inbox.iterdir() if f.is_file() and f.suffix.lower() in (".md", ".txt")],
        key=lambda x: x.name,
    )
    rows = []
    for f in files:
        text = f.read_text(encoding="utf-8", errors="replace")
        meta, body = _parse_md(text)
        title = str(meta.get("title") or f.stem)
        kind = str(meta.get("kind") or "activity")
        if kind not in ("activity", "result", "either"):
            kind = "activity"
        rows.append(
            {
                "period_key": meta.get("period_key") or date.today().strftime("%Y-%m"),
                "kind": kind,
                "title": title,
                "body": body.strip() or title,
                "source": str(meta.get("source") or "grok_drive"),
                "drive_path": str(f),
                "tags": list(meta.get("tags") or ["grok"]),
                "for_result": bool(meta.get("for_result")) or kind == "result",
                "status": "pending",
                "recorded_at": str(meta.get("recorded_at") or date.today()),
                "payload": {"filename": f.name},
            }
        )

    print(json.dumps({"files": len(files), "rows": len(rows)}, ensure_ascii=False))
    if args.dry_run:
        print(json.dumps(rows[:3], ensure_ascii=False, indent=2))
        return 0
    if rows:
        _post(rows)
    for f in files:
        dest = processed / f.name
        if dest.exists():
            dest = processed / f"{f.stem}_{date.today().isoformat()}{f.suffix}"
        shutil.move(str(f), str(dest))
    print(f"# applied {len(rows)} → processed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
