# -*- coding: utf-8 -*-
"""314 週次レビュー 2026-11-28 の修正テスト。

① 機械チェック: Todoist コメントの引用行（本文:）・cursor-agent status を誤検知しない
② 状況ウォッチ: WeStudy の state が古い「failure」を出し続けない
③ launchd runner: `if ! cmd; then echo $?` は常に 0 になるので使わない
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class ReviewCheckerFalsePositiveTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.m = _load("wr314_20261128", "scripts/jarvis_weekly_review_314.py")

    def test_quoted_comment_body_is_not_error(self) -> None:
        self.assertFalse(self.m.is_error_line("   本文: 🤖 [要フォロー][westudy_weekly] failure · 連続成功 0/2"))
        self.assertFalse(self.m.is_error_line("   本文: [apps] CHRLINE同期: cl.sync() の RecursionError を特定"))

    def test_real_error_still_detected(self) -> None:
        self.assertTrue(self.m.is_error_line("OSError: [Errno 11] Resource deadlock avoided"))
        self.assertTrue(self.m.is_error_line("Traceback (most recent call last):"))

    def test_cursor_agent_status_is_not_ai_call(self) -> None:
        r = self.m.AI_CALL_RE
        self.assertIsNone(r.search('subprocess.run(["cursor-agent", "status"], capture_output=True)'))
        self.assertIsNone(r.search("cursor-agent のログインを確かめてください。"))
        self.assertIsNotNone(r.search('cmd = ["cursor-agent", "-p", prompt]'))
        self.assertIsNotNone(r.search("subprocess.run(['claude -p', x])"))


class WestudyStaleStateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.m = _load("sw_20261128", "scripts/jarvis_situation_watch.py")
        cls.meta = {"id": "westudy_weekly", "title": "WeStudy", "category": "x"}

    def _data(self, days_ago: float, conc: str) -> dict:
        t = datetime.now(timezone.utc) - timedelta(days=days_ago)
        return {"last_conclusion": conc, "consecutive_successes": 0, "success_needed": 2,
                "last_checked_at": t.astimezone().isoformat(timespec="seconds")}

    def test_old_failure_becomes_warn_not_attention(self) -> None:
        c = self.m.eval_westudy(self.meta, self._data(6, "failure"))
        self.assertEqual(c["level"], "warn")
        self.assertIn("止まっている", c["summary"])

    def test_fresh_failure_stays_attention(self) -> None:
        self.assertEqual(self.m.eval_westudy(self.meta, self._data(0.1, "failure"))["level"], "attention")

    def test_success_unchanged(self) -> None:
        self.assertIn(self.m.eval_westudy(self.meta, self._data(6, "success"))["level"], ("ok", "info"))


class RunnerExitCodeTest(unittest.TestCase):
    def test_no_if_not_then_echo_status(self) -> None:
        import re
        for p in (REPO / "launchd").glob("*.sh"):
            txt = p.read_text(encoding="utf-8")
            bad = re.search(r'if ! [^\n]+; then\n\s*echo "[^"\n]*\$\?', txt)
            self.assertIsNone(bad, f"{p.name}: if ! の中の $? は常に 0")

    def test_dashboard_runner_marks_westudy(self) -> None:
        txt = (REPO / "launchd/dashboard_push_runner.sh").read_text(encoding="utf-8")
        self.assertIn("jarvis_westudy_weekly_check.py", txt)
        self.assertLess(txt.index("jarvis_westudy_weekly_check.py"), txt.index("jarvis_situation_watch.py"))


if __name__ == "__main__":
    unittest.main()
