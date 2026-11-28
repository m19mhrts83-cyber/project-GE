#!/usr/bin/env python3
"""IMP-001: List-Unsubscribe つき・未返信の差出人は skim（架空文のみ・ネットワークなし）。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import jarvis_night_triage_general as g  # noqa: E402

HUMANISH = "松野様\nお世話になっております。資料を公開しました。"
FROM = "service@example.com"


class _Exec:
    def __init__(self, v=None, exc=None):
        self.v, self.exc = v, exc

    def execute(self):
        if self.exc:
            raise self.exc
        return self.v


class _Svc:
    def __init__(self, v=None, exc=None):
        self.v, self.exc = v, exc

    def users(self):
        return self

    def messages(self):
        return self

    def list(self, **kw):
        self.q = kw.get("q")
        return _Exec(self.v, self.exc)


class ListUnsubscribeSkim(unittest.TestCase):
    def test_header_and_never_replied_goes_skim(self):
        k = g.classify_general_kind("資料公開のお知らせ", HUMANISH, FROM, list_unsubscribe=True, replied_before=False)
        self.assertEqual(k, "skim")

    def test_default_unchanged(self):
        self.assertEqual(g.classify_general_kind("資料公開のお知らせ", HUMANISH, FROM), "mail")

    def test_replied_before_stays_mail(self):
        k = g.classify_general_kind("資料公開のお知らせ", HUMANISH, FROM, list_unsubscribe=True, replied_before=True)
        self.assertEqual(k, "mail")

    def test_no_header_stays_mail(self):
        k = g.classify_general_kind("資料公開のお知らせ", HUMANISH, FROM, list_unsubscribe=False, replied_before=False)
        self.assertEqual(k, "mail")

    def test_strong_word_wins(self):
        k = g.classify_general_kind(
            "確認依頼", "松野様\nご返信をお願いします。", FROM, list_unsubscribe=True, replied_before=False
        )
        self.assertEqual(k, "mail")

    def test_noreply_urgent_wins(self):
        k = g.classify_general_kind(
            "お支払い期限のお知らせ", "本文", "noreply@example.com", list_unsubscribe=True, replied_before=False
        )
        self.assertEqual(k, "mail")

    def test_has_replied_lookup(self):
        self.assertTrue(g.has_replied_to_sender(_Svc({"messages": [{"id": "x"}]}), FROM))
        self.assertFalse(g.has_replied_to_sender(_Svc({}), FROM))

    def test_lookup_failure_counts_as_replied(self):
        self.assertTrue(g.has_replied_to_sender(_Svc(exc=RuntimeError("x")), FROM))
        self.assertTrue(g.has_replied_to_sender(_Svc({}), ""))


if __name__ == "__main__":
    unittest.main()
