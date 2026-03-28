#!/usr/bin/env python3
"""
保存セッションでトーク一覧を表示する（chatMid と名前のタブ区切り）。

次のステップ: chrline_dump_messages_poc.py に --chat-mid を渡すか、
--title-substring でダンプ側に任せる。

標準出力のみ（stderr にヘルプ）。トークンは表示しない。
"""
from __future__ import annotations

import argparse
import sys

from chrline_client_utils import build_logged_in_client, save_root_from_env


def _chat_mid_from(cl, c, fallback_mid: str | None = None) -> str | None:
    """
    Thrift の Chat は chatMid がフィールド 2。フィールド 1 は type（整数）のため、
    checkAndGetValue(..., 1) だけだと「1」が mid として誤認される。
    """
    if isinstance(c, dict):
        v = c.get("chatMid")
        if isinstance(v, str) and v.strip():
            return v.strip()
        v2 = c.get(2)
        if isinstance(v2, str) and v2.strip():
            return v2.strip()
    else:
        v = getattr(c, "chatMid", None)
        if isinstance(v, str) and v.strip():
            return v.strip()
        v = cl.checkAndGetValue(c, "chatMid", 2)
        if isinstance(v, str) and v.strip():
            return v.strip()
        v = getattr(c, "val_2", None)
        if isinstance(v, str) and v.strip():
            return v.strip()
    if fallback_mid and isinstance(fallback_mid, str) and fallback_mid.strip():
        return fallback_mid.strip()
    return None


def _chat_name(cl, chat) -> str:
    if isinstance(chat, dict):
        for k in ("chatName", "chat_name", 6):
            v = chat.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
        return "(無題)"
    for v in (
        getattr(chat, "chatName", None),
        cl.checkAndGetValue(chat, "chatName", 6),
        getattr(chat, "val_6", None),
    ):
        if isinstance(v, str) and v.strip():
            return v.strip()
    for k in ("chatName", "chat_name", 21, 22, 20):
        v = cl.checkAndGetValue(chat, k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return "(無題)"


def _iter_group_mids(cl):
    raw = cl.getAllChatMids()
    mids = cl.checkAndGetValue(raw, "memberChatMids", 1)
    if mids is None and isinstance(raw, dict):
        mids = raw.get(1) or raw.get("memberChatMids")
    if not mids:
        return []
    if isinstance(mids, (list, tuple)):
        return list(mids)
    return [mids]


def main() -> int:
    parser = argparse.ArgumentParser(description="LINE グループ等の chatMid 一覧")
    parser.add_argument(
        "--batch",
        type=int,
        default=30,
        help="getChats 呼び出しごとの mid 数（既定 30）",
    )
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    save_root = save_root_from_env()
    cl = build_logged_in_client(save_root)

    mids = _iter_group_mids(cl)
    if not mids:
        print("グループ chatMid が取得できませんでした。", file=sys.stderr)
        return 1

    batch = max(1, args.batch)
    for i in range(0, len(mids), batch):
        chunk = mids[i : i + batch]
        try:
            res = cl.getChats(chunk)
        except Exception as e:
            print(f"getChats エラー: {e}", file=sys.stderr)
            return 1
        chats = cl.checkAndGetValue(res, "chats", 1)
        if chats is None and isinstance(res, dict):
            chats = res.get(1) or res.get("chats")
        if not chats:
            continue
        if not isinstance(chats, (list, tuple)):
            chats = [chats]
        for j, c in enumerate(chats):
            fb = chunk[j] if j < len(chunk) else None
            mid = _chat_mid_from(cl, c, fb)
            if not mid:
                continue
            name = _chat_name(cl, c)
            print(f"{mid}\t{name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
