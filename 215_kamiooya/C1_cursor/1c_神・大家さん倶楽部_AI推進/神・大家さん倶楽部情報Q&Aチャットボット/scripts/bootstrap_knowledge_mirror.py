#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WeStudy 管理者CSV → ローカル SQLite / Supabase comments ブートストラップ

例:
  python3 bootstrap_knowledge_mirror.py --csv exports/full_authors_bootstrap_20260720.csv
  python3 bootstrap_knowledge_mirror.py --csv ... --supabase-only
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from knowledge_local import connect, counts, upsert_comments  # noqa: E402
from upload_csv_to_supabase import read_csv_records  # noqa: E402


def try_supabase(records: list[dict], chunk_size: int = 300) -> tuple[int, int]:
    url = (os.environ.get("SUPABASE_URL") or "").strip()
    key = (
        (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
        or (os.environ.get("SUPABASE_ANON_KEY") or "").strip()
    )
    if not url or not key:
        print("Supabase: skipped (URL/KEY missing)")
        return 0, 0
    try:
        from supabase import create_client
    except ImportError:
        print("Supabase: skipped (supabase package missing)")
        return 0, 0
    try:
        client = create_client(url, key)
        ok = 0
        failed = 0
        for i in range(0, len(records), chunk_size):
            chunk = records[i : i + chunk_size]
            try:
                client.table("comments").upsert(chunk, on_conflict="comment_id").execute()
                ok += len(chunk)
                print(f"  supabase chunk ok {i+1}-{i+len(chunk)}")
            except Exception as e:
                failed += len(chunk)
                print(f"  supabase chunk NG {i+1}-{i+len(chunk)}: {e}", file=sys.stderr)
        return ok, failed
    except Exception as e:
        print(f"Supabase connection failed: {e}", file=sys.stderr)
        return 0, len(records)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--skip-local", action="store_true")
    ap.add_argument("--skip-supabase", action="store_true")
    args = ap.parse_args()

    # Load chatbot .env if present
    env_path = SCRIPT_DIR / ".env"
    od_env = Path(
        "/Users/matsunomasaharu2/Library/CloudStorage/OneDrive-個人用/"
        "215_神・大家さん倶楽部/C1_cursor/1c_神・大家さん倶楽部_AI推進/"
        "神・大家さん倶楽部情報Q&Aチャットボット/scripts/.env"
    )
    for p in (env_path, od_env):
        if p.is_file():
            for line in p.read_text(encoding="utf-8").splitlines():
                s = line.strip()
                if not s or s.startswith("#") or "=" not in s:
                    continue
                k, v = s.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

    csv_path = Path(args.csv).expanduser().resolve()
    records = read_csv_records(csv_path)
    print(f"records={len(records)} file={csv_path}")

    if not args.skip_local:
        conn = connect()
        n = upsert_comments(conn, records)
        print(f"local upsert={n} counts={counts(conn)}")

    if not args.skip_supabase:
        ok, ng = try_supabase(records)
        print(f"supabase upserted={ok} failed={ng}")
        if ok == 0 and ng == 0:
            print(
                "NOTE: Supabase プロジェクトが NXDOMAIN / 休止の場合は Dashboard で "
                "新規作成または Restore し、SUPABASE_URL と SUPABASE_SERVICE_ROLE_KEY を "
                "scripts/.env と GitHub Secrets に設定してください。"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
