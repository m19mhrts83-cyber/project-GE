#!/usr/bin/env python3
"""地場業者返信 triage → Slack #consult に草案＋操作ボタン。

本線（コスパ優先・2026-10-19）:
  Block Kit の action_id ボタン → 既存 consult-action（SLACK_SIGNING_SECRET）
  が block_actions を受け、アプリ内で送信／スキップ／編集モーダル。
  投稿は Bot chat.postMessage（SLACK_BOT_TOKEN）優先。無ければ Incoming Webhook。

フォールバック:
  --url-buttons … 署名付き URL ボタン（ブラウザ。Interactivity 不要）
  context に URL も常時残す

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

DEFAULT_CONSULT_CHANNEL = "C0C7R0UF3MM"

VR_ACTION_IDS = {
    "send": "vendor_reply_send",
    "skip": "vendor_reply_skip",
    "edit": "vendor_reply_edit",
}


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


def _bot_token() -> str:
    return (os.environ.get("SLACK_BOT_TOKEN") or "").strip()


def _consult_channel() -> str:
    return (
        (os.environ.get("SLACK_CONSULT_CHANNEL_ID") or "").strip()
        or DEFAULT_CONSULT_CHANNEL
    )


def truncate(s: str, n: int) -> str:
    s = (s or "").replace("\r\n", "\n").strip()
    if len(s) <= n:
        return s
    return s[: n - 1] + "…"


def _button_elements(tid: str, *, url_mode: bool) -> list[dict[str, Any]]:
    send_u = vr_url(tid, "send")
    edit_u = vr_url(tid, "edit")
    skip_u = vr_url(tid, "skip")
    if url_mode:
        return [
            {"type": "button", "text": {"type": "plain_text", "text": "この草案で送信", "emoji": True}, "style": "primary", "url": send_u},
            {"type": "button", "text": {"type": "plain_text", "text": "編集して送信", "emoji": True}, "url": edit_u},
            {"type": "button", "text": {"type": "plain_text", "text": "返信なし", "emoji": True}, "url": skip_u},
        ]
    return [
        {"type": "button", "text": {"type": "plain_text", "text": "この草案で送信", "emoji": True}, "style": "primary", "action_id": VR_ACTION_IDS["send"], "value": f"vr:send:{tid}"},
        {"type": "button", "text": {"type": "plain_text", "text": "編集して送信", "emoji": True}, "action_id": VR_ACTION_IDS["edit"], "value": f"vr:edit:{tid}"},
        {"type": "button", "text": {"type": "plain_text", "text": "返信なし", "emoji": True}, "action_id": VR_ACTION_IDS["skip"], "value": f"vr:skip:{tid}"},
    ]


def build_payload(row: dict[str, Any], *, url_mode: bool) -> dict[str, Any]:
    tid = str(row.get("id") or "")
    partner = str(row.get("partner") or (row.get("payload") or {}).get("vendor_name") or "業者")
    subject = str(row.get("subject") or "(件名なし)")
    inbound = truncate(str(row.get("original_body") or ""), 900)
    draft = truncate(str(row.get("draft_text") or ""), 900)
    vid = str((row.get("payload") or {}).get("vendor_id") or "")
    prop = (row.get("payload") or {}).get("has_property_signal")
    prop_s = "物件シグナルあり" if prop else "質問／その他"
    send_u = vr_url(tid, "send")
    edit_u = vr_url(tid, "edit")
    skip_u = vr_url(tid, "skip")
    mode_note = "アプリ内ボタン（Interactivity）" if not url_mode else "URLボタン（ブラウザ）"
    text = (
        f"【業者返信】{partner}\n件名: {subject}\n{prop_s}"
        + (f" · {vid}" if vid else "")
        + f"\n[{mode_note}]\n送信: {send_u}\n編集: {edit_u}\n返信なし: {skip_u}"
    )
    blocks: list[dict[str, Any]] = [
        {"type": "header", "text": {"type": "plain_text", "text": f"業者返信 — {partner[:40]}", "emoji": True}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*件名*\n{subject}\n*{prop_s}*" + (f" · `{vid}`" if vid else "")}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*受け取った文面*\n```{inbound or '(本文なし)'}```"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*返信草案*\n```{draft or '(草案なし)'}```"}},
        {"type": "actions", "block_id": f"vr_actions_{tid[:24]}", "elements": _button_elements(tid, url_mode=url_mode)},
        {"type": "context", "elements": [{"type": "mrkdwn", "text": (
            f"id=`{tid}` · {mode_note} · Dashboard `/mail/{tid}`\n"
            f"予備URL: <{send_u}|送信> · <{edit_u}|編集> · <{skip_u}|返信なし>"
        )}]},
    ]
    return {"text": text, "blocks": blocks, "username": "Jarvis 業者返信"}


def post_bot_message(payload: dict[str, Any], *, dry_run: bool) -> int:
    token = _bot_token()
    channel = _consult_channel()
    body = {"channel": channel, "text": payload.get("text") or "業者返信", "blocks": payload.get("blocks") or []}
    if dry_run:
        print("# dry-run chat.postMessage")
        print(json.dumps(body, ensure_ascii=False, indent=2)[:4000])
        return 0
    if not token:
        return 3
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        "https://slack.com/api/chat.postMessage",
        data=data,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            j = json.loads(resp.read().decode("utf-8", errors="replace"))
            if not j.get("ok"):
                print(f"❌ chat.postMessage: {j.get('error')}", file=sys.stderr)
                return 1
            print(f"✅ Slack vendor-reply Bot OK channel={channel} ts={j.get('ts')}")
            return 0
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        print(f"❌ Slack HTTP {e.code}: {err}", file=sys.stderr)
        return 1


def post_webhook(payload: dict[str, Any], *, dry_run: bool) -> int:
    url = _webhook_consult()
    if dry_run:
        print("# dry-run Slack webhook payload")
        print(json.dumps(payload, ensure_ascii=False, indent=2)[:4000])
        return 0
    if not url:
        print("❌ SLACK_WEBHOOK_AI_TEAM_CONSULT（or REPORT）未設定", file=sys.stderr)
        return 2
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            print(f"✅ Slack vendor-reply Webhook OK status={resp.status} body={body!r}")
            return 0
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        print(f"❌ Slack HTTP {e.code}: {err}", file=sys.stderr)
        return 1


def post_slack(payload: dict[str, Any], *, dry_run: bool, force_webhook: bool) -> int:
    if not _action_secret():
        print("⚠️ PROPERTY_GATE_ACTION_TOKEN 未設定（予備 URL 署名なし）", file=sys.stderr)
    use_bot = bool(_bot_token()) and not force_webhook
    if use_bot:
        rc = post_bot_message(payload, dry_run=dry_run)
        if rc == 3:
            return post_webhook(payload, dry_run=dry_run)
        return rc
    return post_webhook(payload, dry_run=dry_run)


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
    ap.add_argument("--url-buttons", action="store_true", help="署名 URL ボタン（ブラウザ）。既定は action_id アプリ内")
    ap.add_argument("--webhook", action="store_true", help="Bot があっても Incoming Webhook で投稿")
    args = ap.parse_args()

    if os.environ.get("JARVIS_VENDOR_REPLY_SLACK_DISABLE", "").strip() in {"1", "true", "yes"}:
        print("disabled via JARVIS_VENDOR_REPLY_SLACK_DISABLE=1")
        return 0

    url_mode = bool(args.url_buttons)
    if (
        not url_mode
        and not _bot_token()
        and not (os.environ.get("SLACK_SIGNING_SECRET") or "").strip()
    ):
        print(
            "⚠️ SLACK_BOT_TOKEN / SLACK_SIGNING_SECRET なし → URL ボタンにフォールバック",
            file=sys.stderr,
        )
        url_mode = True

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

    print(
        f"📎 vendor reply slack — candidates={len(rows)} "
        f"mode={'url' if url_mode else 'interactive'} "
        f"via={'webhook' if args.webhook or not _bot_token() else 'bot'}"
    )
    posted: list[str] = []
    for row in rows:
        tid = str(row.get("id") or "")
        payload = build_payload(row, url_mode=url_mode)
        rc = post_slack(payload, dry_run=args.dry_run, force_webhook=args.webhook)
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
