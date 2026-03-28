#!/usr/bin/env python3
"""参加中オープンチャット（Square）一覧を表示する。"""
from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable
from typing import Any

from chrline_client_utils import build_logged_in_client, save_root_from_env


def _coerce_str(v: Any) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    return s


def _is_chat_mid(s: str) -> bool:
    return len(s) >= 24 and s[:1] in {"m", "c"}


def _is_square_mid(s: str) -> bool:
    return len(s) >= 24 and s.startswith("s")


def _dict_like(obj: Any) -> dict[str, Any] | dict[int, Any]:
    if isinstance(obj, dict):
        return obj
    dd = getattr(obj, "dd", None)
    if callable(dd):
        try:
            out = dd()
            if isinstance(out, dict):
                return out
        except Exception:
            pass
    return {}


def _get(cl, obj: Any, key: str, fid: int | None = None) -> Any:
    if obj is None:
        return None
    v = cl.checkAndGetValue(obj, key, fid) if fid is not None else cl.checkAndGetValue(obj, key)
    if v is not None:
        return v
    d = _dict_like(obj)
    if key in d:
        return d[key]
    if fid is not None and fid in d:
        return d[fid]
    return None


def _pick_list(cl, res: Any, keys: tuple[tuple[str, int], ...]) -> list[Any]:
    for key, fid in keys:
        v = _get(cl, res, key, fid)
        if isinstance(v, list):
            return v
        if v is not None and not isinstance(v, (str, bytes, dict)):
            try:
                return list(v)
            except Exception:
                continue
    d = _dict_like(res)
    for v in d.values():
        if isinstance(v, list):
            return v
    return []


def _pick_continuation(cl, res: Any) -> str:
    for key, fid in (("continuationToken", 2), ("nextContinuationToken", 3), ("token", 4)):
        v = _get(cl, res, key, fid)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _parse_chat(cl, chat: Any) -> tuple[str, str, str, str]:
    square_mid = ""
    square_chat_mid = ""
    name = ""
    square_name = ""

    for key, fid in (
        ("squareMid", 2),
        ("squareChatMid", 1),
        ("chatMid", 1),
        ("name", 6),
        ("chatName", 6),
        ("displayName", 6),
        ("squareName", 5),
    ):
        v = _get(cl, chat, key, fid)
        s = _coerce_str(v)
        if not s:
            continue
        if not square_mid and (_is_square_mid(s) or key == "squareMid"):
            square_mid = s
        if not square_chat_mid and (_is_chat_mid(s) or key in {"squareChatMid", "chatMid"}):
            square_chat_mid = s
        if not name and key in {"name", "chatName", "displayName"} and not _is_chat_mid(s):
            name = s
        if not square_name and key == "squareName":
            square_name = s

    # nested square fields
    square_obj = _get(cl, chat, "square", 2)
    if square_obj is not None:
        if not square_mid:
            s = _coerce_str(_get(cl, square_obj, "squareMid", 1))
            if _is_square_mid(s):
                square_mid = s
        if not square_name:
            square_name = _coerce_str(_get(cl, square_obj, "name", 2))

    if not square_chat_mid:
        d = _dict_like(chat)
        for v in d.values():
            s = _coerce_str(v)
            if _is_chat_mid(s):
                square_chat_mid = s
                break

    if not name:
        name = "(無題)"
    return square_mid, square_chat_mid, name, square_name


def _parse_thread(cl, thread: Any) -> tuple[str, str]:
    mid = ""
    name = ""
    for key, fid in (
        ("squareChatThreadMid", 1),
        ("threadMid", 1),
        ("name", 2),
        ("title", 2),
    ):
        v = _get(cl, thread, key, fid)
        s = _coerce_str(v)
        if not s:
            continue
        if not mid and _is_chat_mid(s):
            mid = s
        if not name and key in {"name", "title"} and not _is_chat_mid(s):
            name = s
    if not mid:
        d = _dict_like(thread)
        for v in d.values():
            s = _coerce_str(v)
            if _is_chat_mid(s):
                mid = s
                break
    if not name:
        name = "(無題スレッド)"
    return mid, name


def _iter_joined_chats_xlt(cl, limit: int):
    continuation = None
    seen_tokens: set[str] = set()
    for _ in range(200):
        res = cl.getJoinedSquareChats(continuation, limit)
        chats = _pick_list(cl, res, (("squareChats", 1), ("chats", 1)))
        for chat in chats:
            yield _parse_chat(cl, chat)

        nxt = _pick_continuation(cl, res)
        if not nxt or nxt in seen_tokens:
            break
        seen_tokens.add(nxt)
        continuation = nxt


def _iter_fetch_my_events(cl, limit: int):
    sync_token = None
    continuation = None
    seen_tokens: set[str] = set()
    for _ in range(100):
        try:
            res = cl.fetchMyEvents(
                syncToken=sync_token,
                continuationToken=continuation,
                limit=limit,
            )
        except Exception:
            # continuation 付きで 400 になるケースがあるため、ここで打ち切る
            break
        events = _pick_list(cl, res, (("events", 2), ("squareEvents", 2), ("eventLogs", 2)))
        for ev in events:
            yield ev
        next_sync = _get(cl, res, "syncToken", 3)
        if isinstance(next_sync, str) and next_sync.strip():
            sync_token = next_sync.strip()
        nxt = _pick_continuation(cl, res)
        if not nxt or nxt in seen_tokens:
            break
        seen_tokens.add(nxt)
        continuation = nxt


def _iter_dictish(root: Any, depth: int = 0) -> Iterable[dict]:
    if root is None or depth > 8:
        return
    if isinstance(root, dict):
        yield root
        for v in root.values():
            yield from _iter_dictish(v, depth + 1)
    elif isinstance(root, (list, tuple)):
        for v in root:
            yield from _iter_dictish(v, depth + 1)
    else:
        dd = getattr(root, "dd", None)
        if callable(dd):
            try:
                d = dd()
                if isinstance(d, dict):
                    yield from _iter_dictish(d, depth + 1)
            except Exception:
                return


def _guess_chat_from_dict(d: dict) -> tuple[str, str, str, str] | None:
    vals = [str(v).strip() for v in d.values() if isinstance(v, str)]
    chat_mid = next((x for x in vals if _is_chat_mid(x) and x.startswith("m")), "")
    square_mid = next((x for x in vals if _is_square_mid(x)), "")
    if not chat_mid:
        return None
    name = ""
    for key in ("chatName", "name", "displayName", "title", 4, 6):
        v = d.get(key)
        if isinstance(v, str) and v.strip() and not _is_chat_mid(v):
            name = v.strip()
            break
    if not name:
        # 文字列候補から mid / url を除外
        for s in vals:
            if s.startswith(("m", "s", "http://", "https://")):
                continue
            if len(s) <= 2:
                continue
            name = s
            break
    return square_mid, chat_mid, (name or "(無題)"), ""


def _iter_joined_chats_fallback(cl, limit: int):
    seen: set[str] = set()
    for ev in _iter_fetch_my_events(cl, max(20, limit)):
        for d in _iter_dictish(ev):
            rec = _guess_chat_from_dict(d)
            if rec is None:
                continue
            _, chat_mid, _, _ = rec
            if chat_mid in seen:
                continue
            seen.add(chat_mid)
            yield rec


def iter_joined_chats(cl, limit: int):
    try:
        yield from _iter_joined_chats_xlt(cl, limit)
        return
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"
        if "NO XLT" not in msg and "Not yet implemented" not in msg:
            raise
    # フォールバック: fetchMyEvents から推定
    yield from _iter_joined_chats_fallback(cl, limit)


def iter_threads(cl, square_chat_mid: str, limit: int):
    continuation = None
    seen_tokens: set[str] = set()
    try:
        for _ in range(200):
            res = cl.getJoinedSquareChatThreads(square_chat_mid, limit=limit, continuationToken=continuation)
            threads = _pick_list(cl, res, (("squareChatThreads", 1), ("threads", 1)))
            for t in threads:
                yield _parse_thread(cl, t)
            nxt = _pick_continuation(cl, res)
            if not nxt or nxt in seen_tokens:
                break
            seen_tokens.add(nxt)
            continuation = nxt
        return
    except Exception:
        pass

    # フォールバック: fetchSquareChatEvents から thread mid らしき値を推定
    try:
        res = cl.fetchSquareChatEvents(square_chat_mid, limit=max(20, limit))
    except Exception:
        return
    seen_mid: set[str] = set()
    for d in _iter_dictish(res):
        for key in ("squareChatThreadMid", "threadMid", 2, 3):
            v = d.get(key)
            if not isinstance(v, str):
                continue
            s = v.strip()
            if not _is_chat_mid(s):
                continue
            if s == square_chat_mid:
                continue
            if s in seen_mid:
                continue
            seen_mid.add(s)
            title = ""
            for nk in ("name", "title", 4, 6):
                nv = d.get(nk)
                if isinstance(nv, str) and nv.strip() and not _is_chat_mid(nv):
                    title = nv.strip()
                    break
            yield (s, title or "(thread?)")


def main() -> int:
    parser = argparse.ArgumentParser(description="LINE オープンチャット（Square）一覧")
    parser.add_argument("--limit", type=int, default=100, help="getJoinedSquareChats のページサイズ")
    parser.add_argument("--with-threads", action="store_true", help="各チャットの参加中スレッドも表示")
    parser.add_argument("--thread-limit", type=int, default=50, help="getJoinedSquareChatThreads のページサイズ")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    save_root = save_root_from_env()
    cl = build_logged_in_client(save_root)
    if not getattr(cl, "can_use_square", False):
        print("Square(オープンチャット) API が利用できません。ログイン状態やアカウントを確認してください。", file=sys.stderr)
        return 1

    chat_count = 0
    thread_count = 0
    # 標準出力はタブ区切り:
    # CHAT   squareMid  squareChatMid  chatName    squareName
    # THREAD squareChatMid  squareChatThreadMid    threadName
    for square_mid, square_chat_mid, chat_name, square_name in iter_joined_chats(cl, max(1, args.limit)):
        if not square_chat_mid:
            continue
        print(f"CHAT\t{square_mid}\t{square_chat_mid}\t{chat_name}\t{square_name}")
        chat_count += 1
        if args.with_threads:
            for thread_mid, thread_name in iter_threads(cl, square_chat_mid, max(1, args.thread_limit)):
                if not thread_mid:
                    continue
                print(f"THREAD\t{square_chat_mid}\t{thread_mid}\t{thread_name}")
                thread_count += 1

    print(f"# chats={chat_count} threads={thread_count}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
