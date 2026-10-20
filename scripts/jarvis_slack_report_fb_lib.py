#!/usr/bin/env python3
"""Slack 報告への FB（スレ返信）— 共通フッタ・分類。

正本: docs/AIエージェントチーム/40_Slack報告FB_スレ拾い_20261020.md
"""
from __future__ import annotations

import os
import re
from typing import Any

# 本線に付ける短い案内（iPhone・1〜2行）
FB_FOOTER_LINE = "FB: スレ返信で（先頭に 見栄え／内容／方針）"
FB_FOOTER_MARKER = "FB: スレ返信で"
FB_FOOTER_CHANNELS = frozenset({"report", "consult"})

_KIND_ALIASES = {
    "見栄え": "layout",
    "レイアウト": "layout",
    "見た目": "layout",
    "グラフ": "layout",
    "内容": "content",
    "調査": "content",
    "ツッコミ": "content",
    "追加": "content",
    "方針": "policy",
    "頻度": "policy",
    "ルール": "policy",
    "やめて": "policy",
}

_KIND_LABEL_JA = {
    "layout": "見栄え",
    "content": "内容",
    "policy": "方針",
    "unknown": "未分類",
}


def footer_enabled() -> bool:
    return (os.environ.get("JARVIS_SLACK_FB_FOOTER_DISABLE") or "").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }


def poll_enabled() -> bool:
    return (os.environ.get("JARVIS_SLACK_FB_THREAD_DISABLE") or "").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }


def has_fb_footer(text: str) -> bool:
    t = text or ""
    return FB_FOOTER_MARKER in t or "FBはスレ返信" in t


def append_fb_footer(text: str, *, channel: str) -> str:
    """report/consult の本文末尾に FB 案内を付ける（重複しない）。"""
    ch = (channel or "").strip().lstrip("#").lower()
    if ch in ("ai-hub", "ai_hub"):
        ch = "hub"
    if ch not in FB_FOOTER_CHANNELS or not footer_enabled():
        return text
    body = (text or "").rstrip()
    if not body or has_fb_footer(body):
        return text
    return f"{body}\n\n—\n{FB_FOOTER_LINE}"


def kind_label_ja(kind: str) -> str:
    return _KIND_LABEL_JA.get(kind, kind)


def classify_fb_reply(text: str) -> str:
    """見栄え / 内容 / 方針 / unknown。先頭トークン優先。"""
    raw = (text or "").strip()
    if not raw:
        return "unknown"
    # 先頭の「見栄え:」「【見栄え】」等
    head = re.split(r"[\s:：・/\|]+", raw, maxsplit=1)[0]
    head = head.strip("【】[]()（）")
    for ja, kind in _KIND_ALIASES.items():
        if head.startswith(ja) or head == ja:
            return kind
    # 本文に明示ラベル
    for ja, kind in _KIND_ALIASES.items():
        if re.search(rf"(?:^|[\s　]){re.escape(ja)}[:：]", raw):
            return kind
    # ヒューリスティック
    if any(w in raw for w in ("グラフ", "短く", "レイアウト", "📌", "見づらい", "長い")):
        return "layout"
    if any(w in raw for w in ("調べて", "おかしい", "数字", "根拠", "追加で")):
        return "content"
    if any(w in raw for w in ("やめ", "減ら", "週1", "頻度", "方針", "ルール変更")):
        return "policy"
    return "unknown"


def next_steps_for_kind(kind: str) -> str:
    if kind == "layout":
        return "次: 同スレに改訂案（Cursor／次回報告で反映）"
    if kind == "content":
        return "次: 追加調査ドラフトを同スレ or Cursor"
    if kind == "policy":
        return "次: Todoist／#consult（方針・頻度は人判断）"
    return "次: 先頭に 見栄え／内容／方針 を付けて再送してほしい"


def build_ack_text(kind: str, *, reply_preview: str = "") -> str:
    label = kind_label_ja(kind)
    prev = (reply_preview or "").replace("\n", " ").strip()
    if len(prev) > 80:
        prev = prev[:79] + "…"
    lines = [
        f"【Jarvis】受けた（{label}）",
        next_steps_for_kind(kind),
    ]
    if prev:
        lines.append(f"引用: {prev}")
    if kind == "unknown":
        lines.append("例: 「見栄え: グラフにして」「内容: ○○も調べて」")
    return "\n".join(lines)


def is_ack_or_bot_reply(msg: dict[str, Any]) -> bool:
    """自分の Ack・Bot 投稿は再処理しない。"""
    if msg.get("bot_id") or msg.get("app_id"):
        return True
    text = str(msg.get("text") or "")
    if text.startswith("【Jarvis】受けた") or "【Jarvis】受けた（" in text[:40]:
        return True
    subtype = str(msg.get("subtype") or "")
    if subtype in {"bot_message", "message_changed", "message_deleted"}:
        return True
    return False
