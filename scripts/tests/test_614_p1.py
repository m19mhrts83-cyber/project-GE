"""614 PR-P1 — run 集約・#ops 通知・Slack 台帳と重複防止・画面反映の照合。

架空の値だけ。Slack・Supabase・サイトには触れない（すべてモック）。state・ログ・緊急ログは一時フォルダ。
"""
import json
import os
import socket
import sys
import tempfile
import unittest
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import types  # noqa: E402

try:  # CI には playwright が無い。画面操作は使わないので空の型だけ用意する
    import playwright.sync_api  # noqa: F401
except ImportError:
    _pw = types.ModuleType("playwright")
    _sync = types.ModuleType("playwright.sync_api")
    _sync.Page = object
    _sync.sync_playwright = lambda: None
    _pw.sync_api = _sync
    sys.modules["playwright"] = _pw
    sys.modules["playwright.sync_api"] = _sync

import jarvis_614_display as dsp  # noqa: E402
import jarvis_614_ops as ops  # noqa: E402
import jarvis_614_runlog as rl  # noqa: E402
import jarvis_614_slack_ledger as led  # noqa: E402
import jarvis_card_benefit_watch as cbw  # noqa: E402
import jarvis_points_rebate_slack_report as sr  # noqa: E402
import jarvis_slack_webhook_post as wh  # noqa: E402
import jarvis_teiki_barai_chance as tb  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        p = mock.patch.dict(os.environ, {
            "JARVIS_STATE_DIR": str(self.dir),
            "JARVIS_614_LOG_DIR": str(self.dir / "614_watch"),
            "JARVIS_614_EMERGENCY_DIR": str(self.dir / "emergency"),
        })
        p.start()
        self.addCleanup(p.stop)
        for k in ("JARVIS_614_GLOBAL_STOP", "JARVIS_614_OPS_ACTIVE", "JARVIS_614_RUN_ID", "SLACK_BOT_TOKEN"):
            os.environ.pop(k, None)

    def emergency(self):
        p = self.dir / "emergency" / "emergency.log"
        return p.read_text(encoding="utf-8") if p.is_file() else ""


# ------------------------------------------------------------------ run 集約
class RunLogTests(Base):
    def rec(self, **kw):
        return rl.RunRecord(run_id="r1", script="x.py", **kw)

    def test_three_levels_and_independent_stages(self):
        r = self.rec()
        r.stage("card_benefit", "fetch", "success")
        r.stage("card_benefit", "save", "success")
        r.stage("card_benefit", "push", "failed", "push exit 1", "push_failed")
        r.stage("etc", "fetch", "waiting")
        d = r.finish()
        self.assertEqual(d["run_id"], "r1")
        cb = d["systems"]["card_benefit"]
        self.assertEqual(cb["stages"]["fetch"]["status"], "success")  # 取得の成功は push の失敗に引きずられない
        self.assertEqual(cb["stages"]["push"]["error_code"], "push_failed")
        self.assertEqual(cb["outcome"], "failed")  # 系統の結果は一番悪い工程
        self.assertEqual(d["systems"]["etc"]["outcome"], "waiting")
        self.assertEqual(d["outcome"], "failed")
        self.assertEqual(rl.read_runs()[0]["run_id"], "r1")  # runs.jsonl に1行

    def test_skipped_and_not_applicable_only_is_skipped_outcome(self):
        r = self.rec()
        r.stage("etc", "fetch", "skipped")
        r.stage("etc", "push", "not_applicable")
        self.assertEqual(r.to_dict()["systems"]["etc"]["outcome"], "skipped")

    def test_unverified_is_not_success(self):
        r = self.rec()
        r.stage("vpoint", "fetch", "success")
        r.stage("vpoint", "display", "unverified")
        self.assertEqual(r.to_dict()["systems"]["vpoint"]["outcome"], "unverified")

    def test_success_counts_exclude_dry_run_skip_unverified_partial(self):
        for rid, dry, st in (("a", False, "success"), ("b", True, "success"), ("c", False, "skipped"),
                             ("d", False, "unverified"), ("e", False, "partial"), ("f", False, "success")):
            r = rl.RunRecord(run_id=rid, dry_run=dry)
            r.stage("etc", "fetch", st)
            r.finish()
        runs = rl.read_runs()
        self.assertEqual(rl.success_count(runs, system="etc"), 2)  # a と f だけ
        self.assertEqual(rl.success_count(runs, system="etc", stage="fetch"), 2)
        self.assertEqual(rl.stage_counts(runs, system="etc", stage="fetch")["dry_run"], 1)  # dry-run は別枠

    def test_unknown_status_rejected(self):
        with self.assertRaises(ValueError):
            self.rec().stage("etc", "fetch", "ok")

    def test_append_failure_never_raises(self):
        with mock.patch.object(rl.os, "open", side_effect=OSError("disk")):
            self.assertFalse(rl.append_run({"run_id": "x"}))
            self.rec().finish()  # 本線を落とさない

    def test_corrupt_lines_are_skipped_not_deleted(self):
        rl.runs_path().parent.mkdir(parents=True)
        rl.runs_path().write_text('{"run_id":"a","systems":{}}\n{broken\n{"run_id":"b","systems":{}}\n')
        self.assertEqual([r["run_id"] for r in rl.read_runs()], ["a", "b"])
        self.assertIn("{broken", rl.runs_path().read_text())

    def test_retention_lists_candidates_but_never_deletes(self):
        old = rl.RunRecord(run_id="old")
        old.started_at = (datetime.now(rl.JST) - timedelta(days=200)).isoformat(timespec="seconds")
        old.stage("etc", "fetch", "success")
        old.finish()
        new = rl.RunRecord(run_id="new")
        new.stage("etc", "fetch", "success")
        new.finish()
        self.assertEqual(rl.aged_candidates(), ["old"])
        self.assertEqual(len(rl.read_runs()), 2)  # 期間経過だけでは削除しない

    def test_run_id_follows_parent_env(self):
        os.environ["JARVIS_614_RUN_ID"] = "parent-1"
        self.assertEqual(rl.new_run_id("etc"), "parent-1")
        del os.environ["JARVIS_614_RUN_ID"]
        self.assertTrue(rl.new_run_id("etc").startswith("etc-"))

    def test_log_file_is_owner_only(self):
        self.rec().finish()
        self.assertEqual(rl.runs_path().stat().st_mode & 0o777, 0o600)


# ------------------------------------------------------------------ #ops 通知
class OpsTests(Base):
    def call(self, poster, **kw):
        base = dict(system="card_benefit", stage="n13 取込", cause="Gmail 検索に失敗", next_action="連携を確認",
                    run_id="r1", poster=poster)
        base.update(kw)
        return ops.notify_ops(**base)

    def test_message_has_stage_cause_next_run(self):
        sent = []
        self.call(lambda t: sent.append(t) or 0)
        t = sent[0]
        for part in ("n13 取込", "Gmail 検索に失敗", "連携を確認", "r1"):
            self.assertIn(part, t)

    def test_same_failure_notified_once_per_day(self):
        n = []
        poster = lambda t: n.append(1) or 0  # noqa: E731
        self.assertEqual(self.call(poster)["status"], "sent")
        self.assertEqual(self.call(poster)["status"], "duplicate")
        self.assertEqual(len(n), 1)
        self.assertEqual(self.call(poster, cause="別の原因")["status"], "sent")

    def test_send_failure_is_queued_privately_then_resent_on_next_start(self):
        self.assertEqual(self.call(lambda t: 1)["status"], "queued")
        self.assertTrue(ops.pending_path().is_file())
        sent = []
        out = ops.flush_pending(poster=lambda t: sent.append(t) or 0)
        self.assertEqual((out["sent"], len(sent)), (1, 1))
        # 履歴は消さず、結果を追記する。再度は送らない
        self.assertEqual(ops.flush_pending(poster=lambda t: sent.append(t) or 0)["sent"], 0)
        statuses = [json.loads(ln)["status"] for ln in ops.pending_path().read_text().splitlines()]
        self.assertEqual(statuses, ["pending", "sent"])

    def test_gives_up_after_max_attempts_and_logs_emergency(self):
        self.call(lambda t: 1)
        for _ in range(ops.MAX_ATTEMPTS):
            ops.flush_pending(poster=lambda t: 1)
        st = ops._pending_state()
        self.assertEqual(list(st.values())[0]["status"], "gave_up")
        self.assertIn("送れず保留のまま", self.emergency())
        self.assertEqual(ops.flush_pending(poster=lambda t: 0)["sent"], 0)  # 諦めたものは再送しない

    def test_global_stop_blocks_new_and_resend_but_queues(self):
        self.call(lambda t: 1)  # 保留1件
        os.environ["JARVIS_614_GLOBAL_STOP"] = "1"
        sent = []
        self.assertEqual(self.call(lambda t: sent.append(t) or 0, cause="停止中の新しい障害")["status"], "stopped")
        out = ops.flush_pending(poster=lambda t: sent.append(t) or 0)
        self.assertEqual(out["skipped"], "global_stop")
        self.assertEqual(sent, [])  # 停止中は送らない
        del os.environ["JARVIS_614_GLOBAL_STOP"]
        self.assertEqual(ops.flush_pending(poster=lambda t: sent.append(t) or 0)["sent"], 2)  # OFF の次回に再送

    def test_global_stop_via_file(self):
        (self.dir / "614_watch").mkdir(parents=True)
        (self.dir / "614_watch" / "GLOBAL_STOP").write_text("")
        self.assertTrue(ops.global_stop())

    def test_recursion_guard_creates_no_new_notification(self):
        os.environ["JARVIS_614_OPS_ACTIVE"] = "1"
        called = []
        self.assertEqual(self.call(lambda t: called.append(1) or 0)["status"], "guard")
        self.assertEqual(called, [])
        self.assertIn("再帰を抑止", self.emergency())
        self.assertEqual(ops.flush_pending(poster=lambda t: 0)["skipped"], "guard")

    def test_poster_runs_with_guard_env_for_child(self):
        seen = {}

        def fake_run(cmd, **kw):
            seen["env"] = kw["env"]
            return mock.Mock(returncode=0)

        with mock.patch.object(ops.subprocess, "run", fake_run):
            self.assertEqual(ops._default_poster("x"), 0)
        self.assertEqual(seen["env"]["JARVIS_614_OPS_ACTIVE"], "1")

    def test_queue_write_failure_falls_back_to_emergency_log(self):
        with mock.patch.object(ops, "_append_jsonl", return_value=False):
            self.assertEqual(self.call(lambda t: 1)["status"], "lost")
        self.assertIn("ops_pending 書込失敗", self.emergency())
        self.assertIn("保存も失敗", self.emergency())

    def test_emergency_log_lives_outside_state_dir_and_never_raises(self):
        self.assertNotIn(str(self.dir / "614_watch"), str(ops.emergency_dir()))
        with mock.patch.object(Path, "mkdir", side_effect=OSError("ro")):
            self.assertFalse(ops.emergency_log("x"))

    def test_dry_run_prints_and_sends_nothing(self):
        called = []
        out = self.call(lambda t: called.append(1) or 0, dry_run=True)
        self.assertEqual((out["status"], called), ("dry_run", []))
        self.assertFalse(ops.pending_path().exists())


# ------------------------------------------------------------------ Slack 台帳
class LedgerTests(Base):
    def test_blocking_states_and_not_sent_retry(self):
        k = led.key("etc", "report", "本文")
        self.assertIsNone(led.should_skip(k))
        led.record(k, "sending", run_id="r")
        self.assertEqual(led.should_skip(k), "sending")  # 途中で落ちた＝結果不明として扱う
        led.record(k, "not_sent", run_id="r")
        self.assertIsNone(led.should_skip(k))  # 届いていないと確定 → 再試行してよい
        led.record(k, "unknown", run_id="r")
        self.assertEqual(led.should_skip(k), "unknown")
        led.record(k, "sent", run_id="r")
        self.assertEqual(led.should_skip(k), "sent")

    def test_ledger_window_expires_for_old_entries(self):
        k = led.key("etc", "report", "本文")
        led.record(k, "sent", run_id="r")
        future = datetime.now(rl.JST) + timedelta(hours=25)
        self.assertIsNone(led.latest(k, now=future))

    def test_ledger_has_no_text_or_amounts(self):
        led.record(led.key("etc", "report", "還元額=12,345円"), "sent", run_id="r")
        self.assertNotIn("12,345", led.ledger_path().read_text())

    def test_text_matches_tolerates_signal_footer_links_and_escapes(self):
        sent = "【614 ポイント還元｜ETC還元】\n・結果: 還元サマリ取得\n・見る: https://example.invalid/etc?a=1&b=2"
        posted = ("【614 ポイント還元｜ETC還元】\n判定: 🟢 問題なし\n・結果: 還元サマリ取得\n"
                  "・見る: <https://example.invalid/etc?a=1&amp;b=2|https://example.invalid/etc?a=1&amp;b=2>\n\nFBは#aiへ")
        self.assertTrue(led.text_matches(posted, sent))
        self.assertFalse(led.text_matches("別の投稿", sent))
        self.assertFalse(led.text_matches(posted, ""))

    def test_confirm_sent_none_without_token_or_channel(self):
        self.assertIsNone(led.confirm_sent("report", "x", history=lambda *a, **k: []))

    def test_confirm_sent_true_false_and_error_is_none(self):
        os.environ["SLACK_BOT_TOKEN"] = "x"
        with mock.patch.object(led, "channel_id", lambda ch: "C123"):
            self.assertTrue(led.confirm_sent("report", "A\nB", history=lambda *a, **k: [{"text": "A\nB"}]))
            self.assertFalse(led.confirm_sent("report", "A\nB", history=lambda *a, **k: [{"text": "他"}]))

            def boom(*a, **k):
                raise RuntimeError("not_in_channel")

            self.assertIsNone(led.confirm_sent("report", "A\nB", history=boom))  # 確認できない≠未送信

    def test_channel_ids_come_from_hub_config(self):
        self.assertTrue(led.channel_id("report").startswith("C"))
        self.assertTrue(led.channel_id("ops").startswith("C"))


# ------------------------------------------------------------------ Slack 短報の投稿の流れ
class PostFlowTests(Base):
    TEXT = "【614 ポイント還元｜ETC還元】\n・結果: 還元サマリ取得"

    def setUp(self):
        super().setUp()
        self.posts = []
        self.rcs = [0]
        self.confirm = None
        self.notified = []
        for p in (
            mock.patch.object(sr, "DEDUPE_STATE", self.dir / "dedupe.json"),
            mock.patch.object(sr, "_run_post", self._run_post),
            mock.patch.object(sr.ledger614, "confirm_sent", lambda ch, t, **kw: self.confirm),
            mock.patch.object(sr.ops614, "notify_ops", lambda **kw: self.notified.append(kw) or {"status": "sent"}),
        ):
            p.start()
            self.addCleanup(p.stop)
        sr._OPS_EXTRA.clear()
        self.addCleanup(sr._OPS_EXTRA.clear)

    def _run_post(self, channel, text):
        self.posts.append((channel, text))
        return self.rcs[min(len(self.posts) - 1, len(self.rcs) - 1)]

    def post(self, channel="report", text=None, **kw):
        return sr._post(channel, text or self.TEXT, dry_run=False, archive_tag="etc_checked", kind="etc", **kw)

    def archive(self):
        return sorted((self.dir / "points_rebate_reports").glob("*"))

    def ledger_states(self):
        return [r["status"] for r in ops._read_jsonl(led.ledger_path())]

    def test_success_saves_body_before_posting_then_appends_result(self):
        order = []
        real_arch = sr._archive_before
        sr_run = self._run_post

        def arch(text, tag, run_id):
            order.append("archive")
            return real_arch(text, tag, run_id)

        with mock.patch.object(sr, "_archive_before", arch), \
                mock.patch.object(sr, "_run_post", lambda c, t: order.append("post") or sr_run(c, t)):
            self.assertEqual(self.post(), 0)
        self.assertEqual(order, ["archive", "post"])  # 控えが先
        body = self.archive()[0].read_text(encoding="utf-8")
        self.assertIn("送信前", body)
        self.assertIn("投稿結果: 送信済み", body)
        self.assertEqual(self.ledger_states(), ["sending", "sent"])

    def test_archive_failure_retries_save_once_then_holds_post(self):
        writes = []
        with mock.patch.object(sr, "_write_archive", lambda p, b: writes.append(1) or False):
            self.assertEqual(self.post(), sr.EXIT_HELD)
        self.assertEqual(len(writes), 2)  # 保存だけ1回再試行
        self.assertEqual(self.posts, [])  # 投稿を保留
        self.assertEqual(self.ledger_states(), ["held"])
        self.assertEqual(self.notified[0]["stage"], "n21 Slack 控え保存")

    def test_archive_first_failure_then_success_still_posts(self):
        n = {"i": 0}
        real = sr._write_archive

        def flaky(p, b):
            n["i"] += 1
            return False if n["i"] == 1 else real(p, b)

        with mock.patch.object(sr, "_write_archive", flaky):
            self.assertEqual(self.post(), 0)
        self.assertEqual(len(self.posts), 1)

    def test_timeout_with_history_none_retries_exactly_once(self):
        self.rcs, self.confirm = [4, 0], False
        self.assertEqual(self.post(), 0)
        self.assertEqual(len(self.posts), 2)
        self.assertEqual(self.ledger_states(), ["sending", "not_sent", "sent"])

    def test_timeout_with_history_found_does_not_repost(self):
        self.rcs, self.confirm = [4], True
        self.assertEqual(self.post(), 0)
        self.assertEqual(len(self.posts), 1)
        self.assertEqual(self.ledger_states()[-1], "sent")

    def test_timeout_unconfirmable_is_unknown_never_reposted_and_blocks_later_runs(self):
        self.rcs, self.confirm = [4], None
        self.assertEqual(self.post(), sr.EXIT_UNKNOWN)
        self.assertEqual(len(self.posts), 1)  # 不明なまま再投稿しない
        self.assertEqual(self.ledger_states()[-1], "unknown")
        self.assertIn("結果不明", self.archive()[0].read_text(encoding="utf-8"))
        self.assertEqual(self.notified[0]["stage"], "n19 Slack 投稿")
        self.assertEqual(self.post(), 0)  # 次の run も（同じ本文は）再投稿しない
        self.assertEqual(len(self.posts), 1)

    def test_retry_that_also_times_out_stays_unknown_without_third_post(self):
        self.rcs, self.confirm = [4, 4], False
        self.assertEqual(self.post(), sr.EXIT_UNKNOWN)
        self.assertEqual(len(self.posts), 2)

    def test_hard_failure_is_not_sent_and_next_run_may_post(self):
        self.rcs = [1, 0]
        self.assertEqual(self.post(), 1)
        self.assertEqual(self.ledger_states()[-1], "not_sent")
        self.assertEqual(self.post(), 0)
        self.assertEqual(len(self.posts), 2)

    def test_result_append_failure_does_not_repost(self):
        with mock.patch.object(sr, "_archive_append_result", lambda p, line: False):
            self.assertEqual(self.post(), 0)
        self.assertEqual(len(self.posts), 1)
        self.assertIn("結果追記に失敗", self.emergency())
        self.assertEqual(self.post(), 0)  # 同じ本文は台帳(sent)で止まる
        self.assertEqual(len(self.posts), 1)

    def test_append_retries_only_the_append_once(self):
        calls = []
        real_open = open

        def flaky_open(path, mode="r", *a, **k):
            if "a" in mode and str(path).endswith(".md"):
                calls.append(1)
                if len(calls) == 1:
                    raise OSError("busy")
            return real_open(path, mode, *a, **k)

        with mock.patch("builtins.open", flaky_open):
            self.assertEqual(self.post(), 0)
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(self.posts), 1)

    def test_dry_run_archive_is_marked_and_never_in_ledger_or_posted(self):
        rc = sr._post("report", self.TEXT, dry_run=True, archive_tag="etc_checked", kind="etc")
        self.assertEqual(rc, 0)
        files = [p.name for p in self.archive()]
        self.assertEqual(files, [f"{datetime.now(sr.JST).strftime('%Y-%m-%d')}_etc_checked_dryrun.md"])
        self.assertIn("dry-run・未配信", self.archive()[0].read_text(encoding="utf-8"))
        self.assertEqual((self.posts, self.ledger_states()), ([], []))

    def test_ops_failure_is_queued_privately_and_ops_unknown_is_not(self):
        self.rcs = [1]
        self.assertEqual(self.post("ops", "【614】失敗 — x"), 1)
        self.assertEqual(len(ops._pending_state()), 1)
        self.rcs, self.confirm = [4], None
        self.posts.clear()
        self.assertEqual(self.post("ops", "【614】失敗 — y"), sr.EXIT_UNKNOWN)
        self.assertEqual(len(ops._pending_state()), 1)  # 結果不明は再送キューに積まない（二重通知を避ける）
        self.assertEqual(self.notified, [])  # #ops 自身の失敗から #ops 通知を作らない

    def test_ops_post_goes_even_if_archive_fails(self):
        with mock.patch.object(sr, "_write_archive", lambda p, b: False):
            self.assertEqual(self.post("ops", "【614】失敗 — z"), 0)
        self.assertEqual(len(self.posts), 1)

    def test_global_stop_skips_report_and_queues_ops(self):
        os.environ["JARVIS_614_GLOBAL_STOP"] = "1"
        self.assertEqual(self.post(), 0)
        self.assertEqual(self.post("ops", "【614】失敗 — s"), 0)
        self.assertEqual(self.posts, [])
        self.assertEqual(len(ops._pending_state()), 1)

    def test_ops_extra_adds_stage_next_and_run(self):
        sr._OPS_EXTRA.update({"stage": "n13 Olive 取込", "next": "連携を確認"})
        os.environ["JARVIS_614_RUN_ID"] = "run-9"
        self.post("ops", "【614】失敗 — q")
        sent = self.posts[0][1]
        for part in ("・工程: n13 Olive 取込", "・次の対応: 連携を確認", "・run: run-9"):
            self.assertIn(part, sent)
        # #report には足さない
        sr._OPS_EXTRA.update({"stage": "x"})
        self.assertEqual(sr._with_ops_extra("report", "T", "r"), "T")

    def test_same_day_same_text_dedupe_still_works(self):
        self.assertEqual(self.post(), 0)
        self.assertEqual(self.post(), 0)
        self.assertEqual(len(self.posts), 1)

    def test_force_may_repost_sent_but_never_unknown(self):
        self.assertEqual(self.post(), 0)
        self.assertEqual(self.post(force=True), 0)
        self.assertEqual(len(self.posts), 2)
        self.rcs, self.confirm = [4], None
        self.post(text="別の本文")
        n = len(self.posts)
        self.post(text="別の本文", force=True)
        self.assertEqual(len(self.posts), n)


class WebhookExitCodeTests(unittest.TestCase):
    def test_classification(self):
        c = wh.classify_exception
        self.assertEqual(c(urllib.error.URLError(socket.gaierror(8, "x"))), 1)  # 接続前＝届いていない
        self.assertEqual(c(urllib.error.URLError(ConnectionRefusedError())), 1)
        self.assertEqual(c(socket.timeout()), wh.EXIT_UNKNOWN)  # 応答待ちで切れた＝届いた可能性
        self.assertEqual(c(urllib.error.URLError(socket.timeout())), wh.EXIT_UNKNOWN)
        self.assertEqual(c(ConnectionResetError()), wh.EXIT_UNKNOWN)
        self.assertEqual(c(ValueError("x")), wh.EXIT_UNKNOWN)  # 分からないものは不明側（再投稿しない）
        self.assertEqual(wh.EXIT_UNKNOWN, sr.EXIT_UNKNOWN)


# ------------------------------------------------------------------ 画面反映の照合
class DisplayTests(Base):
    def seed_state(self):
        cbw.save_state({"olive": {"snapshots": [{"as_of": "2026-11-15", "usage_yen": 1_000_000}]},
                        "bonvoy": {"zaim": {"usage_yen": 500_000, "as_of": "2026-11-24"}}})
        (self.dir / "teiki_barai_chance.json").write_text(json.dumps({"last_check_at": "2026-11-27T10:15:00+09:00"}))
        (self.dir / "etc_monthly.json").write_text(json.dumps(
            {"rebate_history": [{"target_month": "2026-10", "rebate_yen": 1234}]}))

    def row_for(self, wid):
        exp = dsp.expected_for(wid)
        if wid == "vpoint":
            return {"payload": {"card_benefit": cbw.compute_from_files(),
                                "teiki_barai": {"last_check_at": exp["teiki_last_check_at"]}}}
        return {"payload": {"rebate_history": [{"target_month": exp["latest_target_month"],
                                                 "rebate_yen": exp["latest_rebate_yen"]}]}}

    def test_matching_rows_are_success_on_first_push(self):
        self.seed_state()
        pushes = []
        res = dsp.sync_and_verify(["vpoint", "etc_mileage"], pusher=lambda: pushes.append(1) or 0,
                                  fetcher=lambda ids: {i: self.row_for(i) for i in ids})
        self.assertEqual((res["push"], res["display"], res["attempts"], len(pushes)), ("success", "success", 1, 1))

    def test_mismatch_repushes_exactly_once_and_can_recover(self):
        self.seed_state()
        pushes = []
        rows = {"n": 0}

        def fetch(ids):
            rows["n"] += 1
            r = {i: self.row_for(i) for i in ids}
            if rows["n"] == 1:
                r["etc_mileage"]["payload"]["rebate_history"][0]["target_month"] = "2026-09"  # 古いまま
            return r

        res = dsp.sync_and_verify(["etc_mileage"], pusher=lambda: pushes.append(1) or 0, fetcher=fetch)
        self.assertEqual((res["display"], res["attempts"], len(pushes)), ("success", 2, 2))

    def test_persistent_mismatch_fails_after_one_repush_without_amounts(self):
        self.seed_state()
        pushes = []

        def fetch(ids):
            return {i: {"payload": {}} for i in ids}

        res = dsp.sync_and_verify(["vpoint"], pusher=lambda: pushes.append(1) or 0, fetcher=fetch)
        self.assertEqual((res["push"], res["display"], res["attempts"], len(pushes)), ("success", "failed", 2, 2))
        self.assertIn("vpoint:", res["error"])
        self.assertNotIn("1000000", json.dumps(res))  # 実額は出さない

    def test_push_failure_retries_once_and_is_separate_from_display(self):
        self.seed_state()
        pushes = []
        res = dsp.sync_and_verify(["vpoint"], pusher=lambda: pushes.append(1) or 1, fetcher=lambda ids: {})
        self.assertEqual((res["push"], res["display"], len(pushes)), ("failed", "unverified", 2))

    def test_readback_unavailable_is_unverified_not_success_and_no_repush(self):
        self.seed_state()
        pushes = []

        def fetch(ids):
            raise RuntimeError("Supabase の資格情報なし")

        res = dsp.sync_and_verify(["vpoint"], pusher=lambda: pushes.append(1) or 0, fetcher=fetch)
        self.assertEqual((res["push"], res["display"], len(pushes)), ("success", "unverified", 1))

    def test_default_fetcher_without_credentials_raises_runtime_error(self):
        with mock.patch.object(dsp, "private_env", lambda: {}):
            for k in ("JARVIS_SUPABASE_URL", "JARVIS_SUPABASE_SERVICE_ROLE_KEY"):
                os.environ.pop(k, None)
            try:
                dsp.default_row_fetcher(["vpoint"])
            except RuntimeError:
                pass
            except ImportError:
                pass  # supabase 未導入の環境でも unverified 側（例外は sync_and_verify が受ける）
            else:
                self.fail("資格情報なしで読み戻せてしまった")

    def test_card_benefit_view_ignores_changing_fields_and_flags_withheld(self):
        self.seed_state()
        a = dsp.card_benefit_view(cbw.compute_from_files())
        b = dsp.card_benefit_view(dict(cbw.compute_from_files(), computed_at="other"))
        self.assertEqual(a, b)
        self.assertIn("withheld", a)

    def test_diff_fields_names_only(self):
        self.assertEqual(dsp.diff_fields({"a": 1, "c": {"x": 1, "y": 2}}, {"a": 2, "c": {"x": 1, "y": 3}}),
                         ["a", "c.y"])


# ------------------------------------------------------------------ テイチャン（本体は変えず記録だけ）
class TeikiWrapperTests(Base):
    def run_wrapper(self, argv, *, impl, states):
        seq = iter(states)
        with mock.patch.object(tb, "_main_impl", impl), \
                mock.patch.object(tb, "load_state", lambda: next(seq)), \
                mock.patch.object(sys, "argv", ["x", *argv]):
            return tb.main()

    def last(self):
        return rl.read_runs()[-1]["systems"]["teiki"]["stages"]["fetch"]

    def test_executed_run_is_success_and_exit_code_unchanged(self):
        rc = self.run_wrapper(["--run"], impl=lambda: 0, states=[{"last_check_at": "a"}, {"last_check_at": "b"}])
        self.assertEqual((rc, self.last()["status"]), (0, "success"))

    def test_interval_skip_is_skipped_not_success(self):
        self.run_wrapper(["--run"], impl=lambda: 0, states=[{"last_check_at": "a"}, {"last_check_at": "a"}])
        self.assertEqual(self.last()["status"], "skipped")
        self.assertEqual(rl.success_count(rl.read_runs(), system="teiki"), 0)

    def test_maintenance_is_partial(self):
        self.run_wrapper(["--run"], impl=lambda: 0,
                         states=[{"last_check_at": "a"}, {"last_check_at": "b", "site_status": "maintenance"}])
        self.assertEqual(self.last()["status"], "partial")

    def test_nonzero_exit_is_failed_and_returned(self):
        rc = self.run_wrapper(["--run"], impl=lambda: 3, states=[{}, {}])
        self.assertEqual((rc, self.last()["status"]), (3, "failed"))

    def test_status_only_and_dry_run_are_not_applicable_and_not_counted(self):
        self.run_wrapper([], impl=lambda: 0, states=[{}, {}])
        self.run_wrapper(["--run", "--dry-run"], impl=lambda: 0, states=[{}, {}])
        self.assertEqual(rl.success_count(rl.read_runs()), 0)
        self.assertEqual(self.last()["status"], "not_applicable")

    def test_exception_is_recorded_and_reraised(self):
        def boom():
            raise RuntimeError("x")

        with self.assertRaises(RuntimeError):
            self.run_wrapper(["--run"], impl=boom, states=[{}])
        self.assertEqual(self.last()["error_code"], "unexpected_error")

    def test_global_stop_is_honored_by_body(self):
        os.environ["JARVIS_614_GLOBAL_STOP"] = "1"
        with mock.patch.object(tb, "load_env", lambda p: {}), \
                mock.patch.object(sys, "argv", ["x", "--run", "--force"]):
            self.assertEqual(tb.main(), 0)  # 本体は無効化として何もせず終わる
        self.assertEqual(self.last()["status"], "skipped")


if __name__ == "__main__":
    unittest.main()
