#!/usr/bin/env python3
"""メール要対応 triage → Slack #consult（返信／見送り／Todoist）.

  Block Kit action_id → consult-action（業者返信・物件ゲートと同型）
  見送りが続く送信者は sync_meta mail_action_skip_mute で Slack 再掲除外。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_mail_action_slack_post.py --from-triage --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_mail_action_slack_post.py --from-triage
  ~/selenium_env/venv/bin/python scripts/jarvis_mail_action_slack_post.py --id gha-xxxx

正本: docs/Jarvis_メール要対応_Slack操作_20261019.md
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
MUTE_META_KEY = "mail_action_skip_mute"
DEFAULT_CONSULT_CHANNEL = "C0C7R0UF3MM"
DEFAULT_MUTE_THRESHOLD = 2

# Slack 再掲前の軽いノイズ除外（見送り学習の前段・GenMail/night_triage と同趣旨）
NOISE_SUBJECT_RE = re.compile(
    r"(newsletter|キャンペーン|セール|配信停止|unsubscribe|"
    r"お知らせ\]|定期預金|ポイント付与|クーポン|広告|"
    r"プライバシーポリシー|利用規約.*(改訂|変更)|改訂のお知らせ)",
    re.I,
)

MA_ACTION_IDS = {
    "reply": "mail_action_reply",
    "skip": "mail_action_skip",
    "todoist": "mail_action_todoist",
}


def now_iso() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S%z")


def _bot_token() -> str:
    return (os.environ.get("SLACK_BOT_TOKEN") or "").strip()


def _webhook_consult() -> str:
    return (
        (os.environ.get("SLACK_WEBHOOK_AI_TEAM_CONSULT") or "").strip()
        or (os.environ.get("SLACK_WEBHOOK_AI_TEAM_REPORT") or "").strip()
    )


def _consult_channel() -> str:
    return (
        (os.environ.get("SLACK_CONSULT_CHANNEL_ID") or "").strip()
        or DEFAULT_CONSULT_CHANNEL
    )


def _action_secret() -> str:
    return (
        (os.environ.get("MAIL_ACTION_TOKEN") or "").strip()
        or (os.environ.get("PROPERTY_GATE_ACTION_TOKEN") or "").strip()
    )


def _dashboard_base() -> str:
    return (
        (os.environ.get("JARVIS_DASHBOARD_URL") or "").strip().rstrip("/")
        or "https://jarvis-dashboard-amber.vercel.app"
    )


def ma_sig(triage_id: str, action: str) -> str:
    secret = _action_secret()
    if not secret:
        return "nosig"
    dig = hmac.new(
        secret.encode("utf-8"),
        f"ma:{triage_id}:{action}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return dig[:10]


def ma_url(triage_id: str, action: str) -> str:
    return f"{_dashboard_base()}/api/g/ma/{action}/{triage_id}?s={ma_sig(triage_id, action)}"


def mute_key(from_email: str) -> str | None:
    e = (from_email or "").strip().lower()
    if not e or "@" not in e:
        return None
    return f"from:{e}"


def load_mute_registry(sb: Any) -> dict[str, Any]:
    th = int(
        os.environ.get("JARVIS_MAIL_ACTION_MUTE_THRESHOLD") or DEFAULT_MUTE_THRESHOLD
    )
    base = {"threshold": max(1, th), "entries": {}}
    try:
        r = (
            sb.table("sync_meta")
            .select("value")
            .eq("key", MUTE_META_KEY)
            .limit(1)
            .execute()
        )
        rows = r.data or []
        if not rows:
            return base
        raw = rows[0].get("value")
        if isinstance(raw, str) and raw.strip():
            obj = json.loads(raw)
        elif isinstance(raw, dict):
            obj = raw
        else:
            return base
        entries = obj.get("entries") if isinstance(obj.get("entries"), dict) else {}
        t = int(obj.get("threshold") or th)
        return {"threshold": max(1, t), "entries": entries}
    except Exception as e:
        print(f"# mute registry load skip: {e}", file=sys.stderr)
        return base


def is_muted(reg: dict[str, Any], from_email: str) -> bool:
    key = mute_key(from_email)
    if not key:
        return False
    ent = (reg.get("entries") or {}).get(key) or {}
    return bool(ent.get("muted"))


def _button_elements(tid: str, *, url_mode: bool) -> list[dict[str, Any]]:
    if url_mode:
        return [
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "返信する", "emoji": True},
                "style": "primary",
                "url": ma_url(tid, "reply"),
            },
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "見送り", "emoji": True},
                "style": "danger",
                "url": ma_url(tid, "skip"),
            },
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "Todoist追加", "emoji": True},
                "url": ma_url(tid, "todoist"),
            },
        ]
    return [
        {
            "type": "button",
            "text": {"type": "plain_text", "text": "返信する", "emoji": True},
            "style": "primary",
            "action_id": MA_ACTION_IDS["reply"],
            "value": f"ma:reply:{tid}",
        },
        {
            "type": "button",
            "text": {"type": "plain_text", "text": "見送り", "emoji": True},
            "style": "danger",
            "action_id": MA_ACTION_IDS["skip"],
            "value": f"ma:skip:{tid}",
        },
        {
            "type": "button",
            "text": {"type": "plain_text", "text": "Todoist追加", "emoji": True},
            "action_id": MA_ACTION_IDS["todoist"],
            "value": f"ma:todoist:{tid}",
        },
    ]


def build_payload(row: dict[str, Any], *, url_mode: bool) -> dict[str, Any]:
    tid = str(row.get("id") or "")
    partner = str(row.get("partner") or "").strip() or "—"
    subject = str(row.get("subject") or "(件名なし)").strip()
    from_email = str(row.get("from_email") or "").strip()
    body = str(row.get("original_body") or "").strip()
    summary = str(row.get("summary") or "").strip()
    draft = str(row.get("draft_text") or "").strip()
    lane = str(row.get("lane") or "")
    kind = str(row.get("kind") or "")
    account = str(row.get("account") or "admin")

    inbound = body[:1800] if body else summary[:500] or "(本文なし)"
    draft_preview = draft[:900] if draft else "（下書きなし — 返信でモーダル編集）"
    mode_note = "アプリ内ボタン" if not url_mode else "URLボタン"
    text = (
        f"【メール要対応】{partner}\n件名: {subject}\nFrom: {from_email}\n"
        f"lane={lane} kind={kind} account={account}"
    )
    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"メール要対応 — {partner[:40]}",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*件名:* {subject[:120]}\n"
                    f"*From:* `{from_email}` · lane=`{lane}` kind=`{kind}`"
                ),
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*受け取った文面*\n```{inbound}```",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*返信下書き*\n```{draft_preview}```",
            },
        },
        {
            "type": "actions",
            "block_id": f"ma_actions_{tid[:24]}",
            "elements": _button_elements(tid, url_mode=url_mode),
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        f"id=`{tid}` · {mode_note} · Dashboard `/mail/{tid}`\n"
                        f"予備URL: <{ma_url(tid, 'reply')}|返信> · "
                        f"<{ma_url(tid, 'skip')}|見送り> · "
                        f"<{ma_url(tid, 'todoist')}|Todoist>\n"
                        "Todoist＝メール返信以外の手配（電話・ポータル等）"
                    ),
                }
            ],
        },
    ]
    return {"text": text, "blocks": blocks, "username": "Jarvis メール要対応"}


def post_bot_message(payload: dict[str, Any], *, dry_run: bool) -> int:
    token = _bot_token()
    channel = _consult_channel()
    body = {
        "channel": channel,
        "text": payload.get("text") or "メール要対応",
        "blocks": payload.get("blocks") or [],
    }
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
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            j = json.loads(resp.read().decode("utf-8", errors="replace"))
            if not j.get("ok"):
                print(f"❌ chat.postMessage: {j.get('error')}", file=sys.stderr)
                return 1
            print(f"✅ Slack mail-action Bot OK channel={channel} ts={j.get('ts')}")
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
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            print(f"✅ Slack mail-action Webhook OK status={resp.status} body={body!r}")
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


def _sb():
    from supabase import create_client

    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_* 未設定")
    return create_client(url, key)


def fetch_one(tid: str) -> dict[str, Any] | None:
    sb = _sb()
    r = (
        sb.table("triage_items")
        .select(
            "id,status,subject,draft_text,original_body,from_email,partner,"
            "account,lane,kind,summary,payload,received_at"
        )
        .eq("id", tid)
        .limit(1)
        .execute()
    )
    rows = r.data or []
    return rows[0] if rows else None


def load_pending_from_supabase(*, limit: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    sb = _sb()
    mute = load_mute_registry(sb)
    r = (
        sb.table("triage_items")
        .select(
            "id,status,subject,draft_text,original_body,from_email,partner,"
            "account,lane,kind,summary,payload,received_at,priority"
        )
        .eq("status", "pending")
        .order("received_at", desc=True)
        .limit(max(limit * 4, 40))
        .execute()
    )
    out: list[dict[str, Any]] = []
    muted_n = 0
    skipped_vendor = 0
    skipped_skim = 0
    for row in r.data or []:
        tid = str(row.get("id") or "")
        if tid.startswith("re-vendor-"):
            skipped_vendor += 1
            continue
        pl = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        if pl.get("re_vendor_reply"):
            skipped_vendor += 1
            continue
        kind = str(row.get("kind") or "").lower()
        lane = str(row.get("lane") or "").lower()
        pri = str(row.get("priority") or "").lower()
        subj = str(row.get("subject") or "")
        # マーケ一斉は見送り学習に頼る前に投稿しない（返信義務なし）
        if NOISE_SUBJECT_RE.search(subj) and not (row.get("draft_text") or "").strip():
            skipped_skim += 1
            continue
        # 要返信っぽいものだけ（GenMail / night_triage の mail）
        if kind == "skim" and pri != "high" and not (row.get("draft_text") or "").strip():
            skipped_skim += 1
            continue
        if lane not in ("general", "partner", "") and kind not in ("mail", ""):
            # openchat 等は対象外
            if lane == "openchat":
                continue
        if is_muted(mute, str(row.get("from_email") or "")):
            muted_n += 1
            continue
        if pl.get("slack_ma_posted_at") and not os.environ.get(
            "JARVIS_MAIL_ACTION_REPOST"
        ):
            continue
        out.append(row)
        if len(out) >= limit:
            break
    stats = {
        "muted": muted_n,
        "vendor_skip": skipped_vendor,
        "skim_skip": skipped_skim,
        "mute_entries": len(mute.get("entries") or {}),
    }
    return out, stats


def mark_posted(sb: Any, tid: str) -> None:
    try:
        r = (
            sb.table("triage_items")
            .select("payload")
            .eq("id", tid)
            .limit(1)
            .execute()
        )
        rows = r.data or []
        if not rows:
            return
        pl = rows[0].get("payload") if isinstance(rows[0].get("payload"), dict) else {}
        pl = dict(pl)
        pl["slack_ma_posted_at"] = now_iso()
        sb.table("triage_items").update(
            {"payload": pl, "updated_at": now_iso()}
        ).eq("id", tid).execute()
    except Exception as e:
        print(f"# mark posted skip {tid}: {e}", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(description="メール要対応 → Slack #consult")
    ap.add_argument("--from-triage", action="store_true")
    ap.add_argument("--id", type=str, default="")
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--url-buttons", action="store_true")
    ap.add_argument("--webhook", action="store_true", help="Bot を使わず Webhook")
    args = ap.parse_args()

    if os.environ.get("JARVIS_MAIL_ACTION_SLACK_DISABLE", "").strip() in {
        "1",
        "true",
        "yes",
    }:
        print("disabled via JARVIS_MAIL_ACTION_SLACK_DISABLE=1")
        return 0

    url_mode = bool(args.url_buttons)
    rows: list[dict[str, Any]] = []
    stats: dict[str, Any] = {}
    if args.id:
        one = fetch_one(args.id.strip())
        if not one:
            print(f"not found: {args.id}", file=sys.stderr)
            return 2
        rows = [one]
    elif args.from_triage:
        rows, stats = load_pending_from_supabase(limit=args.limit)
    else:
        ap.print_help()
        return 2

    print(
        f"📎 mail action slack — candidates={len(rows)} "
        f"mode={'url' if url_mode else 'interactive'} "
        f"via={'webhook' if args.webhook or not _bot_token() else 'bot'} "
        f"stats={stats}"
    )
    if not rows:
        print("投稿対象なし（pending 要対応が無い／ミュート除外）")
        return 0

    sb = None if args.dry_run else _sb()
    posted = 0
    for row in rows:
        tid = str(row.get("id") or "")
        payload = build_payload(row, url_mode=url_mode)
        rc = post_slack(payload, dry_run=args.dry_run, force_webhook=args.webhook)
        if rc != 0:
            return rc
        posted += 1
        if sb and not args.dry_run:
            mark_posted(sb, tid)
    print(f"# posted={posted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
