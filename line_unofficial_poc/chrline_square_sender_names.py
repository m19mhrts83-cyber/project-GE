"""Square オープンチャット: 送信者 MID → 表示名の解決。"""
from __future__ import annotations

from typing import Any

BATCH_SIZE = 50
SELF_LABEL = "自分"
UNKNOWN_LABEL = "不明"


def _sanitize_heading_part(text: str) -> str:
    s = (text or "").strip().replace("\n", " ").replace("｜", " ")
    return s


def _short_mid(mid: str) -> str:
    s = (mid or "").strip()
    if not s:
        return UNKNOWN_LABEL
    if len(s) <= 10:
        return s
    return f"{s[:8]}…"


def build_my_square_mid_map(cl, chat_mids: set[str] | list[str]) -> dict[str, str]:
    """チャット MID ごとの自分 squareMemberMid。"""
    out: dict[str, str] = {}
    for cmid in chat_mids:
        if not cmid:
            continue
        try:
            smid = cl.getMySquareMidByChatMid(cmid)
        except Exception:
            smid = None
        if isinstance(smid, str) and smid.strip():
            out[str(cmid)] = smid.strip()
    return out


def _member_mid(cl, member: Any) -> str:
    for fid in (1, 2):
        v = cl.checkAndGetValue(member, "squareMemberMid", fid)
        if v is None and isinstance(member, dict):
            v = member.get(fid) or member.get("squareMemberMid")
        s = str(v or "").strip()
        if s:
            return s
    return ""


def _member_display_name(cl, member: Any) -> str:
    for fid in (3, 4):
        v = cl.checkAndGetValue(member, "displayName", fid)
        if v is None and isinstance(member, dict):
            v = member.get(fid) or member.get("displayName")
        if isinstance(v, str) and v.strip():
            return _sanitize_heading_part(v)
    return ""


def _iter_square_members(cl, resp: Any) -> list[Any]:
    for key, fid in (("members", 1), ("squareMembers", 1), ("members", 2)):
        items = cl.checkAndGetValue(resp, key, fid)
        if items is None and isinstance(resp, dict):
            items = resp.get(fid) or resp.get(key)
        if isinstance(items, list) and items:
            return items
    if isinstance(resp, list) and resp:
        return resp
    return []


class SquareSenderNameResolver:
    """getSquareMembers で表示名を解決（セッション内キャッシュ）。"""

    def __init__(self, cl, *, my_square_mids: dict[str, str] | None = None):
        self.cl = cl
        self.my_square_mids = dict(my_square_mids or {})
        self._my_square_mid_set = {v for v in self.my_square_mids.values() if v}
        self._cache: dict[str, str] = {}
        self._pending: set[str] = set()
        self._failed: set[str] = set()
        for smid in self._my_square_mid_set:
            self._cache[smid] = SELF_LABEL

    def register_my_square_mid(self, chat_mid: str, square_member_mid: str) -> None:
        chat_mid = (chat_mid or "").strip()
        square_member_mid = (square_member_mid or "").strip()
        if not square_member_mid:
            return
        if chat_mid:
            self.my_square_mids[chat_mid] = square_member_mid
        self._my_square_mid_set.add(square_member_mid)
        self._cache[square_member_mid] = SELF_LABEL

    def is_self(self, sender_mid: str, *, chat_mid: str = "") -> bool:
        s = (sender_mid or "").strip()
        if not s:
            return False
        if s in self._my_square_mid_set:
            return True
        if chat_mid and self.my_square_mids.get(chat_mid) == s:
            return True
        return s == str(getattr(self.cl, "mid", "") or "")

    def queue_many(self, mids: list[str] | set[str]) -> None:
        for mid in mids:
            s = (mid or "").strip()
            if not s or s in self._cache or s in self._failed:
                continue
            self._pending.add(s)

    def flush(self) -> None:
        if not self._pending:
            return
        pending = list(self._pending)
        self._pending.clear()
        for i in range(0, len(pending), BATCH_SIZE):
            chunk = pending[i : i + BATCH_SIZE]
            self._fetch_batch(chunk)

    def _fetch_batch(self, mids: list[str]) -> None:
        if not mids:
            return
        try:
            resp = self.cl.getSquareMembers(mids)
        except Exception:
            for mid in mids:
                self._fetch_single(mid)
            return
        found: set[str] = set()
        for member in _iter_square_members(self.cl, resp):
            smid = _member_mid(self.cl, member)
            if not smid:
                continue
            found.add(smid)
            if smid in self._my_square_mid_set:
                self._cache[smid] = SELF_LABEL
                continue
            name = _member_display_name(self.cl, member)
            self._cache[smid] = name or _short_mid(smid)
        for mid in mids:
            if mid not in found:
                self._fetch_single(mid)

    def _fetch_single(self, mid: str) -> None:
        if mid in self._cache or mid in self._failed:
            return
        if mid in self._my_square_mid_set:
            self._cache[mid] = SELF_LABEL
            return
        try:
            resp = self.cl.getSquareMember(mid)
        except Exception:
            self._failed.add(mid)
            self._cache[mid] = _short_mid(mid)
            return
        member = self.cl.checkAndGetValue(resp, "squareMember", 1)
        if member is None and isinstance(resp, dict):
            member = resp.get(1) or resp.get("squareMember")
        if member is None:
            member = resp
        name = _member_display_name(self.cl, member)
        self._cache[mid] = name or _short_mid(mid)

    def label(self, sender_mid: str, *, chat_mid: str = "") -> str:
        s = (sender_mid or "").strip()
        if not s:
            return UNKNOWN_LABEL
        if self.is_self(s, chat_mid=chat_mid):
            return SELF_LABEL
        if s in self._cache:
            return self._cache[s]
        self.queue_many([s])
        self.flush()
        return self._cache.get(s, _short_mid(s))
