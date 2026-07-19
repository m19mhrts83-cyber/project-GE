#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
サンプル Notta（fixture）で端到端接続を検証する。

1. fixtures/notta の xlsx + srt を parse / chunk
2. ローカル SQLite へ upsert（冪等）
3. SUPABASE_* があれば remote へも upsert
4. 「融資」等で横断検索し、タイトル・開始秒が出ることを確認

例:
  python3 sample_notta_e2e.py
  python3 sample_notta_e2e.py --with-supabase
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
PY = "/Users/matsunomasaharu2/selenium_env/venv/bin/python"
FIXTURES = ROOT / "fixtures" / "notta"
IMPORTER = SCRIPT_DIR / "notta_to_knowledge.py"


def load_env() -> None:
    for p in (
        Path.home() / "git-repos" / ".env.jarvis_private",
        SCRIPT_DIR / ".env",
        Path(
            "/Users/matsunomasaharu2/Library/CloudStorage/OneDrive-個人用/"
            "215_神・大家さん倶楽部/C1_cursor/1c_神・大家さん倶楽部_AI推進/"
            "神・大家さん倶楽部情報Q&Aチャットボット/scripts/.env"
        ),
    ):
        if not p.is_file():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def run(cmd: list[str]) -> int:
    print("==>", " ".join(cmd))
    return subprocess.call(cmd)


def main() -> int:
    load_env()
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-supabase", action="store_true")
    ap.add_argument("--query", default="融資")
    args = ap.parse_args()

    xlsx = FIXTURES / "with_ts_speaker.xlsx"
    srt = FIXTURES / "with_ts.srt"
    if not xlsx.is_file() or not srt.is_file():
        print(f"fixtures missing under {FIXTURES}", file=sys.stderr)
        return 2

    # dry-run both formats
    for path, vid, title in (
        (srt, "sample_step3_smtb", "【サンプル】神大家 STEP3 三井住友信託"),
        (xlsx, "sample_step3_smtb", "【サンプル】神大家 STEP3 三井住友信託"),
    ):
        cmd = [
            PY,
            str(IMPORTER),
            "--input",
            str(path),
            "--video-id",
            vid,
            "--title",
            title,
            "--video-url",
            "https://westudy.ex-server.jp/sample?t=0",
            "--dry-run",
        ]
        if run(cmd) != 0:
            return 3

    # apply local (+ optional supabase)
    cmd = [
        PY,
        str(IMPORTER),
        "--input",
        str(xlsx),
        "--video-id",
        "sample_step3_smtb",
        "--title",
        "【サンプル】神大家 STEP3 三井住友信託",
        "--video-url",
        "https://westudy.ex-server.jp/sample?t=0",
        "--instructor",
        "サンプル講師",
    ]
    if not args.with_supabase:
        cmd.append("--skip-supabase")
    if run(cmd) != 0:
        return 4

    # second apply = idempotent
    if run(cmd) != 0:
        return 5

    sys.path.insert(0, str(SCRIPT_DIR))
    from knowledge_local import connect, counts, search_all

    conn = connect()
    c = counts(conn)
    hits = search_all(conn, args.query, limit=5)
    print(f"counts={c}")
    print(f"search q={args.query!r} hits={len(hits)}")
    ok_video = False
    for h in hits:
        kind = h.get("kind")
        title = h.get("video_title") or h.get("author_name")
        label = h.get("start_label")
        snip = (h.get("snippet") or h.get("content") or "")[:80]
        print(f"  [{kind}] {title} {label} :: {snip}")
        if kind == "video_chunk" and label:
            ok_video = True
    conn.close()

    if not ok_video:
        print("FAIL: video_chunk with start_label not found", file=sys.stderr)
        return 6

    has_sb = bool(
        (os.environ.get("SUPABASE_URL") or "").strip()
        and (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    )
    if args.with_supabase and not has_sb:
        print("FAIL: --with-supabase but keys missing", file=sys.stderr)
        return 7
    if has_sb and args.with_supabase:
        print("OK: sample Notta → local + Supabase path exercised")
    else:
        print("OK: sample Notta → local path exercised (Supabase はキー設定後に --with-supabase)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
