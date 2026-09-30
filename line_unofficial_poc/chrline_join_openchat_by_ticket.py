#!/usr/bin/env python3
"""WeStudy/line.me 招待チケットから Square を解決し、joinSquare で参加する。

例:
  ./run_patch.sh chrline_join_openchat_by_ticket.py --url 'https://line.me/ti/g2/...' \\
    --display-name '松野真治' --pass-code '1162' --dry-run
  ./run_patch.sh chrline_join_openchat_by_ticket.py --from-queue --apply
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from chrline_client_utils import build_logged_in_client, save_root_from_env

REPO = Path(__file__).resolve().parents[1]
QUEUE_PATH = REPO / ".jarvis_state" / "openchat_join_queue.json"


def ticket_from_url(url: str) -> str:
    s = (url or "").strip()
    m = re.search(r"/ti/g2/([^/?#]+)", s)
    if m:
        return m.group(1)
    # bare ticket
    if re.fullmatch(r"[A-Za-z0-9_-]{10,}", s):
        return s
    raise ValueError(f"招待チケットを抽出できません: {url[:80]}")


def _get(cl, obj: Any, key: str, fid: int | None = None) -> Any:
    if obj is None:
        return None
    try:
        if fid is not None:
            v = cl.checkAndGetValue(obj, key, fid)
        else:
            v = cl.checkAndGetValue(obj, key)
        if v is not None:
            return v
    except Exception:
        pass
    dd = getattr(obj, "dd", None)
    if callable(dd):
        try:
            d = dd()
            if isinstance(d, dict):
                if key in d:
                    return d[key]
                if fid is not None and fid in d:
                    return d[fid]
        except Exception:
            pass
    return getattr(obj, key, None)


def find_square(cl, ticket: str) -> Any:
    last_err: Exception | None = None
    for meth in ("findSquareByInvitationTicketV2", "findSquareByInvitationTicket"):
        fn = getattr(cl, meth, None)
        if not callable(fn):
            continue
        try:
            return fn(ticket)
        except Exception as e:
            last_err = e
            print(f"# {meth} fail: {type(e).__name__}: {e}", file=sys.stderr)
    if last_err:
        raise last_err
    raise RuntimeError("findSquareByInvitationTicket* がありません")


def extract_mids(cl, res: Any) -> dict[str, str]:
    """findSquareByInvitationTicketV2 の thrift 構造から mid を取る。

    実測: 1=Square(mid=s…), 7=SquareChat(mid=m…), Square.14 に参加案内文。
    """
    out: dict[str, str] = {}
    dd: dict[Any, Any] = {}
    if callable(getattr(res, "dd", None)):
        try:
            dd = res.dd() or {}
        except Exception:
            dd = {}
    square = dd.get(1)
    chat = dd.get(7)
    sq_dd = square.dd() if square is not None and callable(getattr(square, "dd", None)) else {}
    chat_dd = chat.dd() if chat is not None and callable(getattr(chat, "dd", None)) else {}
    sq_mid = sq_dd.get(1) or _get(cl, square, "mid", 1)
    chat_mid = chat_dd.get(1) or _get(cl, chat, "mid", 1)
    name = sq_dd.get(2) or chat_dd.get(4) or ""
    # 参加案内（会員番号 姓 名）
    hint = ""
    try:
        join_note = sq_dd.get(14)
        if join_note is not None and callable(getattr(join_note, "dd", None)):
            hint = str(join_note.dd())
        elif isinstance(join_note, dict):
            hint = str(join_note)
    except Exception:
        pass
    if sq_mid:
        out["square_mid"] = str(sq_mid)
    if chat_mid:
        out["square_chat_mid"] = str(chat_mid)
    if name:
        out["name"] = str(name)
    if hint:
        out["join_hint"] = hint[:200]
    out["_keys"] = ",".join(str(k) for k in list(dd.keys())[:20])
    return out


def join_one(
    cl,
    *,
    ticket: str,
    display_name: str,
    pass_code: str | None,
    dry_run: bool,
) -> dict[str, Any]:
    res = find_square(cl, ticket)
    info = extract_mids(cl, res)
    print(f"# find: {json.dumps(info, ensure_ascii=False)}")
    sq = info.get("square_mid")
    chat = info.get("square_chat_mid")
    if not sq:
        return {"status": "error", "reason": "square_mid missing", "info": info, "raw_type": type(res).__name__}
    if dry_run:
        return {"status": "dry_run", "info": info}
    kwargs: dict[str, Any] = {"passCode": pass_code} if pass_code else {}
    try:
        joined = cl.joinSquare(
            sq,
            display_name,
            True,
            pass_code,
            chat,
            None,
        )
        print(f"# joinSquare OK: {type(joined).__name__}")
        return {"status": "joined", "info": info}
    except Exception as e:
        msg = f"{type(e).__name__}:{e}"
        print(f"# joinSquare fail: {msg}", file=sys.stderr)
        # retry without chat mid
        try:
            joined = cl.joinSquare(sq, display_name, True, pass_code)
            print(f"# joinSquare OK (no chatMid): {type(joined).__name__}")
            return {"status": "joined", "info": info, "note": "no_chat_mid"}
        except Exception as e2:
            return {"status": "error", "reason": f"{msg} / retry:{type(e2).__name__}:{e2}", "info": info}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="")
    ap.add_argument("--ticket", default="")
    ap.add_argument("--display-name", default="松野真治")
    ap.add_argument("--pass-code", default="")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--from-queue", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--sleep", type=float, default=1.5)
    ap.add_argument("--allow-qr-login", action="store_true")
    args = ap.parse_args()

    if not args.dry_run and not args.apply and not args.from_queue:
        print("--dry-run または --apply を指定してください", file=sys.stderr)
        return 2

    save_root = save_root_from_env()
    cl = build_logged_in_client(save_root, allow_qr_login=args.allow_qr_login)

    items: list[dict[str, Any]] = []
    if args.from_queue:
        queue = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
        for it in queue:
            if it.get("status") != "pending":
                continue
            items.append(it)
        if args.limit > 0:
            items = items[: args.limit]
    else:
        url = args.url or args.ticket
        if not url:
            print("--url / --ticket / --from-queue が必要です", file=sys.stderr)
            return 2
        items = [{"url": url, "name": url, "i": 0, "status": "pending"}]

    dry = args.dry_run or not args.apply
    results = []
    for it in items:
        name = it.get("name") or ""
        url = it.get("url") or ""
        try:
            ticket = ticket_from_url(url if "line.me" in url or url.startswith("http") else (args.ticket or url))
        except Exception as e:
            print(f"# skip {name}: {e}")
            results.append({"name": name, "status": "error", "reason": str(e)})
            continue
        print(f"\n=== [{it.get('i')}] {name} ticket={ticket[:12]}…")
        r = join_one(
            cl,
            ticket=ticket,
            display_name=args.display_name,
            pass_code=args.pass_code or None,
            dry_run=dry,
        )
        r["name"] = name
        r["url"] = url
        results.append(r)
        if args.from_queue and r.get("status") in {"joined", "dry_run"} and r.get("info"):
            # annotate queue item in memory
            it["probe"] = r
            if r.get("status") == "joined" and r["info"].get("square_chat_mid"):
                it["status"] = "joined_via_api"
                it["square_chat_mid"] = r["info"]["square_chat_mid"]
                it["square_mid"] = r["info"].get("square_mid")
                it["joined_title"] = r["info"].get("name") or name
        time.sleep(max(0.0, args.sleep))

    if args.from_queue and args.apply:
        QUEUE_PATH.write_text(
            json.dumps(_merge_queue(results), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    ok = sum(1 for r in results if r.get("status") in {"joined", "dry_run"})
    err = sum(1 for r in results if r.get("status") == "error")
    print(f"\n📎 join_by_ticket: total={len(results)} okish={ok} error={err} dry={dry}")
    return 0 if err == 0 else 1


def _merge_queue(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    queue = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    by_url = {r.get("url"): r for r in results}
    for it in queue:
        r = by_url.get(it.get("url"))
        if not r:
            continue
        if r.get("status") == "joined" and (r.get("info") or {}).get("square_chat_mid"):
            it["status"] = "joined_via_api"
            it["square_chat_mid"] = r["info"]["square_chat_mid"]
            it["square_mid"] = r["info"].get("square_mid")
            it["joined_title"] = r["info"].get("name") or it.get("name")
        elif r.get("status") == "error":
            it["last_error"] = r.get("reason")
    return queue


if __name__ == "__main__":
    raise SystemExit(main())
