#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""312 Slack Block Kit ヘルパー（起票／見送りボタン）.

Bot chat.postMessage 本線（action_id）／Webhook 時は URL ボタン。
署名: PROPERTY_GATE_ACTION_TOKEN（または TODOIST_*）。
提案ペイロードは base64url JSON（Vercel が state なしで create できる）。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

DEFAULT_CONSULT_CHANNEL = "C0C7R0UF3MM"
AGENT_USERNAME = "312 Todoist起票整理"

T312_ACTION_IDS = {
    "create": "todoist_312_create",
    "dismiss": "todoist_312_dismiss",
}


def _dashboard() -> str:
    return (
        (os.environ.get("JARVIS_DASHBOARD_URL") or "").strip().rstrip("/")
        or "https://jarvis-dashboard-amber.vercel.app"
    )


def _action_secret_name() -> str:
    for name in (
        "TODOIST_312_ACTION_TOKEN",
        "TODOIST_313_ACTION_TOKEN",
        "PROPERTY_GATE_ACTION_TOKEN",
        "MAIL_ACTION_TOKEN",
        "TODOIST_API_TOKEN",
    ):
        if (os.environ.get(name) or "").strip():
            return name
    return ""


def _action_secret() -> str:
    name = _action_secret_name()
    return (os.environ.get(name) or "").strip() if name else ""


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


def encode_proposal(it: dict[str, Any]) -> str:
    origin = str(it.get("origin") or "312")
    labels = ["SecondBrain", "quick"] if origin == "sb" else ["quick"]
    compact = {
        "n": int(it.get("n") or 0),
        "lane": str(it.get("lane") or "ai_raimo")[:40],
        "title": str(it.get("title") or "")[:200],
    }
    if it.get("summary"):
        compact["summary"] = str(it.get("summary"))[:240]
    if origin:
        compact["origin"] = origin[:40]
    if it.get("project_url"):
        compact["project_url"] = str(it.get("project_url"))[:300]
    compact["labels"] = labels
    raw = json.dumps(compact, ensure_ascii=False, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def t312_sig(action: str, payload_b64: str) -> str:
    secret = _action_secret()
    if not secret:
        return ""
    payload = f"t312:{action}:{payload_b64}"
    return hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:10]


def t312_button_value(action: str, it: dict[str, Any]) -> str:
    b64 = encode_proposal(it)
    s = t312_sig(action, b64)
    return f"t312:{action}:{b64}:{s}"


def t312_url(action: str, it: dict[str, Any]) -> str:
    b64 = encode_proposal(it)
    s = t312_sig(action, b64)
    n = int(it.get("n") or 0)
    return f"{_dashboard()}/api/g/t312/{action}/n{n}?p={b64}&s={s}"


def create_button(it: dict[str, Any], *, url_mode: bool) -> dict[str, Any]:
    n = int(it.get("n") or 0)
    label = f"#{n} 起票する" if n else "起票する"
    if url_mode:
        return {
            "type": "button",
            "text": {"type": "plain_text", "text": label[:24], "emoji": True},
            "style": "primary",
            "url": t312_url("create", it),
        }
    return {
        "type": "button",
        "text": {"type": "plain_text", "text": label[:24], "emoji": True},
        "style": "primary",
        "action_id": T312_ACTION_IDS["create"],
        "value": t312_button_value("create", it)[:2000],
    }


def dismiss_button(it: dict[str, Any], *, url_mode: bool) -> dict[str, Any]:
    n = int(it.get("n") or 0)
    label = f"#{n} 見送る" if n else "見送る"
    if url_mode:
        return {
            "type": "button",
            "text": {"type": "plain_text", "text": label[:24], "emoji": True},
            "url": t312_url("dismiss", it),
        }
    return {
        "type": "button",
        "text": {"type": "plain_text", "text": label[:24], "emoji": True},
        "action_id": T312_ACTION_IDS["dismiss"],
        "value": t312_button_value("dismiss", it)[:2000],
    }


def build_create_blocks(
    items: list[dict[str, Any]],
    *,
    header_text: str,
    fallback_text: str,
    url_mode: bool,
) -> dict[str, Any]:
    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": header_text[:150], "emoji": True},
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "ボタン＝1件ずつ起票 ／ 番号返信も可（`起票して 1,3`）\n"
                    "見送りボタンは Slack 上の ack（digest state は CLI／番号で）"
                ),
            },
        },
    ]
    for it in items:
        n = int(it.get("n") or 0)
        title = str(it.get("title") or "")[:80]
        lane = str(it.get("lane") or "").replace("_", " ")
        origin = str(it.get("origin") or "")
        link = title
        if it.get("project_url"):
            link = f"<{it['project_url']}|{title}>"
        meta = f"#{n} · _{lane}_"
        if origin:
            meta += f" · {origin}"
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*{meta}*\n{link}"},
            }
        )
        can_button = bool(title) and (not url_mode or bool(_action_secret()))
        if can_button:
            blocks.append(
                {
                    "type": "actions",
                    "block_id": f"t312_c_{n}_{abs(hash(title)) % 100000}",
                    "elements": [
                        create_button(it, url_mode=url_mode),
                        dismiss_button(it, url_mode=url_mode),
                    ],
                }
            )
    mode = (
        "アプリ内ボタン"
        if not url_mode
        else (
            "URLボタン（確認画面あり）"
            if _action_secret()
            else "ボタンなし（署名トークン未設定・番号返信を使用）"
        )
    )
    blocks.append(
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"312 · {mode} · 返信「起票して N」も可",
                }
            ],
        }
    )
    return {
        "text": fallback_text,
        "blocks": blocks,
        "username": AGENT_USERNAME,
    }


def post_bot(payload: dict[str, Any], *, dry_run: bool) -> int:
    token = _bot_token()
    channel = _consult_channel()
    body = {
        "channel": channel,
        "text": payload.get("text") or "312",
        "blocks": payload.get("blocks") or [],
        "username": payload.get("username") or AGENT_USERNAME,
    }
    if dry_run:
        print("# dry-run chat.postMessage (312)")
        print(json.dumps(body, ensure_ascii=False, indent=2)[:5000])
        return 0
    if not token:
        return 3
    req = urllib.request.Request(
        "https://slack.com/api/chat.postMessage",
        data=json.dumps(body).encode("utf-8"),
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
            print(f"✅ Slack 312 Bot OK channel={channel} ts={j.get('ts')}")
            return 0
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        print(f"❌ Slack HTTP {e.code}: {err}", file=sys.stderr)
        return 1


def post_webhook(payload: dict[str, Any], *, dry_run: bool) -> int:
    url = _webhook_consult()
    if dry_run:
        print("# dry-run Slack webhook (312)")
        print(json.dumps(payload, ensure_ascii=False, indent=2)[:5000])
        return 0
    if not url:
        print("❌ SLACK_WEBHOOK_AI_TEAM_CONSULT 未設定", file=sys.stderr)
        return 2
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            print(f"✅ Slack 312 Webhook OK status={resp.status}")
            return 0
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        print(f"❌ Slack HTTP {e.code}: {err}", file=sys.stderr)
        return 1


def post_slack(
    payload: dict[str, Any],
    *,
    dry_run: bool = False,
    force_webhook: bool = False,
    force_url_buttons: bool = False,
) -> int:
    sec_name = _action_secret_name()
    if not sec_name:
        print(
            "⚠️ 署名トークン未設定（URLボタンなし・番号返信を使用）",
            file=sys.stderr,
        )
    elif sec_name != "PROPERTY_GATE_ACTION_TOKEN":
        print(
            f"ℹ️ 312 URL署名: {sec_name}"
            "（本線は PROPERTY_GATE。Vercel は候補キーを照合）",
            file=sys.stderr,
        )
    use_bot = bool(_bot_token()) and not force_webhook and not force_url_buttons
    if force_url_buttons and _bot_token() and not force_webhook:
        use_bot = True
    if use_bot:
        rc = post_bot(payload, dry_run=dry_run)
        if rc == 3:
            return post_webhook(payload, dry_run=dry_run)
        return rc
    return post_webhook(payload, dry_run=dry_run)


def prefer_url_mode(*, force_url: bool = False) -> bool:
    if force_url:
        return True
    if not _bot_token():
        return True
    return False
