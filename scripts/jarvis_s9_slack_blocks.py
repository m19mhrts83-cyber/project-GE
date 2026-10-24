#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S9 管理会社開拓 — Slack 候補カード（採用／見送りボタン）.

312／313 と同型。Bot `chat.postMessage` 本線（action_id → /api/slack/consult-action）、
Bot が無い／チャンネル未参加なら Incoming Webhook ＋ 署名 URL ボタン。

ボタン → Vercel が kurashift_jobs に `re_mgmt_vendor_decision` を積む
→ Mac worker が `scripts/jarvis_s9_decision_apply.py` を実行して台帳へ反映。

iPhone 前提のレイアウト:
  - 1社＝見出し1行＋地域・理由1行＋リンク1行（長い URL はラベルに畳む）
  - その直下に［採用］［見送り］の2ボタン（片手で押せる幅）
  - 判断するとボタンが結果1行に置き換わる（メッセージは履歴として残る）
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
AGENT_USERNAME = "S9 管理会社開拓"
HEADER_MAX = 150

S9_ACTIONS = {"adopt": "s9_adopt", "skip": "s9_skip"}
DECISION_LABEL = {"adopt": "採用", "skip": "見送り"}
DECISION_ICON = {"adopt": "✅", "skip": "🗑️"}

_CHANNEL_ICON = {"email": "✉️ メール", "web_form": "🔗 フォーム", "phone": "☎️ 電話"}


def _dashboard() -> str:
    return (
        (os.environ.get("JARVIS_DASHBOARD_URL") or "").strip().rstrip("/")
        or "https://jarvis-dashboard-amber.vercel.app"
    )


def _action_secret_name() -> str:
    for name in (
        "S9_ACTION_TOKEN",
        "PROPERTY_GATE_ACTION_TOKEN",
        "TODOIST_313_ACTION_TOKEN",
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


# ---------------------------------------------------------------- payload / sig


def encode_candidate(it: dict[str, Any]) -> str:
    """ボタンに載せる最小情報（名前・連絡先・出典）。"""
    compact = {
        "n": int(it.get("n") or 0),
        "name": str(it.get("name") or "")[:120],
        "area": str(it.get("property_area") or it.get("area") or "")[:40],
        "pref": str(it.get("prefecture") or "愛知県")[:20],
        "city": str(it.get("city") or "")[:20],
        "lane": str(it.get("property_lane") or "midori_caramel")[:40],
        "url": str(it.get("url") or "")[:300],
        "cu": str(it.get("contact_url") or "")[:300],
        "em": str(it.get("contact_email") or "")[:120],
        "tel": str(it.get("phone") or "")[:30],
        "ch": str(it.get("channel") or "")[:20],
        "memo": str(it.get("memo") or it.get("why") or "")[:200],
        "src": str(it.get("source_md") or "")[:80],
        "dt": str(it.get("md_date") or "")[:10],
    }
    raw = json.dumps(compact, ensure_ascii=False, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def s9_sig(decision: str, payload_b64: str) -> str:
    secret = _action_secret()
    if not secret:
        return ""
    payload = f"s9:{decision}:{payload_b64}"
    return hmac.new(
        secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()[:10]


def button_value(decision: str, it: dict[str, Any]) -> str:
    b64 = encode_candidate(it)
    return f"s9:{decision}:{b64}:{s9_sig(decision, b64)}"


def action_url(decision: str, it: dict[str, Any]) -> str:
    b64 = encode_candidate(it)
    sig = s9_sig(decision, b64)
    n = int(it.get("n") or 0)
    return f"{_dashboard()}/api/g/s9/{decision}/n{n}?p={b64}&s={sig}"


# ------------------------------------------------------------------- blocks


def _link_label(it: dict[str, Any]) -> str:
    url = str(it.get("contact_url") or it.get("url") or "").lower()
    if any(k in url for k in ("form", "contact", "toiawase", "mail")):
        return "🔗 フォーム"
    ch = str(it.get("channel") or "")
    return _CHANNEL_ICON.get(ch, "🔗 サイト")


def _candidate_section(it: dict[str, Any]) -> dict[str, Any]:
    n = int(it.get("n") or 0)
    name = str(it.get("name") or "")
    area = str(it.get("property_area") or it.get("area") or "")
    if area.startswith(("愛知", "〒", "名古屋市")):
        area = ""
    why = str(it.get("why") or "")
    url = str(it.get("contact_url") or it.get("url") or "")
    email = str(it.get("contact_email") or "")
    lines = [f"*{n}. {name}*"]
    meta = " · ".join(x for x in (area, why) if x)
    if meta:
        lines.append(meta)
    if url:
        lines.append(f"<{url}|{_link_label(it)}>")
    if email:
        lines.append(email)
    return {
        "type": "section",
        "text": {"type": "mrkdwn", "text": "\n".join(lines)[:2900]},
    }


def _decision_buttons(it: dict[str, Any], *, url_mode: bool) -> dict[str, Any]:
    n = int(it.get("n") or 0)
    elements: list[dict[str, Any]] = []
    for decision in ("adopt", "skip"):
        if url_mode:
            btn = {
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": f"{DECISION_ICON[decision]} {DECISION_LABEL[decision]}",
                    "emoji": True,
                },
                "url": action_url(decision, it),
            }
            if decision == "adopt":
                btn["style"] = "primary"
            elements.append(btn)
            continue
        btn = {
            "type": "button",
            "action_id": S9_ACTIONS[decision],
            "text": {
                "type": "plain_text",
                "text": f"{DECISION_ICON[decision]} {DECISION_LABEL[decision]}",
                "emoji": True,
            },
            "value": button_value(decision, it)[:2000],
        }
        if decision == "adopt":
            btn["style"] = "primary"
        elements.append(btn)
    return {"type": "actions", "block_id": f"s9_c_{n}", "elements": elements}


def build_decision_blocks(
    items: list[dict[str, Any]],
    *,
    url_mode: bool,
    header_text: str = "【相談】S9 管理会社・候補の判断",
    note: str = "",
) -> dict[str, Any]:
    """1社＝見出し＋リンク＋［採用］［見送り］。iPhone で縦に読める形。"""
    total = len(items)
    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": header_text[:HEADER_MAX]},
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        f"*{total}社* · ボタンで決めてOK"
                        "（採用＝台帳へ・見送り＝除外。数秒で反映）"
                        + (f"\n{note}" if note else "")
                    ),
                }
            ],
        },
        {"type": "divider"},
    ]
    for i, it in enumerate(items):
        it = dict(it)
        it.setdefault("n", i + 1)
        blocks.append(_candidate_section(it))
        blocks.append(_decision_buttons(it, url_mode=url_mode))
        if i < total - 1:
            blocks.append({"type": "divider"})
    blocks.append(
        {
            "type": "context",
            "block_id": "s9_footer",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        f"残り{total}件 · "
                        + (
                            "アプリ内ボタン"
                            if not url_mode
                            else "URLボタン（確認画面あり）"
                        )
                        + " · 迷ったらスレッドに一言"
                    ),
                }
            ],
        }
    )
    fallback = f"【相談】S9 管理会社・候補{total}社の判断（採用／見送り）"
    return {"text": fallback, "blocks": blocks, "username": AGENT_USERNAME}


def build_consult_text(
    items: list[dict[str, Any]], *, md_note: str = "", handoff: bool = True
) -> str:
    """ボタンが使えない場所（ログ・通知）用のプレーン本文。"""
    lines = ["【相談】S9 管理会社開拓・候補の判断", ""]
    for i, it in enumerate(items):
        n = int(it.get("n") or i + 1)
        area = it.get("area") or it.get("property_area") or "-"
        why = it.get("why") or ""
        lines.append(
            f"{n}. {it.get('name')}（{area}）" + (f": {why}" if why else "")
        )
        lines.append(f"　{it.get('contact_url') or it.get('url') or it.get('phone') or '連絡先なし'}")
    lines += ["", "採用／見送りは上のボタンで（台帳には未追加）"]
    if handoff:
        lines += [
            "",
            "次: Jarvisに依頼",
            "",
            f"担当メモ: 採用分は jarvis_s9_decision_apply.py で台帳へ（元 MD: {md_note or '-'}）",
            "",
            "橋渡し: 松野が了承したら、上記の担当へ一声（当面は人が橋）",
        ]
    return "\n".join(lines)


# -------------------------------------------------------------------- post


def _post_chat(body: dict[str, Any]) -> tuple[bool, str]:
    token = _bot_token()
    if not token:
        return False, "no_bot_token"
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
    except urllib.error.HTTPError as e:
        return False, f"http_{e.code}"
    if not j.get("ok"):
        return False, str(j.get("error") or "unknown")
    return True, str(j.get("ts") or "")


def _post_webhook(payload: dict[str, Any]) -> int:
    url = _webhook_consult()
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
            print(f"✅ Slack S9 Webhook OK status={resp.status}")
            return 0
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        print(f"❌ Slack HTTP {e.code}: {err}", file=sys.stderr)
        return 1


def post_decision_card(
    items: list[dict[str, Any]], *, dry_run: bool = False, md_note: str = ""
) -> int:
    """Bot（アプリ内ボタン）→ 失敗時は Webhook（URLボタン）へ自動フォールバック。"""
    if not items:
        return 0
    text = build_consult_text(items, md_note=md_note)
    bot_payload = build_decision_blocks(items, url_mode=False)
    bot_payload["text"] = text
    if dry_run:
        print("# dry-run S9 decision card (bot)")
        print(json.dumps(bot_payload, ensure_ascii=False, indent=2)[:6000])
        return 0

    channel = _consult_channel()
    body = {
        "channel": channel,
        "text": text,
        "blocks": bot_payload["blocks"],
        "username": AGENT_USERNAME,
        "unfurl_links": False,
        "unfurl_media": False,
    }
    ok, detail = _post_chat(body)
    if ok:
        print(f"✅ Slack S9 Bot OK channel={channel} ts={detail}")
        return 0
    print(f"⚠️ S9 Bot 投稿不可（{detail}）→ Webhook URLボタンで再送", file=sys.stderr)
    url_payload = build_decision_blocks(items, url_mode=True)
    url_payload["text"] = text
    return _post_webhook(url_payload)


def thread_ack(
    *, channel: str, thread_ts: str, text: str, dry_run: bool = False
) -> int:
    """判断結果を元メッセージのスレッドへ一言（任意・失敗は無視）。"""
    if not channel or not thread_ts:
        return 0
    body = {"channel": channel, "thread_ts": thread_ts, "text": text}
    if dry_run:
        print("# dry-run S9 thread ack")
        print(json.dumps(body, ensure_ascii=False, indent=2)[:2000])
        return 0
    ok, detail = _post_chat(body)
    if not ok:
        print(f"⚠️ S9 thread ack 失敗: {detail}", file=sys.stderr)
        return 1
    return 0
