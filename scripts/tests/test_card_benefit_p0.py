"""614 年間特典ウォッチ PR-P0 — 誤成功防止・月印・保存検証・取得品質・推奨停止。

架空の値だけ。Gmail(orca)・Zaim・Slack・ネットワークには触れない（すべてモック）。state は一時フォルダ。
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jarvis_614_runlog as runlog  # noqa: E402
import jarvis_614_verified_state as vs  # noqa: E402
import jarvis_card_benefit_monthly as m  # noqa: E402
import jarvis_card_benefit_watch as c  # noqa: E402

TODAY = date(2026, 11, 28)
CFG = {
    "pace": {"reach_ratio": 1.0, "tight_ratio": 1.5},
    "zaim_note": "概算",
    "zaim_stale_days": 10,
    "cards": {
        "olive": {
            "name": "カードO", "short": "O", "usage_source": "gmail_monthly", "stale_days": 45,
            "period": {"type": "fixed", "start": "2026-06-01", "end": "2027-06-30"},
            "tiers": [{"id": "t", "label": "目標", "threshold_yen": 4_000_000, "reward": "r",
                       "threshold_status": "estimated"}],
        },
        "bonvoy": {
            "name": "カードB", "short": "B", "usage_source": "zaim_estimate",
            "period": {"type": "annual_from", "month": 3, "day": 1},
            "zaim_pay_contains": "FOO CARD", "zaim_exclude_keywords": ["年会費"],
            "tiers": [{"id": "t", "label": "目標", "threshold_yen": 4_000_000, "reward": "r",
                       "threshold_status": "needs_check"}],
        },
    },
}


def mail_body(y, mo, d, yen):
    return f"{y}年{mo}月{d}日現在\n利用金額 {yen:,}円（税込）"


class FakeOrca:
    """orca gmail の代わり。search/read の応答を差し替えられる。呼び出し回数を数える。"""

    def __init__(self, *, search_ok=True, mails=(), read_ok=True):
        self.search_ok, self.mails, self.read_ok = search_ok, list(mails), read_ok
        self.calls = 0

    def __call__(self, args, timeout=60):
        self.calls += 1
        if args[0] == "search":
            if not self.search_ok:
                return None
            return {"ok": True, "result": {"threads": [{"ref": f"r{i}"} for i, _ in enumerate(self.mails)]}}
        if not self.read_ok:
            return None
        i = int(args[1][1:])
        return {"ok": True, "result": {"messages": [{"body": self.mails[i]}]}}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        patcher = mock.patch.dict(os.environ, {
            "JARVIS_STATE_DIR": str(self.dir),
            "JARVIS_614_LOG_DIR": str(self.dir / "614_watch"),
            "JARVIS_614_EMERGENCY_DIR": str(self.dir / "emergency"),
        })
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("JARVIS_CARD_BENEFIT_DISABLE", None)
        os.environ.pop("JARVIS_CARD_BENEFIT_SLACK_REPORT_DISABLE", None)
        os.environ.pop("JARVIS_POINTS_REBATE_SLACK_REPORT_DISABLE", None)
        os.environ.pop("JARVIS_614_GLOBAL_STOP", None)

    def write_index(self, as_of="2026-11-25", pay="FOO CARD", amount=1000, updated_at="x"):
        rows = {"k1": {"pay": pay, "date": as_of, "amount": amount, "shop": "s", "item": "i"}}
        (self.dir / "zaim_learn_csv_index.json").write_text(
            json.dumps({"rows": rows, "updated_at": updated_at}))

    def write_weekly(self, **kw):
        (self.dir / "zaim_csv_weekly.json").write_text(json.dumps(kw))

    def state(self):
        return json.loads(c.state_path().read_text(encoding="utf-8"))


class OliveQualityTests(Base):
    def run_olive(self, orca, state=None):
        with mock.patch.object(c, "_orca_json", orca):
            return c.fetch_olive_checked(state if state is not None else {}, cfg=CFG, today=TODAY)

    def test_gmail_search_failure_is_failed_not_success(self):  # F5
        r = self.run_olive(FakeOrca(search_ok=False))
        self.assertEqual((r["status"], r["error_code"]), (c.SRC_FAILED, "gmail_search_failed"))

    def test_fresh_mail_is_success(self):
        r = self.run_olive(FakeOrca(mails=[mail_body(2026, 11, 15, 1_000_000)]))
        self.assertEqual((r["status"], r["as_of"], r["added"]), (c.SRC_OK, "2026-11-15", 1))

    def test_no_mail_and_no_snapshot_is_waiting(self):
        r = self.run_olive(FakeOrca(mails=[]))
        self.assertEqual((r["status"], r["error_code"]), (c.SRC_WAITING, "olive_mail_not_arrived"))

    def test_no_new_mail_but_latest_within_45_days_is_success(self):
        st = {"olive": {"snapshots": [{"as_of": "2026-10-15", "usage_yen": 1}]}}
        self.assertEqual(self.run_olive(FakeOrca(mails=[]), st)["status"], c.SRC_OK)

    def test_old_latest_and_no_mail_is_waiting_not_success(self):
        st = {"olive": {"snapshots": [{"as_of": "2026-09-01", "usage_yen": 1}]}}
        self.assertEqual(self.run_olive(FakeOrca(mails=[]), st)["status"], c.SRC_WAITING)

    def test_stale_mail_is_partial(self):
        r = self.run_olive(FakeOrca(mails=[mail_body(2026, 9, 1, 5)]))
        self.assertEqual((r["status"], r["error_code"]), (c.SRC_PARTIAL, "olive_stale"))

    def test_unparsable_mail_is_failed(self):
        r = self.run_olive(FakeOrca(mails=["本文が読めない形式"]))
        self.assertEqual((r["status"], r["error_code"]), (c.SRC_FAILED, "olive_mail_parse_failed"))

    def test_read_failure_without_snapshot_is_failed(self):
        r = self.run_olive(FakeOrca(mails=["x"], read_ok=False))
        self.assertEqual((r["status"], r["error_code"]), (c.SRC_FAILED, "gmail_read_failed"))


class BonvoyQualityTests(Base):
    def run_bonvoy(self, state=None):
        return c.refresh_bonvoy_checked(state if state is not None else {}, CFG, TODAY)

    def test_index_missing_and_unreadable_are_failed(self):
        self.assertEqual(self.run_bonvoy()["error_code"], "zaim_index_missing")
        (self.dir / "zaim_learn_csv_index.json").write_text("{broken")
        r = self.run_bonvoy()
        self.assertEqual((r["status"], r["error_code"]), (c.SRC_FAILED, "zaim_index_unreadable"))

    def test_failure_keeps_previous_values_untouched(self):
        st = {"bonvoy": {"zaim": {"usage_yen": 7, "as_of": "2026-11-01"}}}
        self.run_bonvoy(st)
        self.assertEqual(st["bonvoy"]["zaim"]["usage_yen"], 7)

    def test_no_rows_is_unconfirmed(self):
        self.write_index(pay="OTHER")
        self.assertEqual(self.run_bonvoy()["status"], c.SRC_UNCONFIRMED)

    def test_stale_is_partial_and_fresh_is_success(self):
        self.write_index(as_of="2026-11-12")  # 16日前 > 10日
        r = self.run_bonvoy()
        self.assertEqual((r["status"], r["error_code"]), (c.SRC_PARTIAL, "zaim_stale"))
        self.write_index(as_of="2026-11-25")
        self.assertEqual(self.run_bonvoy()["status"], c.SRC_OK)


class ZaimFreshnessByCsvRangeTests(Base):
    """Zaim の鮮度は『取込CSVの範囲の終了日』で見る。Bonvoy 行の最新日（最終利用日）は補足。"""

    def run_bonvoy(self):
        st = {}
        return c.refresh_bonvoy_checked(st, CFG, TODAY), st

    def test_old_last_use_but_fresh_csv_is_success(self):
        self.write_index(as_of="2026-11-12", updated_at="2026-11-27T12:00:59+0900")
        self.write_weekly(last_ok=True, end_date="2026-11-27", last_success_at="2026-11-27T12:00:05+0900")
        r, st = self.run_bonvoy()
        self.assertEqual(r["status"], c.SRC_OK)
        self.assertEqual(r["as_of"], "2026-11-27")  # 基準日=CSV範囲の終了日
        z = st["bonvoy"]["zaim"]
        self.assertEqual((z["last_use_date"], z["csv_range_end"]), ("2026-11-12", "2026-11-27"))
        self.assertIn("最終利用日 2026-11-12", r["note"])

    def test_old_csv_range_is_partial(self):
        self.write_index(as_of="2026-11-12", updated_at="2026-11-12T12:00:00+0900")
        self.write_weekly(last_ok=True, end_date="2026-11-12", last_success_at="2026-11-12T12:00:05+0900")
        r, _ = self.run_bonvoy()
        self.assertEqual((r["status"], r["error_code"]), (c.SRC_PARTIAL, "zaim_stale"))

    def test_failed_weekly_export_does_not_count_its_end_date(self):
        # 失敗した run も end_date は今日で書かれる。最後に成功した日（11/05）で見る
        self.write_index(as_of="2026-11-04", updated_at="2026-11-27T12:00:59+0900")
        self.write_weekly(last_ok=False, end_date="2026-11-27", last_success_at="2026-11-05T12:00:05+0900")
        r, _ = self.run_bonvoy()
        self.assertEqual((r["status"], r["as_of"]), (c.SRC_PARTIAL, "2026-11-05"))

    def test_index_rebuilt_late_but_weekly_export_old_follows_the_older(self):
        self.write_index(as_of="2026-11-04", updated_at="2026-11-27T12:00:59+0900")
        self.write_weekly(last_ok=True, end_date="2026-11-10", last_success_at="2026-11-10T12:00:05+0900")
        self.assertEqual(self.run_bonvoy()[0]["status"], c.SRC_PARTIAL)

    def test_no_csv_range_info_falls_back_to_last_use_date(self):
        self.write_index(as_of="2026-11-12")  # updated_at 不明・weekly なし
        r, st = self.run_bonvoy()
        self.assertEqual((r["status"], r["as_of"]), (c.SRC_PARTIAL, "2026-11-12"))
        self.assertNotIn("csv_range_end", st["bonvoy"]["zaim"])

    def test_future_dated_csv_end_is_capped_at_today(self):
        self.write_index(as_of="2026-11-12", updated_at="2027-01-01T00:00:00+0900")
        self.assertEqual(self.run_bonvoy()[0]["as_of"], "2026-11-28")

    def test_recommendation_not_withheld_and_last_use_shown(self):
        self.write_index(as_of="2026-11-12", updated_at="2026-11-27T12:00:59+0900")
        self.write_weekly(last_ok=True, end_date="2026-11-27")
        st = {"olive": {"snapshots": [{"as_of": "2026-11-15", "usage_yen": 1_000_000}]}}
        c.refresh_bonvoy_checked(st, CFG, TODAY)
        r = c.compute(CFG, st, TODAY)
        self.assertTrue(r["cards"][1]["reliable"])
        self.assertFalse(r["recommendation"].get("withheld"))
        txt = c.build_slack_text(r, header="H", dash_url="u", mask=True)
        self.assertIn("・Bの最終利用日は11/12（Zaim は11/27まで取込）", txt)
        self.assertNotIn("Zaim が古い", txt)


class RecommendStopTests(Base):
    def st(self, olive_asof="2026-11-15", zaim_asof="2026-11-25", sources=None):
        s = {
            "olive": {"snapshots": [{"as_of": olive_asof, "usage_yen": 1_000_000}]},
            "bonvoy": {"zaim": {"usage_yen": 1_500_000, "as_of": zaim_asof}},
        }
        if sources:
            s["sources"] = sources
        return s

    def test_both_fresh_recommends(self):
        r = c.compute(CFG, self.st(), TODAY)
        self.assertTrue(all(x["reliable"] for x in r["cards"]))
        self.assertFalse(r["recommendation"].get("withheld"))

    def test_stale_zaim_withholds_card_to_card_recommendation(self):  # F9
        r = c.compute(CFG, self.st(zaim_asof="2026-11-12"), TODAY)
        self.assertTrue(r["recommendation"]["withheld"])
        self.assertIsNone(r["recommendation"]["card"])
        self.assertIn("Zaim が古い", r["recommendation"]["line"])
        # 取れている側の達成率などは出し続ける
        self.assertEqual(r["cards"][1]["usage_as_of"], "2026-11-12")
        self.assertIsNotNone(r["cards"][1]["tiers"][0]["achieved_pct"])

    def test_failed_source_withholds_even_if_old_value_is_fresh(self):
        src = {"bonvoy": {"status": c.SRC_FAILED, "error_code": "zaim_index_missing"}}
        r = c.compute(CFG, self.st(sources=src), TODAY)
        self.assertTrue(r["recommendation"]["withheld"])
        self.assertEqual(r["cards"][1]["source_status"], c.SRC_FAILED)

    def test_waiting_and_unconfirmed_withhold(self):
        for st in (c.SRC_WAITING, c.SRC_UNCONFIRMED, c.SRC_PARTIAL):
            r = c.compute(CFG, self.st(sources={"olive": {"status": st}}), TODAY)
            self.assertTrue(r["recommendation"]["withheld"], st)

    def test_one_side_missing_withholds(self):
        s = self.st()
        del s["olive"]
        self.assertTrue(c.compute(CFG, s, TODAY)["recommendation"]["withheld"])

    def test_slack_text_says_withheld_and_has_no_amounts(self):
        r = c.compute(CFG, self.st(zaim_asof="2026-11-12"), TODAY)
        txt = c.build_slack_text(r, header="H", dash_url="u", mask=True)
        self.assertIn("おすすめは保留", txt)
        self.assertNotIn("今月はこちらを使うのがおすすめ", txt)

    def test_slack_text_flags_failed_source(self):
        src = {"olive": {"status": c.SRC_FAILED}}
        txt = c.build_slack_text(c.compute(CFG, self.st(sources=src), TODAY), header="H", dash_url="u", mask=True)
        self.assertIn("・Oは取込失敗", txt)


class VerifiedSaveTests(Base):
    def test_roundtrip_ok_and_pending_removed(self):
        p = self.dir / "s.json"
        pend = self.dir / "s.pending.json"
        pend.write_text("{}")
        r = vs.save_json_verified(p, {"a": 1, "b": [1, 2]}, pending_path=pend)
        self.assertTrue(r["ok"])
        self.assertEqual(json.loads(p.read_text()), {"a": 1, "b": [1, 2]})
        self.assertFalse(pend.exists())

    def test_mismatch_keeps_pending_and_retries_save_only_once(self):
        p = self.dir / "s.json"
        pend = self.dir / "s.pending.json"
        real = vs._write_atomic
        writes = []

        def bad(path, data):  # state 本体だけ内容を落とす（pending は正しく書く）
            writes.append(path.name)
            real(path, {} if path == p else data)

        with mock.patch.object(vs, "_write_atomic", bad):
            r = vs.save_json_verified(p, {"month": "2026-11"}, pending_path=pend)
        self.assertFalse(r["ok"])
        self.assertEqual(r["attempts"], 2)  # 初回＋保存だけ1回
        self.assertEqual(json.loads(pend.read_text()), {"month": "2026-11"})

    def test_second_attempt_can_succeed(self):
        p = self.dir / "s.json"
        real = vs._write_atomic
        n = {"i": 0}

        def flaky(path, data):
            n["i"] += 1
            real(path, {} if n["i"] == 1 else data)

        with mock.patch.object(vs, "_write_atomic", flaky):
            r = vs.save_json_verified(p, {"x": 1})
        self.assertEqual((r["ok"], r["attempts"]), (True, 2))

    def test_corrupt_state_is_not_treated_as_empty(self):
        p = self.dir / "card_benefit_watch.json"
        p.write_text("{broken")
        with self.assertRaises(c.StateReadError):
            c.load_state_strict()
        p.write_text("[1]")
        with self.assertRaises(c.StateReadError):
            c.load_state_strict()
        self.assertEqual(c.load_state_strict(self.dir / "none.json"), {})

    def test_backup_not_overwritten_by_broken_file(self):
        p = self.dir / "s.json"
        vs.save_json_verified(p, {"v": 1})
        vs.save_json_verified(p, {"v": 2})
        self.assertEqual(json.loads((self.dir / "s.json.bak").read_text()), {"v": 1})
        p.write_text("{broken")
        vs.save_json_verified(p, {"v": 3})
        self.assertEqual(json.loads((self.dir / "s.json.bak").read_text()), {"v": 1})

    def test_failed_attempt_does_not_overwrite_backup_and_leaves_no_tmp(self):
        p = self.dir / "s.json"
        vs.save_json_verified(p, {"v": 1})
        vs.save_json_verified(p, {"v": 2})  # .bak = v1
        real = vs._write_atomic

        def bad(path, data):
            real(path, {"v": "bad"} if path == p else data)

        with mock.patch.object(vs, "_write_atomic", bad):
            r = vs.save_json_verified(p, {"v": 3})
        self.assertFalse(r["ok"])
        self.assertEqual(json.loads((self.dir / "s.json.bak").read_text()), {"v": 2})  # 検証失敗後の再試行で壊れた版に更新されない
        with mock.patch.object(vs.os, "replace", side_effect=OSError("disk")):
            r = vs.save_json_verified(p, {"v": 4})
        self.assertFalse(r["ok"])
        self.assertEqual([x.name for x in self.dir.glob(".*.tmp")], [])  # tmp を残さない

    def test_state_file_is_owner_only(self):
        p = self.dir / "s.json"
        vs.save_json_verified(p, {"v": 1})
        self.assertEqual(p.stat().st_mode & 0o777, 0o600)

    def test_lock_blocks_second_holder(self):
        lp = self.dir / "x.lock"
        with vs.file_lock(lp):
            with self.assertRaises(vs.LockBusy):
                with vs.file_lock(lp):
                    pass
        with vs.file_lock(lp):  # 解放後は取れる
            pass


class MonthlyFlowTests(Base):
    """月次本体: 取得失敗で月印が付かない／Slack 失敗で月印が消えない／未完了の取得元だけやり直す。"""

    def setUp(self):
        super().setUp()
        self.slack_calls = []
        self.slack_rc = 0
        self.ops_calls = []
        self.sync = {"push": "success", "display": "success", "attempts": 1, "mismatches": [], "error": ""}
        self.orca = FakeOrca(mails=[mail_body(2026, 11, 15, 1_000_000)])
        for patcher in (
            mock.patch.object(c, "load_config", lambda *a, **k: CFG),
            mock.patch.object(c, "_orca_json", self.orca),
            mock.patch.object(m, "_today", lambda: TODAY),
            mock.patch.object(m, "_slack", self._slack),
            mock.patch.object(m.ops614, "notify_ops", lambda **kw: self.ops_calls.append(kw) or {"status": "sent"}),
            mock.patch.object(m.ops614, "flush_pending", lambda **kw: {"sent": 0}),
            mock.patch.object(m.display614, "sync_and_verify", lambda ids, **kw: self.sync),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.write_index(as_of="2026-11-25")

    def _slack(self, *extra):
        self.slack_calls.append(extra)
        return self.slack_rc

    def run_m(self, *flags):
        return m.main(["--force", *flags])

    def posted(self):
        return [x for x in self.slack_calls if "--from-state" in x]

    def ops(self):
        return self.ops_calls

    def test_all_success_stamps_after_save_verification(self):
        self.assertEqual(self.run_m(), 0)
        st = self.state()
        self.assertEqual(st["last_monthly_run"], "2026-11")
        self.assertEqual(st["monthly"]["fetched"], {"olive": "success", "bonvoy": "success"})
        self.assertEqual(len(self.posted()), 1)

    def test_olive_fetch_failure_does_not_stamp_and_notifies_ops(self):  # F5
        self.orca.search_ok = False
        self.assertEqual(self.run_m(), 1)
        st = self.state()
        self.assertNotIn("last_monthly_run", st)
        self.assertEqual(st["sources"]["olive"]["status"], c.SRC_FAILED)
        self.assertTrue(any("Oliveの取込に失敗" in x["cause"] for x in self.ops()))

    def test_unexpected_exception_becomes_failed_not_crash(self):
        with mock.patch.object(c, "refresh_bonvoy_checked", side_effect=KeyError("x")):
            self.assertEqual(self.run_m(), 1)
        st = self.state()
        self.assertEqual(st["sources"]["bonvoy"]["status"], c.SRC_FAILED)
        self.assertEqual(st["sources"]["bonvoy"]["error_code"], "unexpected_KeyError")
        self.assertNotIn("last_monthly_run", st)
        self.assertTrue(self.ops())

    def test_all_sources_failed_posts_no_report_but_notifies_ops(self):
        self.orca.search_ok = False
        (self.dir / "zaim_learn_csv_index.json").unlink()
        self.assertEqual(self.run_m(), 1)
        self.assertEqual(self.posted(), [])
        self.assertEqual(len(self.ops()), 2)

    def test_good_side_result_is_kept_when_other_fails(self):
        self.orca.search_ok = False
        self.run_m()
        st = self.state()
        self.assertEqual(st["sources"]["bonvoy"]["status"], c.SRC_OK)
        self.assertEqual(st["bonvoy"]["zaim"]["as_of"], "2026-11-25")

    def test_partial_stale_zaim_does_not_stamp_but_posts_once(self):
        self.write_index(as_of="2026-11-12")
        self.assertEqual(self.run_m(), 0)
        st = self.state()
        self.assertNotIn("last_monthly_run", st)
        self.assertEqual(st["monthly"]["fetched"]["bonvoy"], c.SRC_PARTIAL)
        self.assertEqual(len(self.posted()), 1)
        self.run_m()  # 状態が変わらない再実行では二重投稿しない
        self.assertEqual(len(self.posted()), 1)

    def test_retry_fetches_only_unfinished_source(self):
        self.write_index(as_of="2026-11-12")
        self.run_m()
        olive_calls = self.orca.calls
        self.write_index(as_of="2026-11-26")  # Zaim が更新された
        self.assertEqual(self.run_m(), 0)
        self.assertEqual(self.orca.calls, olive_calls)  # 成功済みの Olive は取り直さない
        self.assertEqual(self.state()["last_monthly_run"], "2026-11")
        self.assertEqual(len(self.posted()), 2)  # 状態が変わったので出し直す

    def test_slack_failure_keeps_stamp_and_retries_post_only(self):
        self.slack_rc = 1
        self.assertEqual(self.run_m(), 1)
        st = self.state()
        self.assertEqual(st["last_monthly_run"], "2026-11")  # 取得済みの月印は消えない
        self.assertFalse(st["monthly"].get("slack_fp"))
        self.assertTrue(any("取得・保存・月印は済み" in x["cause"] for x in self.ops()))
        calls = self.orca.calls
        self.slack_rc = 0
        self.assertEqual(self.run_m(), 0)
        self.assertEqual(self.orca.calls, calls)  # 取得し直さない
        self.assertTrue(self.state()["monthly"]["slack_fp"])

    def test_slack_timeout_style_failure_never_double_posts_after_success(self):
        self.run_m()
        self.run_m()
        self.run_m("--force")
        self.assertEqual(len(self.posted()), 1)

    def test_save_verification_failure_blocks_stamp_and_slack(self):
        real = vs._write_atomic

        def bad(path, data):
            real(path, {"truncated": True} if path.name == "card_benefit_watch.json" else data)

        with mock.patch.object(vs, "_write_atomic", bad):
            self.assertEqual(self.run_m(), 1)
        self.assertEqual(self.posted(), [])  # 保存を確認できないものを下流へ渡さない
        self.assertTrue((self.dir / "card_benefit_watch.pending.json").is_file())
        self.assertNotIn("last_monthly_run", json.loads(c.state_path().read_text()))
        self.assertTrue(any("保存を読み戻して確認できず" in x["cause"] for x in self.ops()))

    def test_corrupt_state_aborts_without_overwrite(self):
        c.state_path().write_text("{broken")
        self.assertEqual(self.run_m(), 1)
        self.assertEqual(c.state_path().read_text(), "{broken")
        self.assertEqual(self.orca.calls, 0)

    def test_dry_run_records_no_progress_and_no_stamp(self):
        self.assertEqual(self.run_m("--dry-run"), 0)
        st = self.state()
        self.assertNotIn("last_monthly_run", st)
        self.assertNotIn("monthly", st)
        self.assertIn("--dry-run", self.posted()[0])

    def test_lock_busy_skips_without_fetch(self):
        with vs.file_lock(c.lock_path()):
            self.assertEqual(self.run_m(), 0)
        self.assertEqual(self.orca.calls, 0)

    def test_all_flag_refetches_succeeded_sources(self):
        self.run_m()
        calls = self.orca.calls
        self.run_m("--all")
        self.assertGreater(self.orca.calls, calls)

    # ---- P1: run 集約・画面反映・Slack の独立 ----
    def last_run(self):
        runs = runlog.read_runs()
        return runs[-1]

    def stages(self):
        return self.last_run()["systems"]["card_benefit"]["stages"]

    def test_run_is_recorded_with_independent_stages(self):
        self.run_m()
        r = self.last_run()
        st = r["systems"]["card_benefit"]["stages"]
        for name in ("fetch", "save", "save_verify", "stamp", "push", "display", "slack"):
            self.assertEqual(st[name]["status"], "success", name)
        self.assertFalse(r["dry_run"])
        self.assertEqual(r["run_id"], os.environ["JARVIS_614_RUN_ID"])
        self.assertEqual(runlog.success_count(runlog.read_runs(), system="card_benefit"), 1)

    def test_dry_run_is_recorded_but_never_counts_as_success(self):
        self.run_m("--dry-run")
        r = self.last_run()
        self.assertTrue(r["dry_run"])
        st = self.stages()
        self.assertEqual((st["stamp"]["status"], st["push"]["status"], st["slack"]["status"]),
                         ("not_applicable",) * 3)
        self.assertEqual(runlog.success_count(runlog.read_runs()), 0)

    def test_push_failure_is_separate_from_fetch_save_stamp(self):
        self.sync = {"push": "failed", "display": "unverified", "attempts": 2, "mismatches": [], "error": "push exit 1"}
        self.assertEqual(self.run_m(), 0)  # 取得・保存・月印は成功のまま
        st = self.stages()
        self.assertEqual((st["fetch"]["status"], st["save_verify"]["status"], st["stamp"]["status"]),
                         ("success", "success", "success"))
        self.assertEqual((st["push"]["status"], st["display"]["status"]), ("failed", "unverified"))
        self.assertEqual(self.state()["last_monthly_run"], "2026-11")  # 月印は消えない
        self.assertTrue(any(o["stage"].startswith("n17") for o in self.ops()))

    def test_display_mismatch_fails_display_only_and_notifies(self):
        self.sync = {"push": "success", "display": "failed", "attempts": 2,
                     "mismatches": ["vpoint:teiki_last_check_at"], "error": "画面の値が保存済み state と違う"}
        self.assertEqual(self.run_m(), 0)
        st = self.stages()
        self.assertEqual((st["push"]["status"], st["display"]["status"]), ("success", "failed"))
        self.assertEqual(self.state()["last_monthly_run"], "2026-11")
        self.assertTrue(any(o["stage"].startswith("n18") for o in self.ops()))
        self.assertEqual(len(self.posted()), 1)  # 短報は画面反映の失敗に引きずられない

    def test_slack_unknown_result_is_not_reposted_and_not_counted_success(self):
        self.slack_rc = 4
        self.assertEqual(self.run_m(), 1)
        self.assertEqual(self.stages()["slack"]["status"], "unverified")
        st = self.state()
        self.assertEqual(st["last_monthly_run"], "2026-11")
        self.assertEqual(st["monthly"]["slack_result"], "unknown")
        self.assertTrue(st["monthly"]["slack_fp"])
        self.slack_rc = 0
        self.assertEqual(self.run_m(), 0)
        self.assertEqual(len(self.posted()), 1)  # 自動では再投稿しない
        self.assertFalse(m.needs_catchup(datetime(2026, 11, 29, 9, tzinfo=c.JST)))
        # 送信側で既に #ops 通知済みなので、月次側から二重に通知しない
        self.assertEqual([o for o in self.ops() if o["stage"].startswith("n19")], [])

    def test_slack_held_for_archive_failure_is_not_double_notified(self):
        self.slack_rc = 3
        self.assertEqual(self.run_m(), 3)
        self.assertEqual(self.stages()["slack"]["status"], "failed")
        self.assertEqual([o for o in self.ops() if o["stage"].startswith("n19")], [])
        self.assertEqual(self.state()["last_monthly_run"], "2026-11")

    def test_global_stop_overrides_force_and_skips_everything(self):
        os.environ["JARVIS_614_GLOBAL_STOP"] = "1"
        self.assertEqual(self.run_m("--all"), 0)
        self.assertEqual(self.orca.calls, 0)
        self.assertEqual(self.slack_calls, [])
        self.assertFalse(m.needs_catchup(datetime(2026, 11, 29, 9, tzinfo=c.JST)))

    def test_all_failed_skips_push_and_slack_stage(self):
        self.orca.search_ok = False
        (self.dir / "zaim_learn_csv_index.json").unlink()
        self.run_m()
        st = self.stages()
        self.assertEqual((st["fetch"]["status"], st["push"]["status"], st["slack"]["status"]),
                         ("failed", "skipped", "skipped"))

    def test_unexpected_error_is_recorded_and_notified(self):
        with mock.patch.object(m, "run", side_effect=RuntimeError("x")):
            with self.assertRaises(RuntimeError):
                self.run_m()
        self.assertEqual(self.stages()["fetch"]["error_code"], "unexpected_error")
        self.assertTrue(self.ops())

    def test_disabled_does_nothing(self):
        os.environ["JARVIS_CARD_BENEFIT_DISABLE"] = "1"
        self.assertEqual(self.run_m(), 0)
        self.assertEqual(self.orca.calls, 0)

    def test_slack_disabled_does_not_mark_posted(self):
        os.environ["JARVIS_CARD_BENEFIT_SLACK_REPORT_DISABLE"] = "1"
        self.run_m()
        self.assertFalse(self.state()["monthly"].get("slack_fp"))
        self.assertFalse(m.needs_catchup(datetime(2026, 11, 29, 9, tzinfo=c.JST)))


class CatchupTests(Base):
    def test_catchup_conditions(self):
        d = lambda day: datetime(2026, 11, day, 9, tzinfo=c.JST)  # noqa: E731
        self.assertFalse(m.needs_catchup(d(27)))
        self.assertTrue(m.needs_catchup(d(28)))
        # 今日もう試した → 1日1回
        c.save_state({"monthly": {"month": "2026-11", "fetched": {}, "last_attempt_day": "2026-11-28"}})
        self.assertFalse(m.needs_catchup(d(28)))
        self.assertTrue(m.needs_catchup(d(29)))  # 翌朝は未完了なので再試行
        # 印あり・短報なし → 投稿だけの取りこぼし
        c.save_state({"last_monthly_run": "2026-11", "monthly": {"month": "2026-11", "fetched": {}}})
        self.assertTrue(m.needs_catchup(d(29)))
        # 印あり・短報済み → 何もしない
        c.save_state({"last_monthly_run": "2026-11", "monthly": {"month": "2026-11", "slack_fp": "x"}})
        self.assertFalse(m.needs_catchup(d(29)))
        # 前月の印は今月に効かない
        c.save_state({"last_monthly_run": "2026-10", "monthly": {"month": "2026-10", "slack_fp": "x"}})
        self.assertTrue(m.needs_catchup(d(29)))


class WatchCliExitCodeTests(Base):
    def test_refresh_exits_nonzero_when_a_source_failed(self):  # exit 0 に埋もれない
        self.write_index(as_of="2026-11-25")
        with mock.patch.object(c, "_orca_json", FakeOrca(search_ok=False)), \
                mock.patch.object(c, "load_config", lambda *a, **k: CFG):
            self.assertEqual(c.main(["--refresh", "--mask"]), 2)

    def test_refresh_exits_zero_when_all_ok_and_state_verified(self):
        self.write_index(as_of=datetime.now(c.JST).strftime("%Y-%m-%d"))
        ok = FakeOrca(mails=[mail_body(2026, 11, 15, 5)])
        with mock.patch.object(c, "_orca_json", ok), mock.patch.object(c, "load_config", lambda *a, **k: CFG):
            self.assertEqual(c.main(["--refresh", "--mask"]), 0)
        self.assertIn(self.state()["sources"]["bonvoy"]["status"], (c.SRC_OK, c.SRC_PARTIAL))

    def test_refresh_stops_on_corrupt_state(self):
        c.state_path().write_text("{broken")
        with mock.patch.object(c, "load_config", lambda *a, **k: CFG):
            self.assertEqual(c.main(["--refresh"]), 3)
        self.assertEqual(c.state_path().read_text(), "{broken")


if __name__ == "__main__":
    unittest.main()
