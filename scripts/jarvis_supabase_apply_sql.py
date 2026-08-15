#!/usr/bin/env python3
"""jarvis-dashboard 向け DDL を Supabase Management API で適用する。

Cloudflare がデフォルト UA を弾く（error 1010）ことがあるため、
ブラウザ相当の User-Agent を必ず付ける。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_supabase_apply_sql.py \\
    apps/jarvis-dashboard/supabase/migrations/20260815_kurashift_re_inquiry.sql
  ~/selenium_env/venv/bin/python scripts/jarvis_supabase_apply_sql.py --sql 'select 1'

要: SUPABASE_ACCESS_TOKEN
対象: JARVIS_SUPABASE_PROJECT_REF（既定 idkdqneutpvkhxhpjtgc = jarvis-dashboard）
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_REF = "idkdqneutpvkhxhpjtgc"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def apply_sql(ref: str, sql: str, *, dry_run: bool = False) -> int:
    token = (os.environ.get("SUPABASE_ACCESS_TOKEN") or "").strip()
    if not token:
        print("SUPABASE_ACCESS_TOKEN 未設定", file=sys.stderr)
        return 1
    url = f"https://api.supabase.com/v1/projects/{ref}/database/query"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": UA,
    }
    print(f"# ref={ref} sql_chars={len(sql)} dry_run={dry_run}", file=sys.stderr)
    if dry_run:
        print(sql[:500] + ("…" if len(sql) > 500 else ""))
        return 0
    data = json.dumps({"query": sql}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            body = resp.read().decode("utf-8", "replace")
            print(f"# OK status={resp.status}", file=sys.stderr)
            if body and body != "[]":
                print(body[:2000])
            return 0
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", "replace")[:800]
        print(f"# FAIL HTTP {e.code}: {err}", file=sys.stderr)
        if e.code in (403, 1010) or "1010" in err:
            print(
                "ヒント: Cloudflare 1010 / 403 は UA 不足か Access Token 無効のことが多い。\n"
                "  Dashboard → Account → Access Tokens で再発行し "
                ".env.jarvis_private の SUPABASE_ACCESS_TOKEN を更新。\n"
                "  このスクリプトはブラウザ相当 UA を付与済み。",
                file=sys.stderr,
            )
        return 2
    except Exception as e:
        print(f"# FAIL {type(e).__name__}: {e}", file=sys.stderr)
        return 2


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", help="SQL ファイルパス")
    ap.add_argument("--sql", default="", help="インライン SQL")
    ap.add_argument(
        "--ref",
        default=(os.environ.get("JARVIS_SUPABASE_PROJECT_REF") or DEFAULT_REF).strip(),
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    if args.sql.strip():
        sql = args.sql
    elif args.path:
        p = Path(args.path).expanduser()
        if not p.is_file():
            print(f"file not found: {p}", file=sys.stderr)
            return 1
        sql = p.read_text(encoding="utf-8")
    else:
        ap.print_help()
        return 2
    return apply_sql(args.ref, sql, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
