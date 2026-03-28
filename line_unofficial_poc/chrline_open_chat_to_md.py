#!/usr/bin/env python3
"""
LINE オープンチャット（Square）差分を Markdown に追記する。

- ルート設定: YAML（--routes-yaml / LINE_OPEN_CHAT_ROUTES_YAML）
- 対応: メインタイムライン + 参加中スレッド
- 状態: LINE_UNOFFICIAL_AUTH_DIR/.chrline_open_chat_state.json
- 重複排除: LINE_UNOFFICIAL_AUTH_DIR/.chrline_open_chat_dedup.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from chrline_client_utils import build_logged_in_client, save_root_from_env
from chrline_dump_messages_poc import _format_line_msg_when, _msg_plain_text, _msg_sender_mid, _msg_time
from chrline_list_open_chats_poc import iter_joined_chats, iter_threads
from chrline_md_utils import insert_block_after_timeline_header, make_summary, wrap_details

STATE_FILENAME = ".chrline_open_chat_state.json"
DEDUP_FILENAME = ".chrline_open_chat_dedup.json"


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


def _resolve_streams(cl, route: Route, square_chat_mid: str, chat_name: str, no_main: bool, no_threads: bool) -> list[Stream]:
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

    thread_rows = list(iter_threads(cl, square_chat_mid, 100))
    title_filter = route.thread_title_substring
    mids_filter = {x for x in route.thread_mids if x}
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
                thread_label=tname or tmid,
                route=route,
            )
        )

    # thread_mids を明示した場合、一覧に無いものも同期対象に含める（参加状態差分用）
    if mids_filter:
        existing = {s.thread_mid for s in out if s.thread_mid}
        for tmid in sorted(mids_filter):
            if tmid in existing:
                continue
            out.append(
                Stream(
                    stream_key=f"{square_chat_mid}::thread::{tmid}",
                    square_chat_mid=square_chat_mid,
                    thread_mid=tmid,
                    thread_label=tmid,
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


def _append_markdown(path: Path, heading: str, body: str) -> None:
    block = f"""

{heading}

{wrap_details(body)}

---
"""
    content = path.read_text(encoding="utf-8")
    path.write_text(insert_block_after_timeline_header(content, block), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="LINE オープンチャット差分を Markdown に追記")
    parser.add_argument("--routes-yaml", type=Path, default=None, help="ルート YAML（未指定時は環境変数 LINE_OPEN_CHAT_ROUTES_YAML または ./open_chat_routes.yaml）")
    parser.add_argument("--limit", type=int, default=100, help="fetchSquareChatEvents の limit")
    parser.add_argument("--max-pages-per-stream", type=int, default=20, help="1ストリームあたりの最大ページ数")
    parser.add_argument("--init", action="store_true", help="保存済み sync_token/continuation を使わず初回取得として開始")
    parser.add_argument("--dry-run", action="store_true", help="MD/state/dedup を更新しない")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--no-main", action="store_true", help="メイン（thread 無し）を同期しない")
    parser.add_argument("--no-threads", action="store_true", help="スレッドを同期しない")
    parser.add_argument("--include-empty", action="store_true", help="本文なしメッセージも追記する（既定はスキップ）")
    args = parser.parse_args()

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
    for r in routes:
        if not r.output_md.is_file():
            print(f"エラー: output_md が見つかりません [{r.rid}]: {r.output_md}", file=sys.stderr)
            return 1

    save_root = save_root_from_env()
    state_path = save_root / STATE_FILENAME
    dedup_path = save_root / DEDUP_FILENAME
    state = _load_state(state_path)
    streams_state = state.setdefault("streams", {})
    seen_dedup = _load_dedup(dedup_path)
    new_dedup: set[str] = set()

    cl = build_logged_in_client(save_root)
    if not getattr(cl, "can_use_square", False):
        print("エラー: Square(オープンチャット) API が利用できません。", file=sys.stderr)
        return 1

    all_streams: list[Stream] = []
    for route in routes:
        try:
            chat_mid, chat_name = _resolve_route_chat_mid(cl, route)
        except RuntimeError as e:
            print(f"エラー: {e}", file=sys.stderr)
            return 1
        streams = _resolve_streams(cl, route, chat_mid, chat_name, args.no_main, args.no_threads)
        if args.verbose:
            print(f"# route={route.rid} chat={chat_mid} streams={len(streams)}", file=sys.stderr)
        all_streams.extend(streams)

    if not all_streams:
        print("対象ストリームがありません（設定・オプションを確認してください）。", file=sys.stderr)
        return 0

    appended = 0
    for st in all_streams:
        sdata = streams_state.get(st.stream_key, {})
        sync_token = "" if args.init else str(sdata.get("sync_token") or "")
        cont_token = "" if args.init else str(sdata.get("continuation_token") or "")
        if args.verbose:
            print(f"# stream={st.stream_key} sync={bool(sync_token)} cont={bool(cont_token)}", file=sys.stderr)

        for _ in range(max(1, args.max_pages_per_stream)):
            try:
                res = cl.fetchSquareChatEvents(
                    st.square_chat_mid,
                    syncToken=sync_token or None,
                    continuationToken=cont_token or None,
                    limit=max(1, min(args.limit, 200)),
                    threadMid=st.thread_mid or None,
                )
            except Exception as e:
                print(f"# stream エラー: {st.stream_key} {type(e).__name__}: {e}", file=sys.stderr)
                break

            events = _extract_events(cl, res)
            before_appended = appended
            for ev in events:
                msg = _best_message_from_event(cl, ev)
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
                direction = "送信" if sender and sender == str(getattr(cl, "mid", "")) else "受信"
                msg_id = _message_id(cl, msg, "")
                related_id = _related_message_id(cl, msg, ev)
                dk = _dedup_key(st.stream_key, msg_id, ts, body)
                if dk in seen_dedup:
                    continue

                thread_tag = f"・スレッド「{st.thread_label}」" if st.thread_mid else "・メイン"
                if related_id:
                    thread_tag += "・スレッド返信"
                heading = (
                    f"### {date_part}｜{st.route.org_label}｜"
                    f"{st.route.heading_tag}{thread_tag}・{direction}｜{make_summary(body)}"
                )
                body_for_write = body
                if related_id:
                    body_for_write = f"[relatedMessageId] {related_id}\n\n{body}"
                if args.dry_run:
                    print(f"[dry-run] {st.route.output_md.name}: {heading}", file=sys.stderr)
                else:
                    _append_markdown(st.route.output_md, heading, body_for_write)
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

        if not args.dry_run:
            streams_state[st.stream_key] = {
                "sync_token": sync_token or "",
                "continuation_token": cont_token or "",
            }

    if new_dedup and not args.dry_run:
        _save_dedup(dedup_path, seen_dedup)
    if not args.dry_run:
        _save_state(state_path, state)

    print(f"# open-chat 追記: {appended} 件", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
