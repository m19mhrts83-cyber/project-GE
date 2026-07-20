#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mirror Supabase/local knowledge (step3_1_lf etc.) into Raimo miniApp tables via admin API."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request
from pathlib import Path

CHATBOT = Path(__file__).resolve().parents[1]
API_PREFIX = "/miniAppApi/be_nXbcTm3EumRbotHtAwGGXb45raHz0"


def load_env() -> None:
    for p in [Path.home() / "git-repos" / ".env.jarvis_private", CHATBOT / "scripts" / ".env"]:
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    for a, b in [("RAIMO_APP_URL", "LIMO_APP_URL")]:
        if not os.environ.get(a) and os.environ.get(b):
            os.environ[a] = os.environ[b]


def post_json(base: str, endpoint: str, payload: dict) -> tuple[int, str]:
    url = base.rstrip("/") + API_PREFIX + endpoint
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")


def get_json(base: str, endpoint: str) -> dict:
    url = base.rstrip("/") + API_PREFIX + endpoint
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def load_from_sqlite(video_id: str) -> tuple[dict, list[dict]]:
    db = CHATBOT / "state" / "knowledge_local.sqlite3"
    if not db.exists():
        od = (
            Path.home()
            / "Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/C1_cursor/1c_神・大家さん倶楽部_AI推進/神・大家さん倶楽部情報Q&Aチャットボット/state/knowledge_local.sqlite3"
        )
        db = od
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    src = conn.execute(
        "select * from knowledge_sources where video_id = ? or source_key = ? limit 1",
        (video_id, f"notta:{video_id}"),
    ).fetchone()
    if not src:
        raise SystemExit(f"source not found for {video_id} in {db}")
    chunks = conn.execute(
        "select * from knowledge_chunks where source_id = ? order by start_sec asc",
        (src["id"],),
    ).fetchall()
    source = {
        "source_key": src["source_key"],
        "source_kind": src["source_kind"] if "source_kind" in src.keys() else "video",
        "content_channel": src["content_channel"] if "content_channel" in src.keys() else "seminar_video",
        "title": src["title"],
        "video_id": src["video_id"],
        "video_url": src["video_url"],
        "instructor": src["instructor"],
        "origin_path": src["origin_path"],
        "meta_json": src["meta_json"] if "meta_json" in src.keys() else "{}",
        "ingest_status": "ready",
    }
    if isinstance(source["meta_json"], (dict, list)):
        source["meta_json"] = json.dumps(source["meta_json"], ensure_ascii=False)
    out_chunks = []
    for ch in chunks:
        out_chunks.append(
            {
                "chunk_key": ch["chunk_key"],
                "source_key": src["source_key"],
                "start_sec": int(ch["start_sec"] or 0),
                "end_sec": ch["end_sec"],
                "speaker": ch["speaker"] or "",
                "content": ch["content"] or "",
                "search_text": ch["search_text"] if "search_text" in ch.keys() else (ch["content"] or ""),
            }
        )
    conn.close()
    return source, out_chunks


def upsert_source(base: str, source: dict) -> None:
    existing = get_json(base, "/knowledge-sources").get("sources") or []
    keys = {s.get("source_key") for s in existing}
    if source["source_key"] in keys:
        st, body = post_json(base, "/admin/knowledge-sources/update", source)
        print("source update", st, body[:200])
        if st == 404:
            st, body = post_json(base, "/admin/knowledge-sources", source)
            print("source insert fallback", st, body[:200])
    else:
        st, body = post_json(base, "/admin/knowledge-sources", source)
        print("source insert", st, body[:200])


def replace_chunks(base: str, source_key: str, chunks: list[dict]) -> tuple[int, int]:
    st, body = post_json(base, "/admin/knowledge-chunks/delete-by-source", {"source_key": source_key})
    print("chunks delete-by-source", st, body[:200])
    ok = 0
    fail = 0
    for ch in chunks:
        st, body = post_json(base, "/admin/knowledge-chunks", ch)
        if 200 <= st < 300:
            ok += 1
        else:
            fail += 1
            if fail <= 3:
                print("chunk fail", st, body[:180], ch["chunk_key"])
    return ok, fail


def main() -> int:
    load_env()
    base = (os.environ.get("RAIMO_APP_URL") or "").rstrip("/")
    if not base:
        raise SystemExit("RAIMO_APP_URL missing")
    video_id = sys.argv[1] if len(sys.argv) > 1 else "step3_1_lf"
    source, chunks = load_from_sqlite(video_id)
    print(f"mirror {video_id}: chunks={len(chunks)} title={source['title'][:40]}")

    upsert_source(base, source)
    ok, fail = replace_chunks(base, source["source_key"], chunks)
    print(f"chunks ok={ok} fail={fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
