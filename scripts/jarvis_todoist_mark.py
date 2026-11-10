#!/usr/bin/env python3
"""Todoist の件名に「誰が入れたか」の印を付ける（2026-11-10 松野さん決定）。

- 🤖      … AI が自分の判断で入れたもの（監視・メール仕分け・週次など）
- 🦾依頼  … 松野さんが頼んで入れたもの（ボタンを押した／「入れて」と言われた）
- 印なし  … 松野さんが自分で入れたもの

AI が Todoist にタスクを作るときは必ずこのどちらかを付ける。
重複確認や件名の比較は strip_mark() を通して、印の有無で別物と見なさない。
"""
from __future__ import annotations

AI_MARK = "🤖"
REQUESTED_MARK = "🦾依頼"
_MARKS = (REQUESTED_MARK, AI_MARK)


def strip_mark(title: str) -> str:
    """先頭の印（と直後の空白）を外す。印が無ければそのまま。"""
    s = (title or "").strip()
    for m in _MARKS:
        if s.startswith(m):
            return s[len(m):].strip()
    return s


def has_mark(title: str) -> bool:
    s = (title or "").lstrip()
    return any(s.startswith(m) for m in _MARKS)


def mark_title(title: str, *, requested: bool = False) -> str:
    """印を付ける。すでに印があればそのまま返す（付け直さない）。"""
    s = (title or "").strip()
    if has_mark(s):
        return s
    return f"{REQUESTED_MARK if requested else AI_MARK} {s}"


def keep_mark(new_title: str, current_title: str) -> str:
    """件名を書き直すとき、今付いている印を引き継ぐ（無ければ 🤖）。"""
    cur = (current_title or "").lstrip()
    if cur.startswith(REQUESTED_MARK):
        return mark_title(strip_mark(new_title), requested=True)
    return mark_title(strip_mark(new_title))
