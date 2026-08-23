#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Supabase 接続・スキーマ健全性チェック（秘密は表示しない）

Free 休止（INACTIVE）だとホストの DNS が消え、週次スクレイプ後に落ちる。
DNS リトライ・（任意）Management API での Restore・心拍までをここで行う。

例:
  python3 supabase_healthcheck.py
  python3 supabase_healthcheck.py --touch
  python3 supabase_healthcheck.py --touch --restore-if-paused
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

SCRIPT_DIR = Path(__file__).resolve().parent
MANAGEMENT_API = "https://api.supabase.com/v1"


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


def project_ref_from_url(url: str) -> str:
    host = urlparse(url).hostname or ""
    if host.endswith(".supabase.co"):
        return host.split(".", 1)[0]
    return (os.environ.get("SUPABASE_PROJECT_REF") or "").strip()


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
    except (urllib.error.URLError, TimeoutError, socket.timeout, OSError) as e:
        return 0, str(e).encode("utf-8", errors="replace")


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
    except (urllib.error.URLError, TimeoutError, socket.timeout, OSError) as e:
        return 0, str(e)[:200]


def dns_ok(host: str) -> bool:
    if not host:
        return False
    try:
        socket.getaddrinfo(host, 443)
        return True
    except socket.gaierror:
        return False


def wait_dns(host: str, attempts: int, wait_sec: float) -> bool:
    for i in range(1, max(1, attempts) + 1):
        if dns_ok(host):
            if i > 1:
                print(f"DNS: OK (retry {i}/{attempts})")
            else:
                print("DNS: OK")
            return True
        print(f"DNS: NG ({i}/{attempts}) — 休止復帰待ち {wait_sec:.0f}s")
        if i < attempts:
            time.sleep(wait_sec)
    return False


def management_get_status(ref: str, access_token: str) -> str:
    req = urllib.request.Request(
        f"{MANAGEMENT_API}/projects/{ref}",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8", errors="replace") or "{}")
        return str(data.get("status") or "")
    except Exception as e:
        print(f"Management GET status: skipped ({type(e).__name__})")
        return ""


def try_restore_project(ref: str, access_token: str) -> bool:
    """Paused プロジェクトを Restore。トークン値は出さない。"""
    if not ref or not access_token:
        return False
    status = management_get_status(ref, access_token)
    if status:
        print(f"Management status: {status}")
    if status in ("ACTIVE_HEALTHY", "COMING_UP", "RESTORING"):
        return True
    req = urllib.request.Request(
        f"{MANAGEMENT_API}/projects/{ref}/restore",
        data=b"{}",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            print(f"Restore requested: HTTP {r.status}")
            return True
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:180]
        # 既に起動中・復元中は成功扱い
        if e.code in (200, 201, 409):
            print(f"Restore HTTP {e.code} (already in progress)")
            return True
        print(f"Restore HTTP {e.code} {body}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"Restore failed: {type(e).__name__}", file=sys.stderr)
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--touch",
        action="store_true",
        help="jarvis_heartbeat を upsert（Free 休止防止・週次必須）",
    )
    ap.add_argument("--note", default="westudy-weekly", help="心拍 note")
    ap.add_argument(
        "--restore-if-paused",
        action="store_true",
        help="DNS 失敗時に SUPABASE_ACCESS_TOKEN があれば Restore して待つ",
    )
    ap.add_argument(
        "--retries",
        type=int,
        default=int(os.environ.get("SUPABASE_HEALTH_RETRIES") or "16"),
        help="DNS/REST リトライ回数（既定 16）",
    )
    ap.add_argument(
        "--retry-wait",
        type=float,
        default=float(os.environ.get("SUPABASE_HEALTH_RETRY_WAIT") or "15"),
        help="リトライ間隔秒（既定 15）",
    )
    args = ap.parse_args()

    load_env()
    url = (os.environ.get("SUPABASE_URL") or "").strip().rstrip("/")
    key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    anon = (os.environ.get("SUPABASE_ANON_KEY") or "").strip()
    access = (os.environ.get("SUPABASE_ACCESS_TOKEN") or "").strip()
    print(f"SUPABASE_URL set={bool(url)} host={urlparse(url).hostname or '-'}")
    print(f"SERVICE_ROLE set={bool(key)} len={len(key)}")
    print(f"ANON set={bool(anon)} len={len(anon)}")
    print(f"ACCESS_TOKEN set={bool(access)}")
    if not url:
        print("NG: SUPABASE_URL missing")
        print("SUMMARY: 疎通=NG 心拍=skipped reason=no_url")
        return 2
    host = urlparse(url).hostname or ""
    ref = project_ref_from_url(url)

    if not dns_ok(host):
        print("DNS: NG — プロジェクト休止の可能性")
        if args.restore_if_paused:
            if access:
                print("Restore を試みます（Management API）")
                if not try_restore_project(ref, access):
                    print("SUMMARY: 疎通=NG 心拍=skipped reason=restore_failed")
                    return 3
            else:
                print(
                    "Restore スキップ: SUPABASE_ACCESS_TOKEN 未設定。"
                    "Dashboard で Restore するか、日次心拍で休止を防ぐ。"
                )
        if not wait_dns(host, args.retries, args.retry_wait):
            print(f"DNS: NG after {args.retries} retries — Dashboard で Restore")
            print("SUMMARY: 疎通=NG 心拍=skipped reason=dns")
            return 3
    else:
        print("DNS: OK")

    token = key or anon
    if not token:
        print("NG: no API key")
        print("SUMMARY: 疎通=NG 心拍=skipped reason=no_key")
        return 2

    status = 0
    last_err = ""
    for i in range(1, max(1, args.retries) + 1):
        status, raw = rest_get(url, token, "/rest/v1/comments?select=comment_id&limit=1")
        if 200 <= status < 300:
            print(f"REST comments: HTTP {status}")
            break
        last_err = raw.decode("utf-8", errors="replace")[:120] if raw else ""
        print(f"REST comments: HTTP {status or 'err'} ({i}/{args.retries}) {last_err}")
        if i < args.retries:
            time.sleep(args.retry_wait)
    else:
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
