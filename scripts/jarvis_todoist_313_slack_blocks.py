#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""313 Slack Block Kit ヘルパー（完了／延期ボタン）.

Bot chat.postMessage 本線（action_id）／Webhook 時は URL ボタン。
署名: PROPERTY_GATE_ACTION_TOKEN（または TODOIST_313_ACTION_TOKEN）。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

DEFAULT_CONSULT_CHANNEL = "C0C7R0UF3MM"
AGENT_USERNAME = "313 完了候補確認"

T313_ACTION_IDS = {
    "close": "todoist_313_close",
    "reschedule": "todoist_313_reschedule",
}


def _dashboard() -> str:
    return (
        (os.environ.get("JARVIS_DASHBOARD_URL") or "").strip().rstrip("/")
        or "https://jarvis-dashboard-amber.vercel.app"
    )


def _action_secret() -> str:
    # 本線は PROPERTY_GATE（116/511と同系）。未設定時は Todoist トークンで署名
    # （Cloud／Vercel の両方に TODOIST_API_TOKEN があるため URL ボタンを通せる）
    return (
        (os.environ.get("TODOIST_313_ACTION_TOKEN") or "").strip()
        or (os.environ.get("PROPERTY_GATE_ACTION_TOKEN") or "").strip()
        or (os.environ.get("MAIL_ACTION_TOKEN") or "").strip()
        or (os.environ.get("TODOIST_API_TOKEN") or "").strip()
    )


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


def t313_sig(task_id: str, action: str, due: str = "") -> str:
    secret = _action_secret()
    if not secret:
        return ""
    payload = (
        f"t313:{task_id}:{action}:{due}"
        if action == "reschedule"
        else f"t313:{task_id}:{action}"
    )
    return hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:10]


def t313_url(task_id: str, action: str, due: str = "") -> str:
    s = t313_sig(task_id, action, due)
    base = _dashboard()
    if action == "reschedule":
        return f"{base}/api/g/t313/reschedule/{task_id}?due={due}&s={s}"
    return f"{base}/api/g/t313/close/{task_id}?s={s}"


def close_button(task_id: str, *, url_mode: bool, n: int | None = None) -> dict[str, Any]:
    label = f"✅{n} 完了する" if n else "完了する"
    if url_mode:
        return {
            "type": "button",
            "text": {"type": "plain_text", "text": label, "emoji": True},
            "style": "primary",
            "url": t313_url(task_id, "close"),
        }
    return {
        "type": "button",
        "text": {"type": "plain_text", "text": label, "emoji": True},
        "style": "primary",
        "action_id": T313_ACTION_IDS["close"],
        "value": f"t313:close:{task_id}",
    }


def reschedule_button(
    task_id: str, due: str, *, url_mode: bool, n: int | None = None
) -> dict[str, Any]:
    short = due[5:] if len(due) >= 10 else due  # MM-DD
    label = f"📅{n} →{short}" if n else f"→{short} へ延期"
    if url_mode:
        return {
            "type": "button",
            "text": {"type": "plain_text", "text": label[:24], "emoji": True},
            "style": "primary",
            "url": t313_url(task_id, "reschedule", due),
        }
    return {
        "type": "button",
        "text": {"type": "plain_text", "text": label[:24], "emoji": True},
        "style": "primary",
        "action_id": T313_ACTION_IDS["reschedule"],
        "value": f"t313:reschedule:{task_id}:{due}",
    }


def build_close_blocks(
    items: list[dict[str, Any]],
    *,
    header_text: str,
    fallback_text: str,
    url_mode: bool,
) -> dict[str, Any]:
    """完了候補: 各件に「完了する」ボタン。"""
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
                    "ボタン＝1件ずつ完了 ／ 番号返信も可（`✅1,3`）\n"
                    "※ Todoist タイトルリンクは詳細確認用（押しても完了しません）"
                ),
            },
        },
    ]
    for it in items:
        n = int(it.get("n") or 0)
        tid = str(it.get("task_id") or "")
        title = str(it.get("title_short") or it.get("title") or tid)[:80]
        lane = str(it.get("lane") or "").replace("_", " ")
        kind = str(it.get("kind") or "")
        link = f"<https://app.todoist.com/app/task/{tid}|{title}>" if tid else title
        meta = f"✅{n} · _{lane}_"
        if kind == "confirm_only":
            meta += " · 確認のみ"
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*{meta}*\n{link}"},
            }
        )
        can_button = bool(tid) and (not url_mode or bool(_action_secret()))
        if can_button:
            blocks.append(
                {
                    "type": "actions",
                    "block_id": f"t313_c_{tid[:20]}_{n}",
                    "elements": [close_button(tid, url_mode=url_mode, n=n)],
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
                    "text": f"313 · {mode} · 返信「閉じて ✅N」も可",
                }
            ],
        }
    )
    return {
        "text": fallback_text,
        "blocks": blocks,
        "username": AGENT_USERNAME,
    }


def build_reschedule_blocks(
    items: list[dict[str, Any]],
    *,
    header_text: str,
    fallback_text: str,
    url_mode: bool,
    total: int,
) -> dict[str, Any]:
    """期日超過: 各件に「提案日へ延期」ボタン。"""
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
                    f"超過 *{total}件* ／ 上位{len(items)}件\n"
                    "ボタン＝提案日へ延期 ／ 番号返信も可（`📅1,3`）\n"
                    "※ Todoist リンクは詳細確認用"
                ),
            },
        },
    ]
    for it in items:
        n = int(it.get("n") or 0)
        tid = str(it.get("task_id") or "")
        title = str(it.get("title_short") or it.get("title") or tid)[:70]
        new_due = str(it.get("new_due") or "")
        days = it.get("days_over")
        link = f"<https://app.todoist.com/app/task/{tid}|{title}>" if tid else title
        meta = f"📅{n}"
        if days is not None:
            meta += f" · {days}日超過"
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{meta}*\n{link}\n→ *{new_due}* へ",
                },
            }
        )
        can_button = bool(tid and new_due) and (
            not url_mode or bool(_action_secret())
        )
        if can_button:
            blocks.append(
                {
                    "type": "actions",
                    "block_id": f"t313_r_{tid[:20]}_{n}",
                    "elements": [
                        reschedule_button(
                            tid, new_due, url_mode=url_mode, n=n
                        )
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
                    "text": f"313 · {mode} · 返信「リスケ 📅N」も可",
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
        "text": payload.get("text") or "313",
        "blocks": payload.get("blocks") or [],
        "username": payload.get("username") or AGENT_USERNAME,
    }
    if dry_run:
        print("# dry-run chat.postMessage (313)")
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
            print(f"✅ Slack 313 Bot OK channel={channel} ts={j.get('ts')}")
            return 0
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        print(f"❌ Slack HTTP {e.code}: {err}", file=sys.stderr)
        return 1


def post_webhook(payload: dict[str, Any], *, dry_run: bool) -> int:
    url = _webhook_consult()
    if dry_run:
        print("# dry-run Slack webhook (313)")
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
            print(f"✅ Slack 313 Webhook OK status={resp.status}")
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
    """Bot 優先。Bot 無し／force_webhook なら Incoming Webhook。"""
    if not _action_secret():
        print(
            "⚠️ PROPERTY_GATE_ACTION_TOKEN 未設定（URLボタン署名なし）",
            file=sys.stderr,
        )
    use_bot = bool(_bot_token()) and not force_webhook and not force_url_buttons
    # force_url_buttons でも Bot があれば Bot＋URL ボタンで投稿可
    if force_url_buttons and _bot_token() and not force_webhook:
        use_bot = True
    if use_bot:
        rc = post_bot(payload, dry_run=dry_run)
        if rc == 3:
            return post_webhook(payload, dry_run=dry_run)
        return rc
    return post_webhook(payload, dry_run=dry_run)


def prefer_url_mode(*, force_url: bool = False) -> bool:
    """Interactivity 無し／明示時は URL ボタン。"""
    if force_url:
        return True
    if not _bot_token():
        return True
    # Bot があっても Signing Secret 未配線環境向けに URL 併用は呼び出し側で選択
    return False
