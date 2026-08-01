#!/usr/bin/env python3
"""
NotebookLM 作業セットを開く（Finder の 200_NoteBookLM ＋ NotebookLM）。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  python scripts/jarvis_notebooklm_workbench_open.py
  python scripts/jarvis_notebooklm_workbench_open.py --dry-run
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
CFG_PATH = REPO / "config" / "notebooklm_workbench.yaml"


def load_cfg() -> dict:
    return yaml.safe_load(CFG_PATH.read_text(encoding="utf-8")) or {}


def expand_path(p: str) -> Path:
    return Path(os.path.expanduser(p)).resolve()


def open_target(target: str, *, dry_run: bool) -> None:
    if dry_run:
        print(f"# dry-run open {target}")
        return
    subprocess.run(["open", target], check=False)


def open_workbench(*, dry_run: bool = False, skip_browser: bool = False) -> int:
    cfg = load_cfg()
    local = expand_path(str(cfg.get("local_folder") or ""))
    nlm = (os.environ.get("NOTEBOOKLM_URL") or cfg.get("notebooklm_url") or "").strip()
    drive = (
        (os.environ.get("NOTEBOOKLM_DRIVE_FOLDER_URL") or "").strip()
        or str(cfg.get("drive_folder_url") or "").strip()
    )

    if not local.is_dir():
        print(f"# missing local folder: {local}", file=sys.stderr)
        return 1

    print(f"# finder {local}")
    open_target(str(local), dry_run=dry_run)

    if not skip_browser and nlm:
        print(f"# notebooklm {nlm}")
        open_target(nlm, dry_run=dry_run)

    if drive:
        print(f"# drive_web {drive}")
        open_target(drive, dry_run=dry_run)

    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-browser", action="store_true", help="Finder のみ")
    args = ap.parse_args(argv)
    return open_workbench(dry_run=args.dry_run, skip_browser=args.skip_browser)


if __name__ == "__main__":
    raise SystemExit(main())
