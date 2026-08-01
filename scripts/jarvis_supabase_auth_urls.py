#!/usr/bin/env python3
"""
Jarvis: jarvis-dashboard Auth の Site URL / Redirect を本番向けに揃える。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  python scripts/jarvis_supabase_auth_urls.py
  python scripts/jarvis_supabase_auth_urls.py --dry-run

要: SUPABASE_ACCESS_TOKEN（Management API）。403 のときは Dashboard で手動設定。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_SITE = "https://jarvis-dashboard-amber.vercel.app"
PROJECT_REF = "idkdqneutpvkhxhpjtgc"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default=os.environ.get("JARVIS_DASHBOARD_URL") or DEFAULT_SITE)
    ap.add_argument("--ref", default=PROJECT_REF)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    token = (os.environ.get("SUPABASE_ACCESS_TOKEN") or "").strip()
    if not token:
        print("SUPABASE_ACCESS_TOKEN 未設定", file=sys.stderr)
        return 1

    site = args.site.rstrip("/")
    extras = [
        site,
        f"{site}/auth/callback",
        "http://localhost:3001",
        "http://localhost:3001/auth/callback",
    ]
    url = f"https://api.supabase.com/v1/projects/{args.ref}/config/auth"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req) as r:
            cur = json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read()[:300]
        print(f"# GET failed: {e.code} {body!r}", file=sys.stderr)
        print(
            "Dashboard で手動: Authentication → URL Configuration\n"
            f"  Site URL = {site}\n"
            f"  Redirect URLs に {site}/auth/callback と localhost:3001 を追加\n"
            "ヒント: 403 / Cloudflare 1010 は SUPABASE_ACCESS_TOKEN 期限切れか無効のことが多い。\n"
            "  Dashboard → Account → Access Tokens で新規発行し .env.jarvis_private を更新して再実行。\n"
            "  パスワードログインは Site URL 未変更でも動作する（本設定は OAuth／マジックリンク向け）。",
            file=sys.stderr,
        )
        return 2

    allow = cur.get("uri_allow_list") or ""
    parts = [p.strip() for p in allow.split(",") if p.strip()]
    for u in extras:
        if u not in parts:
            parts.append(u)
    new_allow = ",".join(parts)
    body = {"site_url": site, "uri_allow_list": new_allow}
    print(f"# current site_url={cur.get('site_url')}", file=sys.stderr)
    print(f"# next site_url={site}", file=sys.stderr)
    if args.dry_run:
        print(json.dumps(body, ensure_ascii=False, indent=2))
        return 0

    data = json.dumps(body).encode()
    req2 = urllib.request.Request(
        url,
        data=data,
        method="PATCH",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req2) as r:
            out = json.load(r)
        print(f"# updated site_url={out.get('site_url')}", file=sys.stderr)
        print(json.dumps({"ok": True, "site_url": out.get("site_url")}, ensure_ascii=False))
        return 0
    except urllib.error.HTTPError as e:
        print(f"# PATCH failed: {e.code} {e.read()[:300]!r}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
