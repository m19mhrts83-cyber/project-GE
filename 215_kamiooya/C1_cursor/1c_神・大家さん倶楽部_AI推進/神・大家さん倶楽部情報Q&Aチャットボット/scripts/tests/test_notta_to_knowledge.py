#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Notta 取込の単体テスト（pytest なしでも実行可）"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1]
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from knowledge_local import connect, counts, make_chunk_key, search_all  # noqa: E402
from notta_to_knowledge import chunk_cues, parse_srt, parse_xlsx  # noqa: E402


FIX = ROOT / "fixtures" / "notta"


def test_parse_srt():
    cues, _ = parse_srt(FIX / "with_ts.srt"), []
    # parse_srt returns list only
    cues = parse_srt(FIX / "with_ts.srt")
    assert len(cues) >= 4
    assert cues[0].start_sec == 1
    assert "三井住友" in cues[0].text
    assert cues[0].speaker == "講師"


def test_parse_xlsx_with_ts():
    cues, warnings = parse_xlsx(FIX / "with_ts_speaker.xlsx")
    assert len(cues) >= 4
    assert cues[0].start_sec == 1
    assert cues[0].speaker == "講師"
    assert "possible_merged_full_text" not in warnings


def test_parse_body_only():
    cues, warnings = parse_xlsx(FIX / "body_only.xlsx")
    assert len(cues) >= 1
    assert "no_header_assumed_body_only" in warnings or all(c.start_sec == 0 for c in cues)


def test_chunk_and_idempotent_keys():
    cues = parse_srt(FIX / "with_ts.srt")
    chunks = chunk_cues(cues, max_sec=15, max_chars=200, overlap_sec=3)
    assert len(chunks) >= 1
    keys = [make_chunk_key("vid", c["start_sec"], c["content"]) for c in chunks]
    assert len(keys) == len(set(keys))


def test_srt_xlsx_time_align():
    srt = parse_srt(FIX / "with_ts.srt")
    xlsx, _ = parse_xlsx(FIX / "with_ts_speaker.xlsx")
    # first starts should be close (within 2s)
    assert abs(srt[0].start_sec - xlsx[0].start_sec) <= 2


def test_local_upsert_and_search():
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "t.sqlite3"
        conn = connect(db)
        from knowledge_local import upsert_chunks, upsert_source

        cues = parse_srt(FIX / "with_ts.srt")
        chunks = chunk_cues(cues)
        for ch in chunks:
            ch["video_id"] = "testvid"
            ch["chunk_key"] = make_chunk_key("testvid", ch["start_sec"], ch["content"])
            ch["content_hash"] = ch["chunk_key"].split(":")[-1]
        sid = upsert_source(
            conn,
            source_key="notta:testvid",
            title="テスト講義",
            video_id="testvid",
            video_url="https://example.com/v",
        )
        n1 = upsert_chunks(conn, sid, chunks)
        n2 = upsert_chunks(conn, sid, chunks)
        assert n1 == n2 == len(chunks)
        assert counts(conn)["knowledge_chunks"] == len(chunks)
        hits = search_all(conn, "金利 融資", limit=5)
        assert any(h.get("kind") == "video_chunk" for h in hits)
        assert any(h.get("start_label") for h in hits if h.get("kind") == "video_chunk")


def main() -> int:
    tests = [
        test_parse_srt,
        test_parse_xlsx_with_ts,
        test_parse_body_only,
        test_chunk_and_idempotent_keys,
        test_srt_xlsx_time_align,
        test_local_upsert_and_search,
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"OK  {fn.__name__}")
        except Exception as e:
            failed += 1
            print(f"NG  {fn.__name__}: {e}", file=sys.stderr)
    print(f"done failed={failed}/{len(tests)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
