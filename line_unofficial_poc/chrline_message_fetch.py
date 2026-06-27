#!/usr/bin/env python3
"""CHRLINE トーク履歴の取得（直近 + ページング）。"""
from __future__ import annotations

from chrline_dump_messages_poc import _fetch_messages, _messages_from_response
from chrline_sync_delta_poc import _looks_like_line_chat_mid, _msg_time


def _message_dedup_key(cl, msg) -> str | None:
    mid = cl.checkAndGetValue(msg, "id", 4)
    if mid is None and isinstance(msg, dict):
        mid = msg.get(4) or msg.get("id")
    ts = _msg_time(cl, msg)
    if mid:
        return f"id:{mid}|ts:{ts}"
    if ts:
        return f"nts:{ts}"
    return None


def _message_id(cl, msg) -> int:
    mid = cl.checkAndGetValue(msg, "id", 4)
    if mid is None and isinstance(msg, dict):
        mid = msg.get(4) or msg.get("id")
    try:
        return int(mid) if mid is not None else 0
    except (TypeError, ValueError):
        return 0


def fetch_recent_messages(
    cl,
    chat_mid: str,
    count: int,
    *,
    skip_e2ee_key_register: bool = False,
    trace: bool = False,
) -> list:
    n = max(1, min(int(count), 300))
    _res, msgs = _fetch_messages(
        cl,
        chat_mid,
        n,
        trace=trace,
        skip_e2ee_key_register=skip_e2ee_key_register,
    )
    return list(msgs or [])


def fetch_messages_deep(
    cl,
    chat_mid: str,
    max_messages: int,
    *,
    skip_e2ee_key_register: bool = False,
    trace: bool = False,
) -> list:
    """
    getRecentMessagesV2 + getPreviousMessagesV2 で最大 max_messages 件まで遡る。
    重複は message dedup key で除去。
    """
    target = max(1, int(max_messages))
    seen_dk: set[str] = set()
    collected: list = []

    batch = min(300, target)
    msgs = fetch_recent_messages(
        cl,
        chat_mid,
        batch,
        skip_e2ee_key_register=skip_e2ee_key_register,
        trace=trace,
    )
    for m in msgs:
        dk = _message_dedup_key(cl, m)
        if dk and dk in seen_dk:
            continue
        if dk:
            seen_dk.add(dk)
        collected.append(m)

    rounds = 0
    max_rounds = max(1, (target // 100) + 5)
    while len(collected) < target and msgs and rounds < max_rounds:
        rounds += 1
        oldest = min(msgs, key=lambda m: _msg_time(cl, m) or 0)
        dt = int(_msg_time(cl, oldest) or 0)
        nid = _message_id(cl, oldest)
        if dt <= 0:
            break
        try:
            res = cl.getPreviousMessagesV2(chat_mid, dt, nid, min(300, target - len(collected)))
        except Exception:
            break
        prev = _messages_from_response(cl, res)
        if not prev:
            break
        new_in_round = 0
        for m in prev:
            dk = _message_dedup_key(cl, m)
            if dk and dk in seen_dk:
                continue
            if dk:
                seen_dk.add(dk)
            collected.append(m)
            new_in_round += 1
            if len(collected) >= target:
                break
        if new_in_round == 0:
            break
        msgs = prev

    collected.sort(key=lambda m: _msg_time(cl, m) or 0)
    return collected[:target]


def group_fetch_mid(chat_mid: str) -> str | None:
    n = (chat_mid or "").strip()
    if n.startswith("c") and _looks_like_line_chat_mid(n):
        return n
    return None
