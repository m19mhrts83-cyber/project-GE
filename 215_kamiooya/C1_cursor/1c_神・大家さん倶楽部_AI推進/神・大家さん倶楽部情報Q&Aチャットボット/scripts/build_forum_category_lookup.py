#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""raw CSV 群から comment_id → forum_category のクライアント lookup を生成する。

  python3 build_forum_category_lookup.py
  python3 build_forum_category_lookup.py --raw-dir ../../exports/raw/20260721-120849
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from forum_category_map import enrich_comment_meta, UNCLASSIFIED

SCRIPTS = Path(__file__).resolve().parent
CHATBOT = SCRIPTS.parent
DEFAULT_RAW = (
    Path.home()
    / "Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部"
    / "C1_cursor/1c_神・大家さん倶楽部_AI推進/神・大家さん倶楽部情報Q&Aチャットボット"
    / "exports/raw"
)


def normalize_cid(raw: str) -> str:
    s = (raw or "").strip().strip('"')
    if s.startswith("comment-"):
        s = s[8:].strip()
    return s


def collect(raw_roots: list[Path]) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for root in raw_roots:
        if not root.is_dir():
            continue
        for fp in root.rglob("*.csv"):
            try:
                with fp.open("r", encoding="utf-8-sig", newline="", errors="replace") as f:
                    reader = csv.DictReader(f)
                    if not reader.fieldnames or "comment_id" not in reader.fieldnames:
                        continue
                    for row in reader:
                        cid = normalize_cid(row.get("comment_id") or "")
                        if not cid:
                            continue
                        title = (row.get("topic_title") or "").strip()
                        url = (row.get("topic_url") or "").strip()
                        meta = enrich_comment_meta(title, url)
                        if meta["forum_category"] == UNCLASSIFIED and cid in out:
                            continue
                        out[cid] = {
                            "forum_category": meta["forum_category"],
                            "topic_title": meta["topic_title"],
                            "source_system": meta["source_system"],
                            "source_kind": meta["source_kind"],
                        }
            except Exception as e:
                print(f"[WARN] {fp}: {e}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--raw-dir",
        action="append",
        default=[],
        help="raw ディレクトリ（複数可）。未指定時は OneDrive exports/raw 配下の全 RUN",
    )
    ap.add_argument(
        "--out-json",
        default=str(CHATBOT / "forum_category_lookup.json"),
    )
    ap.add_argument(
        "--out-js",
        default=str(CHATBOT / "forum_category_lookup.js"),
    )
    args = ap.parse_args()

    roots = [Path(p).expanduser() for p in args.raw_dir] if args.raw_dir else [DEFAULT_RAW]
    mapping = collect(roots)
    cats: dict[str, int] = {}
    uncat = 0
    for m in mapping.values():
        c = m["forum_category"]
        cats[c] = cats.get(c, 0) + 1
        if c == UNCLASSIFIED:
            uncat += 1
    print(f"lookup entries: {len(mapping)} uncategorized: {uncat}")
    for k in sorted(cats, key=lambda x: -cats[x])[:30]:
        print(f"  {k}: {cats[k]}")

    out_json = Path(args.out_json)
    out_js = Path(args.out_js)
    out_json.write_text(
        json.dumps(mapping, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    # compact client map: id -> category string only (smaller)
    compact = {cid: m["forum_category"] for cid, m in mapping.items() if m["forum_category"] != UNCLASSIFIED}
    out_js.write_text(
        "window.FORUM_CATEGORY_LOOKUP = "
        + json.dumps(compact, ensure_ascii=False, separators=(",", ":"))
        + ";\n",
        encoding="utf-8",
    )
    print(f"wrote {out_json} ({out_json.stat().st_size} bytes)")
    print(f"wrote {out_js} ({out_js.stat().st_size} bytes, compact={len(compact)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
