#!/usr/bin/env python3
"""
LINE オープンチャット（Square）差分を Markdown に追記する。

- ルート設定: YAML（--routes-yaml / LINE_OPEN_CHAT_ROUTES_YAML）
- 対応: メインタイムライン + 参加中スレッド
- 状態: LINE_UNOFFICIAL_AUTH_DIR/.chrline_open_chat_state.json
- 重複排除: LINE_UNOFFICIAL_AUTH_DIR/.chrline_open_chat_dedup.json
- スレッド MID 補助: --discover-thread-mids でメインタイムラインのイベントから threadMid 候補を集計し、
  --auto-append-thread-mids で open_chat_routes.yaml の thread_mids に追記（--dry-run 時は YAML も未変更）
- 再ログイン: 保存トークン失効時に QR を出すのは --allow-qr-login のときだけ（取り込み確認で意図したときに付与）
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from chrline_client_utils import (
    build_logged_in_client,
    chrline_throttle,
    open_chat_session_lock,
    probe_square_session,
    recover_session_midrun,
    save_root_from_env,
)
from chrline_dump_messages_poc import _format_line_msg_when, _msg_plain_text, _msg_sender_mid, _msg_time
from chrline_list_open_chats_poc import iter_joined_chats, iter_threads
from chrline_md_utils import insert_block_after_timeline_header, make_summary, wrap_details
from chrline_square_sender_names import SquareSenderNameResolver, build_my_square_mid_map

STATE_FILENAME = ".chrline_open_chat_state.json"
DEDUP_FILENAME = ".chrline_open_chat_dedup.json"

# スレッド専用ストリーム: 失敗時の指数バックオフ（秒）
THREAD_BACKOFF_BASE_SEC = 3600
THREAD_BACKOFF_MAX_SEC = 86400 * 7
THREAD_DELETED_RETRY_SEC = 86400 * 30
# 閉鎖済みとみなし日常差分では再参照しない status（YAML の thread_mids は履歴として維持）
THREAD_CLOSED_STATUSES = frozenset({"closed", "deleted", "join_denied"})


@dataclass
class Route:
    rid: str
    square_chat_mid: str
    title_substring: str
    output_md: Path
    org_label: str
    heading_tag: str
    include_main: bool
    include_threads: bool
    thread_title_substring: str
    thread_mids: list[str]
    thread_titles: dict[str, str]


@dataclass(frozen=True)
class Stream:
    stream_key: str
    square_chat_mid: str
    thread_mid: str
    thread_label: str
    route: Route


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except Exception:
        print("エラー: PyYAML が見つかりません。`pip install pyyaml` を実行してください。", file=sys.stderr)
        raise SystemExit(1)

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as e:
        print(f"エラー: YAML を読めません: {path} ({e})", file=sys.stderr)
        raise SystemExit(1)
    if not isinstance(data, dict):
        print(f"エラー: YAML のトップレベルは map である必要があります: {path}", file=sys.stderr)
        raise SystemExit(1)
    return data


def _parse_routes(path: Path) -> list[Route]:
    data = _load_yaml(path)
    rows = data.get("routes")
    if not isinstance(rows, list) or not rows:
        print("エラー: routes が空、または配列ではありません。", file=sys.stderr)
        raise SystemExit(1)
    out: list[Route] = []
    for i, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            print(f"エラー: routes[{i}] が map ではありません。", file=sys.stderr)
            raise SystemExit(1)
        rid = str(row.get("id") or f"route_{i}")
        square_chat_mid = str(row.get("square_chat_mid") or "").strip()
        title_substring = str(row.get("title_substring") or "").strip()
        output_md_raw = str(row.get("output_md") or "").strip()
        if not output_md_raw:
            print(f"エラー: routes[{i}] output_md は必須です。", file=sys.stderr)
            raise SystemExit(1)
        if not square_chat_mid and not title_substring:
            print(f"エラー: routes[{i}] は square_chat_mid か title_substring のどちらかが必須です。", file=sys.stderr)
            raise SystemExit(1)
        output_md = Path(output_md_raw).expanduser().resolve()
        raw_titles = row.get("thread_titles") or {}
        thread_titles: dict[str, str] = {}
        if isinstance(raw_titles, dict):
            for k, v in raw_titles.items():
                mk = str(k).strip()
                mv = str(v).strip()
                if mk and mv:
                    thread_titles[mk] = mv
        out.append(
            Route(
                rid=rid,
                square_chat_mid=square_chat_mid,
                title_substring=title_substring,
                output_md=output_md,
                org_label=str(row.get("org_label") or rid or "オープンチャット"),
                heading_tag=str(row.get("heading_tag") or "LINEオープンチャット"),
                include_main=bool(row.get("include_main", True)),
                include_threads=bool(row.get("include_threads", True)),
                thread_title_substring=str(row.get("thread_title_substring") or "").strip(),
                thread_mids=[str(x).strip() for x in (row.get("thread_mids") or []) if str(x).strip()],
                thread_titles=thread_titles,
            )
        )
    return out


def _load_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"streams": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("streams"), dict):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return {"streams": {}}


def _save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_dedup(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        keys = data.get("keys")
        if isinstance(keys, list):
            return {str(x) for x in keys if x}
    except (json.JSONDecodeError, OSError):
        pass
    return set()


def _save_dedup(path: Path, keys: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    trimmed = sorted(keys)[-5000:]
    path.write_text(json.dumps({"keys": trimmed}, ensure_ascii=False, indent=2), encoding="utf-8")


def _get(cl, obj: Any, key: str, fid: int | None = None) -> Any:
    if obj is None:
        return None
    v = cl.checkAndGetValue(obj, key, fid) if fid is not None else cl.checkAndGetValue(obj, key)
    if v is not None:
        return v
    if isinstance(obj, dict):
        if key in obj:
            return obj.get(key)
        if fid is not None:
            return obj.get(fid)
    dd = getattr(obj, "dd", None)
    if callable(dd):
        try:
            d = dd()
            if isinstance(d, dict):
                if key in d:
                    return d.get(key)
                if fid is not None:
                    return d.get(fid)
        except Exception:
            pass
    return None


def _pick_list(cl, res: Any, keys: tuple[tuple[str, int], ...]) -> list[Any]:
    for key, fid in keys:
        v = _get(cl, res, key, fid)
        if isinstance(v, list):
            return v
    if isinstance(res, dict):
        for v in res.values():
            if isinstance(v, list):
                return v
    return []


def _deep_find_string(res: Any, wanted_keys: set[str], depth: int = 0) -> str:
    if depth > 7 or res is None:
        return ""
    if isinstance(res, dict):
        for k, v in res.items():
            if str(k) in wanted_keys and isinstance(v, str) and v.strip():
                return v.strip()
        for v in res.values():
            x = _deep_find_string(v, wanted_keys, depth + 1)
            if x:
                return x
    elif isinstance(res, (list, tuple)):
        for v in res:
            x = _deep_find_string(v, wanted_keys, depth + 1)
            if x:
                return x
    else:
        dd = getattr(res, "dd", None)
        if callable(dd):
            try:
                return _deep_find_string(dd(), wanted_keys, depth + 1)
            except Exception:
                pass
    return ""


def _extract_tokens(cl, res: Any, prev_sync: str, prev_cont: str) -> tuple[str, str]:
    sync_token = ""
    cont_token = ""
    for key, fid in (("syncToken", 3), ("nextSyncToken", 4), ("subscriptionSyncToken", 5)):
        v = _get(cl, res, key, fid)
        if isinstance(v, str) and v.strip():
            sync_token = v.strip()
            break
    if not sync_token:
        sync_token = _deep_find_string(res, {"syncToken", "nextSyncToken", "subscriptionSyncToken"})
    for key, fid in (("continuationToken", 4), ("nextContinuationToken", 5), ("token", 6)):
        v = _get(cl, res, key, fid)
        if isinstance(v, str) and v.strip():
            cont_token = v.strip()
            break
    if not cont_token:
        cont_token = _deep_find_string(res, {"continuationToken", "nextContinuationToken"})
    return (sync_token or prev_sync or "", cont_token or prev_cont or "")


def _looks_like_message(cl, x: Any) -> bool:
    if x is None:
        return False
    if _get(cl, x, "id", 4) is not None:
        return True
    if _msg_plain_text(cl, x):
        return True
    ct = _get(cl, x, "contentType", 15)
    if ct is not None:
        return True
    ts = _msg_time(cl, x)
    return bool(ts and ts > 0)


def _deep_find_message(cl, root: Any, depth: int = 0, seen: set[int] | None = None) -> Any | None:
    if seen is None:
        seen = set()
    if root is None or depth > 8:
        return None
    if id(root) in seen:
        return None
    seen.add(id(root))
    if _looks_like_message(cl, root):
        return root
    if isinstance(root, dict):
        first = _get(cl, root, "message", 2) or _get(cl, root, "message", 4)
        if first is not None:
            m = _deep_find_message(cl, first, depth + 1, seen)
            if m is not None:
                return m
        for v in root.values():
            m = _deep_find_message(cl, v, depth + 1, seen)
            if m is not None:
                return m
    elif isinstance(root, (list, tuple)):
        for v in root:
            m = _deep_find_message(cl, v, depth + 1, seen)
            if m is not None:
                return m
    else:
        dd = getattr(root, "dd", None)
        if callable(dd):
            try:
                return _deep_find_message(cl, dd(), depth + 1, seen)
            except Exception:
                return None
    return None


def _iter_message_candidates(cl, root: Any, depth: int = 0, seen: set[int] | None = None):
    if seen is None:
        seen = set()
    if root is None or depth > 8:
        return
    oid = id(root)
    if oid in seen:
        return
    seen.add(oid)
    if _looks_like_message(cl, root):
        yield root
    if isinstance(root, dict):
        for v in root.values():
            yield from _iter_message_candidates(cl, v, depth + 1, seen)
    elif isinstance(root, (list, tuple)):
        for v in root:
            yield from _iter_message_candidates(cl, v, depth + 1, seen)
    else:
        dd = getattr(root, "dd", None)
        if callable(dd):
            try:
                d = dd()
                if isinstance(d, dict):
                    yield from _iter_message_candidates(cl, d, depth + 1, seen)
            except Exception:
                return


def _best_message_from_event(cl, ev: Any) -> Any | None:
    first = _deep_find_message(cl, ev)
    best = None
    best_score = -1
    if first is not None:
        t = _msg_plain_text(cl, first) or ""
        score = 1000 if t.strip() else (10 if _get(cl, first, "contentType", 15) is not None else 1)
        best = first
        best_score = score
    for cand in _iter_message_candidates(cl, ev):
        t = _msg_plain_text(cl, cand) or ""
        score = 1000 + len(t.strip()) if t.strip() else (10 if _get(cl, cand, "contentType", 15) is not None else 1)
        if score > best_score:
            best = cand
            best_score = score
    return best


def _event_type(cl, ev: Any) -> int:
    v = _get(cl, ev, "type", 1)
    try:
        return int(v)
    except (TypeError, ValueError):
        return -1


def _message_text(cl, msg: Any) -> str:
    text = (_msg_plain_text(cl, msg) or "").strip()
    if text:
        return text
    ct = _get(cl, msg, "contentType", 15)
    if ct is None:
        return "[本文なし]"
    return f"[非テキスト contentType={ct}]"


def _event_time(cl, ev: Any) -> int:
    for key, fid in (("createdTime", 2), ("eventTime", 2), ("timestamp", 5)):
        v = _get(cl, ev, key, fid)
        try:
            iv = int(v)
            if iv > 946684800000:  # 2000-01-01
                return iv
        except (TypeError, ValueError):
            continue
    return 0


def _message_id(cl, msg: Any, fallback: str) -> str:
    mid = _get(cl, msg, "id", 4)
    if mid is not None:
        s = str(mid).strip()
        if s:
            return s
    return fallback


def _related_message_id(cl, msg: Any, ev: Any) -> str:
    """
    Square の返信系メッセージで使われる relatedMessageId（field 21）を優先して返す。
    msg に無ければ event 側を深掘りして補完する。
    """
    rid = _get(cl, msg, "relatedMessageId", 21)
    if rid is not None:
        s = str(rid).strip()
        if s:
            return s
    # event 側から補完
    for d in _iter_dicts(ev):
        rv = d.get(21) or d.get("relatedMessageId")
        if rv is None:
            continue
        s = str(rv).strip()
        if s:
            return s
    return ""


def _iter_dicts(root: Any, depth: int = 0):
    if root is None or depth > 8:
        return
    if isinstance(root, dict):
        yield root
        for v in root.values():
            yield from _iter_dicts(v, depth + 1)
    elif isinstance(root, (list, tuple)):
        for v in root:
            yield from _iter_dicts(v, depth + 1)
    else:
        dd = getattr(root, "dd", None)
        if callable(dd):
            try:
                d = dd()
                if isinstance(d, dict):
                    yield from _iter_dicts(d, depth + 1)
            except Exception:
                return


def _dedup_key(stream_key: str, msg_id: str, ts: int, body: str) -> str:
    if msg_id:
        return f"{stream_key}|id:{msg_id}|ts:{ts}"
    h = hashlib.sha1(body.encode("utf-8", errors="replace")).hexdigest()[:16]
    return f"{stream_key}|ts:{ts}|h:{h}"


def _is_chat_mid(s: str) -> bool:
    """chrline_list_open_chats_poc と同基準（メイン / チャット MID の粗い判定）。"""
    return len(s) >= 24 and s[:1] in {"m", "c"}


def _is_thread_mid(s: str) -> bool:
    return len(s) >= 24 and s[:1] == "t"


def _is_square_stream_mid(s: str) -> bool:
    """メインまたはスレッドの Square ストリーム MID。"""
    return _is_chat_mid(s) or _is_thread_mid(s)


def _resolve_thread_mid_via_api(cl, square_chat_mid: str, message_id: str) -> str:
    """メイン上の relatedMessageId からスレッド MID を解決する。"""
    msg_id = str(message_id or "").strip()
    if not msg_id:
        return ""
    try:
        res = cl.getSquareThreadMid(square_chat_mid, msg_id)
    except Exception:
        return ""
    tmid = ""
    if isinstance(res, dict):
        tmid = str(res.get(1) or res.get("threadMid") or "").strip()
    if not tmid and hasattr(cl, "checkAndGetValue"):
        try:
            tmid = str(cl.checkAndGetValue(res, 1, 1) or "").strip()
        except Exception:
            pass
    return tmid if _is_thread_mid(tmid) else ""


def _discover_thread_mids_from_yoritoori(cl, route: Route, square_chat_mid: str) -> Counter[str]:
    """既存 5.やり取り.md の [relatedMessageId] 行から thread MID を一括解決。"""
    if not route.output_md.is_file():
        return Counter()
    text = route.output_md.read_text(encoding="utf-8")
    msg_ids = list(dict.fromkeys(re.findall(r"\[relatedMessageId\]\s*(\d+)", text)))
    cnt: Counter[str] = Counter()
    for msg_id in msg_ids:
        tmid = _resolve_thread_mid_via_api(cl, square_chat_mid, msg_id)
        if tmid:
            cnt[tmid] += 1
    return cnt


def _extract_thread_mids_from_event(ev: Any, square_chat_mid: str) -> set[str]:
    """
    メインタイムラインのイベントから、スレッド MID 候補を抽出する。
    square_chat_mid 自身（メインチャット）と同一の値は除外。
    """
    out: set[str] = set()
    sq = (square_chat_mid or "").strip()
    for d in _iter_dicts(ev):
        for key in (
            "squareChatThreadMid",
            "threadMid",
            "chatThreadMid",
            "squareThreadMid",
        ):
            v = d.get(key)
            if isinstance(v, str):
                t = v.strip()
                if t and t != sq and _is_square_stream_mid(t):
                    out.add(t)
        # thrift フィールド番号（thread 系でよく使われる 1〜3）
        for fid in (1, 2, 3):
            if fid not in d:
                continue
            v = d.get(fid)
            if not isinstance(v, str):
                continue
            t = v.strip()
            if t and t != sq and _is_square_stream_mid(t) and len(t) <= 72:
                out.add(t)
    return out


def _append_thread_mids_to_routes_yaml(
    routes_yaml: Path,
    route_id_to_new_mids: dict[str, list[str]],
) -> int:
    """
    routes の各 id に対し thread_mids を重複なく追記する。
    戻り値: 追記した MID の総数（ルート横断で重複する同一文字列は都度カウント）。
    """
    try:
        import yaml
    except Exception:
        print("エラー: PyYAML が見つかりません。`pip install pyyaml` を実行してください。", file=sys.stderr)
        raise SystemExit(1)

    text = routes_yaml.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    if not isinstance(data, dict) or not isinstance(data.get("routes"), list):
        print(f"エラー: YAML 形式が不正です: {routes_yaml}", file=sys.stderr)
        raise SystemExit(1)

    appended = 0
    for row in data["routes"]:
        if not isinstance(row, dict):
            continue
        rid = str(row.get("id") or "").strip()
        if not rid or rid not in route_id_to_new_mids:
            continue
        new_list = route_id_to_new_mids[rid]
        if not new_list:
            continue
        existing = [str(x).strip() for x in (row.get("thread_mids") or []) if str(x).strip()]
        seen = set(existing)
        for mid in new_list:
            if mid in seen:
                continue
            existing.append(mid)
            seen.add(mid)
            appended += 1
        row["thread_mids"] = existing

    routes_yaml.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    return appended


def _append_thread_titles_to_routes_yaml(
    routes_yaml: Path,
    route_id_to_titles: dict[str, dict[str, str]],
) -> int:
    """thread_titles を routes YAML にマージ。戻り値: 新規追記したエントリ数。"""
    try:
        import yaml
    except Exception:
        print("エラー: PyYAML が見つかりません。", file=sys.stderr)
        raise SystemExit(1)

    data = yaml.safe_load(routes_yaml.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("routes"), list):
        print(f"エラー: YAML 形式が不正です: {routes_yaml}", file=sys.stderr)
        raise SystemExit(1)

    added = 0
    for row in data["routes"]:
        if not isinstance(row, dict):
            continue
        rid = str(row.get("id") or "").strip()
        if not rid or rid not in route_id_to_titles:
            continue
        new_map = route_id_to_titles[rid]
        if not new_map:
            continue
        existing = row.get("thread_titles")
        if not isinstance(existing, dict):
            existing = {}
        for mid, title in new_map.items():
            if mid in existing and existing[mid]:
                continue
            existing[mid] = title
            added += 1
        row["thread_titles"] = existing

    routes_yaml.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    return added


def _joined_thread_mids(cl, square_chat_mid: str) -> set[str]:
    return {tmid for tmid, _ in iter_threads(cl, square_chat_mid, 100) if tmid}


def _thread_title_from_api(cl, res: Any) -> str:
    for key, fid in (("name", 2), ("title", 2), ("threadName", 3), ("displayName", 4)):
        v = _get(cl, res, key, fid)
        if isinstance(v, str) and v.strip() and not _is_square_stream_mid(v.strip()):
            return v.strip()
    return _deep_find_string(res, {"name", "title", "threadName", "displayName"})


def _load_join_confirm_mids(path: Path | None) -> set[str]:
    if path is None or not path.is_file():
        return set()
    out: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            out.add(s)
    return out


def _confirm_join_thread(thread_mid: str, title: str, *, auto_yes: bool) -> bool:
    if auto_yes:
        return True
    label = title or thread_mid
    try:
        ans = input(f"スレッドに参加して取り込みますか? [{label}] mid={thread_mid} [y/N]: ").strip().lower()
    except EOFError:
        print(f"# join スキップ（非対話）: {thread_mid}", file=sys.stderr)
        return False
    return ans in {"y", "yes"}


def _ensure_thread_joined(
    cl,
    square_chat_mid: str,
    thread_mid: str,
    *,
    joined_cache: set[str],
    join_threads: bool,
    join_confirm_file: Path | None,
    join_auto_yes: bool,
) -> bool:
    if thread_mid in joined_cache:
        return True
    if not join_threads and not join_confirm_file and not join_auto_yes:
        return False

    title = ""
    try:
        title = _fetch_thread_title_from_api(cl, square_chat_mid, thread_mid)
    except Exception:
        title = ""

    approved = join_auto_yes
    if join_confirm_file is not None:
        approved = thread_mid in _load_join_confirm_mids(join_confirm_file)
    elif join_threads:
        approved = _confirm_join_thread(thread_mid, title, auto_yes=False)

    if not approved:
        print(f"# join 未承認のためスキップ: {thread_mid}", file=sys.stderr)
        return False

    try:
        cl.joinSquareThread(square_chat_mid, thread_mid)
        joined_cache.add(thread_mid)
        print(f"# joinSquareThread OK: {thread_mid} ({title or '?'})", file=sys.stderr)
        return True
    except Exception as e1:
        try:
            cl.joinSquareChatThread(square_chat_mid, thread_mid)
            joined_cache.add(thread_mid)
            print(f"# joinSquareChatThread OK: {thread_mid} ({title or '?'})", file=sys.stderr)
            return True
        except Exception as e2:
            print(
                f"# join 失敗 ({thread_mid}): joinSquareThread={type(e1).__name__}, "
                f"joinSquareChatThread={type(e2).__name__}",
                file=sys.stderr,
            )
            return False


def _is_fetch_permission_error(exc: BaseException) -> bool:
    code = getattr(exc, "code", None)
    if code == 401:
        return True
    msg = str(exc)
    return "Code: 401" in msg or "don't have permission" in msg.lower()


def _is_session_logged_out_error(exc: BaseException) -> bool:
    msg = str(exc)
    if "V3_TOKEN_CLIENT_LOGGED_OUT" in msg:
        return True
    code = getattr(exc, "code", None)
    if code == 8:
        return True
    return "LOGGED_OUT" in msg.upper()


def _fetch_square_chat_events(
    cl,
    *,
    square_chat_mid: str,
    sync_token: str,
    cont_token: str,
    limit: int,
    thread_mid: str | None,
):
    """fetchSquareChatEvents + スロットル。"""
    chrline_throttle()
    return cl.fetchSquareChatEvents(
        square_chat_mid,
        syncToken=sync_token or None,
        continuationToken=cont_token or None,
        limit=max(1, min(limit, 200)),
        threadMid=thread_mid or None,
    )


def _is_thread_deleted_error(exc: BaseException) -> bool:
    code = getattr(exc, "code", None)
    if code == 404:
        return True
    msg = str(exc)
    return "404" in msg or "刪除" in msg or "削除" in msg or "deleted" in msg.lower()


def _thread_stream_key(square_chat_mid: str, thread_mid: str) -> str:
    return f"{square_chat_mid}::thread::{thread_mid}"


def _is_thread_closed(sdata: dict[str, Any]) -> bool:
    return _stream_health(sdata).get("status") in THREAD_CLOSED_STATUSES


def _is_session_permission_error_text(err: str) -> bool:
    low = err.lower()
    return "401" in err and ("permission" in low or "don't have permission" in low)


def _reopen_false_closed_threads(streams_state: dict[str, Any]) -> int:
    """
    セッション失効 401 で誤って closed 化したスレッドを再開する。
    （closed_reason=degraded かつ 401 permission のみ対象）
    """
    n = 0
    for key, sdata in streams_state.items():
        if "::thread::" not in key:
            continue
        health = _stream_health(sdata)
        if health.get("status") != "closed":
            continue
        if health.get("closed_reason") != "degraded":
            continue
        if not _is_session_permission_error_text(str(health.get("last_error") or "")):
            continue
        has_sync = bool(str(sdata.get("sync_token") or "").strip())
        health["status"] = "ok" if has_sync else "degraded"
        health.pop("closed_reason", None)
        health.pop("skip_until", None)
        health["fail_streak"] = 0
        sdata["health"] = health
        n += 1
    return n


def _migrate_thread_health(streams_state: dict[str, Any]) -> int:
    """join_denied 等を ok / degraded に整理。変更件数を返す。"""
    n = 0
    for key, sdata in streams_state.items():
        if "::thread::" not in key:
            continue
        health = _stream_health(sdata)
        status = str(health.get("status") or "")
        has_sync = bool(str(sdata.get("sync_token") or "").strip())
        if status == "join_denied" and has_sync:
            health["status"] = "ok"
            health.pop("skip_until", None)
            health.pop("last_error", None)
            sdata["health"] = health
            n += 1
        elif status == "join_denied" and not has_sync:
            # join 失敗だけでは永久 closed にしない（fetch 再試行のため degraded）
            health["status"] = "degraded"
            health.pop("closed_reason", None)
            health.pop("skip_until", None)
            health["fail_streak"] = 0
            sdata["health"] = health
            n += 1
    return n


def _reopen_false_join_denied_threads(
    streams_state: dict[str, Any],
    active_thread_mids: set[str] | None = None,
) -> int:
    """
    join 試行失敗を理由に closed 化されたスレッドを再開する。
    YAML 登録分（active_thread_mids）または sync_token ありは fetch 再試行の対象。
    """
    n = 0
    active = active_thread_mids or set()
    for key, sdata in streams_state.items():
        if "::thread::" not in key:
            continue
        health = _stream_health(sdata)
        if health.get("status") != "closed":
            continue
        if health.get("closed_reason") != "join_denied":
            continue
        tmid = key.split("::thread::", 1)[-1]
        has_sync = bool(str(sdata.get("sync_token") or "").strip())
        if tmid not in active and not has_sync:
            continue
        health["status"] = "ok" if has_sync else "degraded"
        health.pop("closed_reason", None)
        health.pop("skip_until", None)
        health["fail_streak"] = 0
        sdata["health"] = health
        n += 1
    return n


def _stream_health(sdata: dict[str, Any]) -> dict[str, Any]:
    h = sdata.get("health")
    return dict(h) if isinstance(h, dict) else {}


def _parse_health_ts(raw: Any) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    s = str(raw).strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _health_skip_reason(sdata: dict[str, Any], *, now: float | None = None) -> str:
    """非空ならスキップ理由（バックオフ中・削除済みクールダウン）。"""
    now = time.time() if now is None else now
    health = _stream_health(sdata)
    skip_until = _parse_health_ts(health.get("skip_until"))
    if skip_until is not None and now < skip_until:
        status = str(health.get("status") or "degraded")
        return f"{status} backoff"
    return ""


def _heal_degraded_threads_for_sync(streams_state: dict[str, Any]) -> set[str]:
    """
    degraded かつ sync_token 空のスレッドから skip_until / fail_streak をクリアする。
    closed / join_denied / deleted は触らない。heal した stream_key 集合を返す。
    """
    healed: set[str] = set()
    for key, sdata in streams_state.items():
        if "::thread::" not in key:
            continue
        health = _stream_health(sdata)
        status = str(health.get("status") or "")
        if status in THREAD_CLOSED_STATUSES:
            continue
        if status != "degraded":
            continue
        if str(sdata.get("sync_token") or "").strip():
            continue
        health.pop("skip_until", None)
        health["fail_streak"] = 0
        sdata["health"] = health
        healed.add(key)
    return healed


def _health_on_success(sdata: dict[str, Any]) -> dict[str, Any]:
    health = _stream_health(sdata)
    health["status"] = "ok"
    health["fail_streak"] = 0
    health.pop("skip_until", None)
    health["last_ok_at"] = datetime.now(timezone.utc).isoformat()
    return health


def _health_on_closed(sdata: dict[str, Any], exc: BaseException, *, reason: str = "unavailable") -> dict[str, Any]:
    health = _stream_health(sdata)
    health["status"] = "closed"
    health["closed_reason"] = reason
    health["last_error"] = f"{type(exc).__name__}:{getattr(exc, 'code', '')}:{exc}"[:240]
    health["last_error_at"] = datetime.now(timezone.utc).isoformat()
    health.pop("skip_until", None)
    return health


def _health_on_join_denied(sdata: dict[str, Any], exc: BaseException) -> dict[str, Any]:
    return _health_on_closed(sdata, exc, reason="join_denied")


def _health_on_error(sdata: dict[str, Any], exc: BaseException) -> dict[str, Any]:
    health = _stream_health(sdata)
    streak = int(health.get("fail_streak") or 0) + 1
    health["fail_streak"] = streak
    health["last_error"] = f"{type(exc).__name__}:{getattr(exc, 'code', '')}:{exc}"[:240]
    health["last_error_at"] = datetime.now(timezone.utc).isoformat()
    now = datetime.now(timezone.utc)
    if _is_thread_deleted_error(exc):
        health["status"] = "deleted"
        health["skip_until"] = (now + timedelta(seconds=THREAD_DELETED_RETRY_SEC)).isoformat()
    elif _is_fetch_permission_error(exc):
        health["status"] = "degraded"
        backoff = min(THREAD_BACKOFF_BASE_SEC * (2 ** min(streak - 1, 5)), THREAD_BACKOFF_MAX_SEC)
        health["skip_until"] = (now + timedelta(seconds=backoff)).isoformat()
    else:
        health["status"] = "degraded"
        backoff = min(1800 * streak, THREAD_BACKOFF_MAX_SEC)
        health["skip_until"] = (now + timedelta(seconds=backoff)).isoformat()
    return health


@dataclass
class ThreadSyncStats:
    total: int = 0
    skipped: int = 0
    ok: int = 0
    degraded: int = 0
    deleted: int = 0
    join_denied: int = 0
    closed: int = 0
    appended: int = 0


def _resolve_route_chat_mid(cl, route: Route) -> tuple[str, str]:
    if route.square_chat_mid:
        return route.square_chat_mid, ""
    candidates: list[tuple[str, str]] = []
    for _, chat_mid, chat_name, _ in iter_joined_chats(cl, 100):
        if not chat_mid:
            continue
        if route.title_substring and route.title_substring in (chat_name or ""):
            candidates.append((chat_mid, chat_name))
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise RuntimeError(
            f"[{route.rid}] title_substring='{route.title_substring}' に一致するオープンチャットが見つかりません。"
        )
    names = ", ".join(f"{m}:{n}" for m, n in candidates[:5])
    raise RuntimeError(
        f"[{route.rid}] title_substring='{route.title_substring}' の候補が複数です。square_chat_mid を指定してください: {names}"
    )


def _resolve_streams(
    cl,
    route: Route,
    square_chat_mid: str,
    chat_name: str,
    no_main: bool,
    no_threads: bool,
    *,
    streams_state: dict[str, Any] | None = None,
    active_threads_only: bool = False,
) -> list[Stream]:
    out: list[Stream] = []
    if route.include_main and not no_main:
        label = chat_name or route.title_substring or square_chat_mid
        out.append(
            Stream(
                stream_key=f"{square_chat_mid}::main",
                square_chat_mid=square_chat_mid,
                thread_mid="",
                thread_label=label,
                route=route,
            )
        )
    if not route.include_threads or no_threads:
        return out

    mids_filter = {x for x in route.thread_mids if x}
    # スレッド専用同期（--no-main）で thread_mids 未登録ルートは対象外
    if no_main and not mids_filter:
        return out
    if mids_filter and active_threads_only and streams_state is not None:
        mids_filter = {
            tmid
            for tmid in mids_filter
            if not _is_thread_closed(streams_state.get(_thread_stream_key(square_chat_mid, tmid), {}))
        }
    # YAML に thread_mids があるときは iter_threads（未実装 API）を呼ばず登録分だけ同期
    thread_rows: list[tuple[str, str]] = []
    if not mids_filter:
        thread_rows = list(iter_threads(cl, square_chat_mid, 100))
    title_filter = route.thread_title_substring

    def _thread_label(tmid: str, tname: str) -> str:
        if tmid in route.thread_titles and route.thread_titles[tmid]:
            return route.thread_titles[tmid]
        if tname and tname not in {"(thread?)", "(無題スレッド)"}:
            return tname
        return tmid

    for tmid, tname in thread_rows:
        if not tmid:
            continue
        if mids_filter and tmid not in mids_filter:
            continue
        if title_filter and title_filter not in (tname or ""):
            continue
        out.append(
            Stream(
                stream_key=f"{square_chat_mid}::thread::{tmid}",
                square_chat_mid=square_chat_mid,
                thread_mid=tmid,
                thread_label=_thread_label(tmid, tname or ""),
                route=route,
            )
        )

    # thread_mids を明示した場合、一覧に無いものも同期対象に含める（YAML 順を維持）
    if mids_filter:
        existing = {s.thread_mid for s in out if s.thread_mid}
        for tmid in route.thread_mids:
            if not tmid or tmid not in mids_filter or tmid in existing:
                continue
            out.append(
                Stream(
                    stream_key=f"{square_chat_mid}::thread::{tmid}",
                    square_chat_mid=square_chat_mid,
                    thread_mid=tmid,
                    thread_label=_thread_label(tmid, ""),
                    route=route,
                )
            )
    return out


def _extract_events(cl, res: Any) -> list[Any]:
    events = _pick_list(cl, res, (("events", 2), ("events", 1), ("squareChatEvents", 2), ("squareChatEvents", 1), ("eventLogs", 2), ("eventLogs", 1)))
    if events:
        return events
    if isinstance(res, dict):
        all_lists = [v for v in res.values() if isinstance(v, list)]
        if all_lists:
            all_lists.sort(key=len, reverse=True)
            return all_lists[0]
    return []


def _fetch_thread_title_from_api(cl, square_chat_mid: str, thread_mid: str) -> str:
    try:
        meta = cl.getSquareChatThread(square_chat_mid, thread_mid)
        title = _thread_title_from_api(cl, meta)
        if title:
            return title
    except Exception:
        pass
    try:
        meta = cl.getSquareThread(thread_mid)
        return _thread_title_from_api(cl, meta)
    except Exception:
        return ""


def _is_placeholder_thread_label(label: str, thread_mid: str) -> bool:
    s = (label or "").strip()
    if not s:
        return True
    if s == thread_mid:
        return True
    if _is_thread_mid(s):
        return True
    if s in {"(thread?)", "(無題スレッド)"}:
        return True
    return False


def _resolve_thread_display_title(
    cl,
    st: Stream,
    session_titles: dict[str, str],
    route_id_to_new_titles: dict[str, dict[str, str]],
) -> str:
    tmid = st.thread_mid
    if not tmid:
        return ""
    cached = st.route.thread_titles.get(tmid) or session_titles.get(tmid) or st.thread_label
    if cached and not _is_placeholder_thread_label(cached, tmid):
        session_titles[tmid] = cached.strip()
        return session_titles[tmid]
    api_title = _fetch_thread_title_from_api(cl, st.square_chat_mid, tmid)
    if api_title:
        st.route.thread_titles[tmid] = api_title
        route_id_to_new_titles[st.route.rid][tmid] = api_title
        session_titles[tmid] = api_title
        return api_title
    short = f"{tmid[:8]}…" if len(tmid) > 8 else tmid
    session_titles[tmid] = short
    return short


def _heading_stream_kind(*, thread_mid: str, related_id: str) -> str:
    """見出し先頭付近の種別ラベル（メイン / スレッド専用 / メイン上のスレッド返信）。"""
    if related_id:
        return "【スレッド返信】"
    if thread_mid:
        return "【スレッド】"
    return "【メイン】"


def _build_open_chat_heading(
    *,
    date_part: str,
    kind: str,
    org_label: str,
    direction: str,
    sender_label: str,
    summary: str,
    thread_display_title: str = "",
) -> str:
    parts = [f"### {date_part}", kind, org_label]
    if kind == "【スレッド】" and thread_display_title:
        parts.append(f"「{thread_display_title}」")
    parts.extend([direction, sender_label, summary])
    return "｜".join(parts)


def _prefetch_sender_names_for_events(cl, resolver: SquareSenderNameResolver, events: list[Any]) -> None:
    mids: list[str] = []
    for ev in events:
        msg = _best_message_from_event(cl, ev)
        if msg is None:
            continue
        sm = str(_msg_sender_mid(cl, msg) or "").strip()
        if sm:
            mids.append(sm)
    resolver.queue_many(mids)
    resolver.flush()


def _append_markdown(path: Path, heading: str, body: str) -> None:
    block = f"""

{heading}

{wrap_details(body)}

---
"""
    content = path.read_text(encoding="utf-8")
    path.write_text(insert_block_after_timeline_header(content, block), encoding="utf-8")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LINE オープンチャット差分を Markdown に追記")
    parser.add_argument("--routes-yaml", type=Path, default=None, help="ルート YAML（未指定時は環境変数 LINE_OPEN_CHAT_ROUTES_YAML または ./open_chat_routes.yaml）")
    parser.add_argument("--limit", type=int, default=100, help="fetchSquareChatEvents の limit")
    parser.add_argument("--max-pages-per-stream", type=int, default=20, help="1ストリームあたりの最大ページ数")
    parser.add_argument("--init", action="store_true", help="保存済み sync_token/continuation を使わず初回取得として開始")
    parser.add_argument(
        "--reset-continuation",
        action="store_true",
        help="sync_token は維持し continuation のみ空にして深いページング（--init より安全）",
    )
    parser.add_argument("--dry-run", action="store_true", help="MD/state/dedup を更新しない")
    parser.add_argument(
        "--allow-qr-login",
        action="store_true",
        help="保存トークン無効時に QR 再認証を許可する（取り込み確認で再ログインするときのみ推奨）",
    )
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--no-main", action="store_true", help="メイン（thread 無し）を同期しない")
    parser.add_argument("--no-threads", action="store_true", help="スレッドを同期しない")
    parser.add_argument(
        "--threads-only",
        action="store_true",
        help="スレッド専用タイムラインのみ同期（--no-main と同等）",
    )
    parser.add_argument(
        "--resolve-thread-titles",
        action="store_true",
        help="thread_mids の表示タイトルを API から取得し open_chat_routes.yaml の thread_titles に追記（MD は未更新）",
    )
    parser.add_argument(
        "--include-closed-threads",
        action="store_true",
        help="閉鎖済み（closed）スレッドも差分対象に含める（通常は省略。初回再スキャン用）",
    )
    parser.add_argument(
        "--max-thread-pages-per-stream",
        type=int,
        default=5,
        help="スレッド専用ストリームの最大ページ数（差分同期用。既定 5）",
    )
    parser.add_argument(
        "--heal-degraded-threads",
        action="store_true",
        help="--threads-only 開始時に degraded+sync_token 空のスレッドのバックオフを解除して再試行",
    )
    parser.add_argument(
        "--thread-catchup-pages",
        type=int,
        default=0,
        metavar="N",
        help="heal 対象スレッドのみ最大ページ数を N に引き上げ（continuation リセット。パートナー確認既定 8）",
    )
    parser.add_argument("--include-empty", action="store_true", help="本文なしメッセージも追記する（既定はスキップ）")
    parser.add_argument(
        "--discover-thread-mids",
        action="store_true",
        help="メインタイムラインのイベントからスレッド MID 候補を集計する（--min-hit-count でしきい値）",
    )
    parser.add_argument(
        "--auto-append-thread-mids",
        action="store_true",
        help="集計した新規 MID を routes YAML の thread_mids に追記する（--dry-run 時は YAML も未変更）",
    )
    parser.add_argument(
        "--min-hit-count",
        type=int,
        default=1,
        metavar="N",
        help="候補 MID を採用する最小ヒット数（既定: 1）",
    )
    parser.add_argument(
        "--discover-only",
        action="store_true",
        help="メイン履歴のみスキャンして thread MID 候補を集計（MD/state/dedup は更新しない）",
    )
    parser.add_argument(
        "--discover-from-yoritoori",
        action="store_true",
        help="5.やり取り.md の [relatedMessageId] から getSquareThreadMid で候補を解決",
    )
    parser.add_argument(
        "--route-ids",
        nargs="*",
        default=None,
        metavar="ID",
        help="処理対象の route id のみ（例: 01_zentai_shuuchi_g）。未指定時は routes 全件",
    )
    parser.add_argument(
        "--join-threads",
        action="store_true",
        help="未参加スレッドを対話確認のうえ joinSquareChatThread で参加してから取得",
    )
    parser.add_argument(
        "--join-threads-confirm-file",
        type=Path,
        default=None,
        metavar="PATH",
        help="参加を許可する thread MID を1行1件で列挙したファイル",
    )
    parser.add_argument(
        "--join-threads-yes",
        action="store_true",
        help="未参加スレッドを確認なしで参加（bootstrap 用。通常運用では非推奨）",
    )
    return parser


def _run_resolve_thread_titles(
    cl,
    routes: list[Route],
    routes_yaml: Path,
    streams_state: dict[str, Any],
    *,
    include_closed: bool,
    dry_run: bool,
) -> int:
    route_id_to_new: dict[str, dict[str, str]] = defaultdict(dict)
    n_try = n_ok = 0
    for route in routes:
        try:
            chat_mid, _ = _resolve_route_chat_mid(cl, route)
        except RuntimeError as e:
            print(f"エラー: {e}", file=sys.stderr)
            return 1
        for tmid in route.thread_mids:
            if not tmid:
                continue
            if not include_closed:
                sdata = streams_state.get(_thread_stream_key(chat_mid, tmid), {})
                if _is_thread_closed(sdata):
                    continue
            existing = route.thread_titles.get(tmid, "")
            if existing and not _is_placeholder_thread_label(existing, tmid):
                continue
            n_try += 1
            title = _fetch_thread_title_from_api(cl, chat_mid, tmid)
            if title:
                route.thread_titles[tmid] = title
                route_id_to_new[route.rid][tmid] = title
                n_ok += 1
                print(f"# thread_title route={route.rid} {title[:50]}", file=sys.stderr)
    if route_id_to_new and not dry_run:
        added = _append_thread_titles_to_routes_yaml(routes_yaml, dict(route_id_to_new))
        print(
            f"# open_chat_routes.yaml thread_titles 追記: {added} 件（試行 {n_try}, 取得成功 {n_ok}）",
            file=sys.stderr,
        )
    elif dry_run:
        n = sum(len(v) for v in route_id_to_new.values())
        print(
            f"# [dry-run] thread_titles を {n} 件追記する予定（試行 {n_try}, 取得成功 {n_ok}）",
            file=sys.stderr,
        )
    else:
        print(f"# thread_titles 追記: 新規なし（試行 {n_try}）", file=sys.stderr)
    return 0


def run(args: argparse.Namespace, *, client=None) -> int:
    """リアルタイム監視と排他してから本体を実行する。"""
    save_root = save_root_from_env()
    try:
        with open_chat_session_lock(save_root, blocking=False):
            return _run_body(args, client=client)
    except BlockingIOError:
        print(
            "# open-chat skipped: realtime watch holds session lock"
            "（launchd/open_chat_watch_pause.sh で一時停止可）",
            file=sys.stderr,
        )
        return 0


def _run_body(args: argparse.Namespace, *, client=None) -> int:
    if args.min_hit_count < 1:
        print("エラー: --min-hit-count は 1 以上である必要があります。", file=sys.stderr)
        return 1

    if args.discover_only:
        args.discover_thread_mids = True
        args.discover_from_yoritoori = True
        args.no_threads = True
        if not args.init:
            args.reset_continuation = True
        if args.max_pages_per_stream < 50:
            args.max_pages_per_stream = max(args.max_pages_per_stream, 100)

    if args.threads_only:
        args.no_main = True

    skip_md_state = bool(args.dry_run or args.discover_only)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    routes_yaml = args.routes_yaml
    if routes_yaml is None:
        env = (os.environ.get("LINE_OPEN_CHAT_ROUTES_YAML") or "").strip()
        if env:
            routes_yaml = Path(env).expanduser().resolve()
        else:
            routes_yaml = (Path(__file__).resolve().parent / "open_chat_routes.yaml").resolve()

    if not routes_yaml.is_file():
        print(f"エラー: ルート YAML がありません: {routes_yaml}", file=sys.stderr)
        return 1

    routes = _parse_routes(routes_yaml)
    if args.route_ids:
        allowed = {str(x).strip() for x in args.route_ids if str(x).strip()}
        routes = [r for r in routes if r.rid in allowed]
        if not routes:
            print(f"エラー: --route-ids に一致するルートがありません: {sorted(allowed)}", file=sys.stderr)
            return 1
    for r in routes:
        if not r.output_md.is_file():
            print(f"エラー: output_md が見つかりません [{r.rid}]: {r.output_md}", file=sys.stderr)
            return 1

    save_root = save_root_from_env()
    state_path = save_root / STATE_FILENAME
    dedup_path = save_root / DEDUP_FILENAME
    state = _load_state(state_path)
    streams_state = state.setdefault("streams", {})
    reopened = _reopen_false_closed_threads(streams_state)
    migrated = _migrate_thread_health(streams_state)
    reopened_join_denied = 0
    if args.heal_degraded_threads:
        active_mids = {tmid for r in routes for tmid in r.thread_mids if tmid}
        reopened_join_denied = _reopen_false_join_denied_threads(streams_state, active_mids)
    if reopened or migrated or reopened_join_denied:
        _save_state(state_path, state)
        if reopened:
            print(f"# false-closed スレッド再開: {reopened} 件（セッション401誤判定）", file=sys.stderr)
        if migrated:
            print(f"# thread health 整理: {migrated} 件（join_denied → ok/degraded）", file=sys.stderr)
        if reopened_join_denied:
            print(
                f"# false-join_denied スレッド再開: {reopened_join_denied} 件（YAML登録・fetch再試行）",
                file=sys.stderr,
            )
    seen_dedup = _load_dedup(dedup_path)
    new_dedup: set[str] = set()
    discover_counts: defaultdict[str, Counter[str]] = defaultdict(Counter)

    cl = client if client is not None else build_logged_in_client(
        save_root, allow_qr_login=bool(args.allow_qr_login)
    )
    if not probe_square_session(cl):
        print("エラー: Square(オープンチャット) API が利用できません。", file=sys.stderr)
        return 1

    if args.resolve_thread_titles:
        return _run_resolve_thread_titles(
            cl,
            routes,
            routes_yaml,
            streams_state,
            include_closed=bool(args.include_closed_threads),
            dry_run=bool(args.dry_run),
        )

    active_threads_only = bool(
        args.threads_only and not args.init and not args.include_closed_threads
    )
    yaml_thread_total = sum(len(r.thread_mids) for r in routes) if args.threads_only else 0
    all_streams: list[Stream] = []
    joined_by_chat: dict[str, set[str]] = {}
    need_join = bool(args.join_threads or args.join_threads_confirm_file or args.join_threads_yes)
    for route in routes:
        try:
            chat_mid, chat_name = _resolve_route_chat_mid(cl, route)
        except RuntimeError as e:
            print(f"エラー: {e}", file=sys.stderr)
            return 1
        if route.square_chat_mid != chat_mid and chat_mid:
            pass  # title 解決のみ。YAML の square_chat_mid は手動更新
        streams = _resolve_streams(
            cl,
            route,
            chat_mid,
            chat_name,
            args.no_main,
            args.no_threads,
            streams_state=streams_state,
            active_threads_only=active_threads_only,
        )
        if args.verbose:
            print(f"# route={route.rid} chat={chat_mid} streams={len(streams)}", file=sys.stderr)
        all_streams.extend(streams)

    if need_join:
        for route in routes:
            try:
                chat_mid, _ = _resolve_route_chat_mid(cl, route)
            except RuntimeError:
                continue
            if chat_mid not in joined_by_chat:
                joined_by_chat[chat_mid] = _joined_thread_mids(cl, chat_mid)

    if not all_streams:
        print("対象ストリームがありません（設定・オプションを確認してください）。", file=sys.stderr)
        return 0

    if args.threads_only and active_threads_only and yaml_thread_total:
        closed_n = yaml_thread_total - sum(1 for s in all_streams if s.thread_mid)
        print(
            f"# thread diff: YAML登録 {yaml_thread_total} 件のうち "
            f"取得可能 {len([s for s in all_streams if s.thread_mid])} 件を対象"
            f"（閉鎖済みスキップ {closed_n} 件）",
            file=sys.stderr,
        )

    healed_thread_keys: set[str] = set()
    if args.threads_only and args.heal_degraded_threads:
        healed_thread_keys = _heal_degraded_threads_for_sync(streams_state)
        if healed_thread_keys:
            _save_state(state_path, state)
        if healed_thread_keys:
            print(
                f"# thread heal: degraded+sync_token空 {len(healed_thread_keys)} 件のバックオフ解除",
                file=sys.stderr,
            )

    if args.threads_only:
        warmed_chats: set[str] = set()
        for st in all_streams:
            if st.square_chat_mid in warmed_chats:
                continue
            warmed_chats.add(st.square_chat_mid)
            try:
                _fetch_square_chat_events(
                    cl,
                    square_chat_mid=st.square_chat_mid,
                    sync_token="",
                    cont_token="",
                    limit=1,
                    thread_mid=None,
                )
                if args.verbose:
                    print(f"# square warmup OK: {st.square_chat_mid}", file=sys.stderr)
            except Exception as e:
                print(
                    f"# square warmup ({st.square_chat_mid}): {type(e).__name__}: {e}",
                    file=sys.stderr,
                )

    route_id_to_new_titles: dict[str, dict[str, str]] = defaultdict(dict)

    chat_mids_for_self = {st.square_chat_mid for st in all_streams if st.square_chat_mid}
    my_square_mids = build_my_square_mid_map(cl, chat_mids_for_self)
    sender_resolver = SquareSenderNameResolver(cl, my_square_mids=my_square_mids)

    appended = 0
    thread_stats = ThreadSyncStats()
    session_thread_titles: dict[str, str] = {}
    for st in all_streams:
        sdata = streams_state.get(st.stream_key, {})

        if st.thread_mid:
            thread_stats.total += 1
            registered = st.thread_mid in set(st.route.thread_mids or [])
            if not args.init:
                if _is_thread_closed(sdata):
                    thread_stats.skipped += 1
                    if args.verbose:
                        health = _stream_health(sdata)
                        print(
                            f"# stream skip (closed:{health.get('closed_reason', '?')}): {st.stream_key}",
                            file=sys.stderr,
                        )
                    continue
                if not registered:
                    skip_reason = _health_skip_reason(sdata)
                    if skip_reason:
                        thread_stats.skipped += 1
                        if args.verbose:
                            print(f"# stream skip ({skip_reason}): {st.stream_key}", file=sys.stderr)
                        continue

        join_failed = False
        if st.thread_mid and need_join:
            joined = joined_by_chat.setdefault(st.square_chat_mid, set())
            if st.thread_mid not in joined:
                ok = _ensure_thread_joined(
                    cl,
                    st.square_chat_mid,
                    st.thread_mid,
                    joined_cache=joined,
                    join_threads=bool(args.join_threads),
                    join_confirm_file=args.join_threads_confirm_file,
                    join_auto_yes=bool(args.join_threads_yes),
                )
                if not ok:
                    join_failed = True
                    if args.verbose:
                        print(f"# join 失敗・fetch を試行: {st.stream_key}", file=sys.stderr)

        thread_display_title = ""
        if st.thread_mid:
            thread_display_title = _resolve_thread_display_title(
                cl, st, session_thread_titles, route_id_to_new_titles
            )

        if args.init:
            sync_token = ""
            cont_token = ""
        else:
            sync_token = str(sdata.get("sync_token") or "")
            cont_token = "" if args.reset_continuation else str(sdata.get("continuation_token") or "")
            if st.thread_mid and st.stream_key in healed_thread_keys and args.thread_catchup_pages > 0:
                cont_token = ""
            if args.init and st.thread_mid:
                sync_token = ""
                cont_token = ""
        if args.verbose:
            print(f"# stream={st.stream_key} sync={bool(sync_token)} cont={bool(cont_token)}", file=sys.stderr)

        if st.thread_mid and not args.init:
            if st.stream_key in healed_thread_keys and args.thread_catchup_pages > 0:
                page_limit = max(1, args.thread_catchup_pages)
            else:
                page_limit = max(1, args.max_thread_pages_per_stream)
        else:
            page_limit = max(1, args.max_pages_per_stream)
        stream_appended_start = appended
        stream_had_error = False
        last_exc: BaseException | None = None

        for _ in range(page_limit):
            fetch_sync = sync_token
            fetch_cont = cont_token
            retried_after_401 = False
            while True:
                try:
                    res = _fetch_square_chat_events(
                        cl,
                        square_chat_mid=st.square_chat_mid,
                        sync_token=fetch_sync,
                        cont_token=fetch_cont,
                        limit=args.limit,
                        thread_mid=st.thread_mid or None,
                    )
                    break
                except Exception as e:
                    if _is_session_logged_out_error(e):
                        cl2 = recover_session_midrun(
                            save_root,
                            cl,
                            allow_qr_login=bool(args.allow_qr_login),
                        )
                        if cl2 is not None:
                            cl = cl2
                            continue
                        last_exc = e
                        print(
                            f"# stream セッション切断（復旧不可）: {st.stream_key} {type(e).__name__}: {e}",
                            file=sys.stderr,
                        )
                        res = None
                        break
                    if not retried_after_401 and _is_fetch_permission_error(e):
                        print(
                            f"# stream 401 → sync/continuation リセットして再試行: {st.stream_key}",
                            file=sys.stderr,
                        )
                        fetch_sync = ""
                        fetch_cont = ""
                        sync_token = ""
                        cont_token = ""
                        retried_after_401 = True
                        continue
                    last_exc = e
                    print(f"# stream エラー: {st.stream_key} {type(e).__name__}: {e}", file=sys.stderr)
                    res = None
                    break
            if res is None:
                stream_had_error = True
                if not skip_md_state and st.thread_mid:
                    if join_failed and _is_fetch_permission_error(last_exc or Exception()):
                        h = _health_on_closed(sdata, last_exc or RuntimeError("fetch denied"), reason="join_denied")
                        thread_stats.closed += 1
                    else:
                        h = _health_on_error(sdata, last_exc or RuntimeError("fetch failed"))
                        if h.get("status") == "deleted":
                            thread_stats.deleted += 1
                        else:
                            thread_stats.degraded += 1
                    prev_sync = str(sdata.get("sync_token") or "")
                    prev_cont = str(sdata.get("continuation_token") or "")
                    # 401 再試行後も失敗した場合は stale token を残さない
                    preserve_tokens = (
                        not join_failed
                        and _is_fetch_permission_error(last_exc or Exception())
                        and bool(prev_sync or prev_cont)
                        and not retried_after_401
                    )
                    streams_state[st.stream_key] = {
                        "sync_token": prev_sync if preserve_tokens else "",
                        "continuation_token": prev_cont if preserve_tokens else "",
                        "health": h,
                    }
                break

            events = _extract_events(cl, res)
            before_appended = appended
            _prefetch_sender_names_for_events(cl, sender_resolver, events)
            for ev in events:
                if args.discover_thread_mids and not st.thread_mid:
                    for tmid in _extract_thread_mids_from_event(ev, st.square_chat_mid):
                        discover_counts[st.route.rid][tmid] += 1

                msg = _best_message_from_event(cl, ev)
                if args.discover_thread_mids and not st.thread_mid and msg is not None:
                    related_for_discover = _related_message_id(cl, msg, ev)
                    if related_for_discover:
                        tmid = _resolve_thread_mid_via_api(cl, st.square_chat_mid, related_for_discover)
                        if tmid:
                            discover_counts[st.route.rid][tmid] += 1

                if msg is None:
                    continue
                body = _message_text(cl, msg)
                if body == "[本文なし]" and not args.include_empty:
                    continue
                ts = _msg_time(cl, msg)
                if not ts:
                    ts = _event_time(cl, ev)
                when = _format_line_msg_when(ts)
                date_part = when.split()[0] if when and " " in when else when or "?"
                sender = str(_msg_sender_mid(cl, msg) or "")
                my_sm = my_square_mids.get(st.square_chat_mid, "")
                direction = (
                    "送信"
                    if sender
                    and (sender == my_sm or sender == str(getattr(cl, "mid", "")))
                    else "受信"
                )
                sender_label = sender_resolver.label(sender, chat_mid=st.square_chat_mid)
                msg_id = _message_id(cl, msg, "")
                related_id = _related_message_id(cl, msg, ev)
                dk = _dedup_key(st.stream_key, msg_id, ts, body)
                if dk in seen_dedup:
                    continue

                kind = _heading_stream_kind(thread_mid=st.thread_mid or "", related_id=related_id)
                heading = _build_open_chat_heading(
                    date_part=date_part,
                    kind=kind,
                    org_label=st.route.org_label,
                    direction=direction,
                    sender_label=sender_label,
                    summary=make_summary(body),
                    thread_display_title=thread_display_title if kind == "【スレッド】" else "",
                )
                body_for_write = body
                if related_id:
                    body_for_write = f"[relatedMessageId] {related_id}\n\n{body}"
                if skip_md_state:
                    if args.dry_run or args.discover_only:
                        pass  # discover-only は件数のみ（下で discover_counts）
                else:
                    _append_markdown(st.route.output_md, heading, body_for_write)
                if not skip_md_state:
                    seen_dedup.add(dk)
                    new_dedup.add(dk)
                    appended += 1

            sync_token, cont_token = _extract_tokens(cl, res, sync_token, cont_token)
            has_next = bool(cont_token)
            no_new_data = len(events) == 0 or appended == before_appended
            if not has_next and no_new_data:
                break
            if not has_next and len(events) > 0:
                # 同一 sync 内の続きがないのでこのストリームは完了
                cont_token = ""
                break

        if not skip_md_state and not stream_had_error:
            entry: dict[str, Any] = {
                "sync_token": sync_token or "",
                "continuation_token": cont_token or "",
            }
            if st.thread_mid:
                entry["health"] = _health_on_success(sdata)
                thread_stats.ok += 1
                thread_stats.appended += appended - stream_appended_start
            streams_state[st.stream_key] = entry

    yaml_append_total = 0
    if args.discover_thread_mids:
        if args.discover_from_yoritoori:
            for route in routes:
                try:
                    chat_mid, _ = _resolve_route_chat_mid(cl, route)
                except RuntimeError as e:
                    print(f"エラー: {e}", file=sys.stderr)
                    return 1
                cnt = _discover_thread_mids_from_yoritoori(cl, route, chat_mid)
                if cnt:
                    discover_counts[route.rid].update(cnt)
                    print(
                        f"# discover-from-yoritoori route={route.rid} 解決 {len(cnt)} 件（relatedMessageId 由来）",
                        file=sys.stderr,
                    )

        route_id_to_new: dict[str, list[str]] = {}
        for route in routes:
            cnt = discover_counts.get(route.rid) or Counter()
            existing = set(route.thread_mids)
            eligible = [
                tmid
                for tmid, c in cnt.items()
                if c >= args.min_hit_count and tmid not in existing
            ]
            if eligible:
                sorted_mids = sorted(eligible, key=lambda m: (-cnt[m], m))
                route_id_to_new[route.rid] = sorted_mids

        print("# --- thread MID 候補（メイン履歴・yoritoori 由来）---", file=sys.stderr)
        if args.no_main:
            print("# 注意: --no-main のためメインを取得しておらず、候補は通常ありません。", file=sys.stderr)
        for route in routes:
            cnt = discover_counts.get(route.rid) or Counter()
            if not cnt:
                continue
            existing = set(route.thread_mids)
            print(f"# route={route.rid} ({route.org_label})", file=sys.stderr)
            for tmid, c in sorted(cnt.items(), key=lambda x: (-x[1], x[0])):
                if c < args.min_hit_count:
                    tag = f"hits={c}（min {args.min_hit_count} 未満）"
                elif tmid in existing:
                    tag = f"hits={c} 既登録"
                else:
                    tag = f"hits={c} 新規"
                print(f"#   {tag} mid={tmid}", file=sys.stderr)

        if args.auto_append_thread_mids:
            if args.dry_run and not args.discover_only:
                n = sum(len(v) for v in route_id_to_new.values())
                print(f"# [dry-run] open_chat_routes.yaml に thread_mids を {n} 件追記する予定", file=sys.stderr)
            elif route_id_to_new:
                yaml_append_total = _append_thread_mids_to_routes_yaml(routes_yaml, route_id_to_new)
                print(f"# open_chat_routes.yaml thread_mids 追記: {yaml_append_total} 件", file=sys.stderr)
            else:
                print("# open_chat_routes.yaml 追記: 新規 MID なし（既登録・しきい値・候補なし）", file=sys.stderr)

    if route_id_to_new_titles and not args.dry_run:
        n_titles = _append_thread_titles_to_routes_yaml(routes_yaml, dict(route_id_to_new_titles))
        if n_titles:
            print(f"# open_chat_routes.yaml thread_titles 追記: {n_titles} 件", file=sys.stderr)

    if args.discover_only:
        print("# discover-only 完了（MD/state/dedup は未更新）", file=sys.stderr)

    if new_dedup and not skip_md_state:
        _save_dedup(dedup_path, seen_dedup)
    if not skip_md_state:
        _save_state(state_path, state)

    if thread_stats.total > 0:
        print(
            f"# thread sync: total={thread_stats.total} ok={thread_stats.ok} "
            f"skipped={thread_stats.skipped} closed={thread_stats.closed} "
            f"degraded={thread_stats.degraded} deleted={thread_stats.deleted} "
            f"appended={thread_stats.appended}",
            file=sys.stderr,
        )

    print(f"# open-chat 追記: {appended} 件", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None, *, client=None) -> int:
    args = build_arg_parser().parse_args(argv)
    return run(args, client=client)


if __name__ == "__main__":
    raise SystemExit(main())
