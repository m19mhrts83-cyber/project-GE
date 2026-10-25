#!/usr/bin/env python3
"""Slack 報告への FB（スレ返信）— 共通フッタ・分類。

正本: docs/AIエージェントチーム/40_Slack報告FB_スレ拾い_20261020.md
"""
from __future__ import annotations

import os
import re
from typing import Any

# AI チーム共通の名乗り（Jarvis 以外も対応するため。旧 【Jarvis】 も自分の投稿として扱う）
TEAM_PREFIX = "【AIチーム】"
OWN_PREFIXES = (TEAM_PREFIX, "【Jarvis】")

# 本線に付ける短い案内（iPhone・1〜2行）。既定オフ（2026-10-25 松野: 毎回は不要）
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
    """既定オフ。JARVIS_SLACK_FB_FOOTER_ENABLE=1 のときだけ付ける。"""
    on = {"1", "true", "yes", "on"}
    if (os.environ.get("JARVIS_SLACK_FB_FOOTER_DISABLE") or "").strip().lower() in on:
        return False
    return (os.environ.get("JARVIS_SLACK_FB_FOOTER_ENABLE") or "").strip().lower() in on


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


def build_ack_text(kind: str, *, reply_preview: str = "") -> str:
    """受けた（見た）の返信。ラベルの付け直しは頼まない（分類は毎日の FB 対応で読んで決める）。

    reply_preview は互換のため受けるが本文には出さない（元コメントが直上にある）。
    """
    label = kind_label_ja(kind)
    head = f"{TEAM_PREFIX}受けた" if kind == "unknown" else f"{TEAM_PREFIX}受けた（{label}）"
    return f"{head}\n直したらこのスレで「対応したよ」と返します"


def is_ack_or_bot_reply(msg: dict[str, Any]) -> bool:
    """自分の Ack・対応済・Bot 投稿は再処理しない。"""
    if msg.get("bot_id") or msg.get("app_id"):
        return True
    text = str(msg.get("text") or "")
    head = text[:60]
    if text.startswith(OWN_PREFIXES) and any(
        m in head
        for m in (
            "受けた",
            "対応した",
            "対応済み",
            "起票した",
            "完了した",
            "反映した",
        )
    ):
        return True
    subtype = str(msg.get("subtype") or "")
    if subtype in {"bot_message", "message_changed", "message_deleted"}:
        return True
    return False


def build_done_text(*, summary: str, next_line: str = "") -> str:
    """実装・起票など処置完了時のスレ返信（受けただけと区別する）。"""
    lines = [f"{TEAM_PREFIX}対応したよ", (summary or "").strip()]
    if next_line.strip():
        lines.append(next_line.strip())
    return "\n".join(x for x in lines if x)


def build_todoist_seen_text(*, comment_preview: str = "", source: str = "317") -> str:
    """Todoist コメントを見終わったときの可視返信（Slack の「受けた」と同コンセプト）。"""
    prev = (comment_preview or "").replace("\n", " ").strip()
    if len(prev) > 80:
        prev = prev[:79] + "…"
    lines = [
        f"{TEAM_PREFIX}見たよ（受けた）",
        f"経路: {source}",
    ]
    if prev:
        lines.append(f"引用: {prev}")
    lines.append("チャット／次セッションでも続きを見るよ")
    return "\n".join(lines)


# Slack リアクション名（reactions.add 用・: なし）
REACTION_SEEN = "eyes"  # 見た／受けた
REACTION_DONE = "white_check_mark"  # 対応した


def has_handled_reaction(msg: dict[str, Any]) -> bool:
    """👀／✅ が付いていれば受付済み。ローカル state が無い GHA 冗長でも二重 Ack しない。"""
    for r in msg.get("reactions") or []:
        if isinstance(r, dict) and r.get("name") in (REACTION_SEEN, REACTION_DONE):
            return True
    return False
