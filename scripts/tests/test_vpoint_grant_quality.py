"""Vポイント付与サマリの成否判定・月印・定例の保存（614 D6・2026-11-23）。値はすべて架空。"""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import jarvis_points_rebate_slack_report as sr  # noqa: E402
import jarvis_vpoint_monthly_check as mc  # noqa: E402
import jarvis_vpoint_routine as rt  # noqa: E402


def _history(fetched_at: str) -> dict:
    return {
        "fetched_at": fetched_at,
        "key_entries": [
            {"date": "2026-10-05", "desc": "テスト付与A", "pt": 100},
            {"date": "2026-10-20", "desc": "テスト付与B", "pt": 50},
        ],
    }


class QualityTest(unittest.TestCase):
    def test_month_end(self):
        self.assertEqual(mc.month_end_date("2026-10"), date(2026, 10, 31))
        self.assertEqual(mc.month_end_date("2028-02"), date(2028, 2, 29))
        self.assertIsNone(mc.month_end_date("bad"))

    def test_asof(self):
        self.assertEqual(mc.history_asof(_history("2026-09-10T20:00:00+09:00")), date(2026, 9, 10))
        self.assertIsNone(mc.history_asof(_history("")))
        self.assertIsNone(mc.history_asof(None))

    def _q(self, **kw):
        base = dict(target_month="2026-10", asof=date(2026, 11, 1), has_history=True,
                    used_fallback=False, entry_count=2)
        base.update(kw)
        return mc.assess_grant_quality(**base)

    def test_success_on_or_after_month_end(self):
        self.assertEqual(self._q(asof=date(2026, 10, 31))["quality"], "success")
        self.assertEqual(self._q(asof=date(2026, 11, 2))["quality"], "success")

    def test_stale_history_is_partial_with_asof(self):
        q = self._q(asof=date(2026, 10, 30))
        self.assertEqual(q["quality"], "partial")
        self.assertIn("2026-10-30", q["quality_reason"])
        self.assertIn("履歴が古い", q["quality_reason"])

    def test_unknown_asof_is_partial(self):
        self.assertEqual(self._q(asof=None)["quality"], "partial")

    def test_fallback_is_partial_even_if_asof_fresh(self):
        self.assertEqual(self._q(used_fallback=True)["quality"], "partial")

    def test_no_history_and_no_rows_is_failed(self):
        q = self._q(asof=None, has_history=False, entry_count=0)
        self.assertEqual(q["quality"], "failed")

    def test_upsert_does_not_downgrade_success(self):
        state = {"grant_history": [{"target_month": "2026-10", "quality": "success", "total_pt": 10}]}
        mc.upsert_grant_history(state, {"target_month": "2026-10", "quality": "partial", "total_pt": 1})
        self.assertEqual(state["grant_history"][0]["total_pt"], 10)
        mc.upsert_grant_history(state, {"target_month": "2026-11", "quality": "partial", "total_pt": 2})
        self.assertEqual(len(state["grant_history"]), 2)


class MarkDoneTest(unittest.TestCase):
    """--mark-done は成功の時だけ last_check_c を書く。"""

    def _run(self, fetched_at: str) -> dict:
        with tempfile.TemporaryDirectory() as d:
            sd = Path(d)
            (sd / "vpoint_tsite_history_20260101.json").write_text(
                json.dumps(_history(fetched_at)), encoding="utf-8"
            )
            state_path = sd / "vpoint_monthly.json"
            state_path.write_text(json.dumps({"disabled": False}), encoding="utf-8")
            with mock.patch.object(mc, "STATE_DIR", sd), \
                 mock.patch.object(mc, "STATE_PATH", state_path), \
                 mock.patch.object(mc, "RESULT_PATH", sd / "none.json"), \
                 mock.patch.object(mc, "PRIVATE_ENV", sd / "none.env"), \
                 mock.patch.object(sys, "argv", ["x", "--mark-done", "--target-month", "2026-10"]), \
                 contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(mc.main(), 0)
            self._out = out.getvalue()
            return json.loads(state_path.read_text(encoding="utf-8"))

    def test_stale_history_does_not_stamp(self):
        st = self._run("2026-09-10T20:00:00+09:00")
        self.assertIsNone(st.get("last_check_c"))
        rc = st["last_result_c"]
        self.assertEqual(rc["grant_quality"], "partial")
        self.assertEqual(rc["history_asof"], "2026-09-10")
        self.assertFalse(rc["marked_last_check_c"])
        self.assertIn("月印は付けません", self._out)
        self.assertEqual(st["grant_history"][0]["quality"], "partial")

    def test_fresh_history_stamps(self):
        st = self._run("2026-11-02T09:00:00+09:00")
        self.assertEqual(st["last_check_c"], mc.month_key(mc.datetime.now(mc.JST)))
        self.assertEqual(st["last_result_c"]["grant_quality"], "success")


class SlackWordingTest(unittest.TestCase):
    def test_partial_message_has_asof_and_not_update_word(self):
        text = sr.build_vpoint(
            outcome="partial", reason="履歴が古い・基準日=2026-09-10", error="", note="", asks_n=3
        )
        self.assertIn("部分成功", text)
        self.assertIn("2026-09-10", text)
        self.assertNotIn("定例ウォッチ更新", text)

    def test_checked_unchanged(self):
        text = sr.build_vpoint(outcome="checked", reason="", error="", note="", asks_n=None)
        self.assertIn("定例ウォッチ更新", text)


class RoutineSaveTest(unittest.TestCase):
    """F3: PDCA の子プロセスが state を書き直しても last_routine_at／asks が残る。"""

    def test_routine_fields_survive_pdca_rewrite(self):
        with tempfile.TemporaryDirectory() as d:
            sd = Path(d)
            monthly_path = sd / "vpoint_monthly.json"
            monthly_path.write_text(json.dumps({"disabled": False, "last_routine_at": "old"}), encoding="utf-8")

            def fake_run_py(args, *, timeout=300):
                if any("jarvis_vpoint_pdca" in a for a in args):
                    # 子プロセスは state を読み直して pdca_board だけ足して書く
                    cur = json.loads(monthly_path.read_text(encoding="utf-8"))
                    cur["pdca_board"] = {"wins": []}
                    monthly_path.write_text(json.dumps(cur), encoding="utf-8")
                return {"ok": True, "returncode": 0, "stdout_tail": "", "stderr_tail": ""}

            with mock.patch.object(rt, "MONTHLY_PATH", monthly_path), \
                 mock.patch.object(rt, "CADENCE_PATH", sd / "c.json"), \
                 mock.patch.object(rt, "TEIKI_PATH", sd / "t.json"), \
                 mock.patch.object(rt, "PRIVATE_ENV", sd / "none.env"), \
                 mock.patch.object(rt, "STATE_DIR", sd), \
                 mock.patch.object(rt, "run_py", fake_run_py), \
                 mock.patch.object(sys, "argv", ["x", "--apply", "--skip-teiki", "--skip-cadence"]), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(rt.main(), 0)
            st = json.loads(monthly_path.read_text(encoding="utf-8"))
            self.assertNotEqual(st["last_routine_at"], "old")
            self.assertIn("jarvis_asks", st)
            self.assertIn("routine_split", st)
            self.assertIn("pdca_board", st)


if __name__ == "__main__":
    unittest.main()
