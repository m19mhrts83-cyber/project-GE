"""313 週の整理（scripts/jarvis_todoist_313_weekly.py）— 判定・B カード・戻し・画面への混ぜ込み。

固定値は架空のもの（取引先名・実タスク名は書かない）。
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jarvis_todoist_313_weekly as w  # noqa: E402
import jarvis_todoist_cleanup_bulk as b  # noqa: E402
import jarvis_todoist_318_handoff as ho  # noqa: E402

JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 27, 20, 0, tzinfo=JST)  # 金曜 20:00
PR = "https://github.com/example/repo/pull/12"
PR2 = "https://github.com/example/repo/pull/13"
ISSUE = "https://github.com/example/repo/issues/7"
TASK_URL = "https://app.todoist.com/app/task/abc-6xYz12345"


def cfg():
    return w.load_config()


def task(i, content="作業A", desc="", added="2026-11-01T00:00:00Z", updated=None, **kw):
    return {"id": str(i), "content": content, "description": desc, "added_at": added,
            "updated_at": updated or added, "labels": kw.pop("labels", []), **kw}


def com(text, at):
    return {"content": text, "posted_at": at}


DONE = {("pr", "example/repo#12"): {"done": True, "at": "2026-11-10T00:00:00Z"}}


class ConfigTests(unittest.TestCase):
    def test_real_config_loads(self):
        c = cfg()
        self.assertEqual(c["strong_kinds"], {"pr_merged", "issue_closed"})
        self.assertEqual(c["idle_days"], 21)
        self.assertEqual(c["keep_days"], 28)
        self.assertEqual(c["undo_days"], 7)

    def test_broken_config_stops(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.yaml"
            p.write_text("done: 1\n", encoding="utf-8")
            with self.assertRaises(w.ConfigError):
                w.load_config(p)
            with self.assertRaises(w.ConfigError):
                w.load_config(Path(d) / "none.yaml")


class LinkTests(unittest.TestCase):
    def test_extract(self):
        got = w.extract_links(f"PR {PR} と {ISSUE} と {TASK_URL} と {PR}")
        self.assertEqual(sorted(k for k, _, _ in got), ["issue", "pr", "task"])
        self.assertIn(("task", "6xYz12345", TASK_URL), got)


class JudgeTests(unittest.TestCase):
    def test_merged_pr_after_task_is_strong(self):
        d = w.judge_done(task(1, desc=f"実装 {PR}"), [], DONE, cfg())
        self.assertEqual(d["level"], "strong")
        self.assertEqual(d["kind"], "pr_merged")
        self.assertEqual(d["url"], PR)

    def test_open_pr_is_nothing(self):
        st = {("pr", "example/repo#12"): {"done": False}}
        self.assertIsNone(w.judge_done(task(1, desc=PR), [], st, cfg()))

    def test_unreadable_link_is_not_done(self):
        st = {("pr", "example/repo#12"): {"done": None, "error": "HTTP 502"}}
        self.assertIsNone(w.judge_done(task(1, desc=PR), [], st, cfg()))

    def test_all_prs_must_be_merged(self):
        st = {**DONE, ("pr", "example/repo#13"): {"done": False}}
        self.assertIsNone(w.judge_done(task(1, desc=f"{PR} {PR2}"), [], st, cfg()))

    def test_pr_before_task_is_weak(self):
        d = w.judge_done(task(1, desc=PR, added="2026-11-20T00:00:00Z"), [], DONE, cfg())
        self.assertEqual(d["level"], "weak")

    def test_comment_after_merge_is_weak_unless_done_report(self):
        t = task(1, desc=PR)
        d = w.judge_done(t, [com("まだ残りがある", "2026-11-12T00:00:00Z")], DONE, cfg())
        self.assertEqual(d["level"], "weak")
        self.assertIn("根拠の後にコメントあり", d["hold"])
        d = w.judge_done(t, [com("【Miss Lemon】マージ済みです", "2026-11-12T00:00:00Z")], DONE, cfg())
        self.assertEqual(d["level"], "strong")

    def test_hold_words_send_to_owner(self):
        for words in ("本番で様子を見る", "【松野さん】で確認", "マージ後に設定する"):
            d = w.judge_done(task(1, content=f"作業 {words}", desc=PR), [], DONE, cfg())
            self.assertEqual(d["level"], "weak", words)

    def test_task_link_alone_is_weak(self):
        st = {("task", "6xYz12345"): {"done": True, "at": "2026-11-10T00:00:00Z"}}
        d = w.judge_done(task(1, desc=f"元タスク: {TASK_URL}"), [], st, cfg())
        self.assertEqual(d["level"], "weak")

    def test_task_link_ignored_when_pr_present(self):
        st = {**DONE, ("task", "6xYz12345"): {"done": False}}
        d = w.judge_done(task(1, desc=f"{PR}\n元タスク: {TASK_URL}"), [], st, cfg())
        self.assertEqual(d["level"], "strong")

    def test_agent_done_comment_is_weak(self):
        d = w.judge_done(task(1), [com("【Jarvis】完了しました", "2026-11-12T00:00:00Z")], {}, cfg())
        self.assertEqual((d["level"], d["kind"]), ("weak", "agent_comment"))


class StaleTests(unittest.TestCase):
    def test_reason(self):
        c = cfg()
        last = NOW - timedelta(days=30)
        self.assertEqual(w.stale_reason(task(1), last, NOW, c), "30日 動きなし・期日なし")
        t = task(1, due={"date": "2026-11-17"})
        self.assertEqual(w.stale_reason(t, last, NOW, c), "30日 動きなし・期日を10日過ぎ")
        self.assertIsNone(w.stale_reason(task(1, due={"date": "2026-12-10"}), last, NOW, c))  # 先の期日
        self.assertIsNone(w.stale_reason(task(1), NOW - timedelta(days=10), NOW, c))

    def test_comment_counts_as_activity(self):
        t = task(1, added="2026-09-01T00:00:00Z")
        last = w.last_activity(t, [com("x", "2026-11-20T00:00:00Z")])
        self.assertIsNone(w.stale_reason(t, last, NOW, cfg()))


class PlanTests(unittest.TestCase):
    def plan(self, tasks, comments=None, status=None, **kw):
        args = {"exclude_ids": set(), "week9_ids": set(), "kept_ids": set(), **kw}
        return w.plan(tasks, comments or {}, status or {}, cfg=cfg(), now=NOW, **args)

    def test_a_and_b_and_exclusions(self):
        old = "2026-09-01T00:00:00Z"
        tasks = [
            task(1, desc=PR),                                         # A
            task(2, added=old),                                       # B やめる
            task(3, added=old, due={"date": "2026-10-01", "is_recurring": True}),  # 繰り返し
            task(4, added=old),                                       # 318 が聞いている
            task(5, added=old),                                       # 今週の9件
            task(6, added=old),                                       # 残す 4週内
            task(7, added=old, parent_id="2"),                        # サブタスクは親で聞く
            task(8, desc=PR, added="2026-11-05T00:00:00Z"),           # 済み？（子が残る親）
            task(9, added=old, parent_id="8"),
        ]
        p = self.plan(tasks, status=DONE, exclude_ids={"4"}, week9_ids={"5"}, kept_ids={"6"})
        self.assertEqual([r["task"]["id"] for r in p["a"]], ["1"])
        bids = [r["task"]["id"] for r in p["b"]]
        self.assertEqual(bids[0], "8")  # 済み？ が先
        self.assertEqual(p["b"][0]["suggest"], "close")
        self.assertIn("サブタスク", p["b"][0]["why"])
        self.assertIn("2", bids)
        for x in ("3", "4", "5", "6", "7"):
            self.assertNotIn(x, bids)
        self.assertEqual(p["skipped"]["recurring"], 1)
        self.assertEqual(p["skipped"]["by_318"], 1)

    def test_recurring_never_closed(self):
        t = task(1, desc=PR, due={"date": "2026-11-20", "is_recurring": True})
        p = self.plan([t], status=DONE)
        self.assertEqual(p["a"], [])

    def test_caps(self):
        old = "2026-09-01T00:00:00Z"
        p = self.plan([task(i, added=old) for i in range(30)])
        self.assertEqual(len(p["b"]), 20)
        self.assertEqual(p["carried_b"], 10)

    def test_b_card_shape(self):
        p = self.plan([task(2, added="2026-09-01T00:00:00Z")])
        c = w.b_card(p["b"][0], NOW)
        self.assertEqual(c["origin"], "313")
        self.assertEqual(c["suggest"], "drop")
        self.assertEqual(c["age_days"], 87)
        for k in ("id", "title", "sender", "gmail_url", "due", "why"):
            self.assertIn(k, c)


class TextTests(unittest.TestCase):
    def test_comment_and_slack(self):
        d = {"line": "PR がマージ済み", "url": PR}
        cm = w.close_comment(d, "313", 7)
        self.assertIn("根拠: PR がマージ済み", cm)
        self.assertIn(PR, cm)
        self.assertIn("--undo", cm)
        run = {"undo_days": 7, "counts": {"closed": 1, "b_published": 2, "close_failed": 0}}
        txt = w.slack_text(run, [{"task": {"content": "作業A"}, "done": d}], [{}, {}], "https://x/313/bulk")
        self.assertTrue(txt.startswith("【相談】313 週の整理"))
        self.assertIn("済みました 1件", txt)
        self.assertIn("やめる提案 2件", txt)
        self.assertIn("/313/bulk", txt)


class UndoTests(unittest.TestCase):
    def test_undoable_window(self):
        st = {"closed": [
            {"task_id": "1", "closed_at": "2026-11-27T20:00:00+09:00", "undo_until": "2026-12-04T20:00:00+09:00"},
            {"task_id": "2", "closed_at": "2026-11-13T20:00:00+09:00", "undo_until": "2026-11-20T20:00:00+09:00"},
            {"task_id": "3", "closed_at": "2026-11-27T20:00:00+09:00", "undo_until": "2026-12-04T20:00:00+09:00",
             "undone_at": "2026-11-28T09:00:00+09:00"},
        ]}
        self.assertEqual([r["task_id"] for r in w.undoable(st, NOW + timedelta(days=1))], ["1"])
        self.assertEqual(w.undoable(st, NOW + timedelta(days=8)), [])


class BulkMergeTests(unittest.TestCase):
    def q(self, ids, at=NOW):
        return {"published": True, "generated_at": at.isoformat(), "cards": [{"id": i, "title": "古い題", "suggest": "drop", "why": "x"} for i in ids]}

    def test_order_and_filters(self):
        cards = [{"id": "a", "origin": "318"}, {"id": "s"}]
        active = {i: {"id": i, "content": f"今の題{i}"} for i in ("a", "s", "p", "q")}
        got = b.merge_313_cards(cards, self.q(["p", "a", "q", "gone", "h"]), active_by_id=active, held={"q"}, now=NOW)
        self.assertEqual([c["id"] for c in got], ["a", "p", "s"])  # 318 → 313 → スター、重複・残す中・閉じた件は出さない
        self.assertEqual(got[1]["origin"], "313")
        self.assertEqual(got[1]["title"], "今の題p")

    def test_stale_or_unpublished(self):
        active = {"p": {"id": "p", "content": "x"}}
        self.assertEqual(b.merge_313_cards([], self.q(["p"], NOW - timedelta(days=9)), active_by_id=active, held=set(), now=NOW), [])
        self.assertEqual(b.merge_313_cards([], {**self.q(["p"]), "published": False}, active_by_id=active, held=set(), now=NOW), [])
        self.assertEqual(b.merge_313_cards([], None, active_by_id=active, held=set(), now=NOW), [])


class ReflectTests(unittest.TestCase):
    def test_313_drop_closes_not_deletes(self):
        calls = []

        class Fake:
            @staticmethod
            def todoist(path, method="GET", body=None):
                calls.append((method, path))
                return {}

        orig = b._io
        b._io = lambda: Fake
        try:
            r = b.apply_one({"target_id": "9", "action": "drop", "payload": {"origin": "313"}}, dry=False)
            self.assertEqual(r, "ok")
            self.assertEqual(calls, [("POST", "comments"), ("POST", "tasks/9/close")])
            calls.clear()
            b.apply_one({"target_id": "9", "action": "drop", "payload": {"origin": "318"}}, dry=False)
            self.assertEqual(calls, [("DELETE", "tasks/9")])  # 313 以外は従来どおり
        finally:
            b._io = orig


class Handoff318Tests(unittest.TestCase):
    def test_asked_by_313_weekly(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "todoist_313_weekly.json"
            self.assertEqual(ho.asked_by_313_weekly(p, NOW), set())
            p.write_text(json.dumps({"at": NOW.isoformat(), "b_ids": ["1", "2"]}), encoding="utf-8")
            self.assertEqual(ho.asked_by_313_weekly(p, NOW + timedelta(days=1)), {"1", "2"})
            self.assertEqual(ho.asked_by_313_weekly(p, NOW + timedelta(days=9)), set())
            p.write_text("{壊れ", encoding="utf-8")
            self.assertIsNone(ho.asked_by_313_weekly(p, NOW))


if __name__ == "__main__":
    unittest.main()
