#!/usr/bin/env python3
"""jarvis-dashboard 向け DDL を Supabase Management API で適用する。

Cloudflare がデフォルト UA を弾く（error 1010）ことがあるため、
ブラウザ相当の User-Agent を必ず付ける。

エラー分岐（品質点検正本）:
  429 → 指数バックオフ（最大3回、X-RateLimit-Reset 尊重）
  1010 / bot 403 → 1回だけ再試行のあと代替経路案内（連打しない）
  401 → 即停止＋ Access Token 再発行案内

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
import time
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_REF = "idkdqneutpvkhxhpjtgc"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

ALT_HINT = """\
代替手順（1010 / 連続失敗時の正）:
  1) Supabase Dashboard → SQL Editor で同マイグレーションを貼って実行
  2) または supabase CLI: cd apps/jarvis-dashboard && npx supabase db push
  3) Access Token 疑いなら Dashboard → Account → Access Tokens で再発行し
     .env.jarvis_private の SUPABASE_ACCESS_TOKEN を更新
  ※ CAPTCHA 突破・スクレイパー系は使わない
"""


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": UA,
    }


def _post_query(ref: str, sql: str, token: str) -> tuple[int, str, dict[str, str]]:
    url = f"https://api.supabase.com/v1/projects/{ref}/database/query"
    data = json.dumps({"query": sql}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=_headers(token), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            body = resp.read().decode("utf-8", "replace")
            hdrs = {k.lower(): v for k, v in resp.headers.items()}
            return resp.status, body, hdrs
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", "replace")
        hdrs = {k.lower(): v for k, v in e.headers.items()} if e.headers else {}
        return e.code, err, hdrs


def apply_sql(ref: str, sql: str, *, dry_run: bool = False) -> int:
    token = (os.environ.get("SUPABASE_ACCESS_TOKEN") or "").strip()
    if not token:
        print("SUPABASE_ACCESS_TOKEN 未設定", file=sys.stderr)
        return 1
    print(f"# ref={ref} sql_chars={len(sql)} dry_run={dry_run}", file=sys.stderr)
    if dry_run:
        print(sql[:500] + ("…" if len(sql) > 500 else ""))
        return 0

    bot_retries = 0
    rate_retries = 0
    while True:
        try:
            status, body, hdrs = _post_query(ref, sql, token)
        except Exception as e:
            print(f"# FAIL {type(e).__name__}: {e}", file=sys.stderr)
            print(ALT_HINT, file=sys.stderr)
            return 2

        if 200 <= status < 300:
            print(f"# OK status={status}", file=sys.stderr)
            if body and body != "[]":
                print(body[:2000])
            print(
                "# 成功後: migrations と schema.sql の同期を確認してください",
                file=sys.stderr,
            )
            return 0

        err_snip = body[:800]
        print(f"# FAIL HTTP {status}: {err_snip}", file=sys.stderr)

        if status == 401:
            print(
                "ヒント: 401 → SUPABASE_ACCESS_TOKEN を再発行して "
                ".env.jarvis_private を更新してください。",
                file=sys.stderr,
            )
            return 2

        if status == 429:
            if rate_retries >= 3:
                print("# 429 が続きました。しばらく待ってから再実行。", file=sys.stderr)
                print(ALT_HINT, file=sys.stderr)
                return 2
            reset = hdrs.get("x-ratelimit-reset") or hdrs.get("retry-after")
            try:
                wait = max(2, min(60, int(float(reset))))
            except (TypeError, ValueError):
                wait = min(60, 2 ** (rate_retries + 1))
            rate_retries += 1
            print(
                f"# 429 → {wait}s 待機して再試行 ({rate_retries}/3)",
                file=sys.stderr,
            )
            time.sleep(wait)
            continue

        is_bot = status == 1010 or "1010" in body or (
            status == 403 and ("cloudflare" in body.lower() or "attention required" in body.lower())
        )
        if is_bot or status == 403:
            if bot_retries >= 1:
                print(
                    "# 1010/403 が再発 → Management API 連打を止め、代替手順へ。",
                    file=sys.stderr,
                )
                print(ALT_HINT, file=sys.stderr)
                return 2
            bot_retries += 1
            print("# bot 系 → 5s 後に1回だけ再試行", file=sys.stderr)
            time.sleep(5)
            continue

        print(ALT_HINT, file=sys.stderr)
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
