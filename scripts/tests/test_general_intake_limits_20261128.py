#!/usr/bin/env python3
"""general 取込の上限・未読クエリ・no-reply 例外・metadata 先判定（架空文のみ・ネットワークなし）。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import jarvis_night_triage_general as g  # noqa: E402


def _msg(frm: str, subj: str, ms: int = 1000) -> dict:
    return {
        "id": "m1",
        "internalDate": str(ms),
        "payload": {"headers": [{"name": "From", "value": frm}, {"name": "Subject", "value": subj}]},
    }


class _Exec:
    def __init__(self, v):
        self.v = v

    def execute(self):
        return self.v


class FakeService:
    def __init__(self, threads, metas, pages=None):
        self.threads_ = threads
        self.metas = metas
        self.formats: list[str] = []
        self.list_calls: list[dict] = []
        self.pages = pages

    def users(self):
        return self

    def threads(self):
        return self

    def list(self, **kw):
        self.list_calls.append(kw)
        if self.pages is not None:
            return _Exec(self.pages[len(self.list_calls) - 1])
        return _Exec({"threads": self.threads_})

    def get(self, userId, id, format, **kw):
        self.formats.append(format)
        return _Exec({"messages": [self.metas[id]]})


class QueryAndLimitTest(unittest.TestCase):
    def test_unread_query_switch(self):
        self.assertIn("is:unread", g.build_general_query(14, True))
        self.assertNotIn("is:unread", g.build_general_query(14, False))
        with mock.patch.object(g, "UNREAD_ONLY", False):
            self.assertNotIn("is:unread", g.build_general_query(14))

    def test_max_threads_default_and_override(self):
        self.assertEqual(g.resolve_max_threads(None), g.DEFAULT_MAX_THREADS)
        self.assertGreaterEqual(g.DEFAULT_MAX_THREADS, 150)
        self.assertEqual(g.resolve_max_threads(7), 7)
        with mock.patch.dict("os.environ", {"GENERAL_MAX_THREADS": "33"}):
            self.assertEqual(g.resolve_max_threads(None), 33)

    def test_paging_and_truncation(self):
        pages = [
            {"threads": [{"id": "a"}, {"id": "b"}], "nextPageToken": "t1"},
            {"threads": [{"id": "c"}, {"id": "d"}], "nextPageToken": "t2"},
        ]
        svc = FakeService([], {}, pages=pages)
        got, trunc = g._fetch_threads(svc, "q", 3)
        self.assertEqual([t["id"] for t in got], ["a", "b", "c"])
        self.assertTrue(trunc)
        self.assertEqual(len(svc.list_calls), 2)


class NoreplyExceptionTest(unittest.TestCase):
    def test_strong_subject_kept(self):
        for subj in ("口座連携エラーのお知らせ", "お引き落とし未済のご連絡", "書類提出のお願い（期限あり）"):
            self.assertTrue(g.is_noreply_urgent_notice("noreply@ex.example.com", subj), subj)
            self.assertEqual(g.classify_general_kind(subj, "", "noreply@ex.example.com"), "mail")

    def test_no_strong_word_dropped(self):
        self.assertFalse(g.is_noreply_urgent_notice("noreply@ex.example.com", "ご利用明細のお知らせ"))
        self.assertEqual(g.classify_general_kind("ご利用明細のお知らせ", "", "noreply@ex.example.com"), "skim")

    def test_promo_dropped(self):
        for subj in ("期限間近！お得なキャンペーン", "セール最終日 提出不要"):
            self.assertFalse(g.is_noreply_urgent_notice("noreply@ex.example.com", subj), subj)

    def test_new_registration_not_revived(self):
        self.assertFalse(g.is_noreply_urgent_notice("noreply@ex.example.com", "新規登録の承認のお願い・期限"))

    def test_non_noreply_noise_unchanged(self):
        self.assertFalse(g.is_noreply_urgent_notice("news@ex.example.com", "エラーのお知らせ"))
        self.assertFalse(g.is_noreply_urgent_notice("alerts@github.com", "エラー"))


class MetadataFirstTest(unittest.TestCase):
    def _run(self, metas):
        svc = FakeService([{"id": k} for k in metas], metas)
        full_calls: list[str] = []
        orig_get = svc.get

        def get(userId, id, format, **kw):
            if format == "full":
                full_calls.append(id)
                return _Exec({"messages": []})
            return orig_get(userId, id, format, **kw)

        svc.get = get  # type: ignore[assignment]
        with mock.patch.object(g, "build_admin_gmail_service", return_value=(svc, "me@ex.example.com")), \
             mock.patch.object(g, "load_partner_filters", return_value=(set(), set())):
            g.find_general_unreplied(contact_yaml=Path("x.yaml"), max_threads=10)
        return full_calls

    def test_noise_not_fetched_full_and_urgent_is(self):
        metas = {
            "n1": _msg("Bot <noreply@ex.example.com>", "ご利用明細のお知らせ"),
            "n2": _msg("x@ex.example.com", "配信停止はこちら"),
            "u1": _msg("Bot <noreply@ex.example.com>", "口座連携エラーのお知らせ"),
            "h1": _msg("Taro <taro.yamada@ex.example.com>", "打合せの件"),
        }
        full = self._run(metas)
        self.assertNotIn("n1", full)
        self.assertNotIn("n2", full)
        self.assertIn("u1", full)
        self.assertIn("h1", full)


if __name__ == "__main__":
    unittest.main()
