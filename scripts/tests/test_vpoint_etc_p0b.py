"""614 PR-P0b — Vポイントの保存読み戻し（工程28）・D6 の確認・ETC の対象月／取得待ち／失敗の区別（工程9）。

架空の値だけ。サイト・Slack・ダッシュボードには触れない（すべてモック）。state は一時フォルダ。
"""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jarvis_614_display as display614  # noqa: E402
import jarvis_614_ops as ops614  # noqa: E402
import jarvis_614_runlog as runlog614  # noqa: E402
import jarvis_614_verified_state as vs  # noqa: E402
import jarvis_etc_rebate_fetch as etc  # noqa: E402
import jarvis_points_rebate_slack_report as sr  # noqa: E402
import jarvis_vpoint_routine as rt  # noqa: E402

JST = ZoneInfo("Asia/Tokyo")


def hermetic(case: unittest.TestCase, base: Path) -> None:
    """614 の run 記録・#ops 保留・緊急ログを一時フォルダへ（実 state・実ログを汚さない）。"""
    p = mock.patch.dict(os.environ, {
        "JARVIS_STATE_DIR": str(base),
        "JARVIS_614_LOG_DIR": str(base / "614_watch"),
        "JARVIS_614_EMERGENCY_DIR": str(base / "emergency"),
    })
    p.start()
    case.addCleanup(p.stop)
    os.environ.pop("JARVIS_614_GLOBAL_STOP", None)


class StampInvariantTests(unittest.TestCase):
    def test_stamp_only_when_expected(self):
        f = rt.check_stamp_invariant
        self.assertEqual(f("2026-11", None, stamp_expected=True, month="2026-11"), [])
        self.assertTrue(f(None, None, stamp_expected=True, month="2026-11"))
        self.assertEqual(f(None, None, stamp_expected=False, month="2026-11"), [])
        self.assertTrue(f("2026-11", None, stamp_expected=False, month="2026-11"))  # 部分成功なのに印
        self.assertEqual(f("2026-10", "2026-10", stamp_expected=False, month="2026-11"), [])


class RoutineVerifiedSaveTests(unittest.TestCase):
    """窓C の定例全体（子プロセスはモック）。保存の読み戻し・月印・結果語・画面反映の止め方。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.sd = Path(self.tmp.name)
        hermetic(self, self.sd)
        self.monthly = self.sd / "vpoint_monthly.json"
        self.monthly.write_text(json.dumps({"disabled": False, "last_routine_at": "old"}))
        self.calls = []
        self.child = {"quality": "success", "stamp": True}
        self.sync = {"push": "success", "display": "success", "attempts": 1, "mismatches": [], "error": ""}
        self.sync_calls = []
        self.notified = []
        for patcher in (
            mock.patch.object(rt.display614, "sync_and_verify", lambda ids, **kw: self.sync_calls.append(ids) or self.sync),
            mock.patch.object(rt.ops614, "flush_pending", lambda **kw: {}),
            mock.patch.object(rt.ops614, "notify_ops", lambda **kw: self.notified.append(kw) or {"status": "sent"}),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def fake_run_py(self, args, *, timeout=300):
        self.calls.append(args)
        joined = " ".join(args)
        if "jarvis_vpoint_monthly_check" in joined:
            cur = json.loads(self.monthly.read_text())
            if self.child["stamp"]:
                cur["last_check_c"] = rt.month_key(self.now)
            cur["last_result_c"] = {"grant_summary": {
                "quality": self.child["quality"], "quality_reason": "テスト", "source_note": "n",
                "history_asof": "2026-10-31"}}
            self.monthly.write_text(json.dumps(cur))
        if "jarvis_vpoint_pdca" in joined and "--apply" in joined:
            cur = json.loads(self.monthly.read_text())
            cur["pdca_board"] = {"wins": []}
            self.monthly.write_text(json.dumps(cur))
        return {"ok": True, "returncode": 0, "stdout_tail": "", "stderr_tail": ""}

    def run_routine(self, *flags, now=None):
        self.now = now or datetime(2026, 11, 25, 9, 40, tzinfo=JST)

        class FakeDT(datetime):
            @classmethod
            def now(cls, tz=None):
                return self_now

        self_now = self.now
        out = io.StringIO()
        with mock.patch.object(rt, "MONTHLY_PATH", self.monthly), \
                mock.patch.object(rt, "CADENCE_PATH", self.sd / "c.json"), \
                mock.patch.object(rt, "TEIKI_PATH", self.sd / "t.json"), \
                mock.patch.object(rt, "PRIVATE_ENV", self.sd / "none.env"), \
                mock.patch.object(rt, "STATE_DIR", self.sd), \
                mock.patch.object(rt, "datetime", FakeDT), \
                mock.patch.object(rt, "run_py", self.fake_run_py), \
                mock.patch.object(sys, "argv", ["x", "--apply", "--skip-teiki", "--skip-cadence", *flags]), \
                contextlib.redirect_stdout(out):
            rc = rt.main()
        self.report = json.loads(out.getvalue()[out.getvalue().rindex("\n{"):]) if "\n{" in out.getvalue() else None
        return rc

    def state(self):
        return json.loads(self.monthly.read_text())

    def slack_args(self):
        for a in self.calls:
            if any("jarvis_points_rebate_slack_report" in x for x in a):
                return a
        return None

    def test_success_in_window_stamps_and_verifies(self):
        self.assertEqual(self.run_routine("--push"), 0)
        st = self.state()
        self.assertEqual(st["last_check_c"], "2026-11")
        self.assertNotEqual(st["last_routine_at"], "old")
        self.assertIn("jarvis_asks", st)
        self.assertIn("pdca_board", st)
        self.assertTrue(self.report["save_verify"]["ok"])
        self.assertEqual(self.slack_args()[self.slack_args().index("--outcome") + 1], "checked")
        self.assertFalse((self.sd / "vpoint_monthly.pending.json").exists())

    def test_partial_in_window_does_not_stamp_and_reports_partial(self):  # D6
        self.child = {"quality": "partial", "stamp": False}
        self.assertEqual(self.run_routine("--push"), 0)
        st = self.state()
        self.assertIsNone(st.get("last_check_c"))
        self.assertIn("jarvis_asks", st)  # asks・更新日時は部分成功でも残る
        self.assertNotEqual(st["last_routine_at"], "old")
        self.assertEqual(self.slack_args()[self.slack_args().index("--outcome") + 1], "partial")

    def test_failed_quality_reports_failed(self):
        self.child = {"quality": "failed", "stamp": False}
        self.run_routine("--push")
        a = self.slack_args()
        self.assertEqual(a[a.index("--outcome") + 1], "failed")

    def test_child_stamping_a_partial_is_detected_as_save_verify_failure(self):
        self.child = {"quality": "partial", "stamp": True}  # D6 の退行を想定
        self.assertEqual(self.run_routine("--push"), 1)
        self.assertFalse(self.report["save_verify"]["ok"])
        self.assertTrue(any("last_check_c" in e for e in self.report["save_verify"]["errors"]))
        # 保存を確認できない結果は画面へ渡さず、#ops へ失敗を出す
        self.assertEqual(self.sync_calls, [])
        a = self.slack_args()
        self.assertEqual(a[a.index("--outcome") + 1], "failed")

    def test_readback_mismatch_fails_and_keeps_pending_and_blocks_downstream(self):
        real = vs._write_atomic

        def bad(path, data):  # 本体だけ asks を落として書く（読み戻しで検出される）
            if path == self.monthly:
                data = {k: v for k, v in data.items() if k != "jarvis_asks"}
            real(path, data)

        with mock.patch.object(vs, "_write_atomic", bad):
            self.assertEqual(self.run_routine("--push"), 1)
        self.assertFalse(self.report["save_verify"]["ok"])
        self.assertEqual(self.report["save_verify"]["attempts"], 2)  # 保存だけ1回やり直す
        self.assertTrue((self.sd / "vpoint_monthly.pending.json").is_file())
        self.assertIn("jarvis_asks", json.loads((self.sd / "vpoint_monthly.pending.json").read_text()))
        self.assertEqual(self.sync_calls, [])
        a = self.slack_args()
        self.assertEqual(a[a.index("--outcome") + 1], "failed")
        self.assertIn("読み戻して確認できず", a[a.index("--error") + 1])

    def test_tuple_in_asks_does_not_cause_false_mismatch(self):
        with mock.patch.object(rt, "build_jarvis_asks", lambda **kw: [{"id": "a", "level": "x", "text": "t", "k": ("a", "b")}]):
            self.assertEqual(self.run_routine(), 0)
        self.assertTrue(self.report["save_verify"]["ok"])

    # ---- P1: run 集約・排他・画面反映・全体停止 ----
    def last_stages(self):
        return runlog614.read_runs()[-1]["systems"]["vpoint"]["stages"]

    def test_run_recorded_with_independent_stages_on_success(self):
        self.assertEqual(self.run_routine("--push"), 0)
        st = self.last_stages()
        for name in ("fetch", "save", "save_verify", "stamp", "push", "display", "slack"):
            self.assertEqual(st[name]["status"], "success", name)
        self.assertEqual(self.sync_calls, [["vpoint"]])
        self.assertEqual(runlog614.success_count(runlog614.read_runs(), system="vpoint"), 1)

    def test_partial_grant_is_partial_fetch_and_no_stamp_stage(self):
        self.child = {"quality": "partial", "stamp": False}
        self.run_routine("--push")
        st = self.last_stages()
        self.assertEqual(st["fetch"]["status"], "partial")
        self.assertEqual(st["stamp"]["status"], "skipped")
        self.assertEqual(st["save"]["status"], "success")  # 保存は別に成功
        self.assertEqual(runlog614.success_count(runlog614.read_runs(), system="vpoint"), 0)

    def test_display_failure_is_separate_and_keeps_stamp_and_rc0(self):
        self.sync = {"push": "success", "display": "failed", "attempts": 2, "mismatches": ["vpoint:x"],
                     "error": "画面の値が保存済み state と違う"}
        self.assertEqual(self.run_routine("--push"), 0)
        st = self.last_stages()
        self.assertEqual((st["save_verify"]["status"], st["stamp"]["status"], st["display"]["status"]),
                         ("success", "success", "failed"))
        self.assertEqual(self.state()["last_check_c"], "2026-11")
        self.assertTrue(any(n["stage"] == "n17/18 画面反映" for n in self.notified))
        self.assertEqual(self.slack_args()[self.slack_args().index("--outcome") + 1], "checked")

    def test_readback_unavailable_is_unverified_not_success(self):
        self.sync = {"push": "success", "display": "unverified", "attempts": 1, "mismatches": [],
                     "error": "読み戻せず（RuntimeError）"}
        self.run_routine("--push")
        self.assertEqual(self.last_stages()["display"]["status"], "unverified")

    def test_dry_run_is_recorded_as_dry_run(self):
        self.run_routine("--dry-run")
        self.assertTrue(runlog614.read_runs()[-1]["dry_run"])
        self.assertEqual(runlog614.success_count(runlog614.read_runs()), 0)

    def test_concurrent_run_is_excluded_and_state_untouched(self):
        before = self.monthly.read_text()
        with vs.file_lock(rt.lock_path()) if False else vs.file_lock(self.sd / "vpoint_routine.lock"):
            self.assertEqual(self.run_routine("--push"), 0)
        self.assertEqual(self.monthly.read_text(), before)
        self.assertEqual(self.calls, [])  # 子プロセス（付与サマリ・PDCA）を起動しない
        self.assertEqual(runlog614.read_runs()[-1]["systems"]["vpoint"]["stages"]["fetch"]["error_code"], None)
        self.assertEqual(self.last_stages()["fetch"]["status"], "skipped")

    def test_global_stop_skips_even_with_force_window(self):
        os.environ["JARVIS_614_GLOBAL_STOP"] = "1"
        self.assertEqual(self.run_routine("--push", "--force-window-c"), 0)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.last_stages()["fetch"]["status"], "skipped")

    def test_outside_window_never_stamps(self):
        self.run_routine(now=datetime(2026, 11, 10, 9, 40, tzinfo=JST))
        self.assertIsNone(self.state().get("last_check_c"))
        self.assertTrue(self.report["save_verify"]["ok"])

    def test_state_file_stays_owner_only_and_keeps_backup(self):
        self.run_routine()
        self.assertEqual(self.monthly.stat().st_mode & 0o777, 0o600)
        self.assertTrue((self.sd / "vpoint_monthly.json.bak").is_file())


class EtcClassifyTests(unittest.TestCase):
    def test_labels(self):
        self.assertEqual(etc.parse_label("2026年08月"), (2026, 8))
        self.assertIsNone(etc.parse_label(""))

    def test_unavailable_is_waiting_only_when_latest_page_is_before_grant_month(self):
        c = etc.classify_unavailable
        self.assertEqual(c("2026年10月", "2026年11月"), "waiting")  # 最新が付与月より前＝付与前
        self.assertEqual(c("2026年12月", "2026年11月"), "failed")   # 付与月を飛び越えている＝開けない異常
        self.assertEqual(c("", "2026年11月"), "failed")             # 月が読めない（ログイン失敗等）
        self.assertEqual(c("2026年11月", "2026年11月"), "failed")

    def test_validate_scraped(self):
        ok = {"target_month": "2026-10", "grant_month": "2026-11", "rebate_yen": 1200}
        self.assertIsNone(etc.validate_scraped(ok, "2026-10"))
        self.assertIn("対象月", etc.validate_scraped(ok, "2026-09"))  # 古い月・別の月
        self.assertIn("付与月", etc.validate_scraped(dict(ok, grant_month="2026-10"), "2026-10"))
        for bad in (None, -1, "1200", True):
            self.assertIn("還元額", etc.validate_scraped(dict(ok, rebate_yen=bad), "2026-10"))


class EtcApplyTests(unittest.TestCase):
    NOW = datetime(2026, 11, 21, 9, 30, tzinfo=JST)

    def scraped(self, target, yen=1000):
        return {"ok": True, "target_month": target, "grant_month": etc.add_months(target, 1),
                "rebate_yen": yen, "method": "tokuten"}

    def test_regular_target_stamps_month(self):
        st = {}
        etc.apply_result(st, self.scraped("2026-10"), self.NOW)
        self.assertEqual(st["last_check_b"], "2026-11")
        self.assertEqual(st["last_result_b"]["target_month"], "2026-10")

    def test_old_month_manual_fetch_does_not_complete_this_month(self):
        st = {"last_result_b": {"target_month": "2026-10", "rebate_yen": 5}, "etc_wait": {"target_month": "2026-10"}}
        etc.apply_result(st, self.scraped("2026-06", 999), self.NOW)
        self.assertNotIn("last_check_b", st)  # 今月分の定例を完了扱いにしない
        self.assertEqual(st["last_result_b"]["target_month"], "2026-10")  # 新しい月の結果を古い月で上書きしない
        self.assertEqual(st["rebate_history"][0]["target_month"], "2026-06")  # 履歴には載る
        self.assertNotIn("etc_wait", st)


class EtcMainTests(unittest.TestCase):
    """main の流れ（サイト取得 scrape_rebate と Slack はモック）。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        hermetic(self, Path(self.tmp.name))
        self.state_path = Path(self.tmp.name) / "etc_monthly.json"
        self.slack = []
        self.slack_res = {"ok": True}
        self.sync_calls = []
        self.sync = {"push": "success", "display": "success", "attempts": 1, "mismatches": [], "error": ""}

    def run_main(self, scrape, *argv, day=21, state=None):
        if state is not None:
            self.state_path.write_text(json.dumps(state))
        fixed = datetime(2026, 11, day, 9, 30, tzinfo=JST)

        class FakeDT(datetime):
            @classmethod
            def now(cls, tz=None):
                return fixed

        out = io.StringIO()
        with mock.patch.object(etc, "STATE_PATH", self.state_path), \
                mock.patch.object(etc, "datetime", FakeDT), \
                mock.patch.object(etc, "load_dotenv", lambda p: {"ETC_MILEAGE_ID": "x", "ETC_MILEAGE_WEB_PASSWORD": "y"}), \
                mock.patch.object(etc, "scrape_rebate", scrape), \
                mock.patch.object(etc.display614, "sync_and_verify", lambda ids, **kw: self.sync_calls.append(ids) or self.sync), \
                mock.patch.object(etc.ops614, "flush_pending", lambda **kw: {}), \
                mock.patch.object(etc, "push_slack_report", lambda **kw: self.slack.append(kw) or self.slack_res), \
                mock.patch.object(sys, "argv", ["x", "--apply", "--push", *argv]), \
                contextlib.redirect_stdout(out):
            rc = etc.main()
        self.out = json.loads(out.getvalue())
        return rc

    def st(self):
        return json.loads(self.state_path.read_text())

    def ok_scrape(self, **kw):
        return lambda **a: {"ok": True, "target_month": a["target_month"],
                            "grant_month": etc.add_months(a["target_month"], 1), "rebate_yen": 1234, **kw}

    def test_success_saves_verified_and_reports_checked(self):
        self.assertEqual(self.run_main(self.ok_scrape()), 0)
        self.assertEqual(self.st()["last_check_b"], "2026-11")
        self.assertTrue(self.out["save_verify"]["ok"])
        self.assertEqual(self.slack[-1]["outcome"], "checked")

    def test_waiting_is_not_failure_and_has_no_month_stamp(self):
        sc = lambda **a: {"ok": False, "kind": "waiting", "error": "付与前"}  # noqa: E731
        self.assertEqual(self.run_main(sc), 0)
        self.assertEqual(self.out["status"], "waiting")
        st = self.st()
        self.assertNotIn("last_check_b", st)
        self.assertEqual(st["etc_wait"]["target_month"], "2026-10")
        self.assertEqual(st["etc_wait"]["attempts"], 1)
        self.assertEqual([s["outcome"] for s in self.slack], ["waiting"])

    def test_waiting_not_rechecked_on_same_day_but_rechecked_next_day(self):
        calls = []
        sc = lambda **a: calls.append(1) or {"ok": False, "kind": "waiting", "error": "付与前"}  # noqa: E731
        self.run_main(sc, day=21)
        self.run_main(sc, day=21)  # 同じ日の再起動（朝の取りこぼし起動など）
        self.assertEqual(len(calls), 1)
        self.assertIn("今日は確認済み", self.out["skipped"])
        self.run_main(sc, day=22)  # 翌日は再確認
        self.assertEqual(len(calls), 2)
        self.assertEqual(self.st()["etc_wait"]["attempts"], 2)
        self.assertEqual([s["outcome"] for s in self.slack], ["waiting"])  # 毎日は出さない（最初の1回だけ）

    def test_waiting_on_last_window_day_notifies_ops_as_failed(self):
        sc = lambda **a: {"ok": False, "kind": "waiting", "error": "付与前"}  # noqa: E731
        self.assertEqual(self.run_main(sc, day=26), 0)
        self.assertEqual(self.slack[-1]["outcome"], "failed")
        self.assertIn("最終日まで未付与", self.slack[-1]["error"])
        self.assertNotIn("last_check_b", self.st())

    def test_technical_failure_is_failed_exit_1(self):
        sc = lambda **a: {"ok": False, "kind": "failed", "error": "開けませんでした"}  # noqa: E731
        self.assertEqual(self.run_main(sc), 1)
        self.assertEqual(self.slack[-1]["outcome"], "failed")
        self.assertFalse(self.state_path.exists())

    def test_exception_is_failed(self):
        def boom(**a):
            raise RuntimeError("playwright")
        self.assertEqual(self.run_main(boom), 1)
        self.assertEqual(self.slack[-1]["outcome"], "failed")

    def test_wrong_month_result_is_not_completed(self):
        sc = lambda **a: {"ok": True, "target_month": "2026-06", "grant_month": "2026-07", "rebate_yen": 9}  # noqa: E731
        self.assertEqual(self.run_main(sc), 1)
        self.assertIn("対象月", self.out["error"])
        self.assertEqual(self.slack[-1]["outcome"], "failed")
        self.assertFalse(self.state_path.exists())

    def test_existing_history_is_not_overwritten_without_force(self):
        hist = {"rebate_history": [{"target_month": "2026-10", "rebate_yen": 500, "source": "manual"}]}
        calls = []
        sc = lambda **a: calls.append(1) or {"ok": True}  # noqa: E731
        self.run_main(sc, state=hist)
        self.assertEqual(calls, [])
        self.assertEqual(self.st()["rebate_history"][0]["rebate_yen"], 500)

    def test_save_readback_failure_blocks_success_and_dashboard(self):
        real = vs._write_atomic

        def bad(path, data):
            real(path, {"truncated": True} if path == self.state_path else data)

        with mock.patch.object(vs, "_write_atomic", bad):
            self.assertEqual(self.run_main(self.ok_scrape()), 1)
        self.assertFalse(self.out["save_verify"]["ok"])
        self.assertEqual(self.sync_calls, [])  # 保存を確認できない結果は画面へ渡さない
        self.assertEqual(self.slack[-1]["outcome"], "failed")
        self.assertTrue(self.state_path.with_name("etc_monthly.pending.json").is_file())

    def test_manual_old_month_is_allowed_outside_window(self):
        self.assertEqual(self.run_main(self.ok_scrape(), "--target-month", "2026-06", day=3), 0)
        st = self.st()
        self.assertEqual(st["rebate_history"][0]["target_month"], "2026-06")
        self.assertNotIn("last_check_b", st)


class EtcRunLogTests(EtcMainTests):
    """ETC の run 記録・画面反映・全体停止（P1）。EtcMainTests の部品を流用。"""

    def stages(self):
        return runlog614.read_runs()[-1]["systems"]["etc"]["stages"]

    def test_success_run_records_every_stage_independently(self):
        self.assertEqual(self.run_main(self.ok_scrape()), 0)
        st = self.stages()
        for name in ("fetch", "save", "save_verify", "stamp", "push", "display", "slack"):
            self.assertEqual(st[name]["status"], "success", name)
        self.assertEqual(self.sync_calls, [["etc_mileage"]])
        self.assertEqual(runlog614.success_count(runlog614.read_runs(), system="etc"), 1)

    def test_display_mismatch_fails_display_only(self):
        self.sync = {"push": "success", "display": "failed", "attempts": 2, "mismatches": ["etc_mileage:x"],
                     "error": "画面の値が保存済み state と違う"}
        notified = []
        with mock.patch.object(etc.ops614, "notify_ops", lambda **kw: notified.append(kw) or {}):
            self.assertEqual(self.run_main(self.ok_scrape()), 0)
        st = self.stages()
        self.assertEqual((st["fetch"]["status"], st["save_verify"]["status"], st["stamp"]["status"],
                          st["display"]["status"]), ("success", "success", "success", "failed"))
        self.assertEqual(self.st()["last_check_b"], "2026-11")  # 月印は取り消さない
        self.assertEqual(notified[0]["stage"], "n17/18 画面反映")

    def test_waiting_run_is_waiting_not_success(self):
        sc = lambda **a: {"ok": False, "kind": "waiting", "error": "付与前"}  # noqa: E731
        self.run_main(sc)
        st = self.stages()
        self.assertEqual((st["fetch"]["status"], st["stamp"]["status"]), ("waiting", "skipped"))
        self.assertEqual(runlog614.success_count(runlog614.read_runs(), system="etc"), 0)
        self.assertEqual(self.sync_calls, [])

    def test_failure_run_is_failed_and_not_success(self):
        sc = lambda **a: {"ok": False, "kind": "failed", "error": "x"}  # noqa: E731
        self.run_main(sc)
        self.assertEqual(self.stages()["fetch"]["status"], "failed")
        self.assertEqual(self.slack[-1]["stage"], "n09 ETC 取得")  # 工程と次の対応つきで #ops へ
        self.assertTrue(self.slack[-1]["next_action"])

    def test_slack_unknown_result_is_unverified(self):
        self.slack_res = {"ok": False, "returncode": 4}
        self.run_main(self.ok_scrape())
        self.assertEqual(self.stages()["slack"]["status"], "unverified")

    def test_skip_is_recorded_but_not_success(self):
        self.run_main(self.ok_scrape(), state={"rebate_history": [{"target_month": "2026-10", "rebate_yen": 5}]})
        self.assertEqual(self.stages()["fetch"]["status"], "skipped")
        self.assertEqual(runlog614.success_count(runlog614.read_runs(), system="etc"), 0)

    def test_global_stop_beats_force_and_manual(self):
        os.environ["JARVIS_614_GLOBAL_STOP"] = "1"
        calls = []
        sc = lambda **a: calls.append(1) or {"ok": True}  # noqa: E731
        self.assertEqual(self.run_main(sc, "--force", "--target-month", "2026-10"), 0)
        self.assertEqual(calls, [])
        self.assertIn("全体停止", self.out["skipped"])

    def test_dry_run_is_not_counted(self):
        self.run_main(self.ok_scrape(), "--dry-run")
        self.assertTrue(runlog614.read_runs()[-1]["dry_run"])
        self.assertEqual(runlog614.success_count(runlog614.read_runs()), 0)


class SlackWaitingWordingTests(unittest.TestCase):
    def test_waiting_is_not_failure_wording(self):
        t = sr.build_etc(outcome="waiting", target_month="2026-10", rebate_yen=None, asayu_trip_count=None,
                         asayu_rate_pct=None, savings_yen=None, reason="付与前", error="", note="")
        self.assertIn("取得待ち", t)
        self.assertNotIn("失敗", t)


if __name__ == "__main__":
    unittest.main()
