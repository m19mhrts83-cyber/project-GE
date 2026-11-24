#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""314/317 の Slack 投稿は判定色（--signal）を呼び出し側で明示する。実送信はしない。"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


wr = _load("jarvis_weekly_review_314")
cd = _load("jarvis_comment_dispatch")


class Test314(unittest.TestCase):
    def test_flags_red_none_green(self):
        self.assertEqual(wr.slack_signal({"flags": ["依存不足: x"]}), "red")
        self.assertEqual(wr.slack_signal({"flags": []}), "green")


class Test317(unittest.TestCase):
    def sig(self, **kw):
        base = dict(path="mac", fb_rc=0, wh_rc=0, notes=[], phase_b=[])
        base.update(kw)
        return cd.report_signal(**base)

    def test_green_when_done_only(self):
        self.assertEqual(self.sig(), "green")
        self.assertEqual(self.sig(phase_b=["local_ok", "cloud_ok:u"]), "green")

    def test_yellow_for_notes_and_failover(self):
        self.assertEqual(self.sig(notes=[{"kind": "要判断"}]), "yellow")
        self.assertEqual(self.sig(path="failover"), "yellow")

    def test_red_for_failure(self):
        for r in ("cloud_limit", "cloud_fail:x", "hook_fail:x", "queued_after_local:y", "hook_rc=1"):
            self.assertEqual(self.sig(phase_b=[r]), "red", r)
        self.assertEqual(self.sig(fb_rc=1), "red")
        self.assertEqual(self.sig(notes=[{"kind": "要判断"}], wh_rc=2), "red")

    def test_post_passes_signal_arg(self):
        with mock.patch.object(cd.subprocess, "run") as run:
            run.return_value.returncode = 0
            cd.post_slack_report("t", dry_run=False, signal="yellow")
            cmd = run.call_args[0][0]
            self.assertEqual(cmd[cmd.index("--signal") + 1], "yellow")
            cd.post_slack_report("t", dry_run=False)
            self.assertNotIn("--signal", run.call_args[0][0])


if __name__ == "__main__":
    unittest.main()
