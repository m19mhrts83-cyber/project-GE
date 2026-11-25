#!/usr/bin/env python3
"""Grok 候補スナップショットの単体テスト（架空データ・ネットワーク不要）。"""
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import jarvis_grok_candidates_snapshot as snap  # noqa: E402

NOW = datetime(2026, 11, 25, 3, 0, tzinfo=timezone.utc)
ROW = {
    "name": "架空不動産", "property_area": "緑区", "prefecture": "愛知県", "city": "名古屋市",
    "property_lane": "midori_caramel", "url": "https://example.test/", "contact_url": "https://example.test/c",
    "contact_email": "", "phone": "000-0000-0000", "channel": "web_form", "discovered_at": "2026-11-25",
    "_memo": "メモ",
}


def item(key="架空不動産", kind="add", at=NOW, **kw):
    return snap.make_item(ROW, kind, kw.pop("why", ""), key=key, n=1, source_md="x.md", now=at, **kw)


class SnapshotTests(unittest.TestCase):
    def test_make_item_keeps_adopt_payload_fields(self):
        it = item(kind="consult", why="メモに「要確認」")
        self.assertEqual(it["cand"]["cu"], "https://example.test/c")
        self.assertEqual(it["cand"]["ch"], "web_form")
        self.assertNotIn("_memo", it["cand"])
        self.assertEqual(it["cand"]["memo"], "メモ")

    def test_existing_and_bad_kind(self):
        it = item(kind="dup", existing={"name": "既存社", "status": "contacted", "secret": "x"})
        self.assertEqual(it["existing"], {"name": "既存社", "status": "contacted"})
        with self.assertRaises(ValueError):
            item(kind="bogus")

    def test_merge_overrides_same_key_with_newer(self):
        old = item(kind="consult", at=NOW - timedelta(days=1))
        new = item(kind="dup", at=NOW)
        out = snap.merge_items([old], [new], now=NOW)
        self.assertEqual([i["kind"] for i in out], ["dup"])

    def test_merge_keeps_newer_when_older_arrives_later(self):
        out = snap.merge_items([item(kind="dup", at=NOW)], [item(kind="add", at=NOW - timedelta(hours=1))], now=NOW)
        self.assertEqual(out[0]["kind"], "dup")

    def test_merge_expires_and_caps(self):
        old = item(key="old", at=NOW - timedelta(days=snap.KEEP_DAYS + 1))
        many = [item(key=f"k{i}", at=NOW - timedelta(minutes=i)) for i in range(snap.MAX_ITEMS + 5)]
        out = snap.merge_items([old], many, now=NOW)
        self.assertEqual(len(out), snap.MAX_ITEMS)
        self.assertNotIn("old", [i["key"] for i in out])
        self.assertEqual(out[0]["key"], "k0")

    def test_merge_drops_malformed(self):
        out = snap.merge_items([{"key": "", "kind": "add"}, {"key": "a", "kind": "zzz"}], [], now=NOW)
        self.assertEqual(out, [])


if __name__ == "__main__":
    unittest.main()
