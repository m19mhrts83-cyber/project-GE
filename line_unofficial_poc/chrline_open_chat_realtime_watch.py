#!/usr/bin/env python3
"""
LINE オープンチャット（Square）リアルタイム監視。

目的:
- メイン / スレッド返信 / 専用スレッドの新着をイベント駆動で即時記録
- スレッドが約30日で消える前に本文を蓄積
- 履歴APIの読み取り回数制限を避け、PUSH受信で補完する

使い方（正本は CHRLINE-Patch）:
  cd ~/git-repos/line_unofficial_poc
  ./run_patch.sh chrline_open_chat_realtime_watch.py --routes-yaml ./open_chat_routes.yaml
  # 初回のみトークン無効時: --allow-qr-login
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from CHRLINE.hooks import HooksTracer

from chrline_client_utils import (
    build_logged_in_client,
    open_chat_session_lock,
    save_root_from_env,
)
from chrline_list_open_chats_poc import iter_joined_chats
from chrline_md_utils import insert_block_after_timeline_header, make_summary, wrap_details
from chrline_open_chat_to_md import (
    DEDUP_FILENAME as BATCH_DEDUP_FILENAME,
    _build_open_chat_heading,
    _heading_stream_kind,
)
from chrline_square_sender_names import SquareSenderNameResolver

RT_DEDUP_FILENAME = ".chrline_open_chat_realtime_dedup.json"
WATCH_STATUS_FILENAME = ".chrline_open_chat_watch_status.json"
DEDUP_FLUSH_EVERY = 25
DEDUP_FLUSH_SECONDS = 60.0
HEARTBEAT_SECONDS = 30.0
MAC_LINE_CHECK_SECONDS = 5.0


@dataclass
class RtRoute:
    rid: str
    chat_mid: str
    output_md: Path
    org_label: str
    heading_tag: str
    thread_titles: dict[str, str] = field(default_factory=dict)


def _is_chat_mid(s: str) -> bool:
    return len(s) >= 24 and s[:1] in {"m", "c"}


def _is_thread_mid(s: str) -> bool:
    return len(s) >= 24 and s[:1] == "t"


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
        print("エラー: routes YAML のトップレベルが不正です。", file=sys.stderr)
        raise SystemExit(1)
    return data


def _resolve_chat_mid_by_title(cl, title_substring: str) -> str:
    cands: list[str] = []
    for _, chat_mid, chat_name, _ in iter_joined_chats(cl, 100):
        if chat_mid and title_substring in (chat_name or ""):
            cands.append(chat_mid)
    cands = sorted(set(cands))
    if len(cands) == 1:
        return cands[0]
    if not cands:
        raise RuntimeError(f"title_substring '{title_substring}' に一致する chat_mid が見つかりません")
    raise RuntimeError(f"title_substring '{title_substring}' が複数ヒット: {', '.join(cands[:5])}")


def _load_routes(path: Path, cl) -> dict[str, RtRoute]:
    data = _load_yaml(path)
    rows = data.get("routes")
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("routes が空です")
    out: dict[str, RtRoute] = {}
    for i, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            continue
        rid = str(row.get("id") or f"route_{i}")
        chat_mid = str(row.get("square_chat_mid") or "").strip()
        title_substring = str(row.get("title_substring") or "").strip()
        if not chat_mid:
            if not title_substring:
                continue
            chat_mid = _resolve_chat_mid_by_title(cl, title_substring)
        output_md_raw = str(row.get("output_md") or "").strip()
        if not output_md_raw:
            continue
        output_md = Path(output_md_raw).expanduser().resolve()
        if not output_md.is_file():
            continue
        titles_raw = row.get("thread_titles") or {}
        thread_titles: dict[str, str] = {}
        if isinstance(titles_raw, dict):
            for k, v in titles_raw.items():
                kk = str(k).strip()
                vv = str(v or "").strip()
                if kk and vv:
                    thread_titles[kk] = vv
        out[chat_mid] = RtRoute(
            rid=rid,
            chat_mid=chat_mid,
            output_md=output_md,
            org_label=str(row.get("org_label") or rid),
            heading_tag=str(row.get("heading_tag") or "LINEオープンチャット"),
            thread_titles=thread_titles,
        )
    return out


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
    trimmed = sorted(keys)[-8000:]
    path.write_text(json.dumps({"keys": trimmed}, ensure_ascii=False, indent=2), encoding="utf-8")


def _mac_line_is_running() -> bool:
    """公式Mac版LINEとのデスクトップ認証競合を検出する。"""
    try:
        result = subprocess.run(
            ["/usr/bin/pgrep", "-f", r"application\.jp\.naver\.line\.mac|/Applications/LINE\.app"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _write_watch_status(path: Path, **updates: Any) -> None:
    """launchd/healthcheck向け状態を秘密情報なしで原子的に保存する。"""
    current: dict[str, Any] = {}
    try:
        if path.is_file():
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                current = loaded
    except (OSError, json.JSONDecodeError):
        pass
    current.update(updates)
    current["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _message_ids_from_batch_dedup(path: Path) -> set[str]:
    """バッチ側 dedup キー（stream|id:MSG|ts:...）から messageId 集合を抽出。"""
    out: set[str] = set()
    for key in _load_dedup(path):
        # ...|id:123456|ts:...
        parts = str(key).split("|")
        for p in parts:
            if p.startswith("id:") and len(p) > 3:
                mid = p[3:].strip()
                if mid:
                    out.add(mid)
    return out


def _get(obj: Any, *keys: Any) -> Any:
    if obj is None:
        return None
    for k in keys:
        if isinstance(obj, dict) and k in obj:
            return obj.get(k)
        v = getattr(obj, f"val_{k}", None) if isinstance(k, int) else getattr(obj, str(k), None)
        if v is not None:
            return v
    return None


def _to_dict(obj: Any) -> dict[Any, Any]:
    if isinstance(obj, dict):
        return obj
    dd = getattr(obj, "dd", None)
    if callable(dd):
        try:
            d = dd()
            if isinstance(d, dict):
                return d
        except Exception:
            pass
    return {}


def _iter_dictish(root: Any, depth: int = 0):
    if root is None or depth > 8:
        return
    if isinstance(root, dict):
        yield root
        for v in root.values():
            yield from _iter_dictish(v, depth + 1)
        return
    if isinstance(root, (list, tuple)):
        for v in root:
            yield from _iter_dictish(v, depth + 1)
        return
    d = _to_dict(root)
    if d:
        yield from _iter_dictish(d, depth + 1)


def _chat_mid_candidates(*objs: Any) -> list[str]:
    mids: list[str] = []
    seen: set[str] = set()
    for obj in objs:
        for d in _iter_dictish(obj):
            for v in d.values():
                if not isinstance(v, str):
                    continue
                s = v.strip()
                if not _is_chat_mid(s):
                    continue
                if s in seen:
                    continue
                seen.add(s)
                mids.append(s)
    return mids


def _find_notification_message_like(root: Any) -> Any:
    for d in _iter_dictish(root):
        cmid = d.get("squareChatMid")
        if not isinstance(cmid, str):
            v1 = d.get(1)
            if isinstance(v1, str):
                cmid = v1
        if not isinstance(cmid, str) or not _is_chat_mid(cmid):
            continue
        has_sqmsg = "squareMessage" in d or 2 in d
        has_msg = "message" in d
        if has_sqmsg or has_msg:
            return d
    return None


def _to_ms(ts: Any) -> int:
    try:
        iv = int(ts)
    except (TypeError, ValueError):
        return 0
    if iv <= 0:
        return 0
    if iv < 10_000_000_000:
        iv *= 1000
    return iv


def _fmt_date(ms: int) -> str:
    if ms <= 0:
        return "?"
    try:
        return datetime.fromtimestamp(ms / 1000.0).strftime("%Y/%m/%d")
    except Exception:
        return "?"


def _msg_text(msg: Any) -> str:
    t = _get(msg, "text", 10)
    if isinstance(t, str) and t.strip():
        return t.strip()
    ct = _get(msg, "contentType", 15)
    if ct is None:
        return "[本文なし]"
    return f"[非テキスト contentType={ct}]"


def _append(route: RtRoute, heading: str, body: str) -> None:
    block = f"""

{heading}

{wrap_details(body)}

---
"""
    content = route.output_md.read_text(encoding="utf-8")
    route.output_md.write_text(insert_block_after_timeline_header(content, block), encoding="utf-8")


def _extract_thread_notification(event: Any) -> tuple[str, str, Any] | None:
    """event 54: (chat_mid, thread_mid, message) or None."""
    payload = _get(event, "payload", 4)
    ntm = _get(payload, "notificationThreadMessage", 52)
    if ntm is None:
        return None
    thread_mid = str(_get(ntm, "threadMid", 1) or "").strip()
    chat_mid = str(_get(ntm, "chatMid", 2) or "").strip()
    sq_msg = _get(ntm, "squareMessage", 3)
    msg = _get(sq_msg, "message", 1) if sq_msg is not None else None
    if not chat_mid or not _is_chat_mid(chat_mid) or msg is None:
        return None
    if thread_mid and not _is_thread_mid(thread_mid):
        thread_mid = ""
    return chat_mid, thread_mid, msg


def main() -> int:
    parser = argparse.ArgumentParser(description="オープンチャットをリアルタイム監視して MD に追記")
    parser.add_argument("--routes-yaml", type=Path, default=None, help="open_chat_routes.yaml のパス")
    parser.add_argument(
        "--allow-qr-login",
        action="store_true",
        help="保存トークン無効時に QR 再認証を許可する（常駐では通常付けない）",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    save_root = save_root_from_env()
    rt_dedup_path = save_root / RT_DEDUP_FILENAME
    batch_dedup_path = save_root / BATCH_DEDUP_FILENAME
    watch_status_path = save_root / WATCH_STATUS_FILENAME
    dedup = _load_dedup(rt_dedup_path)
    batch_msg_ids = _message_ids_from_batch_dedup(batch_dedup_path)
    flush_state = {"count": 0, "last": time.time()}
    status_lock = threading.Lock()
    stop_event = threading.Event()

    def _status(**updates: Any) -> None:
        with status_lock:
            _write_watch_status(watch_status_path, **updates)

    def _maybe_flush(*, force: bool = False) -> None:
        now = time.time()
        if force or flush_state["count"] >= DEDUP_FLUSH_EVERY or (now - flush_state["last"]) >= DEDUP_FLUSH_SECONDS:
            _save_dedup(rt_dedup_path, dedup)
            flush_state["count"] = 0
            flush_state["last"] = now

    try:
        session_cm = open_chat_session_lock(save_root, blocking=False)
        session_cm.__enter__()
    except BlockingIOError:
        print(
            "エラー: オープンチャット同期が実行中のため常駐監視を開始できません。"
            "バッチ完了後に再起動してください。",
            file=sys.stderr,
        )
        return 2

    try:
        if _mac_line_is_running():
            _status(
                state="blocked",
                reason="mac_line_running",
                pid=os.getpid(),
            )
            print(
                "エラー: Mac版LINEが起動中です。デスクトップ認証競合を避けるため監視を開始しません。",
                file=sys.stderr,
            )
            return 75

        _status(
            state="starting",
            reason="",
            pid=os.getpid(),
            started_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            stopped_at="",
        )
        cl = build_logged_in_client(save_root, allow_qr_login=bool(args.allow_qr_login))
        # can_use_square は getJoinedSquares 後に立つ遅延フラグ。
        # 起動時の履歴 probe / 一覧連打はセッションを傷めるため行わない。
        # PUSH（initServices=[3]）はログイン済みクライアントで開始する。
        if not getattr(cl, "is_login", False) and not getattr(cl, "mid", None):
            print("エラー: ログインに失敗しました。", file=sys.stderr)
            return 1
        # Square ヘルパーを有効化するため一覧を1回だけ（失敗しても監視は続行）
        try:
            _ = cl.squares
            print(f"# square enabled can_use_square={getattr(cl, 'can_use_square', False)}", file=sys.stderr)
        except Exception as e:
            print(
                f"# square list skip ({type(e).__name__}: {e}) — PUSH 監視は続行",
                file=sys.stderr,
            )

        routes_yaml = args.routes_yaml
        if routes_yaml is None:
            env = (os.environ.get("LINE_OPEN_CHAT_ROUTES_YAML") or "").strip()
            routes_yaml = (
                Path(env).expanduser().resolve()
                if env
                else (Path(__file__).resolve().parent / "open_chat_routes.yaml")
            )

        try:
            routes = _load_routes(routes_yaml, cl)
        except RuntimeError as e:
            print(f"エラー: {e}", file=sys.stderr)
            return 1
        if not routes:
            print("対象ルートがありません。", file=sys.stderr)
            return 1

        routes_by_chat: dict[str, RtRoute] = dict(routes)
        msgid_to_route: dict[str, RtRoute] = {}
        # 起動時の getMySquareMid 連打は履歴制限と同系統でセッションを傷めるため省略。
        # 方向判定は「受信」寄りになるが、追記自体は問題ない。
        my_square_mid: dict[str, str] = {}
        sender_resolver = SquareSenderNameResolver(cl, my_square_mids=my_square_mid)

        print(f"# realtime watch start chats={len(routes)}", file=sys.stderr)
        for c, r in routes.items():
            print(f"#  - {r.rid}: {c} -> {r.output_md}", file=sys.stderr)

        tracer = HooksTracer(cl, prefixes=[""])

        def _shutdown(_sig, _frm):
            stop_event.set()
            _maybe_flush(force=True)
            _status(state="stopping", reason="signal")
            print("# realtime watch stop", file=sys.stderr)
            raise SystemExit(0)

        signal.signal(signal.SIGINT, _shutdown)
        signal.signal(signal.SIGTERM, _shutdown)

        def _append_message(
            *,
            route: RtRoute,
            msg: Any,
            chat_mid: str,
            thread_mid: str,
            related: str,
            event_code: int,
            route_source: str,
        ) -> None:
            message_id = str(_get(msg, "id", 4) or "").strip()
            if not message_id:
                return
            text = _msg_text(msg)
            if text == "[本文なし]":
                return

            key = f"{route.chat_mid}|{message_id}"
            if key in dedup or message_id in batch_msg_ids:
                return

            created_ms = _to_ms(_get(msg, "createdTime", 5))
            date = _fmt_date(created_ms)
            sender = str(_get(msg, "_from", 1) or "")
            mine = my_square_mid.get(route.chat_mid, "")
            direction = "送信" if mine and sender == mine else "受信"
            sender_label = sender_resolver.label(sender, chat_mid=route.chat_mid)
            kind = _heading_stream_kind(thread_mid=thread_mid, related_id=related or "")
            thread_title = ""
            if kind == "【スレッド】" and thread_mid:
                thread_title = route.thread_titles.get(thread_mid, "") or thread_mid[:12]
            heading = _build_open_chat_heading(
                date_part=date,
                kind=kind,
                org_label=route.org_label,
                direction=direction,
                sender_label=sender_label,
                summary=make_summary(text),
                thread_display_title=thread_title,
            )
            body = f"[messageId] {message_id}\n"
            if thread_mid:
                body += f"[threadMid] {thread_mid}\n"
            elif chat_mid != route.chat_mid:
                body += f"[squareChatMid] {chat_mid}\n"
            if related:
                body += f"[relatedMessageId] {related}\n"
            body += f"\n{text}"
            _append(route, heading, body)
            dedup.add(key)
            batch_msg_ids.add(message_id)
            msgid_to_route[message_id] = route
            flush_state["count"] += 1
            _maybe_flush()
            _status(
                state="running",
                last_append_at=datetime.now().astimezone().isoformat(timespec="seconds"),
                last_append_route=route.rid,
                last_append_kind=kind,
            )
            if len(msgid_to_route) > 5000:
                for k in list(msgid_to_route.keys())[:1000]:
                    msgid_to_route.pop(k, None)
            if args.verbose:
                print(
                    f"# append {route.rid} kind={kind} msg={message_id} "
                    f"thread={bool(thread_mid)} related={bool(related)} "
                    f"src={route_source} ev={event_code}",
                    file=sys.stderr,
                )

        def _process_square_event(event: Any, event_code: int):
            # 専用スレッド（SquareEventType=54）
            if event_code == 54:
                extracted = _extract_thread_notification(event)
                if extracted is None:
                    if args.verbose:
                        print(f"# skip event_code=54 (no notificationThreadMessage)", file=sys.stderr)
                    return
                chat_mid, thread_mid, msg = extracted
                route = routes_by_chat.get(chat_mid)
                if route is None:
                    if args.verbose:
                        print(f"# skip event_code=54 unmatched chat={chat_mid}", file=sys.stderr)
                    return
                related = str(_get(msg, "relatedMessageId", 21) or "").strip()
                _append_message(
                    route=route,
                    msg=msg,
                    chat_mid=chat_mid,
                    thread_mid=thread_mid,
                    related=related,
                    event_code=event_code,
                    route_source="notificationThreadMessage",
                )
                return

            notif = _get(event, "payload", 4)
            notif_msg = _get(notif, "notificationMessage", 30, 1)
            if notif_msg is None:
                notif_msg = _get(event, 4, "val_4")
                notif_msg = _get(notif_msg, 30, 1)
            if notif_msg is None:
                notif_msg = _find_notification_message_like(event)
            if notif_msg is None:
                if args.verbose:
                    print(f"# skip event_code={event_code} (no notificationMessage)", file=sys.stderr)
                return

            chat_mid = _get(notif_msg, "squareChatMid", 1)
            if not isinstance(chat_mid, str):
                if args.verbose:
                    print(f"# skip event_code={event_code} (no squareChatMid)", file=sys.stderr)
                return

            sq_msg = _get(notif_msg, "squareMessage", 2)
            msg = _get(sq_msg, "message", 1) if sq_msg is not None else None
            if msg is None:
                msg = _get(notif_msg, "message", 1)
            if msg is None:
                if args.verbose:
                    print(f"# skip event_code={event_code} chat={chat_mid} (no message)", file=sys.stderr)
                return

            related = str(_get(msg, "relatedMessageId", 21) or "").strip()
            route = routes_by_chat.get(chat_mid)
            route_source = "squareChatMid"
            if route is None and related:
                route = msgid_to_route.get(related)
                if route is not None:
                    route_source = "relatedMessageId"
            if route is None:
                mids = _chat_mid_candidates(event, notif, notif_msg, sq_msg, msg)
                for cmid in mids:
                    rr = routes_by_chat.get(cmid)
                    if rr is not None:
                        route = rr
                        route_source = "event-mid-candidate"
                        break
            if route is None:
                if args.verbose:
                    print(
                        f"# skip unmatched chat_mid={chat_mid} related={bool(related)} ev={event_code}",
                        file=sys.stderr,
                    )
                return

            thread_mid = ""
            if chat_mid != route.chat_mid and _is_thread_mid(chat_mid):
                thread_mid = chat_mid
            elif chat_mid != route.chat_mid:
                # 旧経路: スレッドMIDが squareChatMid に入るケース
                thread_mid = chat_mid if chat_mid != route.chat_mid else ""

            _append_message(
                route=route,
                msg=msg,
                chat_mid=chat_mid,
                thread_mid=thread_mid,
                related=related,
                event_code=event_code,
                route_source=route_source,
            )

        def _register_square_handler(event_code: int):
            @tracer.SquareEvent(event_code)
            def _handler(event, _cl):
                _process_square_event(event, event_code)

        # 29=NOTIFICATION_MESSAGE, 54=専用スレッド。周辺コードも保険で購読
        for ev_code in (29, 30, 31, 32, 33, 34, 35, 36, 54):
            _register_square_handler(ev_code)

        @tracer.Event
        def onReady():
            _status(
                state="running",
                reason="",
                ready_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            )
            if args.verbose:
                print("# push ready", file=sys.stderr)

        @tracer.Event
        def onInitializePushConn():
            _status(
                state="running",
                reason="",
                push_initialized_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            )
            if args.verbose:
                print("# push initialized", file=sys.stderr)

        def _runtime_guard() -> None:
            last_heartbeat = 0.0
            while not stop_event.wait(MAC_LINE_CHECK_SECONDS):
                if _mac_line_is_running():
                    _status(state="blocked", reason="mac_line_started")
                    print(
                        "エラー: Mac版LINEの起動を検出しました。トークン保護のため監視を停止します。",
                        file=sys.stderr,
                    )
                    os.kill(os.getpid(), signal.SIGTERM)
                    return
                # プロセス生存の確認用。PUSH障害は tracer.run が例外終了してlaunchdが再起動する。
                now = time.time()
                if now - last_heartbeat >= HEARTBEAT_SECONDS:
                    _status(
                        state="running",
                        heartbeat_at=datetime.now().astimezone().isoformat(timespec="seconds"),
                    )
                    last_heartbeat = now

        guard_thread = threading.Thread(target=_runtime_guard, name="line-watch-guard", daemon=True)
        guard_thread.start()

        try:
            tracer.run(2, initServices=[3])
        finally:
            stop_event.set()
            _maybe_flush(force=True)
        return 0
    finally:
        stop_event.set()
        try:
            _status(
                state="stopped",
                stopped_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            )
        except Exception:
            pass
        try:
            session_cm.__exit__(None, None, None)
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
