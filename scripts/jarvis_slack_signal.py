#!/usr/bin/env python3
"""Slack 報告の緑・黄・赤シグナル（共通部品）。

先頭行は「判定: 🟢 …」の形にそろえる（315 ops_health の「判定: 🟢OK／🔴…」と同じ）。
色の意味:
  🟢 green  回っている。何もしなくてよい。
  🟡 yellow 遅れ気味・様子見。通知はせず、週次まとめなどに載せる。
  🔴 red    松野さんの判断・対応が要る。通知するのは基本これだけ。
  ⚪ none   まだ判定できない（データなし・対象外）。
"""
from __future__ import annotations

from typing import Iterable

ICON = {"green": "🟢", "yellow": "🟡", "red": "🔴", "none": "⚪"}
LABEL_JA = {"green": "回っています", "yellow": "遅れ気味", "red": "要対応", "none": "判定なし"}
_ORDER = {"none": 0, "green": 1, "yellow": 2, "red": 3}


def icon(level: str) -> str:
    return ICON.get(level, ICON["none"])


def worst(levels: Iterable[str]) -> str:
    """複数の色のうち一番悪いもの。空なら none。"""
    best = "none"
    for lv in levels:
        if _ORDER.get(lv, 0) > _ORDER[best]:
            best = lv
    return best


def head_line(level: str, text: str | None = None) -> str:
    """先頭行。例: 判定: 🟢 回っています"""
    return f"判定: {icon(level)} {text or LABEL_JA.get(level, '')}".rstrip()


def item_line(level: str, text: str) -> str:
    """項目行。例: 🟡 S2地場紹介: 直近7日の送信 3件"""
    return f"{icon(level)} {text}"
