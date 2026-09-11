#!/usr/bin/env python3
"""参加カタログ／queue の招待URLを findSquareByInvitationTicketV2 で実名解決する。"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

from chrline_client_utils import build_logged_in_client, save_root_from_env

REPO = Path(__file__).resolve().parents[1]
QUEUE = REPO / ".jarvis_state" / "openchat_join_queue.json"
OUT = REPO / ".jarvis_state" / "openchat_join_resolve.json"


def ticket_from_url(url: str) -> str:
    m = re.search(r"/ti/g2/([^/?#]+)", url or "")
    return m.group(1) if m else ""


def resolve(cl, ticket: str) -> dict[str, str]:
    res = cl.findSquareByInvitationTicketV2(ticket)
    dd = res.dd()
    sq = dd.get(1)
    chat = dd.get(7)
    sq_dd = sq.dd() if sq is not None else {}
    chat_dd = chat.dd() if chat is not None else {}
    return {
        "square_mid": str(sq_dd.get(1) or ""),
        "name": str(sq_dd.get(2) or chat_dd.get(4) or ""),
        "square_chat_mid": str(chat_dd.get(1) or ""),
    }


def number_key(s: str) -> str:
    m = re.search(r"(\d{1,3}(?:-\d)?)", s or "")
    return m.group(1) if m else ""


def roughly_match(label: str, resolved: str) -> bool:
    ln = number_key(label)
    rn = number_key(resolved)
    if ln and rn and ln == rn:
        return True
    a = re.sub(r"[\s■!！【】]", "", label or "")
    b = re.sub(r"[\s■!！【】]", "", resolved or "")
    if not a or not b:
        return False
    return a[:8] in b or b[:8] in a


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--allow-qr-login", action="store_true")
    ap.add_argument("--sleep", type=float, default=0.4)
    args = ap.parse_args()

    queue = json.loads(QUEUE.read_text(encoding="utf-8"))
    cl = build_logged_in_client(save_root_from_env(), allow_qr_login=args.allow_qr_login)

    rows: list[dict] = []
    for it in queue:
        url = it.get("url") or ""
        t = ticket_from_url(url)
        row: dict = {
            "i": it.get("i"),
            "label": it.get("name"),
            "url": url,
            "status": it.get("status"),
            "qr_png": it.get("qr_png"),
        }
        if not t:
            row["error"] = "no ticket"
            rows.append(row)
            print(f"{it.get('i'):02d} ERROR no ticket")
            continue
        try:
            info = resolve(cl, t)
            row["resolved_name"] = info["name"]
            row["square_mid"] = info["square_mid"]
            row["square_chat_mid"] = info["square_chat_mid"]
            row["match"] = roughly_match(str(it.get("name") or ""), info["name"])
            flag = "OK" if row["match"] else "MISMATCH"
            print(f"{it.get('i'):02d} [{flag}] label={it.get('name')}")
            print(f"     resolved={info['name']}")
            print(f"     chat={info['square_chat_mid']}")
        except Exception as e:
            row["error"] = f"{type(e).__name__}:{e}"
            print(f"{it.get('i'):02d} ERROR {e}")
        rows.append(row)
        time.sleep(max(0.0, args.sleep))

    OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    mism = [r for r in rows if r.get("resolved_name") and not r.get("match")]
    print(f"\nwrote {OUT}")
    print(f"mismatch_count={len(mism)} / total={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
