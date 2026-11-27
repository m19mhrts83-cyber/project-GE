"""未読が上限を超えても、パートナー送信元の検索が先に走り拾われる（2026-11-27）。架空データのみ。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "215_kamiooya" / "C1_cursor" / "1b_Cursorマニュアル"))

import jarvis_gha_partner_gmail_yoritoori as m  # noqa: E402


class FakeService:
    def __init__(self, by_query):
        self.by_query = by_query
        self.asked = []

    def users(self):
        return self

    def messages(self):
        return self

    def list(self, userId, q, maxResults):
        self.asked.append(q)
        ids = self.by_query[q]
        outer = self

        class _E:
            def execute(_s):
                return {"messages": [{"id": i} for i in ids]}

        return _E()


def _stats():
    return {"scanned": 0, "appended": 0, "dup": 0, "no_partner": 0, "fail": 0, "dry_run": 0}


class ScanOrderTest(unittest.TestCase):
    def test_partner_found_even_when_unread_exceeds_limit(self):
        unread = [f"u{i}" for i in range(50)]
        svc = FakeService({"PARTNER": ["p1", "p2", "u3"], "is:unread": unread})
        calls = []

        def fake_process(service, mid, resolver, **kw):
            calls.append(mid)
            return "appended" if mid.startswith("p") else "no_partner"

        st = _stats()
        with mock.patch.object(m, "process_one", fake_process):
            m.scan_queries(svc, None, ["PARTNER", "is:unread"], limit=10, dry_run=True, stats=st)
        self.assertEqual(svc.asked, ["PARTNER", "is:unread"])
        self.assertEqual(st["appended"], 2)
        self.assertIn("p1", calls)
        self.assertIn("p2", calls)
        self.assertEqual(calls.count("u3"), 1)  # 両方に出ても1回だけ
        self.assertEqual(st["scanned"], 3 + 9)  # partner 3 + unread は u3 を除く先頭から 10 件枠

    def test_each_query_has_own_limit(self):
        svc = FakeService({"A": [f"a{i}" for i in range(30)], "B": [f"b{i}" for i in range(30)]})
        st = _stats()
        with mock.patch.object(m, "process_one", lambda *a, **k: "no_partner"):
            m.scan_queries(svc, None, ["A", "B"], limit=5, dry_run=True, stats=st)
        self.assertEqual(st["scanned"], 10)


if __name__ == "__main__":
    unittest.main()
