#!/usr/bin/env python3
"""318 Todoist消化係 Phase 2 のテスト（/313/bulk・週次・本人回答・通知・313/317 との重なり）。ネットワーク不要。"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "scripts" / "tests"))

import jarvis_todoist_313_cleanup as cl  # noqa: E402
import jarvis_todoist_318_handoff as ho  # noqa: E402
import jarvis_todoist_318_triage as tr  # noqa: E402
import jarvis_todoist_weekly_pick as wp  # noqa: E402
import jarvis_todoist_webhook_handle as wh  # noqa: E402
from test_todoist_318_triage import CRITERIA, NOW, TODAY, FakeReader, FakeSb, task  # noqa: E402


def decision(tid: str, action: str, at: str = "2026-11-23T01:00:00+00:00", did: str = "d1") -> dict:
    return {"id": did, "action": action, "target_id": tid, "decided_at": at}


class P2Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name)
        self.paths = tr.Paths(self.state)
        (self.state / "todoist_313_judgments.json").write_text(json.dumps({"keep": {}}), encoding="utf-8")
        # 313 0.5 の作業ファイル（/tmp）が実機にあっても結果が変わらないように、無い場所を指す
        _p = mock.patch.object(tr.ms, "T313_PENDING", self.state / "no_t313_pending.json")
        _p.start()
        self.addCleanup(_p.stop)
        self.env = {"TODOIST_API_TOKEN_OWNER": "dummy"}
        self.sb = FakeSb()
        self.posts: list[tuple[str, str]] = []
        self.post_ok = True

    def tearDown(self):
        self.tmp.cleanup()

    def poster(self, ch, text):
        self.posts.append((ch, text))
        return self.post_ok

    def run_once(self, tasks, comments=None, *, now=NOW, dry=False, **kw):
        kw.setdefault("sb", self.sb)
        kw.setdefault("poster", self.poster)
        opts = tr.RunOptions(dry_run=dry, **kw)
        return tr.execute(self.paths, CRITERIA, self.env, lambda _t: FakeReader(tasks, comments), opts, now_fn=lambda: now)

    def hist(self):
        return json.loads(self.paths.history.read_text(encoding="utf-8"))["tasks"]


class OwnerAnswersTest(P2Base):
    def test_read_failure_is_safe_stop(self):
        run = self.run_once([task("a")], sb=FakeSb(fail=True))
        self.assertEqual(run["result"], "failed")
        self.assertEqual(run["stop_code"], "owner_answers_unreadable")
        self.assertFalse(self.paths.history.exists())

    def test_no_reader_is_safe_stop_unless_skip(self):
        opts = tr.RunOptions(dry_run=True, sb=None)
        run = tr.execute(self.paths, CRITERIA, self.env, lambda _t: FakeReader([task("a")]), opts, now_fn=lambda: NOW)
        self.assertEqual(run["stop_code"], "owner_answers_unavailable")
        run = self.run_once([task("a")], dry=True, sb=None, owner_answers="skip")
        self.assertEqual(run["result"], "success")
        self.assertEqual(run["basis"]["owner_answers"], "skipped（明示）")

    def test_answer_is_imported_and_not_reasked_then_rechecked(self):
        t = task("a", content="どうするか決める")
        self.run_once([t])
        self.assertEqual(self.hist()["a"]["queue_state"], "pending")
        self.sb.decisions = [decision("a", "defer")]
        run = self.run_once([t])
        e = run["tasks"][0]
        self.assertEqual(e["status"], "answered")
        self.assertEqual(run["counts"]["answered"], 1)
        self.assertEqual(run["counts"]["queued"], 0)  # 聞き直さない
        h = self.hist()["a"]
        self.assertEqual(h["queue_state"], "answered")
        self.assertEqual(h["recheck_on"], (TODAY + timedelta(days=14)).isoformat())
        # 変化なしのまま 14 日たつと再評価して、また ② なら待ちに戻る
        later = NOW + timedelta(days=14)
        run = self.run_once([t], now=later)
        self.assertEqual(run["tasks"][0]["status"], "recheck")
        self.assertEqual(run["counts"]["queued"], 1)

    def test_answer_with_due_change_is_not_reasked(self):
        self.run_once([task("a", content="どうするか決める")])
        self.sb.decisions = [decision("a", "reschedule")]
        moved = task("a", content="どうするか決める", days_over=0)
        run = self.run_once([moved])
        self.assertEqual(run["tasks"][0]["status"], "answered")
        self.assertEqual(self.hist()["a"]["recheck_on"], TODAY.isoformat())

    def test_new_task_inside_answer_hold_is_not_asked(self):
        self.sb.decisions = [decision("a", "defer")]
        run = self.run_once([task("a", content="どうするか決める")])
        self.assertEqual(run["tasks"][0]["status"], "answered")
        self.assertEqual(run["counts"]["queued"], 0)


class RouteTest(P2Base):
    def test_default_writes_preview_only(self):
        run = self.run_once([task("a", content="どうするか決める"), task("b", content="窓口で受け取り")])
        self.assertEqual(run["counts"]["queued"], 1)
        self.assertEqual(run["counts"]["handoff"], 1)
        self.assertFalse(run["published"])
        self.assertEqual(self.sb.writes, [])
        self.assertEqual(self.posts, [])
        self.assertTrue((self.paths.root / "bulk_queue.preview.json").exists())
        self.assertFalse(self.paths.bulk_queue.exists())  # 313 が外すのは載せた件だけ
        self.assertTrue((self.paths.drafts / f"{run['run_id']}_consult.txt").exists())
        self.assertTrue((self.paths.drafts / f"{run['run_id']}_hub.txt").exists())
        self.assertEqual(run["writes"], {"todoist": 0, "slack": 0, "supabase": 0})

    def test_publish_writes_both_keys_and_card_shape(self):
        run = self.run_once([task("a", content="どうするか決める"), task("b", content="窓口で受け取り")], publish=True)
        self.assertTrue(run["published"])
        keys = [w["key"] for w in self.sb.writes]
        self.assertEqual(keys, [ho.QUEUE_KEY, ho.HANDOFF_KEY])
        q = json.loads(self.sb.writes[0]["value"])
        c = q["cards"][0]
        for k in ("id", "title", "suggest", "why", "due", "origin"):
            self.assertIn(k, c)
        self.assertEqual(c["origin"], "318")
        self.assertEqual(c["suggest"], "keep")
        h = json.loads(self.sb.writes[1]["value"])
        self.assertEqual([x["id"] for x in h["items"]], ["b"])
        self.assertEqual(ho.published_queue_ids(self.paths.bulk_queue), {"a"})

    def test_dry_run_ignores_publish_and_send(self):
        run = self.run_once([task("a", content="どうするか決める")], dry=True, publish=True, send_slack=True)
        self.assertEqual(self.sb.writes, [])
        self.assertEqual(self.posts, [])
        self.assertEqual(run["flags"], {"publish": False, "send_slack": False, "write_comments": False})

    def test_asked_by_313_is_not_queued(self):
        (self.state / "todoist_313_cleanup.json").write_text(
            json.dumps({"at": (NOW - timedelta(hours=10)).isoformat(), "items": [{"task_id": "a"}]}), encoding="utf-8"
        )
        run = self.run_once([task("a", content="どうするか決める")], publish=True)
        self.assertEqual(run["counts"]["queued"], 0)
        self.assertEqual(run["counts"]["asked_313"], 1)

    def test_old_313_state_does_not_block(self):
        (self.state / "todoist_313_cleanup.json").write_text(
            json.dumps({"at": (NOW - timedelta(days=3)).isoformat(), "items": [{"task_id": "a"}]}), encoding="utf-8"
        )
        run = self.run_once([task("a", content="どうするか決める")])
        self.assertEqual(run["counts"]["queued"], 1)

    def test_broken_313_state_is_partial_and_no_queue(self):
        (self.state / "todoist_313_cleanup.json").write_text("{broken", encoding="utf-8")
        run = self.run_once([task("a", content="どうするか決める")], publish=True)
        self.assertEqual(run["result"], "partial")
        self.assertEqual(run["counts"]["queued"], 0)

    def test_publish_failure_is_partial(self):
        class Half(FakeSb):
            def __call__(self, path, **kw):
                if path == "sync_meta":
                    raise OSError("x")
                return super().__call__(path, **kw)

        run = self.run_once([task("a", content="どうするか決める")], publish=True, sb=Half())
        self.assertEqual(run["result"], "partial")
        self.assertFalse(run["published"])
        self.assertFalse(self.paths.bulk_queue.exists())

    def test_reclassified_away_from_2_leaves_queue(self):
        self.run_once([task("a", content="どうするか決める")])
        run = self.run_once([task("a", content="窓口で受け取り")])
        self.assertEqual(run["counts"]["queued"], 0)
        self.assertEqual(run["counts"]["handoff"], 1)

    def test_closed_task_leaves_queue(self):
        self.run_once([task("a", content="どうするか決める")])
        run = self.run_once([])
        self.assertEqual(run["counts"]["queued"], 0)


class NotifyTest(P2Base):
    def test_send_needs_publish_for_consult(self):
        run = self.run_once([task("a", content="どうするか決める")], send_slack=True)
        self.assertEqual([c for c, _ in self.posts], ["hub"])
        self.assertIn("consult_skip", run["notify"])

    def test_consult_once_then_hub_every_run(self):
        t = [task("a", content="どうするか決める")]
        self.run_once(t, publish=True, send_slack=True)
        self.assertEqual([c for c, _ in self.posts], ["consult", "hub"])
        self.assertIn("/313/bulk", self.posts[0][1])
        self.assertTrue(self.posts[0][1].startswith("【相談】318 Todoist消化"))
        self.assertTrue(self.posts[1][1].startswith("【報告】318 Todoist消化"))
        self.posts.clear()
        run = self.run_once(t, publish=True, send_slack=True)
        self.assertEqual([c for c, _ in self.posts], ["hub"])  # 同じ件をもう一度知らせない
        self.assertEqual(run["notify"]["consult_new"], 0)

    def test_consult_failure_is_partial_and_retried(self):
        self.post_ok = False
        run = self.run_once([task("a", content="どうするか決める")], publish=True, send_slack=True)
        self.assertEqual(run["result"], "partial")
        self.assertNotIn("notified_at", self.hist()["a"])

    def test_stopped_does_not_send(self):
        self.paths.root.mkdir(parents=True)
        self.paths.stop.write_text("", encoding="utf-8")
        self.run_once([task("a")], publish=True, send_slack=True)
        self.assertEqual(self.posts, [])


class Cleanup313Test(unittest.TestCase):
    def test_collect_items_skips_318_published(self):
        today = cl._today()
        ts = [{"id": i, "content": "x", "due": {"date": (today - timedelta(days=3)).isoformat()}, "labels": []} for i in ("a", "b")]
        items, total = cl.collect_items(5, None, ts, exclude_ids={"a"})
        self.assertEqual([x["task_id"] for x in items], ["b"])
        self.assertEqual(total, 1)

    def test_published_ids_only(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "q.json"
            self.assertEqual(cl.queued_by_318(p), set())
            p.write_text(json.dumps({"published": False, "cards": [{"id": "a"}]}), encoding="utf-8")
            self.assertEqual(cl.queued_by_318(p), set())
            p.write_text(json.dumps({"published": True, "cards": [{"id": "a"}]}), encoding="utf-8")
            self.assertEqual(cl.queued_by_318(p), {"a"})
            p.write_text("{broken", encoding="utf-8")
            self.assertEqual(cl.queued_by_318(p), set())


class BulkMergeTest(unittest.TestCase):
    def doc(self, at, published=True):
        return {"published": published, "generated_at": at.isoformat(), "cards": [
            {"id": "a", "title": "古い題", "suggest": "keep", "why": "318: x", "origin": "318"},
            {"id": "b", "title": "b", "suggest": "keep", "why": "318: x", "origin": "318"},
            {"id": "c", "title": "c", "suggest": "keep", "why": "318: x", "origin": "318"},
            {"id": "gone", "title": "g", "suggest": "keep", "why": "318: x", "origin": "318"},
        ]}

    def test_merge_rules(self):
        active = {"a": {"content": "新しい題"}, "b": {"content": "b"}, "c": {"content": "c"}}
        base = [{"id": "c", "title": "c", "suggest": "close"}]
        out = ho.merge_bulk_cards(base, self.doc(NOW), active_by_id=active, held={"b"}, now=NOW)
        self.assertEqual([x["id"] for x in out], ["a", "c"])  # b は「残す」14日中、c は重複、gone は閉じた
        self.assertEqual(out[0]["title"], "新しい題")
        self.assertEqual(ho.merge_bulk_cards(base, self.doc(NOW - timedelta(days=4)), active_by_id=active, held=set(), now=NOW), base)
        self.assertEqual(ho.merge_bulk_cards(base, self.doc(NOW, False), active_by_id=active, held=set(), now=NOW), base)
        self.assertEqual(ho.merge_bulk_cards(base, None, active_by_id=active, held=set(), now=NOW), base)

    def test_read_meta_failure_is_none(self):
        def bad(*a, **k):
            raise OSError("x")

        self.assertIsNone(ho.read_meta(bad, ho.QUEUE_KEY))


class WeeklyHandoffTest(unittest.TestCase):
    def test_handoff_adds_candidate_and_reason(self):
        JST = timezone(timedelta(hours=9))
        sun = date(2026, 11, 15)
        now = datetime(2026, 11, 15, 17, 0, tzinfo=JST)
        tasks = [
            {"id": "1", "content": "🤖 窓口で受け取り", "labels": [], "priority": 1, "added_at": "2026-11-01T00:00:00Z"},
            {"id": "2", "content": "ふつうの作業", "labels": [], "priority": 1, "added_at": "2026-11-01T00:00:00Z"},
        ]
        doc = {"published": True, "generated_at": now.isoformat(), "items": [{"id": "1", "reason": ho.HANDOFF_REASON_TEXT}]}
        snap = wp.build_snapshot(tasks=tasks, completed_last_week=[], pick_history={}, inlet_topics=[], today=sun, now=now,
                                 handoff=ho.handoff_map(doc, now))
        c1 = next(c for c in snap["candidates"] if c["id"] == "1")
        self.assertEqual(c1["reasons"][0]["tag"], "handoff_318")
        self.assertTrue(c1["from_318"])
        self.assertEqual(snap["candidates"][0]["id"], "1")
        # 受け渡しが無ければ 🤖 の件は候補に入らない（従来どおり）
        snap0 = wp.build_snapshot(tasks=tasks, completed_last_week=[], pick_history={}, inlet_topics=[], today=sun, now=now)
        self.assertEqual([c["id"] for c in snap0["candidates"]], ["2"])

    def test_stale_handoff_ignored(self):
        doc = {"published": True, "generated_at": (NOW - timedelta(days=9)).isoformat(), "items": [{"id": "1"}]}
        self.assertEqual(ho.handoff_map(doc, NOW), {})


class Comment317Test(unittest.TestCase):
    def test_is_agent_comment(self):
        self.assertTrue(wh.is_agent_comment("【318】処理状態: 途中"))
        self.assertTrue(wh.is_agent_comment("  【318】x"))
        self.assertFalse(wh.is_agent_comment("318 の件どうなった？"))
        self.assertFalse(wh.is_agent_comment("こうして【318】"))
        self.assertFalse(wh.is_agent_comment(""))

    def test_handle_marks_318_processed_without_reply(self):
        rows = [
            {"id": 1, "event_name": "note:added", "event_data": {"item_id": "t1", "content": "【318】記録", "posted_uid": "owner"}},
            {"id": 2, "event_name": "note:added", "event_data": {"item_id": "t2", "content": "これお願い", "posted_uid": "owner"}},
        ]
        marked, replied = [], []
        with mock.patch.object(wh, "_process_item_completed", return_value=0), \
                mock.patch.object(wh, "_fetch_unprocessed", return_value=rows), \
                mock.patch.object(wh, "_mark_processed", side_effect=marked.append), \
                mock.patch.object(wh, "_todoist_comment", side_effect=lambda tid, body: replied.append(tid)), \
                mock.patch.object(sys, "argv", ["x", "--reply"]), \
                mock.patch.dict("os.environ", {"TODOIST_JARVIS_USER_IDS": "jarvis"}):
            wh.main()
        self.assertIn(1, marked)
        self.assertEqual(replied, ["t2"])  # 【318】には受領を返さない

    def test_dispatch_report_drops_318(self):
        import jarvis_comment_dispatch as d

        self.assertTrue(d.is_agent_comment("【318】x"))


if __name__ == "__main__":
    unittest.main()
