"""python3 -m unittest scripts/tests/test_kurashift_property_mail_match_fingerprint.py
fingerprint 付与と既存重複の判定（モックのみ。DB・Gmail は呼ばない）。データは架空。
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import jarvis_kurashift_property_mail_match as m  # noqa: E402


class FakeSb:
    """select/update/eq/limit/execute をたどる最小モック。"""

    def __init__(self, rows):
        self.rows = rows
        self.updates = []
        self._sel = None
        self._eq = None

    def table(self, _):
        return self

    def select(self, *_):
        self._mode = "select"
        return self

    def update(self, payload):
        self._mode = "update"
        self._payload = payload
        return self

    def eq(self, _col, val):
        self._eq = val
        return self

    def limit(self, _):
        return self

    def execute(self):
        r = mock.Mock()
        if self._mode == "update":
            self.updates.append((self._eq, self._payload))
            r.data = []
        else:
            r.data = [x for x in self.rows if x["id"] == self._eq]
        return r


class FingerprintTest(unittest.TestCase):
    def test_row_fingerprint_url_normalized(self):
        a = m.row_fingerprint({"title": "t", "summary_json": {"listing_url": "https://example.com/p/1?utm_source=x"}})
        b = m.row_fingerprint({"title": "other", "summary_json": {"listing_url": "https://example.com/p/1/"}})
        self.assertEqual(a, b)
        self.assertTrue(a.startswith("url:"))

    def test_row_fingerprint_title_price_area(self):
        r = {"title": "Re: 物件A", "price_man": 1000, "area": "X市", "summary_json": {}}
        self.assertTrue(m.row_fingerprint(r).startswith("tp:"))

    def test_row_fingerprint_empty_when_no_basis(self):
        self.assertEqual(m.row_fingerprint({"summary_json": {}}), "")

    def test_index_computes_missing_fingerprint_and_skips_losers(self):
        deals = [
            {"id": "1", "title": "物件A", "price_man": 1000, "area": "X", "summary_json": {}},
            {"id": "2", "title": "物件B", "price_man": 2000, "area": "Y", "summary_json": {"duplicate_of": "1"}},
        ]
        with mock.patch("jarvis_kurashift_re_deal_dedupe_merge.fetch_all_deals", return_value=deals):
            idx = m.build_fingerprint_index(object())
        self.assertEqual(list(idx.values()), ["1"])
        new = {"title": "物件A", "price_man": 1000, "area": "X", "summary_json": {}}
        self.assertIn(m.row_fingerprint(new), idx)

    def test_record_duplicate_gmail_appends_once(self):
        sb = FakeSb([{"id": "1", "summary_json": {"gmail_id": "g0"}}])
        m.record_duplicate_gmail(sb, "1", "g1")
        self.assertEqual(sb.updates[0][1]["summary_json"]["duplicate_gmail_ids"], ["g1"])
        sb2 = FakeSb([{"id": "1", "summary_json": {"duplicate_gmail_ids": ["g1"]}}])
        m.record_duplicate_gmail(sb2, "1", "g1")
        self.assertEqual(sb2.updates, [])


if __name__ == "__main__":
    unittest.main()
