#!/usr/bin/env python3
"""
LINE オープンチャットの各スレッドの「元投稿」（スレッドを始めたメイン投稿）を取得して JSON に貯める。

- 読み取りのみ（getSquareThread includeRootMessage=True）。送信・参加はしない。
- 対象は open_chat_routes.yaml の thread_mids。取得済みは飛ばす（途中で止めても続きから）。
- 出力: LINE_UNOFFICIAL_AUTH_DIR/openchat_thread_roots.json（.line_auth/ は git 管理外）
- DB への反映は scripts/jarvis_openchat_thread_roots_apply.py が行う。

使い方:
  cd ~/git-repos/line_unofficial_poc
  ./run_patch.sh chrline_openchat_thread_roots.py --limit 3          # お試し
  ./run_patch.sh chrline_openchat_thread_roots.py                    # 未取得を全部
  ./run_patch.sh chrline_openchat_thread_roots.py --thread-mids-from .line_auth/active_thread_mids.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from chrline_client_utils import build_logged_in_client, chrline_throttle, save_root_from_env

ROOT = Path(__file__).resolve().parent
OUT_FILENAME = "openchat_thread_roots.json"
ROOT_TEXT_MAX = 2000
SAVE_EVERY = 25


def _plain(x: Any, depth: int = 0) -> Any:
    if depth > 8:
        return None
    if isinstance(x, dict):
        return {k: _plain(v, depth + 1) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_plain(v, depth + 1) for v in x]
    dd = getattr(x, "dd", None)
    if callable(dd):
        try:
            return _plain(dd(), depth + 1)
        except Exception:
            return None
    return x


def _f(d: Any, *keys: Any) -> Any:
    """thrift の番号キー（int / str どちらでも）をたどる。"""
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k, cur.get(str(k)))
    return cur


def parse_thread_response(res: Any) -> dict[str, Any]:
    """getSquareThread の応答から元投稿を取り出す。

    応答（2026-11-18 確認）:
      1: SquareChatThread {1: threadMid, 2: chatMid, 4: rootMessageId, ...}
      3: SquareMessage {1: Message {1: 送信者(p…), 4: messageId, 5: createdTime(ms), 10: text}}
    """
    d = _plain(res)
    thread = _f(d, 1) or {}
    msg = _f(d, 3, 1) or {}
    root_id = str(_f(thread, 4) or _f(msg, 4) or "").strip()
    created = _f(msg, 5)
    text = _f(msg, 10)
    content_type = _f(msg, 15)
    out: dict[str, Any] = {
        "root_message_id": root_id or None,
        "root_sender_mid": str(_f(msg, 1) or "").strip() or None,
        "root_posted_at": (
            datetime.fromtimestamp(int(created) / 1000, tz=timezone.utc).isoformat()
            if isinstance(created, (int, float)) or (isinstance(created, str) and created.isdigit())
            else None
        ),
        "root_text": (str(text)[:ROOT_TEXT_MAX] if isinstance(text, str) and text.strip() else None),
        "root_content_type": content_type if isinstance(content_type, int) else None,
    }
    out["status"] = "ok" if (out["root_message_id"] or out["root_text"]) else "no_root"
    return out


def _classify_error(exc: BaseException) -> str:
    s = str(exc)
    if "404" in s or "刪除" in s or "削除" in s or "deleted" in s.lower():
        return "deleted"
    if "401" in s or "403" in s:
        return "denied"
    return "error"


def load_routes(yaml_path: Path) -> list[dict[str, Any]]:
    import yaml

    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    return (data.get("routes") if isinstance(data, dict) else data) or []


def load_out(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"threads": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def save_out(path: Path, data: dict[str, Any]) -> None:
    data["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="オプチャのスレッド元投稿を取得（読み取りのみ）")
    ap.add_argument("--routes-yaml", type=Path, default=ROOT / "open_chat_routes.yaml")
    ap.add_argument("--out", type=Path, default=None, help=f"既定: 認証フォルダ/{OUT_FILENAME}")
    ap.add_argument("--limit", type=int, default=0, help="今回取る最大件数（0=全部）")
    ap.add_argument("--retry-errors", action="store_true", help="前回 error/denied だったものも取り直す")
    ap.add_argument("--thread-mids-from", type=Path, default=None, help="active_thread_mids.json の threadMid だけ対象")
    ap.add_argument("--allow-qr-login", action="store_true")
    args = ap.parse_args(argv)

    save_root = save_root_from_env()
    out_path = args.out or (save_root / OUT_FILENAME)
    data = load_out(out_path)
    threads: dict[str, Any] = data.setdefault("threads", {})

    only: set[str] | None = None
    if args.thread_mids_from and args.thread_mids_from.exists():
        raw = json.loads(args.thread_mids_from.read_text(encoding="utf-8"))
        only = set()
        for v in (raw.get("routes", raw) if isinstance(raw, dict) else {}).values():
            if isinstance(v, dict):
                only.update(v.keys())
            elif isinstance(v, list):
                only.update(str(x) for x in v)

    todo: list[tuple[dict[str, Any], str]] = []
    for r in load_routes(args.routes_yaml):
        chat_mid = str(r.get("square_chat_mid") or "").strip()
        if not chat_mid:
            continue
        for m in r.get("thread_mids") or []:
            tmid = str(m).strip()
            if not tmid or (only is not None and tmid not in only):
                continue
            prev = threads.get(tmid) or {}
            st = prev.get("status")
            if st in {"ok", "no_root", "deleted"}:
                continue
            if st in {"error", "denied"} and not args.retry_errors:
                continue
            todo.append((r, tmid))
    if args.limit > 0:
        todo = todo[: args.limit]
    print(f"# 元投稿の取得: 対象 {len(todo)} 件（取得済み {len(threads)} 件）→ {out_path}", file=sys.stderr)
    if not todo:
        return 0

    cl = build_logged_in_client(save_root, allow_qr_login=bool(args.allow_qr_login))
    counts: dict[str, int] = {}
    consecutive_err = 0
    started = time.monotonic()
    for i, (r, tmid) in enumerate(todo, 1):
        chrline_throttle()
        rec: dict[str, Any] = {
            "route_id": r.get("id"),
            "chat_title": r.get("org_label"),
            "square_chat_mid": r.get("square_chat_mid"),
            "thread_title": (r.get("thread_titles") or {}).get(tmid),
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        try:
            rec.update(parse_thread_response(cl.getSquareThread(tmid, True)))
            consecutive_err = 0
        except Exception as exc:  # 1件の失敗で止めない
            rec["status"] = _classify_error(exc)
            rec["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
            consecutive_err = consecutive_err + 1 if rec["status"] in {"error", "denied"} else 0
        threads[tmid] = rec
        counts[rec["status"]] = counts.get(rec["status"], 0) + 1
        if i % SAVE_EVERY == 0:
            save_out(out_path, data)
            print(f"# {i}/{len(todo)} {counts} {int(time.monotonic() - started)}s", file=sys.stderr)
        if consecutive_err >= 10:
            print("# 連続10件失敗のため中断（セッションを確認してください）", file=sys.stderr)
            break
    save_out(out_path, data)
    print(f"# 完了: {counts}", file=sys.stderr)
    return 0 if counts.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
