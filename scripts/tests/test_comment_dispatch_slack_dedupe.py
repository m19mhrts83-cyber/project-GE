#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""317 #report fingerprint dedupe（同一未処理バックログ連投防止）."""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _load():
    path = SCRIPTS / "jarvis_comment_dispatch.py"
    spec = importlib.util.spec_from_file_location("jarvis_comment_dispatch", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cd = _load()


class TestSlackReportFingerprint(unittest.TestCase):
    def test_stable_for_same_notes(self):
        notes = [
            {"row_id": 2, "kind": "要判断"},
            {"row_id": 1, "kind": "確認のみ"},
        ]
        a = cd.slack_report_fingerprint(path="mac", notes=notes, phase_b=[])
        b = cd.slack_report_fingerprint(
            path="mac",
            notes=list(reversed(notes)),
            phase_b=[],
        )
        self.assertEqual(a, b)
        self.assertIn("1:確認のみ", a)
        self.assertIn("2:要判断", a)

    def test_changes_when_note_added(self):
        n1 = [{"row_id": 1, "kind": "要判断"}]
        n2 = [{"row_id": 1, "kind": "要判断"}, {"row_id": 9, "kind": "要実装"}]
        a = cd.slack_report_fingerprint(path="mac", notes=n1, phase_b=[])
        b = cd.slack_report_fingerprint(path="mac", notes=n2, phase_b=[])
        self.assertNotEqual(a, b)

    def test_path_matters(self):
        notes = [{"row_id": 1, "kind": "要判断"}]
        a = cd.slack_report_fingerprint(path="mac", notes=notes, phase_b=[])
        b = cd.slack_report_fingerprint(path="failover", notes=notes, phase_b=[])
        self.assertNotEqual(a, b)


class TestShouldPostSlackReport(unittest.TestCase):
    def test_skip_identical_backlog(self):
        notes = [{"row_id": 88, "kind": "要判断"}]
        fp = cd.slack_report_fingerprint(path="mac", notes=notes, phase_b=[])
        ok, out_fp, reason = cd.should_post_slack_report(
            path="mac", notes=notes, phase_b=[], last_fp=fp
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "dedupe_same_fingerprint")
        self.assertEqual(out_fp, fp)

    def test_post_when_fingerprint_new(self):
        notes = [{"row_id": 88, "kind": "要判断"}]
        ok, _fp, reason = cd.should_post_slack_report(
            path="mac", notes=notes, phase_b=[], last_fp=None
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "new_or_changed")

    def test_noop_when_empty_mac(self):
        ok, _fp, reason = cd.should_post_slack_report(
            path="mac", notes=[], phase_b=[], last_fp=None
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "noop")

    def test_failover_empty_still_interesting_once(self):
        ok, fp, reason = cd.should_post_slack_report(
            path="failover", notes=[], phase_b=[], last_fp=None
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "new_or_changed")
        ok2, _fp2, reason2 = cd.should_post_slack_report(
            path="failover", notes=[], phase_b=[], last_fp=fp
        )
        self.assertFalse(ok2)
        self.assertEqual(reason2, "dedupe_same_fingerprint")


class TestFailoverStateless(unittest.TestCase):
    """GHA 冗長は Mac の .jarvis_state を持たない前提。"""

    def test_python_falls_back_off_mac(self):
        self.assertTrue(cd.PY.exists() or cd.PY == Path(sys.executable))

    def test_reacted_reply_counts_as_handled(self):
        from jarvis_slack_report_fb_lib import has_handled_reaction

        self.assertTrue(has_handled_reaction({"reactions": [{"name": "eyes"}]}))
        self.assertTrue(
            has_handled_reaction({"reactions": [{"name": "white_check_mark"}]})
        )
        self.assertFalse(has_handled_reaction({"reactions": [{"name": "+1"}]}))
        self.assertFalse(has_handled_reaction({"text": "見栄え: グラフにして"}))


class TestSlackReportLayout(unittest.TestCase):
    """#report 本文は iPhone 向け（41_）: rc・path を出さない／項目は空行で区切る。"""

    def _notes(self):
        return [
            {"row_id": 1, "kind": "要判断", "task_title": "A案件の件", "comment": "方針どうする？"},
            {"row_id": 2, "kind": "無関係", "task_title": "B案件の件", "comment": "了承済みのためクローズ。"},
        ]

    def test_empty_when_nothing_to_report(self):
        self.assertEqual(cd.build_report(path="mac", fb_rc=0, wh_rc=0, notes=[], phase_b=[]), "")

    def test_no_internal_codes(self):
        text = cd.build_report(path="mac", fb_rc=0, wh_rc=1, notes=self._notes(), phase_b=[])
        self.assertNotIn("rc=", text)
        self.assertNotIn("path=", text)
        self.assertNotIn("[要判断]", text)
        self.assertTrue(text.startswith("【報告】317 コメント起動"))

    def test_items_separated_by_blank_line(self):
        text = cd.build_report(path="mac", fb_rc=0, wh_rc=0, notes=self._notes(), phase_b=[])
        self.assertIn("\n\n1. A案件の件\n", text)
        self.assertIn("\n\n2. B案件の件\n", text)
        self.assertIn("判断待ち｜", text)
        self.assertIn("メモ｜", text)

    def test_failover_marker_and_next_line(self):
        text = cd.build_report(path="failover", fb_rc=0, wh_rc=0, notes=self._notes(), phase_b=[])
        self.assertIn("（Mac停止中・GHA）", text)
        self.assertIn("次: 判断待ちはJarvisに一声", text)

    def test_clip_cuts_on_boundary(self):
        out = cd._clip("あいうえお。かきくけこさしすせそ", 9)
        self.assertTrue(out.endswith("…"))
        self.assertLessEqual(len(out), 10)


if __name__ == "__main__":
    unittest.main()
