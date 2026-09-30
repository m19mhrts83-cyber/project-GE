#!/usr/bin/env python3
"""Resolve all WeStudy CP invite URLs via findSquareByInvitationTicketV2."""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import yaml
from chrline_client_utils import build_logged_in_client, save_root_from_env

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "line_unofficial_poc"))


def ticket_from_url(url: str) -> str:
    m = re.search(r"/ti/g2/([^/?#]+)", url or "")
    return m.group(1) if m else ""


def main() -> int:
    urls = json.loads((REPO / ".jarvis_state" / "openchat_westudy_urls.json").read_text())["urls"]
    old_path = REPO / ".jarvis_state" / "openchat_join_resolve.json"
    old = {r.get("url") for r in json.loads(old_path.read_text())} if old_path.exists() else set()
    routes = yaml.safe_load((REPO / "line_unofficial_poc" / "open_chat_routes.yaml").read_text())["routes"]
    yaml_mids = {r.get("square_chat_mid") for r in routes if r.get("square_chat_mid")}

    cl = build_logged_in_client(save_root_from_env(), allow_qr_login=False)
    rows: list[dict] = []
    for i, url in enumerate(urls, 1):
        t = ticket_from_url(url)
        row: dict = {"i": i, "url": url, "ticket": t, "in_old_set": url in old}
        try:
            res = cl.findSquareByInvitationTicketV2(t)
            dd = res.dd()
            sq = dd.get(1)
            chat = dd.get(7)
            sq_dd = sq.dd() if sq is not None else {}
            chat_dd = chat.dd() if chat is not None else {}
            name = str(sq_dd.get(2) or chat_dd.get(4) or "")
            chat_mid = str(chat_dd.get(1) or "")
            sq_mid = str(sq_dd.get(1) or "")
            in_yaml = chat_mid in yaml_mids
            row.update(
                {
                    "resolved_name": name,
                    "square_mid": sq_mid,
                    "square_chat_mid": chat_mid,
                    "in_yaml": in_yaml,
                }
            )
            tag = "YAML" if in_yaml else ("OLD " if url in old else "NEW ")
            print(f"{i:02d} {tag} {name}")
        except Exception as e:
            row["error"] = f"{type(e).__name__}: {e}"
            print(f"{i:02d} ERR {e}")
        rows.append(row)
        time.sleep(0.35)

    out = REPO / ".jarvis_state" / "openchat_westudy_resolve_all.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    want = ["02", "13-1", "24", "26", "50", "200", "201", "初心者", "DIY", "RC", "相続", "FIRE", "独身"]
    print("\n=== not in YAML (interesting) ===")
    for r in rows:
        name = r.get("resolved_name") or ""
        if r.get("in_yaml"):
            continue
        if any(w in name for w in want) or not r.get("in_old_set"):
            print(f"  NEED  {name}")
            print(f"        {r['url']}")
    print(f"\nsaved {out}")
    return 0


if __name__ == "__main__":
    # run from line_unofficial_poc via run_patch so CHRLINE imports work
    raise SystemExit(main())
