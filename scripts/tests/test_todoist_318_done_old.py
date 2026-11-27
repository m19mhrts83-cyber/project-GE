#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""318: 上限15件・古い物の拾い・②止まりの7日ごとの済み検出・済みらしい印（件119）."""
from __future__ import annotations

import json
import sys
import unittest
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import jarvis_todoist_318_done as dn  # noqa: E402
import jarvis_todoist_318_triage as tr  # noqa: E402
import jarvis_todoist_318_work as wk  # noqa: E402
from test_todoist_318_triage import NOW, TODAY, Base, FakeReader, task  # noqa: E402

OLD = (TODAY - timedelta(days=45)).isoformat() + "T00:00:00Z"
RECENT = (TODAY - timedelta(days=3)).isoformat() + "T00:00:00Z"


def old_task(i, due=None, added=OLD, updated=OLD, **kw):
    t = task(i, **kw)
    t["due"] = due
    t["added_at"], t["updated_at"] = added, updated
    return t


class FakeSource:
    def __init__(self, name, docs=None, fail=False):
        self.name, self._docs, self._fail = name, docs or [], fail

    def fetch(self, now):
        if self._fail:
            raise RuntimeError("使えない")
        return self._docs


class LimitsTest(unittest.TestCase):
    def test_constants(self):
        self.assertEqual(tr.MAX_TASKS, 15)
        self.assertEqual(wk.MAX_ITEMS, 15)
        self.assertGreaterEqual(tr.MAX_MINUTES, tr.WORK_MAX_MINUTES)
        self.assertEqual(tr.WORK_MAX_MINUTES, 60)


class PickOldTest(unittest.TestCase):
    def test_three_stale_and_three_nodue(self):
        ts = [old_task(f"s{i}", due={"date": (TODAY + timedelta(days=9)).isoformat()}) for i in range(5)]
        ts += [old_task(f"n{i}") for i in range(5)]
        ts += [old_task("fresh", added=RECENT, updated=RECENT)]
        got = tr.pick_old(ts, tr.UID if hasattr(tr, "UID") else "u1", TODAY, {}, set())
        kinds = [k for _, k in got]
        self.assertEqual(kinds.count("old_stale"), 3)
        self.assertEqual(kinds.count("old_nodue"), 3)
        self.assertNotIn("fresh", [t["id"] for t, _ in got])

    def test_rotates_by_last_examined_and_excludes_candidates(self):
        ts = [old_task(f"n{i}") for i in range(8)]
        hist = {f"n{i}": {"last_examined": f"2026-11-{10 + i:02d}"} for i in range(8)}
        a = [t["id"] for t, _ in tr.pick_old(ts, "u1", TODAY, hist, {"n0"})]
        self.assertNotIn("n0", a)
        self.assertEqual(a[:3], ["n1", "n2", "n3"])  # 最後に見た日が古い順

    def test_recent_evaluation_counts_as_change(self):
        t = old_task("x", due={"date": (TODAY + timedelta(days=9)).isoformat()})
        hist = {"x": {"last_evaluated": (NOW - timedelta(days=2)).isoformat()}}
        self.assertEqual(tr.pick_old([t], "u1", TODAY, hist, set()), [])


class RunPicksOldTest(Base):
    def test_old_picks_are_processed_beyond_candidate_cap(self):
        ts = [task(f"c{i}", days_over=i + 1) for i in range(16)]  # 候補が上限を超えても拾いは別枠
        ts += [old_task("n1"), old_task("n2")]
        run = self.run_once(FakeReader(ts), dry=True)
        self.assertEqual(run["counts"]["picked_old_nodue"], 2)
        ids = {e["task_id"] for e in run["tasks"] if e.get("pick")}
        self.assertEqual(ids, {"n1", "n2"})
        self.assertEqual(run["counts"]["carried_over"], 1)


class MatchTest(unittest.TestCase):
    def test_two_terms_and_done_hint(self):
        doc = {"source": "slack", "url": "u", "text": "NURO光の請求書を確認して支払いました"}
        self.assertTrue(dn.match_doc("NURO光 請求書 確認", doc))
        self.assertFalse(dn.match_doc("NURO光 解約", doc))  # 特徴語が1つしか合わない（2語の題）
        self.assertFalse(dn.match_doc("NURO光 請求書", {**doc, "text": "NURO光の請求書について相談"}))  # 完了の手がかり無し

    def test_github_pr_number_and_merged_is_strong(self):
        doc = {"source": "github", "url": "g", "text": "x", "number": 696, "strong_done": True}
        self.assertTrue(dn.match_doc("PR #696 を確認", doc))
        self.assertTrue(dn.match_doc("分類基準 聞く基準", {**doc, "text": "318: 分類基準を聞く基準へ", "number": 1}))

    def test_digest_and_own_posts_and_scattered_words_do_not_match(self):
        digest = {"source": "slack", "url": "u", "text": "【ホークアイ · 判断待ち夜まとめ】NURO光 請求書 支払いました"}
        self.assertFalse(dn.match_doc("NURO光 請求書 確認", digest))
        own = {"source": "slack", "url": "u", "text": "【相談】318 Todoist消化 NURO光 請求書 支払いました"}
        self.assertFalse(dn.match_doc("NURO光 請求書 確認", own))
        far = {"source": "slack", "url": "u", "text": "NURO光 の話。" + "あ" * 200 + "請求書 は支払いました"}
        self.assertFalse(dn.match_doc("NURO光 請求書 確認", far))  # 特徴語が完了の手がかりの近くに揃っていない

    def test_generic_words_only_do_not_match(self):
        self.assertEqual(dn.terms_of("確認 対応 連絡"), [])
        self.assertFalse(dn.match_doc("確認する", {"source": "slack", "url": "u", "text": "確認 完了"}))


class DoneDetectionTest(Base):
    def docs(self):
        return [FakeSource("slack", [{"source": "slack", "url": "https://s/1", "when": "2026-11-26", "text": "NURO光 請求書 支払いました"}]),
                FakeSource("github"), FakeSource("gmail", fail=True)]

    def test_marks_likely_with_link_and_never_closes(self):
        ts = [task("a", content="NURO光 請求書 支払い確認")]
        run = self.run_once(FakeReader(ts), detect_done=True, done_sources=self.docs())
        self.assertEqual(run["counts"]["done_likely"], 1)
        e = [x for x in run["tasks"] if x["task_id"] == "a" and x.get("done_likely")][0]
        self.assertIn("済みらしい", e["comment_draft"])
        self.assertIn("https://s/1", e["comment_draft"])
        self.assertTrue(e["comment_draft"].startswith("【318】"))
        self.assertEqual(run["done"]["unavailable"], {"gmail": "RuntimeError:使えない"})
        self.assertEqual(run["writes"]["todoist"], 0)
        lst = json.loads((self.paths.root / "done_likely.json").read_text(encoding="utf-8"))
        self.assertEqual([r["task_id"] for r in lst["items"]], ["a"])
        self.assertIn("https://s/1", (self.paths.root / "done_likely.md").read_text(encoding="utf-8"))

    def test_all_sources_down_is_not_no_evidence(self):
        ts = [task("a", content="NURO光 請求書 支払い確認")]
        run = self.run_once(FakeReader(ts), detect_done=True, done_sources=[FakeSource("slack", fail=True)])
        self.assertEqual(run["result"], "partial")
        self.assertNotIn("done_check", json.loads(self.paths.history.read_text())["tasks"]["a"])

    def test_stuck_owner_rechecked_every_7_days_only(self):
        ts = [task("a", content="NURO光 請求書 支払い確認")]
        r1 = self.run_once(FakeReader(ts), detect_done=True, done_sources=[FakeSource("slack")])
        self.assertEqual(r1["counts"]["done_checked"], 1)
        # 2回目（変化なし・6日後）: 当て直さない
        t6 = NOW + timedelta(days=6)
        opts = tr.RunOptions(dry_run=False, sb=self.sb, poster=self.poster, detect_done=True, done_sources=[FakeSource("slack")])
        r2 = tr.execute(self.paths, tr.REPO / "config" / "todoist_318_criteria.yaml", self.env, lambda _t: FakeReader(ts), opts, now_fn=lambda: t6)
        self.assertEqual(r2["counts"]["done_checked"], 0)
        # 7日後に根拠が出れば、② で止まっている物にも印を付ける
        hist = json.loads(self.paths.history.read_text())
        hist["tasks"]["a"]["queue_state"] = "pending"
        self.paths.history.write_text(json.dumps(hist), encoding="utf-8")
        t7 = NOW + timedelta(days=7)
        src = [FakeSource("slack", [{"source": "slack", "url": "https://s/2", "text": "NURO光 請求書 支払いました"}])]
        opts = tr.RunOptions(dry_run=False, sb=self.sb, poster=self.poster, detect_done=True, done_sources=src)
        r3 = tr.execute(self.paths, tr.REPO / "config" / "todoist_318_criteria.yaml", self.env, lambda _t: FakeReader(ts), opts, now_fn=lambda: t7)
        self.assertEqual(r3["counts"]["done_stuck_rechecked"], 1)
        self.assertEqual(r3["counts"]["done_likely"], 1)

    def test_default_is_off_in_runoptions(self):
        self.assertFalse(tr.RunOptions().detect_done)


if __name__ == "__main__":
    unittest.main()
