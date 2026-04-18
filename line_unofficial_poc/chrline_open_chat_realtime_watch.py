#!/usr/bin/env python3
"""
LINE オープンチャット（Square）リアルタイム監視。

目的:
- スレッド返信を含む新着メッセージをイベント駆動で即時記録
- 30日経過で見えなくなる前に本文を蓄積

使い方:
  cd ~/git-repos/line_unofficial_poc
  .venv/bin/python chrline_open_chat_realtime_watch.py --routes-yaml ./open_chat_routes.yaml
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from CHRLINE.hooks import HooksTracer

from chrline_client_utils import build_logged_in_client, save_root_from_env
from chrline_list_open_chats_poc import iter_joined_chats
from chrline_md_utils import insert_block_after_timeline_header, make_summary, wrap_details

DEDUP_FILENAME = ".chrline_open_chat_realtime_dedup.json"


@dataclass
class RtRoute:
    rid: str
    chat_mid: str
    output_md: Path
    org_label: str
    heading_tag: str


def _is_chat_mid(s: str) -> bool:
    return len(s) >= 24 and s[:1] in {"m", "c"}


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
        out[chat_mid] = RtRoute(
            rid=rid,
            chat_mid=chat_mid,
            output_md=output_md,
            org_label=str(row.get("org_label") or rid),
            heading_tag=str(row.get("heading_tag") or "LINEオープンチャット"),
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
    trimmed = sorted(keys)[-5000:]
    path.write_text(json.dumps({"keys": trimmed}, ensure_ascii=False, indent=2), encoding="utf-8")


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
    """
    イベント構造差分に備え、notificationMessage 相当の塊を深探索で拾う。
    条件:
    - squareChatMid 相当（key=1 か 'squareChatMid'）がある
    - squareMessage / message のいずれかを持つ
    """
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
    # 秒っぽい値をミリ秒へ
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


def main() -> int:
    parser = argparse.ArgumentParser(description="オープンチャットをリアルタイム監視して MD に追記")
    parser.add_argument("--routes-yaml", type=Path, default=None, help="open_chat_routes.yaml のパス")
    parser.add_argument(
        "--allow-qr-login",
        action="store_true",
        help="保存トークン無効時に QR 再認証を許可する",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    save_root = save_root_from_env()
    dedup_path = save_root / DEDUP_FILENAME
    dedup = _load_dedup(dedup_path)

    cl = build_logged_in_client(save_root, allow_qr_login=bool(args.allow_qr_login))
    if not getattr(cl, "can_use_square", False):
        print("エラー: Square API が使えません。", file=sys.stderr)
        return 1

    routes_yaml = args.routes_yaml
    if routes_yaml is None:
        env = (os.environ.get("LINE_OPEN_CHAT_ROUTES_YAML") or "").strip()
        routes_yaml = Path(env).expanduser().resolve() if env else (Path(__file__).resolve().parent / "open_chat_routes.yaml")

    try:
        routes = _load_routes(routes_yaml, cl)
    except RuntimeError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 1
    if not routes:
        print("対象ルートがありません。", file=sys.stderr)
        return 1

    # main chat mid -> route
    routes_by_chat: dict[str, RtRoute] = dict(routes)

    # route 推定補助（relatedMessageId 経由）
    msgid_to_route: dict[str, RtRoute] = {}

    # チャットごとの自分 square member mid（方向判定用）
    my_square_mid: dict[str, str] = {}
    for cmid in routes:
        try:
            smid = cl.getMySquareMidByChatMid(cmid)
            if isinstance(smid, str):
                my_square_mid[cmid] = smid
        except Exception:
            pass

    print(f"# realtime watch start chats={len(routes)}", file=sys.stderr)
    for c, r in routes.items():
        print(f"#  - {r.rid}: {c} -> {r.output_md}", file=sys.stderr)

    tracer = HooksTracer(cl, prefixes=[""])
    stop = {"flag": False}

    def _shutdown(_sig, _frm):
        stop["flag"] = True
        _save_dedup(dedup_path, dedup)
        print("# realtime watch stop", file=sys.stderr)
        raise SystemExit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    def _process_square_event(event: Any, event_code: int):
        # 新旧構造の両方に対応
        notif = _get(event, "payload", 4)
        notif_msg = _get(notif, "notificationMessage", 30, 1)
        if notif_msg is None:
            notif_msg = _get(event, 4, "val_4")
            notif_msg = _get(notif_msg, 30, 1)
        if notif_msg is None:
            # イベント型によっては notificationMessage 直下でない
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
            # notificationMessage が message 直持ちのパターンに対応
            msg = _get(notif_msg, "message", 1)
        if msg is None:
            if args.verbose:
                print(f"# skip event_code={event_code} chat={chat_mid} (no message)", file=sys.stderr)
            return

        message_id = str(_get(msg, "id", 4) or "").strip()
        if not message_id:
            if args.verbose:
                print(f"# skip event_code={event_code} chat={chat_mid} (no messageId)", file=sys.stderr)
            return

        text = _msg_text(msg)
        if text == "[本文なし]":
            return

        related = str(_get(msg, "relatedMessageId", 21) or "").strip()

        route = routes_by_chat.get(chat_mid)
        route_source = "squareChatMid"
        if route is None and related:
            route = msgid_to_route.get(related)
            if route is not None:
                route_source = "relatedMessageId"
        if route is None:
            # squareChatMid がスレッド側 MID の可能性があるため、イベント全体から候補を抽出
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
                    f"# skip unmatched msg={message_id} chat_mid={chat_mid} related={bool(related)}",
                    file=sys.stderr,
                )
            return

        key = f"{route.chat_mid}|{message_id}"
        if key in dedup:
            return

        created_ms = _to_ms(_get(msg, "createdTime", 5))
        date = _fmt_date(created_ms)
        sender = str(_get(msg, "_from", 1) or "")
        mine = my_square_mid.get(route.chat_mid, "")
        direction = "送信" if mine and sender == mine else "受信"
        tag = f"{route.heading_tag}・メイン"
        if chat_mid != route.chat_mid:
            tag += "・スレッド"
        if related:
            tag += "・スレッド返信"
        heading = f"### {date}｜{route.org_label}｜{tag}・{direction}｜{make_summary(text)}"
        body = f"[messageId] {message_id}\n"
        if chat_mid != route.chat_mid:
            body += f"[squareChatMid] {chat_mid}\n"
        if related:
            body += f"[relatedMessageId] {related}\n"
        body += f"\n{text}"
        _append(route, heading, body)
        dedup.add(key)
        msgid_to_route[message_id] = route
        # メモリ肥大化防止
        if len(msgid_to_route) > 5000:
            for k in list(msgid_to_route.keys())[:1000]:
                msgid_to_route.pop(k, None)
        if args.verbose:
            print(
                f"# append {route.rid} msg={message_id} related={bool(related)} src={route_source} ev={event_code}",
                file=sys.stderr,
            )

    # 29 以外に配送されるケースがあるため、候補イベントを複数購読
    def _register_square_handler(event_code: int):
        @tracer.SquareEvent(event_code)
        def _handler(event, _cl):
            _process_square_event(event, event_code)

    for ev_code in (29, 30, 31, 32, 33, 34, 35, 36):
        _register_square_handler(ev_code)

    @tracer.Event
    def onReady():
        if args.verbose:
            print("# push ready", file=sys.stderr)

    @tracer.Event
    def onInitializePushConn():
        if args.verbose:
            print("# push initialized", file=sys.stderr)

    try:
        tracer.run(2, initServices=[3])
    finally:
        _save_dedup(dedup_path, dedup)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
