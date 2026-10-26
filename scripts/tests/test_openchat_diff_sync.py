#!/usr/bin/env python3
"""差分 openchat sync の単体テスト（DB 不要）。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

from jarvis_kurashift_openchat_sync import (  # noqa: E402
    partition_diff_rows,
    partition_windowed_rows,
    row_fingerprint,
)
from jarvis_openchat_publish import is_noise  # noqa: E402


def _row(**kwargs):
    base = {
        "id": "oc_x",
        "route_id": "r1",
        "chat_title": "修繕",
        "chat_name": "修繕",
        "stream_type": "main",
        "thread_title": None,
        "post_date": "2026-10-01",
        "posted_at": "2026-10-01T12:00:00+09:00",
        "sender_name": "A",
        "content": "漏水です",
        "is_repair_related": True,
        "repair_category": "水回り・給排水",
        "source_system": "line_openchat",
        "ingest_status": "staging",
        "metadata": {},
    }
    base.update(kwargs)
    return base


class DiffSyncTests(unittest.TestCase):
    def test_new_row(self):
        parsed = [_row(id="oc_new")]
        upsert, _, unchanged = partition_diff_rows(parsed, {})
        self.assertEqual(len(upsert), 1)
        self.assertEqual(unchanged, 0)
        self.assertEqual(upsert[0]["ingest_status"], "staging")

    def test_unchanged_skipped(self):
        existing = {"oc_1": _row(id="oc_1", ingest_status="ready")}
        parsed = [_row(id="oc_1")]
        upsert, _, unchanged = partition_diff_rows(parsed, existing)
        self.assertEqual(len(upsert), 0)
        self.assertEqual(unchanged, 1)

    def test_content_change(self):
        existing = {"oc_1": _row(id="oc_1", content="旧本文")}
        parsed = [_row(id="oc_1", content="新本文")]
        upsert, _, unchanged = partition_diff_rows(parsed, existing)
        self.assertEqual(len(upsert), 1)
        self.assertEqual(unchanged, 0)
        self.assertEqual(upsert[0]["content"], "新本文")

    def test_fingerprint_normalizes_empty(self):
        a = row_fingerprint(_row(thread_title="", sender_name=None))
        b = row_fingerprint(_row(thread_title=None, sender_name=""))
        self.assertEqual(a, b)

    def test_window_old_known_skipped_without_body(self):
        # 窓より古く DB にある行は本文を照合せず変更なし扱い
        parsed = [_row(id="oc_old", post_date="2026-09-01", content="本文が違っても")]
        upsert, unchanged = partition_windowed_rows(parsed, {}, {"oc_old"}, "2026-10-12")
        self.assertEqual(upsert, [])
        self.assertEqual(unchanged, 1)

    def test_window_old_but_missing_is_new(self):
        # スレ追い取り等で古い日付の未登録行が来たら新規として入れる
        parsed = [_row(id="oc_backfill", post_date="2026-09-01")]
        upsert, unchanged = partition_windowed_rows(parsed, {}, set(), "2026-10-12")
        self.assertEqual([r["id"] for r in upsert], ["oc_backfill"])
        self.assertEqual(unchanged, 0)

    def test_window_recent_compares_body(self):
        existing = {"oc_r": _row(id="oc_r", post_date="2026-10-20", content="旧")}
        same = _row(id="oc_s", post_date="2026-10-20")
        existing["oc_s"] = dict(same)
        parsed = [_row(id="oc_r", post_date="2026-10-20", content="新"), same]
        upsert, unchanged = partition_windowed_rows(
            parsed, existing, {"oc_r", "oc_s"}, "2026-10-12"
        )
        self.assertEqual([r["id"] for r in upsert], ["oc_r"])
        self.assertEqual(unchanged, 1)

    def test_noise(self):
        self.assertTrue(is_noise(""))
        self.assertTrue(is_noise("[非テキスト contentType=1]"))
        self.assertTrue(is_noise("物件紹介になります 想定表面利回り"))
        self.assertFalse(is_noise("水道の漏水で困っています"))


if __name__ == "__main__":
    unittest.main()
