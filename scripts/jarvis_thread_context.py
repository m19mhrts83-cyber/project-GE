#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""判断デスクに出す「1つ前のやりとり」を、仕分けの候補から取り出して短くする。

仕分け（Mac の夜間仕分け・GHA）は、スレッドの直近のやりとり（context）を集めているが、
DB（triage_items.payload）には入れていなかった。判断デスクで「自分が送った前のメール」が
見えない原因はこれ。ここで短くして payload.thread_context に入れる。

形（1通ずつ）:
    {"at": "2026/11/12 21:39", "mine": true, "subject": "...", "body": "..."}

  mine=true  … 松野さん側が送ったもの（デスクで「あなた」と出す）
  mine=false … 相手から来たもの
  いま判断するメール自身は含めない（最新の受信と本文が同じものは落とす）。
  新しいほうから最大 MAX_MSGS 通・本文は MAX_CHARS 文字まで（引用の前まで）。
"""
from __future__ import annotations

import re
from typing import Any

MAX_MSGS = 3
MAX_CHARS = 700

_QUOTE_STOP_RE = re.compile(
    r"^(>|-{2,}\s*$|On .+wrote:|.+のメッセージ:|-----Original Message-----|-----元のメッセージ-----|差出人:|From:)"
)


def _head(text: Any, limit: int = MAX_CHARS) -> str:
    """本文を引用・署名の手前までにして、長さを切る。"""
    out: list[str] = []
    for line in str(text or "").replace("\r", "").split("\n"):
        s = line.rstrip()
        if _QUOTE_STOP_RE.match(s.strip()):
            break
        out.append(s)
    body = "\n".join(out).strip()
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body[:limit]


def _norm(text: Any) -> str:
    return re.sub(r"\s+", "", str(text or ""))[:200]


def compact_context(
    ctx: Any,
    current_body: str = "",
    *,
    max_msgs: int = MAX_MSGS,
    max_chars: int = MAX_CHARS,
) -> list[dict[str, Any]]:
    """context（古い順の list[dict]）→ payload.thread_context（古い順・短い形）。"""
    if not isinstance(ctx, list):
        return []
    items = [e for e in ctx if isinstance(e, dict)]
    # いま判断するメール自身（最後の受信で本文が同じもの）は入れない
    if items:
        last = items[-1]
        if last.get("inbound") and (not current_body or _norm(last.get("body")) == _norm(current_body)):
            items = items[:-1]
    out: list[dict[str, Any]] = []
    for e in items[-max_msgs:]:
        body = _head(e.get("body") or e.get("summary"), max_chars)
        if not body:
            continue
        out.append(
            {
                "at": str(e.get("received_at") or "")[:20],
                "mine": not bool(e.get("inbound")),
                "subject": str(e.get("subject") or "")[:120],
                "body": body,
            }
        )
    return out
