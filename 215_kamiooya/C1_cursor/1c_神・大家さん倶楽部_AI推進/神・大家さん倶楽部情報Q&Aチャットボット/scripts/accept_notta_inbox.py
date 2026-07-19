#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""inbox/notta 配下の新規 xlsx/srt を一括 dry-run / 取込する受入れスクリプト。"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_INBOX = Path(
    "/Users/matsunomasaharu2/Library/CloudStorage/OneDrive-個人用/"
    "215_神・大家さん倶楽部/C1_cursor/1c_神・大家さん倶楽部_AI推進/"
    "神・大家さん倶楽部情報Q&Aチャットボット/inbox/notta"
)
PY = "/Users/matsunomasaharu2/selenium_env/venv/bin/python"
IMPORTER = SCRIPT_DIR / "notta_to_knowledge.py"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inbox", default=str(DEFAULT_INBOX))
    ap.add_argument("--apply", action="store_true", help="dry-run ではなく本番 upsert")
    ap.add_argument(
        "--skip-supabase",
        action="store_true",
        default=None,
        help="Supabase へ送らない（既定: SERVICE_ROLE が無ければ skip）",
    )
    ap.add_argument(
        "--with-supabase",
        action="store_true",
        help="SUPABASE_* があるとき remote upsert する",
    )
    args = ap.parse_args()
    inbox = Path(args.inbox).expanduser()
    if not inbox.is_dir():
        print(f"inbox がありません: {inbox}", file=sys.stderr)
        return 2
    # load env for supabase detection
    for envp in (
        Path.home() / "git-repos" / ".env.jarvis_private",
        SCRIPT_DIR / ".env",
        Path(
            "/Users/matsunomasaharu2/Library/CloudStorage/OneDrive-個人用/"
            "215_神・大家さん倶楽部/C1_cursor/1c_神・大家さん倶楽部_AI推進/"
            "神・大家さん倶楽部情報Q&Aチャットボット/scripts/.env"
        ),
    ):
        if not envp.is_file():
            continue
        import os

        for line in envp.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

    import os

    has_sb = bool(
        (os.environ.get("SUPABASE_URL") or "").strip()
        and (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    )
    skip_sb = True
    if args.skip_supabase is True:
        skip_sb = True
    elif args.with_supabase:
        skip_sb = not has_sb
    elif has_sb and args.apply:
        skip_sb = False

    files = sorted(
        [p for p in inbox.rglob("*") if p.suffix.lower() in (".xlsx", ".srt") and p.is_file()]
    )
    if not files:
        print(
            f"取込対象なし: {inbox} "
            "（サンプル or 実ファイルを日付フォルダへ保存してください）"
        )
        return 0
    rc = 0
    for f in files:
        video_id = f.stem
        cmd = [
            PY,
            str(IMPORTER),
            "--input",
            str(f),
            "--video-id",
            video_id,
            "--title",
            f.stem,
        ]
        if not args.apply:
            cmd.append("--dry-run")
        if skip_sb:
            cmd.append("--skip-supabase")
        print("==>", " ".join(cmd))
        p = subprocess.run(cmd)
        if p.returncode != 0:
            rc = p.returncode
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
