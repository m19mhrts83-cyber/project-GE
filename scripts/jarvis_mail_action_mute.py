#!/usr/bin/env python3
"""メール要対応 — 見送り学習（mail_action_skip_mute）の list / unmute / health.

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_mail_action_mute.py --list
  ~/selenium_env/venv/bin/python scripts/jarvis_mail_action_mute.py --unmute 'from:addr@example.com'
  ~/selenium_env/venv/bin/python scripts/jarvis_mail_action_mute.py --health
  ~/selenium_env/venv/bin/python scripts/jarvis_mail_action_mute.py --health --notify-ops

正本: docs/Jarvis_メール要対応_Slack操作_20261019.md
社員: 116 メール要対応係
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
MUTE_META_KEY = "mail_action_skip_mute"
JST = timezone(timedelta(hours=9))


def _sb() -> tuple[str, str] | None:
    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip().rstrip("/")
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        return None
    return url, key


def load_registry() -> dict[str, Any]:
    creds = _sb()
    if not creds:
        return {"threshold": 2, "entries": {}}
    url, key = creds
    req = urllib.request.Request(
        f"{url}/rest/v1/sync_meta?key=eq.{MUTE_META_KEY}&select=value",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            rows = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"# load failed: {e}", file=sys.stderr)
        return {"threshold": 2, "entries": {}}
    if not rows:
        return {"threshold": 2, "entries": {}}
    raw = rows[0].get("value")
    if isinstance(raw, str) and raw.strip():
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            return {"threshold": 2, "entries": {}}
    elif isinstance(raw, dict):
        obj = raw
    else:
        return {"threshold": 2, "entries": {}}
    entries = obj.get("entries") if isinstance(obj.get("entries"), dict) else {}
    th = int(obj.get("threshold") or 2)
    return {"threshold": th if th > 0 else 2, "entries": entries}


def save_registry(reg: dict[str, Any], *, dry_run: bool) -> None:
    if dry_run:
        print("# dry-run: would save registry")
        return
    creds = _sb()
    if not creds:
        raise SystemExit("JARVIS_SUPABASE_URL / SERVICE_ROLE_KEY が必要です")
    url, key = creds
    now = datetime.now(timezone.utc).isoformat()
    body = json.dumps(
        {"key": MUTE_META_KEY, "value": json.dumps(reg, ensure_ascii=False), "updated_at": now}
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{url}/rest/v1/sync_meta",
        data=body,
        method="POST",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        r.read()


def normalize_key(raw: str) -> str:
    s = (raw or "").strip().lower()
    if s.startswith("from:"):
        return s
    if "@" in s:
        return f"from:{s}"
    raise SystemExit(f"キー形式が不正です: {raw!r}（from:addr@… または email）")


def cmd_list(reg: dict[str, Any]) -> int:
    entries: dict[str, Any] = reg.get("entries") or {}
    print(f"📎 mail_action_skip_mute  threshold={reg.get('threshold')}  entries={len(entries)}")
    if not entries:
        print("（なし）")
        return 0
    for k, v in sorted(entries.items(), key=lambda x: str(x[0])):
        muted = bool((v or {}).get("muted"))
        skips = int((v or {}).get("skips") or 0)
        last = (v or {}).get("last_at") or ""
        subj = ((v or {}).get("last_subject") or "")[:60]
        flag = "MUTED" if muted else f"streak={skips}"
        print(f"- {k}  {flag}  last={last}  {subj}")
    return 0


def cmd_unmute(reg: dict[str, Any], key: str, *, dry_run: bool) -> int:
    k = normalize_key(key)
    entries: dict[str, Any] = dict(reg.get("entries") or {})
    if k not in entries:
        print(f"見つかりません: {k}")
        return 1
    prev = dict(entries[k] or {})
    entries[k] = {
        **prev,
        "muted": False,
        "skips": 0,
        "last_at": datetime.now(JST).isoformat(timespec="seconds"),
    }
    reg["entries"] = entries
    save_registry(reg, dry_run=dry_run)
    print(f"✅ unmuted: {k}" + (" (dry-run)" if dry_run else ""))
    return 0


def _pending_count() -> int | None:
    creds = _sb()
    if not creds:
        return None
    url, key = creds
    q = (
        f"{url}/rest/v1/triage_items?status=eq.pending"
        f"&select=id&limit=1"
    )
    # count via Prefer
    req = urllib.request.Request(
        f"{url}/rest/v1/triage_items?status=eq.pending&select=id",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Prefer": "count=exact",
            "Range": "0-0",
        },
        method="HEAD",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            cr = r.headers.get("content-range") or ""
            # 0-0/123
            if "/" in cr:
                total = cr.split("/")[-1]
                if total.isdigit():
                    return int(total)
    except Exception:
        pass
    # fallback GET
    req2 = urllib.request.Request(
        f"{url}/rest/v1/triage_items?status=eq.pending&select=id&limit=500",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
    )
    try:
        with urllib.request.urlopen(req2, timeout=30) as r:
            rows = json.loads(r.read().decode("utf-8"))
            return len(rows)
    except Exception as e:
        print(f"# pending count failed: {e}", file=sys.stderr)
        return None


def _parse_from_addr(raw: str) -> str:
    s = (raw or "").strip().lower()
    m = re.search(r"<([^>]+)>", s)
    return (m.group(1) if m else s).strip().lower()


def cmd_close_muted_pending(reg: dict[str, Any], *, dry_run: bool) -> int:
    """ミュート済み From の残 pending を skipped（Dashboard 未読から消す）。"""
    creds = _sb()
    if not creds:
        raise SystemExit("JARVIS_SUPABASE_URL / SERVICE_ROLE_KEY が必要です")
    url, key = creds
    muted_addrs: set[str] = set()
    for k, v in (reg.get("entries") or {}).items():
        if not (v or {}).get("muted"):
            continue
        if str(k).startswith("from:"):
            muted_addrs.add(str(k)[5:].lower())
    if not muted_addrs:
        print("📎 close-muted-pending: ミュート送信者なし")
        return 0
    req = urllib.request.Request(
        f"{url}/rest/v1/triage_items?status=eq.pending&kind=neq.activity"
        f"&select=id,from_email,payload&limit=500",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
    )
    with urllib.request.urlopen(req, timeout=45) as r:
        rows = json.loads(r.read().decode("utf-8"))
    now = datetime.now(timezone.utc).isoformat()
    closed = 0
    for row in rows or []:
        addr = _parse_from_addr(str(row.get("from_email") or ""))
        if addr not in muted_addrs:
            continue
        rid = str(row.get("id") or "")
        if not rid:
            continue
        pl = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        pl = dict(pl)
        pl["mail_skip_mute_auto"] = {
            "at": now,
            "source": "mute_cli_close",
            "key": f"from:{addr}",
        }
        body = json.dumps(
            {"status": "skipped", "payload": pl, "updated_at": now},
            ensure_ascii=False,
        ).encode("utf-8")
        if dry_run:
            print(f"# dry-run would skip {rid}  from={addr}")
            closed += 1
            continue
        ureq = urllib.request.Request(
            f"{url}/rest/v1/triage_items?id=eq.{urllib.parse.quote(rid, safe='')}",
            data=body,
            method="PATCH",
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
        )
        try:
            with urllib.request.urlopen(ureq, timeout=30) as r:
                r.read()
            closed += 1
        except Exception as e:
            print(f"# skip failed {rid}: {e}", file=sys.stderr)
    print(
        f"📎 close-muted-pending: muted_senders={len(muted_addrs)} closed={closed}"
        + (" (dry-run)" if dry_run else "")
    )
    return 0


def cmd_health(reg: dict[str, Any], *, notify_ops: bool) -> int:
    muted_n = sum(1 for v in (reg.get("entries") or {}).values() if (v or {}).get("muted"))
    pending = _pending_count()
    issues: list[str] = []
    if pending is not None and pending >= 50:
        issues.append(f"pending triage が多い: {pending}")
    if muted_n >= 20:
        issues.append(f"ミュート送信者が多い: {muted_n}")
    print(
        f"📎 116 メール要対応ヘルス"
        f"  pending={pending if pending is not None else '?'}"
        f"  muted={muted_n}"
        f"  threshold={reg.get('threshold')}"
    )
    if not issues:
        print("判定: OK")
        return 0
    for i in issues:
        print(f"⚠️ {i}")
    if notify_ops:
        text = (
            "【ops】116 メール要対応 — 健全性\n"
            + "\n".join(f"・{i}" for i in issues)
            + "\n参考: scripts/jarvis_mail_action_mute.py --list"
        )
        post = REPO / "scripts" / "jarvis_slack_webhook_post.py"
        if post.is_file():
            subprocess.run(
                [
                    sys.executable,
                    str(post),
                    "--channel",
                    "ops",
                    "--text",
                    text,
                    "--username",
                    "116 メール要対応",
                ],
                cwd=str(REPO),
                check=False,
            )
        else:
            print("# notify skipped: jarvis_slack_webhook_post.py なし", file=sys.stderr)
    return 0 if not issues else 2


def main() -> int:
    ap = argparse.ArgumentParser(description="mail_action_skip_mute list/unmute/health")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--unmute", metavar="KEY", help="from:addr@… または email")
    ap.add_argument("--health", action="store_true")
    ap.add_argument(
        "--close-muted-pending",
        action="store_true",
        help="ミュート済み From の残 pending を skipped（Dashboard 未読から消す）",
    )
    ap.add_argument("--notify-ops", action="store_true", help="health 異常時 #ops")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not (args.list or args.unmute or args.health or args.close_muted_pending):
        ap.print_help()
        return 2
    reg = load_registry()
    rc = 0
    if args.list:
        rc = max(rc, cmd_list(reg))
    if args.unmute:
        rc = max(rc, cmd_unmute(reg, args.unmute, dry_run=args.dry_run))
    if args.close_muted_pending:
        rc = max(rc, cmd_close_muted_pending(reg, dry_run=args.dry_run))
    if args.health:
        rc = max(rc, cmd_health(reg, notify_ops=args.notify_ops))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
