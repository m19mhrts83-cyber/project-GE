"""jarvis_111_night_precheck の判定ロジック単体テスト（架空値のみ・実ファイル/gh/LINEに触れない）。"""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jarvis_111_night_precheck as m  # noqa: E402

JST = m.JST
NOW = datetime(2026, 11, 28, 21, 10, tzinfo=JST)
TODAY = "20261128"
OKPOLL = "\n".join(f"# {s} exit=0" for s in m.POLL_STEPS)
OKNIGHT = "x\n📎 night_pipeline counts: line=0 export=0 fails=なし\nexit=0\n"
WF_T, WF_D = m.WORKFLOWS


def run(created_utc, event="schedule", conclusion="success"):
    return {"createdAt": created_utc, "event": event, "conclusion": conclusion}


# 今日(JST)5:05 の dispatch = 前日 20:05Z
GOOD_GHA = {
    WF_T: [run("2026-11-27T20:05:00Z", "workflow_dispatch")],
    WF_D: [run("2026-11-28T02:00:00Z")],
}


class PollTests(unittest.TestCase):
    def test_ok(self):
        ab, _ = m.check_poll([("poll_20261128_205000.log", OKPOLL)], NOW)
        self.assertEqual(ab, [])

    def test_nonzero_exit(self):
        ab, _ = m.check_poll([("poll_20261128_205000.log", "# gmail_to_inbox exit=2")], NOW)
        self.assertTrue(any("exit!=0" in x for x in ab))

    def test_stale(self):
        ab, _ = m.check_poll([("poll_20261128_194000.log", OKPOLL)], NOW)  # 90分前
        self.assertTrue(any("分前" in x for x in ab))

    def test_none_today(self):
        ab, _ = m.check_poll([], NOW)
        self.assertTrue(ab)


class NightTests(unittest.TestCase):
    def test_ok(self):
        self.assertEqual(m.check_night([("n_1.log", OKNIGHT)])[0], [])

    def test_missing(self):
        self.assertTrue(m.check_night([])[0])

    def test_zero_bytes(self):
        self.assertTrue(m.check_night([("n_1.log", "")])[0])

    def test_fails(self):
        self.assertTrue(m.check_night([("n_1.log", "fails=['x']")])[0])

    def test_no_fails_line(self):
        self.assertTrue(m.check_night([("n_1.log", "something")])[0])

    def test_markers(self):
        for mk in m.NIGHT_BAD_MARKERS:
            with self.subTest(mk=mk):
                self.assertTrue(m.check_night([("n_1.log", OKNIGHT + mk)])[0])


class LineTests(unittest.TestCase):
    def test_running(self):
        ps = "/Applications/LINE.app/Contents/MacOS/LINE\n"
        self.assertTrue(m.check_line_running(ps)[0])

    def test_not_running(self):
        self.assertEqual(m.check_line_running("/usr/bin/python3 x\n/Applications/LINEWORKS.app/a\n")[0], [])


class GhaTests(unittest.TestCase):
    def test_ok(self):
        self.assertEqual(m.check_gha(GOOD_GHA, TODAY)[0], [])

    def test_failure_today(self):
        g = dict(GOOD_GHA)
        g[WF_D] = [run("2026-11-28T02:00:00Z", conclusion="failure")]
        self.assertTrue(m.check_gha(g, TODAY)[0])

    def test_cancelled_today(self):
        g = dict(GOOD_GHA)
        g[WF_T] = GOOD_GHA[WF_T] + [run("2026-11-28T05:00:00Z", conclusion="cancelled")]
        self.assertTrue(m.check_gha(g, TODAY)[0])

    def test_old_failure_ignored(self):
        g = dict(GOOD_GHA)
        g[WF_D] = [run("2026-11-20T02:00:00Z", conclusion="failure"), run("2026-11-28T02:00:00Z")]
        self.assertEqual(m.check_gha(g, TODAY)[0], [])

    def test_no_morning_main(self):
        g = dict(GOOD_GHA)
        g[WF_T] = [run("2026-11-28T05:00:00Z")]  # 14時台 schedule のみ
        self.assertTrue(any("朝の本便" in x for x in m.check_gha(g, TODAY)[0]))

    def test_morning_5h_schedule_counts(self):
        g = dict(GOOD_GHA)
        g[WF_T] = [run("2026-11-27T20:30:00Z")]  # JST 5:30
        self.assertEqual(m.check_gha(g, TODAY)[0], [])

    def test_gh_failed(self):
        g = dict(GOOD_GHA)
        g[WF_T] = None
        self.assertTrue(m.check_gha(g, TODAY)[0])


class MorningTests(unittest.TestCase):
    def test_ok(self):
        self.assertEqual(m.check_morning("# step:mail_action_slack: exit=0\n", TODAY, TODAY), ([], []))

    def test_fail(self):
        self.assertTrue(m.check_morning("# step:mail_action_slack: exit=1\n", TODAY, TODAY)[0])

    def test_last_wins(self):
        t = "# step:mail_action_slack: exit=1\n# step:mail_action_slack: exit=0\n"
        self.assertEqual(m.check_morning(t, TODAY, TODAY)[0], [])

    def test_unknown_not_counted(self):
        for args in [(None, None), ("x", "20261127"), ("no step", TODAY)]:
            ab, un = m.check_morning(args[0], args[1], TODAY)
            self.assertEqual(ab, [])
            self.assertTrue(un)


class DecideTests(unittest.TestCase):
    def test_all_ok_exit1(self):
        code, _ = m.decide([([], []), ([], ["確認不可"])])
        self.assertEqual(code, 1)

    def test_any_abnormal_exit0(self):
        code, r = m.decide([([], []), (["x"], [])])
        self.assertEqual(code, 0)
        self.assertIn("x", r)


class MainTests(unittest.TestCase):
    def test_exception_exit0(self):
        with mock.patch.object(m, "collect", side_effect=RuntimeError("boom")):
            self.assertEqual(m.main(["--dry-run"]), 0)

    def test_all_ok_main_exit1(self):
        ok = [([], [])] * 5
        with mock.patch.object(m, "collect", return_value=ok):
            self.assertEqual(m.main(["--json"]), 1)

    def test_bad_args_exit0(self):
        self.assertEqual(m.main(["--nonsense"]), 0)


if __name__ == "__main__":
    unittest.main()
