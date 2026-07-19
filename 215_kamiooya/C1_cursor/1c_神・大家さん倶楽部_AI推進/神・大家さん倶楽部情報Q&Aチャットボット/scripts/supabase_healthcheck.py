#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Supabase 接続・スキーマ健全性チェック（秘密は表示しない）

例:
  python3 supabase_healthcheck.py
  python3 supabase_healthcheck.py --touch
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

SCRIPT_DIR = Path(__file__).resolve().parent


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


def rest_get(url: str, token: str, path: str, timeout: int = 20) -> tuple[int, bytes]:
    req = urllib.request.Request(
        url.rstrip("/") + path,
        headers={
            "apikey": token,
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def rest_upsert_heartbeat(url: str, token: str, note: str) -> tuple[int, str]:
    now = datetime.now(timezone.utc).isoformat()
    body = json.dumps(
        {
            "id": "weekly",
            "source": "jarvis",
            "note": note,
            "touched_at": now,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        url.rstrip("/") + "/rest/v1/jarvis_heartbeat?on_conflict=id",
        data=body,
        headers={
            "apikey": token,
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, ""
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")[:200]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--touch",
        action="store_true",
        help="jarvis_heartbeat を upsert（Free 休止防止・週次必須）",
    )
    ap.add_argument("--note", default="westudy-weekly", help="心拍 note")
    args = ap.parse_args()

    load_env()
    url = (os.environ.get("SUPABASE_URL") or "").strip().rstrip("/")
    key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    anon = (os.environ.get("SUPABASE_ANON_KEY") or "").strip()
    print(f"SUPABASE_URL set={bool(url)} host={urlparse(url).hostname or '-'}")
    print(f"SERVICE_ROLE set={bool(key)} len={len(key)}")
    print(f"ANON set={bool(anon)} len={len(anon)}")
    if not url:
        print("NG: SUPABASE_URL missing")
        print("SUMMARY: 疎通=NG 心拍=skipped reason=no_url")
        return 2
    host = urlparse(url).hostname or ""
    try:
        socket.getaddrinfo(host, 443)
        print("DNS: OK")
    except socket.gaierror as e:
        print(f"DNS: NG ({e}) — プロジェクト削除/休止の可能性。Dashboard で Restore")
        print("SUMMARY: 疎通=NG 心拍=skipped reason=dns")
        return 3
    token = key or anon
    if not token:
        print("NG: no API key")
        print("SUMMARY: 疎通=NG 心拍=skipped reason=no_key")
        return 2

    status, _ = rest_get(url, token, "/rest/v1/comments?select=comment_id&limit=1")
    print(f"REST comments: HTTP {status}")
    if status >= 400:
        print("SUMMARY: 疎通=NG 心拍=skipped reason=comments_http")
        return 4

    for table in ("knowledge_sources", "knowledge_chunks", "jarvis_heartbeat"):
        st, _ = rest_get(url, token, f"/rest/v1/{table}?select=id&limit=1")
        print(f"REST {table}: HTTP {st}")
        if table == "jarvis_heartbeat" and st == 404:
            print("  hint: schema.sql の jarvis_heartbeat 未適用の可能性")

    touch_note = "skipped"
    if args.touch:
        st, err = rest_upsert_heartbeat(url, token, args.note)
        if 200 <= st < 300 or st == 201:
            print(f"heartbeat touch: OK HTTP {st}")
            touch_note = "OK"
        else:
            print(f"heartbeat touch: NG HTTP {st} {err}", file=sys.stderr)
            print(f"SUMMARY: 疎通=OK 心拍=NG http={st}")
            return 5

    print("OK: reachable")
    print(f"SUMMARY: 疎通=OK 心拍={touch_note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
