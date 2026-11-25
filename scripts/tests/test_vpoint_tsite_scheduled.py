"""Tサイト履歴の定期取得の包み役（614・2026-11-25）。値はすべて架空。"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import jarvis_vpoint_tsite_scheduled as ts  # noqa: E402

class ScheduleGuardTest(unittest.TestCase):
    def test_should_run(self):
        self.assertEqual(ts.should_run({}, "2099-01-24"), (True, "new_day"))
        self.assertEqual(ts.should_run({"date": "2099-01-23", "status": "ok"}, "2099-01-24"), (True, "new_day"))
        self.assertEqual(ts.should_run({"date": "2099-01-24", "status": "ok", "attempts": 1}, "2099-01-24")[0], False)
        self.assertEqual(ts.should_run({"date": "2099-01-24", "status": "auth_wait", "attempts": 1}, "2099-01-24")[0], False)
        self.assertEqual(ts.should_run({"date": "2099-01-24", "status": "failed", "attempts": 1}, "2099-01-24"), (True, "retry_today"))
        self.assertEqual(ts.should_run({"date": "2099-01-24", "status": "failed", "attempts": 2}, "2099-01-24"), (False, "attempts_exhausted"))

    def test_classify(self):
        self.assertEqual(ts.classify_failure(1, "RuntimeError: Gmail から Tサイト OTP を取得できませんでした", False), "auth_wait")
        self.assertEqual(ts.classify_failure(1, "ログイン未完了のままです url=x", False), "auth_wait")
        self.assertEqual(ts.classify_failure(1, "CDP 9236 not ready", False), "failed")
        self.assertEqual(ts.classify_failure(None, "", True), "failed")

    def test_readback(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "vpoint_tsite_history_20990124.json"
            p.write_text(json.dumps({"fetched_at": "2099-01-24T08:31:00+09:00", "key_entries": [{"date": "2099-01-05", "pt": 1}]}), encoding="utf-8")
            self.assertTrue(ts.history_readback_ok("2099-01-24", Path(d)))
            self.assertFalse(ts.history_readback_ok("2099-01-25", Path(d)))
            p.write_text(json.dumps({"fetched_at": "2099-01-23T08:31:00+09:00", "key_entries": [{"x": 1}]}), encoding="utf-8")
            self.assertFalse(ts.history_readback_ok("2099-01-24", Path(d)))

    def test_ops_text_has_no_secrets_and_signal(self):
        t = ts.ops_text("auth_wait", "2099-01-24", 1)
        self.assertIn("判定: 🟡", t)
        self.assertIn("判定: 🔴", ts.ops_text("failed", "2099-01-24", 2))


class ScheduleMainTest(unittest.TestCase):
    """main() の流れ。取得・通知・保存先はすべて差し替え（本番アクセスなし）。"""

    def _run(self, fetch_results, state=None, readback=True):
        with tempfile.TemporaryDirectory() as d:
            st = Path(d) / "run.json"
            if state is not None:
                st.write_text(json.dumps(state), encoding="utf-8")
            calls = {"fetch": 0, "post": 0}
            results = list(fetch_results)

            def fake_fetch():
                calls["fetch"] += 1
                return results.pop(0)

            def fake_post(text):
                calls["post"] += 1
                return True

            with mock.patch.object(ts, "RUN_STATE", st), \
                 mock.patch.object(ts, "PRIVATE_ENV", Path(d) / "none.env"), \
                 mock.patch.object(ts, "now_jst", return_value=__import__("datetime").datetime(2099, 1, 24, 8, 30, tzinfo=ts.JST)), \
                 mock.patch.object(ts, "run_fetch", side_effect=fake_fetch), \
                 mock.patch.object(ts, "post_ops", side_effect=fake_post), \
                 mock.patch.object(ts, "history_readback_ok", return_value=readback), \
                 mock.patch.object(ts.time, "sleep"), \
                 mock.patch.dict(ts.os.environ, {}, clear=False):
                ts.os.environ.pop("JARVIS_VPOINT_TSITE_FETCH_DISABLE", None)
                rc = ts.main(["--retry-wait-sec", "0"])
            return rc, calls, json.loads(st.read_text(encoding="utf-8")) if st.exists() else {}

    def test_success_first_try(self):
        rc, calls, state = self._run([(0, "", False)])
        self.assertEqual((rc, calls["fetch"], calls["post"]), (0, 1, 0))
        self.assertEqual(state["status"], "ok")

    def test_retry_once_then_notify_once(self):
        rc, calls, state = self._run([(1, "CDP not ready", False), (1, "CDP not ready", False)])
        self.assertEqual((rc, calls["fetch"], calls["post"]), (1, 2, 1))  # 再試行は1回まで・通知は1回
        self.assertEqual(state["status"], "failed")
        self.assertEqual(state["attempts"], 2)

    def test_retry_succeeds(self):
        rc, calls, state = self._run([(1, "CDP not ready", False), (0, "", False)])
        self.assertEqual((rc, calls["fetch"], calls["post"]), (0, 2, 0))
        self.assertEqual(state["status"], "ok")

    def test_auth_wait_stops_without_retry(self):
        rc, calls, state = self._run([(1, "Gmail から Tサイト OTP を取得できませんでした", False)])
        self.assertEqual((rc, calls["fetch"], calls["post"]), (1, 1, 1))
        self.assertEqual(state["status"], "auth_wait")

    def test_exit0_without_readback_is_not_success(self):
        rc, calls, state = self._run([(0, "", False), (0, "", False)], readback=False)
        self.assertEqual(rc, 1)
        self.assertEqual(state["status"], "failed")

    def test_skip_when_already_ok_today(self):
        rc, calls, _ = self._run([], state={"date": "2099-01-24", "status": "ok", "attempts": 1})
        self.assertEqual((rc, calls["fetch"]), (0, 0))

    def test_no_second_notice_same_day(self):
        rc, calls, state = self._run(
            [(1, "x", False)],
            state={"date": "2099-01-24", "status": "failed", "attempts": 1, "ops_notified": True},
        )
        self.assertEqual((rc, calls["fetch"], calls["post"]), (1, 1, 0))


if __name__ == "__main__":
    unittest.main()
