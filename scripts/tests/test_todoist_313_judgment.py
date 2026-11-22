#!/usr/bin/env python3
"""313「残す」判断・連続日数・状態時刻のテスト（ネットワーク・Slack・Todoist 不要。ダミーデータ）。"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import jarvis_todoist_313_cleanup as cl  # noqa: E402
import jarvis_todoist_313_judgment as jd  # noqa: E402

TODAY = cl._today()


def task(i: str, days_over: int = 5, content: str = "ダミー作業", **kw) -> dict:
    d = (TODAY - timedelta(days=days_over)).isoformat()
    t = {"id": i, "content": content, "due": {"date": d}, "labels": [], "priority": 1}
    t.update(kw)
    return t


class JudgmentTest(unittest.TestCase):
    def test_keep_suppresses_until_content_changes(self):
        j = {"keep": {}, "streak": {}}
        t = task("a1")
        jd.record_keep(j, "a1", jd.fingerprint(t))
        self.assertTrue(jd.is_kept(j, "a1", jd.fingerprint(t)))
        for changed in (
            task("a1", days_over=2),  # 期限が変わった
            task("a1", content="ダミー作業 改"),
            task("a1", updated_at="2026-11-22T00:00:00Z"),
            task("a1", description="追記"),
        ):
            self.assertFalse(jd.is_kept(j, "a1", jd.fingerprint(changed)))

    def test_collect_items_skips_kept_and_total(self):
        tasks = [task("a1", 9), task("b2", 8), task("c3", 7)]
        j = {"keep": {}, "streak": {}}
        jd.record_keep(j, "a1", jd.fingerprint(tasks[0]))
        items, total = cl.collect_items(5, j, tasks)
        self.assertEqual([i["task_id"] for i in items], ["b2", "c3"])
        self.assertEqual(total, 2)
        self.assertTrue(all(i["fp"] for i in items))

    def test_streak_counts_consecutive_days(self):
        j = {"keep": {}, "streak": {}}
        d0 = date(2026, 11, 10)
        for k in range(5):
            r = jd.update_streak(j, ["a1"], today=d0 + timedelta(days=k))
        self.assertEqual(r["a1"], 5)
        # 同日の再実行は増やさない
        r = jd.update_streak(j, ["a1"], today=d0 + timedelta(days=4))
        self.assertEqual(r["a1"], 5)
        # 2日空くと戻る
        r = jd.update_streak(j, ["a1"], today=d0 + timedelta(days=7))
        self.assertEqual(r["a1"], 1)

    def test_streak_line(self):
        self.assertEqual(jd.streak_line({"a": 1}), "")
        self.assertEqual(jd.streak_line({}), "")
        line = jd.streak_line({"a": 5, "b": 2, "c": 1})
        self.assertIn("5日連続", line)
        self.assertIn("2件", line)

    def test_stamp_run_keeps_other_keys(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "digest.json"
            p.write_text(json.dumps({"proposals": [1], "last_digest_at": "old"}))
            jd.stamp_run(digest_at=False, path=p)
            d = json.loads(p.read_text())
            self.assertEqual(d["last_digest_at"], "old")
            self.assertEqual(d["proposals"], [1])
            self.assertTrue(d["last_run_at"])
            jd.stamp_run(digest_at=True, path=p)
            self.assertNotEqual(json.loads(p.read_text())["last_digest_at"], "old")

    def test_keep_selected_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            state, jpath = td / "cleanup.json", td / "j.json"
            t = task("a1")
            state.write_text(json.dumps({"at": "x", "items": [
                {"n": 1, "task_id": "a1", "fp": jd.fingerprint(t)},
                {"n": 2, "task_id": "b2", "fp": "zz"},
            ]}))
            with mock.patch.object(cl, "STATE", state), mock.patch.object(
                jd, "JUDGMENTS_PATH", jpath
            ):
                self.assertEqual(cl.keep_selected("1"), 0)
                j = jd.load_judgments()
            self.assertTrue(jd.is_kept(j, "a1", jd.fingerprint(t)))
            self.assertFalse(jd.is_kept(j, "b2", "zz"))

    def test_main_dry_run_does_not_write_state(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            with mock.patch.object(cl, "_token", return_value="x"), mock.patch.object(
                cl, "_fetch_active_tasks", return_value=[task("a1")]
            ), mock.patch.object(cl, "STATE", td / "c.json"), mock.patch.object(
                jd, "JUDGMENTS_PATH", td / "j.json"
            ), mock.patch.object(jd, "LEGACY_DIGEST_PATH", td / "d.json"), mock.patch.object(
                cl, "post_slack", return_value=0
            ) as ps:
                self.assertEqual(cl.main(["--dry-run"]), 0)
                self.assertTrue(ps.call_args.kwargs["dry_run"])
            self.assertFalse((td / "d.json").exists())
            self.assertFalse((td / "j.json").exists())

    def test_main_success_records_streak_line_and_stamp(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            j = td / "j.json"
            yesterday = (TODAY - timedelta(days=1)).isoformat()
            j.write_text(json.dumps({"keep": {}, "streak": {
                "a1": {"first": yesterday, "last": yesterday, "days": 4}}}))
            with mock.patch.object(cl, "_token", return_value="x"), mock.patch.object(
                cl, "_fetch_active_tasks", return_value=[task("a1")]
            ), mock.patch.object(cl, "STATE", td / "c.json"), mock.patch.object(
                jd, "JUDGMENTS_PATH", j
            ), mock.patch.object(jd, "LEGACY_DIGEST_PATH", td / "d.json"), mock.patch.object(
                cl, "post_slack", return_value=0
            ), mock.patch.object(cl, "build_cleanup_blocks", return_value={}) as b:
                self.assertEqual(cl.main([]), 0)
            self.assertIn("5日連続", b.call_args.kwargs["extra_line"])
            self.assertTrue(json.loads((td / "d.json").read_text())["last_digest_at"])

    def test_failed_post_does_not_stamp(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            with mock.patch.object(cl, "_token", return_value="x"), mock.patch.object(
                cl, "_fetch_active_tasks", return_value=[task("a1")]
            ), mock.patch.object(cl, "STATE", td / "c.json"), mock.patch.object(
                jd, "JUDGMENTS_PATH", td / "j.json"
            ), mock.patch.object(jd, "LEGACY_DIGEST_PATH", td / "d.json"), mock.patch.object(
                cl, "post_slack", return_value=1
            ):
                self.assertEqual(cl.main([]), 1)
            self.assertFalse((td / "d.json").exists())


if __name__ == "__main__":
    unittest.main()
