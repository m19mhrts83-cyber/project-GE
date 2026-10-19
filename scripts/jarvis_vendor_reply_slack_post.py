#!/usr/bin/env python3
"""地場業者返信 triage → Slack #consult に草案＋操作ボタン（URL）。

調査結論（Slack App）:
  Block Kit の button に url= を付ければ Incoming Webhook だけで
  「送信／編集／返信なし」が実装できる（Interactivity URL 不要）。
  モーダル編集は Bot Token + views.open が必要 → 本線は署名付き HTML 編集ページ。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_vendor_reply_slack_post.py --from-triage
  ~/selenium_env/venv/bin/python scripts/jarvis_vendor_reply_slack_post.py --id re-vendor-xxxx --dry-run

正本: docs/KURASHIFT_業者返信_Slack操作_20261019.md
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]


def _dashboard() -> str:
    return (
        (os.environ.get("JARVIS_DASHBOARD_URL") or "").strip().rstrip("/")
        or "https://jarvis-dashboard-amber.vercel.app"
    )


def _action_secret() -> str:
    return (
        (os.environ.get("VENDOR_REPLY_ACTION_TOKEN") or "").strip()
        or (os.environ.get("PROPERTY_GATE_ACTION_TOKEN") or "").strip()
    )


def vr_sig(triage_id: str, action: str) -> str:
    secret = _action_secret()
    if not secret:
        return ""
    return hmac.new(
        secret.encode("utf-8"),
        f"vr:{triage_id}:{action}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:10]


def vr_url(triage_id: str, action: str) -> str:
    s = vr_sig(triage_id, action)
    base = _dashboard()
    return f"{base}/api/g/vr/{action}/{triage_id}?s={s}"


def _webhook_consult() -> str:
    return (
        (os.environ.get("SLACK_WEBHOOK_AI_TEAM_CONSULT") or "").strip()
        or (os.environ.get("SLACK_WEBHOOK_AI_TEAM_REPORT") or "").strip()
    )


def truncate(s: str, n: int) -> str:
    s = (s or "").replace("\r\n", "\n").strip()
    if len(s) <= n:
        return s
    return s[: n - 1] + "…"


def build_payload(row: dict[str, Any]) -> dict[str, Any]:
    tid = str(row.get("id") or "")
    partner = str(row.get("partner") or row.get("payload", {}).get("vendor_name") or "業者")
    subject = str(row.get("subject") or "(件名なし)")
    inbound = truncate(str(row.get("original_body") or ""), 900)
    draft = truncate(str(row.get("draft_text") or ""), 900)
    vid = str((row.get("payload") or {}).get("vendor_id") or "")
    prop = (row.get("payload") or {}).get("has_property_signal")
    prop_s = "物件シグナルあり" if prop else "質問／その他"

    send_u = vr_url(tid, "send")
    edit_u = vr_url(tid, "edit")
    skip_u = vr_url(tid, "skip")

    text = (
        f"【業者返信】{partner}\n"
        f"件名: {subject}\n"
        f"{prop_s}"
        + (f" · {vid}" if vid else "")
        + f"\n送信: {send_u}\n編集: {edit_u}\n返信なし: {skip_u}"
    )

    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"業者返信 — {partner[:40]}", "emoji": True},
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*件名*\n{subject}\n*{prop_s}*"
                + (f" · `{vid}`" if vid else ""),
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*受け取った文面*\n```{inbound or '(本文なし)'}```",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*返信草案*\n```{draft or '(草案なし)'}```",
            },
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "この草案で送信", "emoji": True},
                    "style": "primary",
                    "url": send_u,
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "編集して送信", "emoji": True},
                    "url": edit_u,
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "返信なし", "emoji": True},
                    "url": skip_u,
                },
            ],
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"id=`{tid}` · Dashboard `/mail/{tid}` · YAML catchup は Mac",
                }
            ],
        },
    ]
    return {"text": text, "blocks": blocks, "username": "Jarvis 業者返信"}


def post_webhook(payload: dict[str, Any], *, dry_run: bool) -> int:
    url = _webhook_consult()
    if dry_run:
        print("# dry-run Slack payload")
        print(json.dumps(payload, ensure_ascii=False, indent=2)[:4000])
        return 0
    if not url:
        print("❌ SLACK_WEBHOOK_AI_TEAM_CONSULT（or REPORT）未設定", file=sys.stderr)
        return 2
    if not _action_secret():
        print(
            "❌ PROPERTY_GATE_ACTION_TOKEN（または VENDOR_REPLY_ACTION_TOKEN）未設定",
            file=sys.stderr,
        )
        return 2
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            print(f"✅ Slack vendor-reply OK status={resp.status} body={body!r}")
            return 0
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        print(f"❌ Slack HTTP {e.code}: {err}", file=sys.stderr)
        return 1


def load_pending_from_supabase(*, limit: int) -> list[dict[str, Any]]:
    from supabase import create_client

    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_* 未設定")
    sb = create_client(url, key)
    r = (
        sb.table("triage_items")
        .select(
            "id,status,subject,draft_text,original_body,from_email,partner,payload,updated_at"
        )
        .eq("status", "pending")
        .order("updated_at", desc=True)
        .limit(max(limit * 5, 50))
        .execute()
    )
    rows: list[dict[str, Any]] = []
    for x in r.data or []:
        pl = x.get("payload") or {}
        if not pl.get("re_vendor_reply"):
            continue
        if pl.get("slack_vr_posted_at"):
            continue
        rows.append(x)
        if len(rows) >= limit:
            break
    return rows


def mark_posted(ids: list[str]) -> None:
    from datetime import datetime, timezone

    from supabase import create_client

    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key or not ids:
        return
    sb = create_client(url, key)
    now = datetime.now(timezone.utc).isoformat()
    for rid in ids:
        r = (
            sb.table("triage_items")
            .select("payload")
            .eq("id", rid)
            .maybe_single()
            .execute()
        )
        pl = dict((r.data or {}).get("payload") or {})
        pl["slack_vr_posted_at"] = now
        sb.table("triage_items").update(
            {"payload": pl, "updated_at": now}
        ).eq("id", rid).execute()


def fetch_one(tid: str) -> dict[str, Any] | None:
    from supabase import create_client

    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_* 未設定")
    sb = create_client(url, key)
    r = (
        sb.table("triage_items")
        .select(
            "id,status,subject,draft_text,original_body,from_email,partner,payload"
        )
        .eq("id", tid)
        .maybe_single()
        .execute()
    )
    return r.data


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from-triage", action="store_true", help="pending の業者返信を投稿")
    ap.add_argument("--id", help="特定 triage id を1件投稿")
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-mark", action="store_true", help="slack_vr_posted_at を書かない")
    args = ap.parse_args()

    if os.environ.get("JARVIS_VENDOR_REPLY_SLACK_DISABLE", "").strip() in {
        "1",
        "true",
        "yes",
    }:
        print("disabled via JARVIS_VENDOR_REPLY_SLACK_DISABLE=1")
        return 0

    rows: list[dict[str, Any]] = []
    if args.id:
        one = fetch_one(args.id.strip())
        if not one:
            print(f"not found: {args.id}", file=sys.stderr)
            return 2
        rows = [one]
    elif args.from_triage:
        rows = load_pending_from_supabase(limit=args.limit)
    else:
        ap.print_help()
        return 2

    print(f"📎 vendor reply slack — candidates={len(rows)}")
    posted: list[str] = []
    for row in rows:
        tid = str(row.get("id") or "")
        payload = build_payload(row)
        rc = post_webhook(payload, dry_run=args.dry_run)
        if rc != 0:
            return rc
        print(f"  - posted {tid} {row.get('partner')}")
        posted.append(tid)

    if posted and not args.dry_run and not args.no_mark:
        mark_posted(posted)
        print(f"# marked slack_vr_posted_at n={len(posted)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
