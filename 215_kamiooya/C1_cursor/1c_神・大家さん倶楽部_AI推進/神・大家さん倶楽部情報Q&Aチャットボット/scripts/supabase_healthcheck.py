#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Supabase 接続・スキーマ健全性チェック（秘密は表示しない）"""

from __future__ import annotations

import os
import socket
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

SCRIPT_DIR = Path(__file__).resolve().parent


def load_env() -> None:
    for p in (
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
            os.environ.setdefault(k.strip(), v.strip())


def main() -> int:
    load_env()
    url = (os.environ.get("SUPABASE_URL") or "").strip().rstrip("/")
    key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    anon = (os.environ.get("SUPABASE_ANON_KEY") or "").strip()
    print(f"SUPABASE_URL set={bool(url)} host={urlparse(url).hostname or '-'}")
    print(f"SERVICE_ROLE set={bool(key)} len={len(key)}")
    print(f"ANON set={bool(anon)} len={len(anon)}")
    if not url:
        print("NG: SUPABASE_URL missing")
        return 2
    host = urlparse(url).hostname or ""
    try:
        socket.getaddrinfo(host, 443)
        print("DNS: OK")
    except socket.gaierror as e:
        print(f"DNS: NG ({e}) — プロジェクト削除/休止の可能性。Dashboard で新規作成または Restore")
        return 3
    token = key or anon
    if not token:
        print("NG: no API key")
        return 2
    req = urllib.request.Request(
        url + "/rest/v1/comments?select=comment_id&limit=1",
        headers={"apikey": token, "Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            print(f"REST comments: HTTP {r.status}")
    except urllib.error.HTTPError as e:
        print(f"REST comments: HTTP {e.code} {e.read()[:120]!r}")
        return 4
    except Exception as e:
        print(f"REST comments: ERR {e}")
        return 4

    # knowledge tables
    for table in ("knowledge_sources", "knowledge_chunks"):
        req2 = urllib.request.Request(
            url + f"/rest/v1/{table}?select=id&limit=1",
            headers={"apikey": token, "Authorization": f"Bearer {token}"},
        )
        try:
            with urllib.request.urlopen(req2, timeout=20) as r:
                print(f"REST {table}: HTTP {r.status}")
        except urllib.error.HTTPError as e:
            print(f"REST {table}: HTTP {e.code} — schema.sql 未適用の可能性")
    print("OK: reachable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
