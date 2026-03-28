#!/usr/bin/env python3
"""
指定 chatMid（またはトーク名の部分一致）の直近メッセージをプレーンテキストで標準出力する。
パイプ先: python \"$LINE_TO_YORITOORI_SCRIPT\" --partner … --group --group-label …

E2EE テキストは可能な範囲で復号。スタンプ・画像等はプレースホルダ。
トークン・JWT は表示しない。
取得は複数の Talk / MessageBox / sync 経路を順に試す（--trace-tries で経路ログ）。
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from chrline_client_utils import build_logged_in_client, save_root_from_env

# インポート用（chrline_list_chats と同じロジックを避けるため最小複製）
from chrline_list_chats_poc import _chat_mid_from, _chat_name, _iter_group_mids

# LINE の created/delivered はミリ秒 UNIX 想定。範囲外は別フィールドの数値と誤認された可能性がある。
_TS_MS_MIN = 946684800000  # 2000-01-01 UTC 前後
_TS_MS_MAX = 4_102_444_800_000  # 2100-01-01 前後（fromtimestamp が扱いやすい範囲）


def _is_plausible_line_timestamp_ms(v: int) -> bool:
    return _TS_MS_MIN <= v <= _TS_MS_MAX


def _format_line_msg_when(ts: int) -> str:
    if ts <= 0 or not _is_plausible_line_timestamp_ms(ts):
        return "?"
    try:
        return datetime.fromtimestamp(ts / 1000.0).strftime("%Y/%m/%d %H:%M")
    except (OSError, OverflowError, ValueError):
        return "?"


def _is_member_mid_map(d: dict) -> bool:
    """GroupExtra.memberMids 等。キーが mid っぽい文字列で値が数値だけのマップは Message ではない。"""
    if len(d) < 2:
        return False
    for k, v in d.items():
        if not isinstance(k, str) or not isinstance(v, (int, float)):
            return False
    return True


def _has_positive_timestamp(cl, x) -> bool:
    for fld, fid in (("createdTime", 5), ("deliveredTime", 6)):
        t = cl.checkAndGetValue(x, fld, fid)
        if t is None and isinstance(x, dict):
            t = x.get(fid) or x.get(fld)
        try:
            v = int(t)
            if _is_plausible_line_timestamp_ms(v):
                return True
        except (TypeError, ValueError):
            continue
    return False


def _looks_like_message_obj(cl, x) -> bool:
    if x is None:
        return False
    if isinstance(x, dict):
        if _is_member_mid_map(x):
            return False
        return (
            _has_positive_timestamp(cl, x)
            or bool(10 in x or x.get("text"))
            or (15 in x and x.get(15) is not None)
            or (x.get("contentType") is not None)
            or bool(4 in x or x.get("id"))
        )
    return (
        _has_positive_timestamp(cl, x)
        or getattr(x, "text", None) is not None
        or getattr(x, "val_10", None) is not None
        or cl.checkAndGetValue(x, "contentType", 15) is not None
        or getattr(x, "val_15", None) is not None
        or getattr(x, "id", None) is not None
        or getattr(x, "val_4", None) is not None
    )


def _v2_anchor_from_node(obj) -> tuple[int, int] | None:
    """MessageBoxV2MessageId 相当: deliveredTime(i64) + messageId(i64)。"""
    if isinstance(obj, dict):
        a, b = obj.get(1), obj.get(2)
    else:
        a = getattr(obj, "deliveredTime", None)
        b = getattr(obj, "messageId", None)
        if a is None:
            a = getattr(obj, "val_1", None)
        if b is None:
            b = getattr(obj, "val_2", None)
    try:
        ia, ib = int(a), int(b)
    except (TypeError, ValueError):
        return None
    if ia <= 0 or ib <= 0:
        return None
    if not _is_plausible_line_timestamp_ms(ia):
        return None
    return ia, ib


def _flexible_pair_from_values(a, b) -> tuple[int, int] | None:
    """
    getPreviousMessageIds 等で、時刻が秒・(id,time) 順・別フィールド番号のときに備える。
    返す時刻は常にミリ秒に正規化する。
    """
    try:
        ia, ib = int(a), int(b)
    except (TypeError, ValueError):
        return None
    if ia == ib:
        return None

    def norm_time_ms(t: int) -> int | None:
        if _is_plausible_line_timestamp_ms(t):
            return t
        if 1_000_000_000 <= t <= 2_600_000_000:
            tms = t * 1000
            if _is_plausible_line_timestamp_ms(tms):
                return tms
        return None

    for first, second in ((ia, ib), (ib, ia)):
        tms = norm_time_ms(first)
        if tms is None:
            continue
        if second <= 0:
            continue
        return (tms, second)
    return None


def _flexible_anchor_from_node(obj) -> tuple[int, int] | None:
    if isinstance(obj, dict):
        cand = [
            (obj.get(1), obj.get(2)),
            (obj.get(2), obj.get(1)),
            (obj.get(3), obj.get(4)),
            (obj.get(4), obj.get(3)),
        ]
        for a, b in cand:
            if a is None or b is None:
                continue
            p = _flexible_pair_from_values(a, b)
            if p:
                return p
        return None
    # MessageBoxV2MessageId 等（名前付きフィールド）
    for a_name, b_name in (
        ("deliveredTime", "messageId"),
        ("messageId", "deliveredTime"),
    ):
        try:
            a = getattr(obj, a_name, None)
            b = getattr(obj, b_name, None)
        except Exception:
            a, b = None, None
        if a is not None and b is not None:
            p = _flexible_pair_from_values(a, b)
            if p:
                return p
    # DummyThrift: val_1 と val_2 以外の隣接ペア（別スキーマ対策）
    for i in range(1, 9):
        a = getattr(obj, f"val_{i}", None)
        b = getattr(obj, f"val_{i + 1}", None)
        if a is not None and b is not None:
            p = _flexible_pair_from_values(a, b)
            if p:
                return p
    return None


def _anchors_from_adjacent_ints(seq) -> list[tuple[int, int]]:
    """リストが int のみの列のとき、隣接ペアから (時刻ms, messageId) 候補を拾う。"""
    if not isinstance(seq, (list, tuple)) or len(seq) < 2:
        return []
    n = min(64, len(seq))
    for x in seq[:n]:
        if type(x) is bool or not isinstance(x, int):
            return []
    out: list[tuple[int, int]] = []
    for i in range(min(len(seq), n) - 1):
        p = _flexible_pair_from_values(seq[i], seq[i + 1])
        if p:
            out.append(p)
    return out


def _deep_collect_loose_anchors(root, max_depth: int = 16) -> list[tuple[int, int]]:
    """厳密な MessageBoxV2MessageId 以外の (時刻, messageId) ペアを拾う。"""
    seen: set[int] = set()
    stack: list[tuple[object, int]] = [(root, 0)]
    out: list[tuple[int, int]] = []

    while stack:
        cur, d = stack.pop()
        if cur is None or d > max_depth:
            continue
        if isinstance(cur, (str, int, float, bool, bytes)):
            continue
        oid = id(cur)
        if oid in seen:
            continue
        seen.add(oid)

        p = _flexible_anchor_from_node(cur)
        if p is not None:
            out.append(p)

        if isinstance(cur, (list, tuple)):
            out.extend(_anchors_from_adjacent_ints(cur))
            if len(cur) == 2:
                p2 = _flexible_pair_from_values(cur[0], cur[1])
                if p2 is not None:
                    out.append(p2)
            for x in cur:
                stack.append((x, d + 1))
        elif isinstance(cur, dict):
            for x in cur.values():
                stack.append((x, d + 1))
        elif hasattr(cur, "dd"):
            try:
                for x in cur.dd().values():
                    stack.append((x, d + 1))
            except Exception:
                pass
        else:
            for i in range(1, 32):
                x = getattr(cur, f"val_{i}", None)
                if x is not None:
                    stack.append((x, d + 1))

    uniq: dict[tuple[int, int], None] = {}
    for p in out:
        uniq[p] = None
    return list(uniq.keys())


def _deep_collect_v2_anchors(root, max_depth: int = 14) -> list[tuple[int, int]]:
    seen: set[int] = set()
    stack: list[tuple[object, int]] = [(root, 0)]
    out: list[tuple[int, int]] = []

    while stack:
        cur, d = stack.pop()
        if cur is None or d > max_depth:
            continue
        if isinstance(cur, (str, int, float, bool, bytes)):
            continue
        oid = id(cur)
        if oid in seen:
            continue
        seen.add(oid)

        pair = _v2_anchor_from_node(cur)
        if pair is not None:
            out.append(pair)

        if isinstance(cur, (list, tuple)):
            for x in cur:
                stack.append((x, d + 1))
        elif isinstance(cur, dict):
            for x in cur.values():
                stack.append((x, d + 1))
        elif hasattr(cur, "dd"):
            try:
                for x in cur.dd().values():
                    stack.append((x, d + 1))
            except Exception:
                pass
        else:
            for i in range(1, 32):
                x = getattr(cur, f"val_{i}", None)
                if x is not None:
                    stack.append((x, d + 1))
    # 重複除去（新しいアンカーを優先）
    uniq: dict[tuple[int, int], None] = {}
    for p in out:
        uniq[p] = None
    return list(uniq.keys())


def _deep_collect_message_objects(cl, root, max_depth: int = 14) -> list:
    """
    getMessageBoxesByIds 等のネストした応答から Message らしきオブジェクトを列挙する。
    """
    seen: set[int] = set()
    stack: list[tuple[object, int]] = [(root, 0)]
    out: list = []

    while stack:
        cur, d = stack.pop()
        if cur is None or d > max_depth:
            continue
        if isinstance(cur, (str, int, float, bool, bytes)):
            continue
        oid = id(cur)
        if oid in seen:
            continue
        seen.add(oid)

        if isinstance(cur, (list, tuple)):
            if cur and _looks_like_message_obj(cl, cur[0]):
                out.extend(cur)
            else:
                for x in cur:
                    stack.append((x, d + 1))
            continue
        if _looks_like_message_obj(cl, cur):
            out.append(cur)
            continue
        if isinstance(cur, dict):
            for x in cur.values():
                stack.append((x, d + 1))
            continue
        if hasattr(cur, "dd"):
            try:
                for x in cur.dd().values():
                    stack.append((x, d + 1))
            except Exception:
                pass
            continue
        for i in range(1, 32):
            x = getattr(cur, f"val_{i}", None)
            if x is not None:
                stack.append((x, d + 1))
    return out


def _msg_delivered_or_created(cl, msg) -> int | None:
    for fld, fid in (("deliveredTime", 6), ("createdTime", 5)):
        t = cl.checkAndGetValue(msg, fld, fid)
        if t is None and isinstance(msg, dict):
            t = msg.get(fid) or msg.get(fld)
        if t is not None:
            try:
                v = int(t)
                if _is_plausible_line_timestamp_ms(v):
                    return v
            except (TypeError, ValueError):
                continue
    return None


def _msg_numeric_line_id(cl, msg) -> int | None:
    mid = cl.checkAndGetValue(msg, "id", 4)
    if mid is None and isinstance(msg, dict):
        mid = msg.get(4) or msg.get("id")
    if isinstance(mid, int):
        return mid
    if isinstance(mid, str) and mid.isdigit():
        return int(mid)
    return None


def _messages_from_response(cl, res, _depth: int = 0) -> list:
    """
    getRecentMessagesV2 / getPreviousMessagesV2 等の応答から Message のリストを取り出す。
    Thrift のフィールド番号は版でずれるため、dd() も走査する。
    """
    if res is None or _depth > 5:
        return []
    if isinstance(res, (list, tuple)) and res and _looks_like_message_obj(cl, res[0]):
        return list(res)

    for fid in range(1, 20):
        m = cl.checkAndGetValue(res, "messages", fid)
        if isinstance(m, (list, tuple)) and m and _looks_like_message_obj(cl, m[0]):
            return list(m)

    if isinstance(res, dict):
        for k in sorted(res.keys()):
            v = res[k]
            if isinstance(v, (list, tuple)) and v and _looks_like_message_obj(cl, v[0]):
                return list(v)

    if hasattr(res, "dd"):
        for _fid, v in sorted(res.dd().items()):
            if isinstance(v, (list, tuple)) and v and _looks_like_message_obj(cl, v[0]):
                return list(v)
        for _fid, v in sorted(res.dd().items()):
            if v is not None and not isinstance(
                v, (list, tuple, str, int, float, bool, bytes)
            ):
                sub = _messages_from_response(cl, v, _depth + 1)
                if sub:
                    return sub

    msgs = cl.checkAndGetValue(res, "messages", 1)
    if msgs is None and isinstance(res, dict):
        msgs = res.get(1) or res.get("messages")
    if isinstance(msgs, (list, tuple)):
        return list(msgs)
    if msgs is not None:
        return [msgs]
    return []


def _nonempty_messages(cl, res) -> list | None:
    m = _messages_from_response(cl, res)
    return m if m else None


def _try_fetch_with_time_message_id(
    cl, mid: str, n: int, dt: int, nid: int
) -> tuple[object, list] | None:
    """同一 (deliveredTime, messageId) で Talk 系の複数 RPC を順に試す。"""
    triers = [
        ("getPreviousMessagesV2WithRequest", lambda: cl.getPreviousMessagesV2WithRequest(mid, dt, nid, n)),
        (
            "getPreviousMessagesV2WithReadCount",
            lambda: cl.getPreviousMessagesV2WithReadCount(mid, dt, nid, min(n, 101)),
        ),
        ("getPreviousMessagesV2", lambda: cl.getPreviousMessagesV2(mid, dt, nid, n)),
    ]
    for _label, fn in triers:
        try:
            r = fn()
        except Exception:
            continue
        m = _nonempty_messages(cl, r)
        if m:
            return (r, m)
    return None


def _try_sync_previous_from_anchors(
    cl, mid: str, n: int, *roots: object
) -> tuple[object, list] | None:
    """MessageBox ツリー内の MessageBoxV2MessageId を列挙し、複数の取得 API で試す。"""
    pairs: list[tuple[int, int]] = []
    for root in roots:
        if root is None:
            continue
        pairs.extend(_deep_collect_v2_anchors(root))
        pairs.extend(_deep_collect_loose_anchors(root))
    if not pairs:
        return None
    pairs = list(dict.fromkeys(pairs))
    seen: set[tuple[int, int]] = set()
    for dt, nid in sorted(pairs, reverse=True):
        if (dt, nid) in seen:
            continue
        seen.add((dt, nid))
        hit = _try_fetch_with_time_message_id(cl, mid, n, dt, nid)
        if hit is not None:
            return hit
    return None


def _trace(trace: bool, msg: str) -> None:
    if trace:
        print(f"# trace: {msg}", file=sys.stderr)


def _trace_exc(trace: bool, label: str, e: BaseException) -> None:
    if not trace:
        return
    msg = f"{type(e).__name__}: {e!s}"
    if len(msg) > 180:
        msg = msg[:177] + "..."
    print(f"# trace: {label} 例外 {msg}", file=sys.stderr)


def _trace_previous_message_ids_response(trace: bool, pid_res) -> None:
    if not trace:
        return
    t = type(pid_res).__name__
    if isinstance(pid_res, (list, tuple)):
        print(
            f"# trace: getPreviousMessageIds 応答 {t} len={len(pid_res)}",
            file=sys.stderr,
        )
        if pid_res:
            z = pid_res[0]
            print(f"# trace:   [0] type={type(z).__name__}", file=sys.stderr)
    elif hasattr(pid_res, "dd"):
        try:
            ddmap = pid_res.dd()
            keys = sorted(ddmap.keys())
        except Exception:
            ddmap, keys = {}, []
        print(f"# trace: getPreviousMessageIds 応答 {t} dd.keys={keys}", file=sys.stderr)
        for k in keys:
            try:
                v = ddmap[k]
            except Exception:
                v = None
            vn = type(v).__name__
            if isinstance(v, (list, tuple)):
                fe = type(v[0]).__name__ if v else "empty"
                print(
                    f"# trace:   pid field {k}: {vn} len={len(v)} first={fe}",
                    file=sys.stderr,
                )
            else:
                s = repr(v)
                if len(s) > 120:
                    s = s[:117] + "..."
                print(f"# trace:   pid field {k}: {vn} {s}", file=sys.stderr)
    else:
        print(f"# trace: getPreviousMessageIds 応答 {t}", file=sys.stderr)


def _trace_previous_message_ids_interpretation(trace: bool, pid_res) -> None:
    """アンカー 0 件時、応答形状からサーバー側の空返却かどうかを補足する。"""
    if not trace or pid_res is None or not hasattr(pid_res, "dd"):
        return
    try:
        ddm = pid_res.dd()
        v1 = ddm.get(1)
        v2 = ddm.get(2)
    except Exception:
        return
    if isinstance(v1, list) and len(v1) == 0:
        tail = f" フィールド2={v2!r}" if v2 is not None else ""
        _trace(
            trace,
            "getPreviousMessageIds → 解釈: フィールド1が空リスト"
            f"{tail}。LINE サーバーがこのセッションにメッセージIDを返していない状態です"
            "（パース不具合ではなく、E2EE・DESKTOP 未同期などで起きうる）。",
        )


def _anchors_from_previous_message_ids_top_level(cl, pid_res) -> list[tuple[int, int]]:
    """
    getPreviousMessageIds の応答が DummyThrift でルート直下に val_1/val_2 だけある場合、
    再帰走査が子に届かずアンカー 0 件になる。フィールド番号で子を明示取得してから掘る。
    """
    out: list[tuple[int, int]] = []
    if pid_res is None:
        return out
    for fid in (1, 2, 3, 4, 5):
        try:
            v = cl.checkAndGetValue(pid_res, fid)
        except Exception:
            v = None
        if v is None:
            continue
        subroots = list(v) if isinstance(v, (list, tuple)) else [v]
        for sub in subroots:
            if sub is None:
                continue
            out.extend(_deep_collect_v2_anchors(sub))
            out.extend(_deep_collect_loose_anchors(sub))
    return out


def _fetch_messages(
    cl,
    mid: str,
    count: int,
    *,
    trace: bool = False,
    skip_e2ee_key_register: bool = False,
):
    """
    直近メッセージ取得。CHRLINE で利用可能な複数経路を順に試す（E2EE グループ向けの追加試行含む）。

    getNextMessagesV2 / getRecentMessages / getMessageBoxCompactWrapUpListV2 は
    現行 DESKTOPWIN トーク RPC で Invalid method name となるため試行しない。
    """
    n = max(1, min(count, 300))
    res = cl.getRecentMessagesV2(mid, n)
    msgs = _messages_from_response(cl, res)
    if msgs:
        _trace(trace, "getRecentMessagesV2 → 成功")
        return res, msgs
    _trace(trace, "getRecentMessagesV2 → 0件")

    if not skip_e2ee_key_register:
        try:
            cl.tryRegisterE2EEGroupKey(mid)
            _trace(trace, "tryRegisterE2EEGroupKey 実行")
        except Exception as e:
            _trace_exc(trace, "tryRegisterE2EEGroupKey", e)
        res = cl.getRecentMessagesV2(mid, n)
        msgs = _messages_from_response(cl, res)
        if msgs:
            _trace(trace, "getRecentMessagesV2（E2EE 登録後）→ 成功")
            return res, msgs
        _trace(trace, "getRecentMessagesV2（E2EE 登録後）→ 0件")

    try:
        res2 = cl.getPreviousMessagesV2(mid, 0, 0, n)
    except Exception as e:
        _trace_exc(trace, "getPreviousMessagesV2(0,0)", e)
        res2 = None
    if res2 is not None:
        msgs2 = _messages_from_response(cl, res2)
        if msgs2:
            _trace(trace, "getPreviousMessagesV2(0,0) → 成功")
            return res2, msgs2
        _trace(trace, "getPreviousMessagesV2(0,0) → 0件")

    try:
        res_w = cl.getPreviousMessagesV2WithReadCount(mid, 0, 0, min(n, 101))
        mw = _nonempty_messages(cl, res_w)
        if mw:
            _trace(trace, "getPreviousMessagesV2WithReadCount(0,0) → 成功")
            return res_w, mw
        _trace(trace, "getPreviousMessagesV2WithReadCount(0,0) → 0件")
    except Exception as e:
        _trace_exc(trace, "getPreviousMessagesV2WithReadCount(0,0)", e)

    try:
        pid_res = cl.getPreviousMessageIds(mid, min(100, n))
        id_pairs = _deep_collect_v2_anchors(pid_res) + _deep_collect_loose_anchors(
            pid_res
        )
        id_pairs = list(dict.fromkeys(id_pairs))
        src = "strict+loose"
        if not id_pairs:
            id_pairs = _anchors_from_previous_message_ids_top_level(cl, pid_res)
            id_pairs = list(dict.fromkeys(id_pairs))
            if id_pairs:
                src = "val_1〜5 展開後"
        _trace(
            trace,
            f"getPreviousMessageIds アンカー候補 {len(id_pairs)} 件 ({src})",
        )
        if not id_pairs:
            _trace_previous_message_ids_response(trace, pid_res)
            _trace_previous_message_ids_interpretation(trace, pid_res)
        seen_pid: set[tuple[int, int]] = set()
        for dt, nid in sorted(id_pairs, reverse=True)[:40]:
            if (dt, nid) in seen_pid:
                continue
            seen_pid.add((dt, nid))
            hit = _try_fetch_with_time_message_id(cl, mid, n, dt, nid)
            if hit is not None:
                _trace(trace, "getPreviousMessageIds 由来のアンカーで取得成功")
                return hit
    except Exception as e:
        _trace_exc(trace, "getPreviousMessageIds 経路", e)

    mb = None
    mb2 = None
    mb3 = None
    extra_mb_roots: list = []
    try:
        mb = cl.getMessageBoxesByIds([mid])
    except Exception as e:
        _trace_exc(trace, "getMessageBoxesByIds", e)
    try:
        mb2 = cl.getMessageBoxes(mid, mid, True, 1, False, n, False, 0)
    except Exception as e:
        _trace_exc(trace, "getMessageBoxes(mid,mid,limit=1)", e)
    try:
        mb3 = cl.getMessageBoxes(mid, mid, True, 20, False, n, False, 0)
        extra_mb_roots.append(mb3)
    except Exception as e:
        _trace_exc(trace, "getMessageBoxes(mid,mid,limit=20)", e)
    for sync_reason in (3, 4, 0):
        try:
            mbs = cl.getMessageBoxes(mid, mid, True, 1, False, n, False, sync_reason)
            extra_mb_roots.append(mbs)
        except Exception:
            continue

    sync_hit = _try_sync_previous_from_anchors(cl, mid, n, mb, mb2, *extra_mb_roots)
    if sync_hit is not None:
        _trace(trace, "MessageBox ツリー + アンカー RPC → 成功")
        return sync_hit

    if mb is not None:
        boxed = _deep_collect_message_objects(cl, mb)
        if boxed:
            _trace(trace, "getMessageBoxesByIds 深層から Message 候補")
            return mb, boxed
    if mb2 is not None:
        boxed2 = _deep_collect_message_objects(cl, mb2)
        if boxed2:
            _trace(trace, "getMessageBoxes(limit=1) 深層から Message 候補")
            return mb2, boxed2
    for root in extra_mb_roots:
        if root is None:
            continue
        bx = _deep_collect_message_objects(cl, root)
        if bx:
            _trace(trace, "getMessageBoxes(拡張) 深層から Message 候補")
            return root, bx

    for anchor_src in (x for x in (mb, mb2, *extra_mb_roots) if x is not None):
        candidates = _deep_collect_message_objects(cl, anchor_src)
        best = None
        best_key = (-1, -1)
        for m in candidates:
            dt = _msg_delivered_or_created(cl, m)
            nid = _msg_numeric_line_id(cl, m)
            if dt is None or nid is None:
                continue
            key = (dt, nid)
            if key > best_key:
                best_key = key
                best = (dt, nid)
        if best is not None:
            dt, nid = best
            hitm = _try_fetch_with_time_message_id(cl, mid, n, dt, nid)
            if hitm is not None:
                _trace(trace, "Message 候補から推測アンカー → 成功")
                return hitm

    try:
        rev = getattr(cl, "revision", 0)
        rev_i = int(rev) if rev is not None else 0
        if rev_i < 0:
            rev_i = 0
        cl.sync(rev_i, 80, 3)
        _trace(trace, "sync(MANUAL_SYNC) 実行")
    except Exception as e:
        _trace_exc(trace, "sync(MANUAL_SYNC)", e)

    res_a = cl.getRecentMessagesV2(mid, n)
    msgs_a = _messages_from_response(cl, res_a)
    if msgs_a:
        _trace(trace, "sync 後 getRecentMessagesV2 → 成功")
        return res_a, msgs_a
    _trace(trace, "sync 後 getRecentMessagesV2 → 0件")

    try:
        mb_a = cl.getMessageBoxesByIds([mid])
        hit_a = _try_sync_previous_from_anchors(cl, mid, n, mb_a)
        if hit_a is not None:
            _trace(trace, "sync 後 getMessageBoxesByIds+アンカー → 成功")
            return hit_a
    except Exception as e:
        _trace_exc(trace, "sync 後 getMessageBoxesByIds", e)

    return res, msgs


def _msg_time(cl, msg) -> int:
    # created を先に。delivered が別用途の数値と誤認されるケースがある。
    for fld, fid in (("createdTime", 5), ("deliveredTime", 6)):
        t = cl.checkAndGetValue(msg, fld, fid)
        if t is None and isinstance(msg, dict):
            t = msg.get(fid) or msg.get(fld)
        try:
            v = int(t)
            if _is_plausible_line_timestamp_ms(v):
                return v
        except (TypeError, ValueError):
            continue
    return 0


def _coerce_line_mid_str(m) -> str | None:
    """_from が dict（誤パース）のときは str() せず、単一 mid キーだけ採用する。"""
    if m is None:
        return None
    if isinstance(m, str):
        s = m.strip()
        return s if s else None
    if isinstance(m, dict):
        if _is_member_mid_map(m):
            return None
        if len(m) == 1:
            k = next(iter(m.keys()))
            if isinstance(k, str) and k.strip():
                return k.strip()
        return None
    if isinstance(m, (bytes, bytearray)):
        try:
            s = m.decode("utf-8", errors="replace").strip()
        except Exception:
            return None
        return s if s else None
    return None


def _msg_sender_mid(cl, msg) -> str | None:
    m = cl.checkAndGetValue(msg, "_from", 1) or cl.checkAndGetValue(msg, "from", 1)
    if m is None and isinstance(msg, dict):
        m = msg.get(1) or msg.get("_from")
    return _coerce_line_mid_str(m)


def _msg_content_type(cl, msg) -> int | None:
    ct = cl.checkAndGetValue(msg, "contentType", 15)
    if ct is None and isinstance(msg, dict):
        v = msg.get(15) if 15 in msg else msg.get("contentType")
        ct = v
    try:
        return int(ct) if ct is not None else None
    except (TypeError, ValueError):
        return None


def _msg_plain_text(cl, msg) -> str | None:
    t = cl.checkAndGetValue(msg, "text", 10)
    if t is None and isinstance(msg, dict):
        t = msg.get(10) or msg.get("text")
    if isinstance(t, str) and t.strip():
        return t.strip()
    return None


def _msg_body_line(cl, msg) -> str:
    ct = _msg_content_type(cl, msg)
    plain = _msg_plain_text(cl, msg)
    if plain:
        return plain
    if ct == 0 or ct is None:
        try:
            dec = cl.decryptE2EETextMessage(msg, isSelf=False)
            if isinstance(dec, str) and dec.strip():
                return dec.strip()
        except Exception:
            pass
        try:
            dec2 = cl.decryptE2EETextMessage(msg, isSelf=True)
            if isinstance(dec2, str) and dec2.strip():
                return dec2.strip()
        except Exception:
            pass
    if ct == 7:
        return "[スタンプ]"
    if ct in (1, 2, 3, 14):
        return "[メディア]"
    return "[本文なし · E2EE 未復号またはコンパクトプレビューのみ]"


def _is_compact_noise_row(cl, msg, target_chat_mid: str, body: str) -> bool:
    """
    MessageBox 等のコンパクト応答で、フィールド 1 に chatMid が入り本文・時刻が空の
    断片が「メッセージ」として混入することがある。出力から除外する。
    """
    sm = _msg_sender_mid(cl, msg)
    if not sm or sm != target_chat_mid:
        return False
    if _msg_time(cl, msg) != 0:
        return False
    if _msg_plain_text(cl, msg):
        return False
    return body.startswith("[本文なし")


def _resolve_chat_mid(cl, chat_mid: str | None, title_sub: str | None) -> str:
    if chat_mid:
        return chat_mid.strip()
    if not title_sub:
        print("エラー: --chat-mid か --title-substring のどちらかが必要です。", file=sys.stderr)
        sys.exit(1)
    needle = title_sub.strip().lower()
    mids = _iter_group_mids(cl)
    batch = 30
    matches: list[tuple[str, str]] = []
    for i in range(0, len(mids), batch):
        chunk = mids[i : i + batch]
        try:
            res = cl.getChats(chunk)
        except Exception as e:
            print(f"getChats エラー: {e}", file=sys.stderr)
            sys.exit(1)
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
            if needle in name.lower():
                matches.append((str(mid), name))
    if not matches:
        print(f"エラー: 名前に「{title_sub}」を含むトークが見つかりません。", file=sys.stderr)
        sys.exit(1)
    if len(matches) > 1:
        print("複数一致しました。--chat-mid を指定してください:", file=sys.stderr)
        for mid, name in matches:
            print(f"  {mid}\t{name}", file=sys.stderr)
        sys.exit(1)
    return matches[0][0]


def main() -> int:
    parser = argparse.ArgumentParser(description="LINE トークの直近メッセージを標準出力")
    parser.add_argument("--chat-mid", default="", help="トークの chatMid（一覧で確認）")
    parser.add_argument(
        "--title-substring",
        default="",
        help="グループ名の部分一致（1件に絞れないときは一覧を stderr に出して終了）",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=80,
        help="取得する最大件数（getRecentMessagesV2、フォールバック時は getPreviousMessagesV2 等）",
    )
    parser.add_argument(
        "--debug-response",
        action="store_true",
        help="応答の型と dd() のキー一覧を stderr に出す（デバッグ用）",
    )
    parser.add_argument(
        "--trace-tries",
        action="store_true",
        help="試した取得経路を stderr に逐次出す（E2EE 等の切り分け用）",
    )
    parser.add_argument(
        "--skip-e2ee-key-register",
        action="store_true",
        help="tryRegisterE2EEGroupKey を呼ばない（サーバー側キー登録の副作用を避ける）",
    )
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    save_root = save_root_from_env()
    cl = build_logged_in_client(save_root)

    mid = _resolve_chat_mid(
        cl,
        args.chat_mid or None,
        args.title_substring or None,
    )

    try:
        res, msgs = _fetch_messages(
            cl,
            mid,
            args.count,
            trace=args.trace_tries,
            skip_e2ee_key_register=args.skip_e2ee_key_register,
        )
    except Exception as e:
        print(f"メッセージ取得エラー: {e}", file=sys.stderr)
        return 1

    if args.debug_response and res is not None:
        print(f"# debug: type={type(res).__name__}", file=sys.stderr)
        if isinstance(res, (list, tuple)):
            print(f"# debug: sequence len={len(res)}", file=sys.stderr)
            if not res:
                print(
                    "# debug: 空リスト — API は成功しているがメッセージ 0 件。"
                    " E2EE・公式 PC 未ログイン・MessageBox 未同期のときに起きやすい。",
                    file=sys.stderr,
                )
            else:
                z = res[0]
                print(
                    f"# debug: [0] type={type(z).__name__} looks_msg={_looks_like_message_obj(cl, z)}",
                    file=sys.stderr,
                )
        if hasattr(res, "dd"):
            print(f"# debug: dd keys={sorted(res.dd().keys())}", file=sys.stderr)

    if not msgs:
        print("# （メッセージ0件、または応答形式が想定外です）", file=sys.stderr)
        print("# --debug-response で応答構造を確認できます。", file=sys.stderr)
        return 0

    my_mid = getattr(cl, "mid", None)
    msgs.sort(key=lambda m: _msg_time(cl, m))

    shown = 0
    for msg in msgs:
        ts = _msg_time(cl, msg)
        body = _msg_body_line(cl, msg)
        if _is_compact_noise_row(cl, msg, mid, body):
            if args.debug_response:
                print(
                    "# debug: ノイズ行をスキップ（送信者欄に取得対象の chatMid が入ったコンパクト断片）",
                    file=sys.stderr,
                )
            continue
        when = _format_line_msg_when(ts)
        sm = _msg_sender_mid(cl, msg)
        if sm and my_mid and sm == my_mid:
            who = "自分"
        elif sm:
            who = sm[:12] + "…" if len(sm) > 14 else sm
        else:
            who = "?"
        print(f"{when}\t{who}\t{body}")
        shown += 1

    if shown == 0:
        print(
            "# （表示できるメッセージはありませんでした。E2EE グループや PC 未同期の可能性があります）",
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
