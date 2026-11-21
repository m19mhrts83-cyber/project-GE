"""315-B 300番台 停止・空回り監視（scripts/jarvis_stall_watch_315b.py）。

本番へは何も書かない: 保存先は一時フォルダ、画面反映と #ops はモック。
"""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jarvis_freshness_watch as fw  # noqa: E402
import jarvis_stall_watch_315b as sw  # noqa: E402

JST = sw.JST
NOW = datetime(2026, 11, 23, 8, 20, tzinfo=JST)
GATE_DIR = "agent311/output"

CONFIG_TMPL = """
products:
  - id: weekly_review_facts
    label: 314 週次機械チェック
    kind: file_mtime
    glob: w314/facts_*.md
    max_age_h: 200
    owner: 314
    action: kick
stall_watch_315b:
  targets:
    - id: "311"
      label: 311 送信前品質
      owner: "311"
      action: poll を確認
      stop:
        kind: log_last_match
        glob: logs/poll.log
        pattern: '(?m)^======== (\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}:\\d{2}) ========$'
        max_age_h: 1
      idle:
        kind: gate_draft_repeat
        dir: agent311/output
        threshold: 4
        window_min: 60
        lookback_h: 14
    - id: "313"
      label: 313 完了候補確認
      owner: "313"
      action: runner を確認
      stop:
        kind: json_time
        file: st/de.json
        path: at
        max_age_h: 26
      idle:
        kind: candidate_repeat
        file: st/de.json
        extra_file: st/cleanup.json
        runs: 3
    - id: "314"
      label: 314 業務品質監査
      owner: "314"
      action: kick
      stop:
        ref: weekly_review_facts
    - id: "317"
      label: 317 コメント起動
      owner: "317"
      action: dispatch を確認
      stop:
        kind: json_time
        file: st/cd.json
        path: last_run_at
        max_age_h: 2
      idle:
        kind: skip
"""


class Fixture:
    """正常な状態の一時リポ。各テストで壊して使う。"""

    def __init__(self, d: Path):
        self.d = d
        self.config = d / "freshness_slo.yaml"
        self.state = d / "state" / "stall_watch_315b.json"
        self.config.write_text(CONFIG_TMPL, encoding="utf-8")
        for sub in ("logs", GATE_DIR, "st", "w314"):
            (d / sub).mkdir(parents=True, exist_ok=True)
        self.poll(NOW - timedelta(minutes=5))
        self.de(NOW - timedelta(hours=12), ["a", "b"])
        self.cleanup(NOW - timedelta(hours=12), ["c"], total=10)
        (d / "st" / "cd.json").write_text(json.dumps({"last_run_at": (NOW - timedelta(minutes=5)).isoformat()}))
        f = d / "w314" / "facts_20261121.md"
        f.write_text("x")
        t = (NOW - timedelta(hours=40)).timestamp()
        import os

        os.utime(f, (t, t))
        self.posts: list[str] = []
        self.pushes: list[dict] = []
        self.post_ok = True
        self.push_ok = True

    def poll(self, at: datetime):
        (self.d / "logs" / "poll.log").write_text(
            f"======== {at.astimezone(JST):%Y-%m-%d %H:%M:%S} ========\ninbox に処理対象 MD がありません\n", encoding="utf-8"
        )

    def gate(self, at: datetime, draft: str):
        p = self.d / GATE_DIR / f"gate_{at.astimezone(JST):%Y%m%d_%H%M%S}.json"
        p.write_text(json.dumps({"draft_path": draft, "overall": "OK"}), encoding="utf-8")

    def de(self, at: datetime, ids: list[str]):
        (self.d / "st" / "de.json").write_text(
            json.dumps({"at": at.isoformat(), "candidates": [{"n": i, "task_id": x} for i, x in enumerate(ids)]})
        )

    def cleanup(self, at: datetime, ids: list[str], total: int):
        (self.d / "st" / "cleanup.json").write_text(
            json.dumps({"at": at.isoformat(), "total": total, "items": [{"task_id": x} for x in ids]})
        )

    def poster(self, text: str):
        self.posts.append(text)
        return (True, "") if self.post_ok else (False, "投稿失敗 rc=1")

    def pusher(self, payload: dict):
        self.pushes.append(payload)
        return (True, "") if self.push_ok else (False, "反映できない: ConnectionError")

    def run(self, now: datetime = NOW, **kw):
        return sw.run(
            now,
            config_path=self.config,
            state_path=self.state,
            repo=self.d,
            pusher=self.pusher,
            poster=self.poster,
            out=lambda _s: None,
            **kw,
        )


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.fx = Fixture(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def row(self, state, tid):
        return next(r for r in state["rows"] if r["id"] == tid)


class CriteriaTests(Base):
    def test_real_config_targets_are_exactly_300s_and_314_uses_existing_setting(self):
        crit = sw.fetch_criteria(sw.CONFIG)
        ids = [t["id"] for t in crit["targets"]]
        self.assertEqual(ids, ["311", "312", "313", "314", "317"])
        by = {t["id"]: t for t in crit["targets"]}
        self.assertEqual(by["311"]["stop"]["max_age_h"], 1)
        self.assertEqual(by["313"]["stop"]["max_age_h"], 26)
        self.assertEqual(by["317"]["stop"]["max_age_h"], 2)
        self.assertEqual(by["314"]["stop"]["ref"], "weekly_review_facts")
        existing = next(p for p in fw.yaml.safe_load(sw.CONFIG.read_text())["products"] if p["id"] == "weekly_review_facts")
        self.assertEqual(by["314"]["stop"]["max_age_h"], float(existing["max_age_h"]))
        self.assertEqual(by["317"]["idle"]["kind"], "skip")

    def test_existing_freshness_watch_ignores_315b_section(self):
        # 315-A 側（既存の鮮度監視）の対象数が変わらない＝重複通知しない
        cfg = fw.yaml.safe_load(sw.CONFIG.read_text())
        ids = [p["id"] for p in cfg["products"]]
        self.assertNotIn("311", ids)
        self.assertIn("weekly_review_facts", ids)

    def test_unreadable_criteria_is_failure_not_success_and_notifies_once(self):
        self.fx.run()  # 前回: 正常
        self.fx.posts.clear()
        self.fx.config.write_text("stall_watch_315b: [broken", encoding="utf-8")
        rc, st = self.fx.run()
        self.assertEqual((rc, st["result"]), (1, "failure"))
        self.assertEqual(st["rows"], [])
        self.assertEqual(len(self.fx.posts), 1)
        self.assertIn("315-B 監視そのもの", self.fx.posts[0])
        self.assertNotIn("回復", self.fx.posts[0])  # 対象を回復扱いにしない
        rc, st = self.fx.run()
        self.assertEqual(len(self.fx.posts), 1)  # 同じ障害は 1 回だけ

    def test_missing_section_and_bad_ref_are_criteria_errors(self):
        self.fx.config.write_text("products: []\n", encoding="utf-8")
        with self.assertRaises(sw.CriteriaError):
            sw.fetch_criteria(self.fx.config)
        self.fx.config.write_text(CONFIG_TMPL.replace("ref: weekly_review_facts", "ref: nope"), encoding="utf-8")
        with self.assertRaises(sw.CriteriaError):
            sw.fetch_criteria(self.fx.config)
        self.fx.config.write_text(CONFIG_TMPL.replace("        max_age_h: 26\n", ""), encoding="utf-8")
        with self.assertRaises(sw.CriteriaError):
            sw.fetch_criteria(self.fx.config)


class StopTests(Base):
    def test_all_fresh_is_success_and_silent(self):
        rc, st = self.fx.run()
        self.assertEqual((rc, st["result"]), (0, "success"))
        self.assertEqual({r["status"] for r in st["rows"]}, {"ok"})
        self.assertEqual(self.fx.posts, [])
        self.assertTrue(st["save"]["ok"])
        self.assertTrue(st["dashboard"]["ok"])

    def test_311_without_requests_is_not_stalled_while_poll_is_alive(self):
        # gate_*.json が 1 件もなくても、定時実行が回っていれば正常
        rc, st = self.fx.run()
        self.assertEqual(self.row(st, "311")["status"], "ok")

    def test_311_poll_stopped_over_1h_is_stale(self):
        self.fx.poll(NOW - timedelta(hours=2))
        _, st = self.fx.run()
        self.assertEqual(self.row(st, "311")["status"], "stale")
        self.assertIn("311 送信前品質: 遅れ", self.fx.posts[0])

    def test_313_and_317_limits(self):
        self.fx.de(NOW - timedelta(hours=27), ["a"])
        (self.fx.d / "st" / "cd.json").write_text(json.dumps({"last_run_at": (NOW - timedelta(hours=3)).isoformat()}))
        _, st = self.fx.run()
        self.assertEqual(self.row(st, "313")["status"], "stale")
        self.assertEqual(self.row(st, "317")["status"], "stale")

    def test_missing_file_is_unknown_and_partial(self):
        (self.fx.d / "st" / "cd.json").unlink()
        rc, st = self.fx.run()
        r = self.row(st, "317")
        self.assertEqual(r["status"], "unknown")
        self.assertTrue(r["missing"])
        self.assertEqual((rc, st["result"]), (2, "partial"))
        self.assertIn("🟡 317 コメント起動: 読取不可", self.fx.posts[0])

    def test_corrupt_json_is_unknown(self):
        (self.fx.d / "st" / "cd.json").write_text("{not json")
        _, st = self.fx.run()
        self.assertEqual(self.row(st, "317")["status"], "unknown")


class Idle311Tests(Base):
    DRAFT = "/x/partners/P000_sample/4.送信下書き.txt"

    def test_same_draft_4_times_in_1h_is_idle(self):
        for m in (0, 15, 30, 45):
            self.fx.gate(NOW - timedelta(hours=3) + timedelta(minutes=m), self.DRAFT)
        _, st = self.fx.run()
        r = self.row(st, "311")
        self.assertEqual(r["status"], "idle")
        self.assertIn("4 回", r["why"])
        self.assertIn("P000_sample/4.送信下書き.txt", r["why"])
        self.assertNotIn("/x/partners", self.fx.posts[0])  # 通知はフォルダ名＋ファイル名だけ

    def test_3_times_or_spread_over_2h_is_not_idle(self):
        for m in (0, 15, 30):
            self.fx.gate(NOW - timedelta(hours=3) + timedelta(minutes=m), self.DRAFT)
        self.fx.gate(NOW - timedelta(hours=1), self.DRAFT)
        _, st = self.fx.run()
        self.assertEqual(self.row(st, "311")["status"], "ok")

    def test_different_drafts_do_not_add_up(self):
        for i, m in enumerate((0, 10, 20, 30)):
            self.fx.gate(NOW - timedelta(hours=2) + timedelta(minutes=m), f"/x/P00{i}/draft.txt")
        _, st = self.fx.run()
        self.assertEqual(self.row(st, "311")["status"], "ok")

    def test_old_burst_outside_lookback_recovers(self):
        for m in (0, 10, 20, 30):
            self.fx.gate(NOW - timedelta(hours=3) + timedelta(minutes=m), self.DRAFT)
        self.fx.run()
        self.assertEqual(len(self.fx.posts), 1)
        _, st = self.fx.run(NOW + timedelta(hours=14))
        self.fx.poll(NOW + timedelta(hours=14))
        _, st = self.fx.run(NOW + timedelta(hours=14))
        self.assertEqual(self.row(st, "311")["status"], "ok")
        self.assertTrue(any("🟢 回復 311" in p for p in self.fx.posts))


class Idle313Tests(Base):
    def _three_runs(self, sets, totals):
        st = None
        for i, (ids, total) in enumerate(zip(sets, totals)):
            at = NOW - timedelta(days=3 - i)
            self.fx.de(at, ids)
            self.fx.cleanup(at, ["c"], total)
            _, st = self.fx.run(at + timedelta(hours=12, minutes=20))
        return st

    def test_same_candidates_3_runs_without_progress_is_idle(self):
        st = self._three_runs([["a", "b"]] * 3, [10, 10, 11])
        r = self.row(st, "313")
        self.assertEqual(r["status"], "idle")
        self.assertIn("3 回連続", r["why"])
        self.assertEqual(sum("313 完了候補確認: 空回り" in p for p in self.fx.posts), 1)

    def test_progress_or_changed_candidates_is_not_idle(self):
        st = self._three_runs([["a", "b"]] * 3, [10, 9, 9])
        self.assertEqual(self.row(st, "313")["status"], "ok")
        self.fx.state.unlink()
        st = self._three_runs([["a"], ["a", "b"], ["a", "b"]], [10, 10, 10])
        self.assertEqual(self.row(st, "313")["status"], "ok")

    def test_two_checks_per_313_run_count_once(self):
        at = NOW - timedelta(hours=12)
        self.fx.de(at, ["a"])
        self.fx.run()
        self.fx.run(NOW + timedelta(hours=10))
        _, st = self.fx.run(NOW + timedelta(hours=10, minutes=1))
        self.assertEqual(len(st["idle_history"]["313"]), 1)

    def test_cleanup_from_other_run_is_not_mixed_in(self):
        self.fx.cleanup(NOW - timedelta(days=5), ["old"], total=3)
        _, st = self.fx.run()
        self.assertEqual(st["idle_history"]["313"][-1]["n"], 2)
        self.assertIsNone(st["idle_history"]["313"][-1]["total"])


class NotifyTests(Base):
    def test_continuing_abnormal_posts_once_and_recovery_once(self):
        self.fx.poll(NOW - timedelta(hours=3))
        self.fx.run()
        self.fx.run(NOW + timedelta(minutes=1))
        self.fx.run(NOW + timedelta(minutes=2))
        self.assertEqual(len(self.fx.posts), 1)
        self.fx.poll(NOW + timedelta(minutes=3))
        _, st = self.fx.run(NOW + timedelta(minutes=4))
        self.fx.run(NOW + timedelta(minutes=5))
        self.assertEqual(len(self.fx.posts), 2)
        self.assertIn("🟢 回復 311 送信前品質（遅れ→正常）", self.fx.posts[1])
        self.assertEqual(st["notified"]["311"]["status"], "ok")

    def test_failed_post_is_not_marked_and_resent_next_time(self):
        self.fx.poll(NOW - timedelta(hours=3))
        self.fx.post_ok = False
        rc, st = self.fx.run()
        self.assertEqual((rc, st["result"]), (2, "partial"))
        self.assertNotIn("311", st["notified"])
        self.assertEqual([c["id"] for c in st["pending"]], ["311"])
        saved = json.loads(self.fx.state.read_text())
        self.assertEqual(saved["notify"]["ok"], False)
        self.fx.post_ok = True
        rc, st = self.fx.run(NOW + timedelta(minutes=1))
        self.assertEqual(len(self.fx.posts), 2)
        self.assertEqual(st["notified"]["311"]["status"], "stale")
        self.assertEqual(st["pending"], [])
        self.fx.run(NOW + timedelta(minutes=2))
        self.assertEqual(len(self.fx.posts), 2)

    def test_status_change_between_abnormals_is_new(self):
        self.fx.poll(NOW - timedelta(hours=3))
        self.fx.run()
        (self.fx.d / "logs" / "poll.log").unlink()
        _, st = self.fx.run(NOW + timedelta(minutes=1))
        self.assertEqual(self.row(st, "311")["status"], "unknown")
        self.assertEqual(len(self.fx.posts), 2)

    def test_without_post_flag_keeps_pending(self):
        self.fx.poll(NOW - timedelta(hours=3))
        rc, st = sw.run(NOW, config_path=self.fx.config, state_path=self.fx.state, repo=self.fx.d,
                        pusher=self.fx.pusher, poster=None, out=lambda _s: None)
        self.assertEqual(st["result"], "partial")
        self.assertNotIn("311", st["notified"])

    def test_dry_run_writes_nothing(self):
        self.fx.poll(NOW - timedelta(hours=3))
        rc, st = self.fx.run(dry_run=True)
        self.assertEqual(rc, 0)
        self.assertFalse(self.fx.state.exists())
        self.assertEqual((self.fx.posts, self.fx.pushes), ([], []))


class ResultTests(Base):
    def test_dashboard_failure_is_partial_and_recorded_separately_from_save(self):
        self.fx.push_ok = False
        rc, st = self.fx.run()
        self.assertEqual((rc, st["result"]), (2, "partial"))
        saved = json.loads(self.fx.state.read_text())
        self.assertTrue(saved["save"]["ok"])
        self.assertFalse(saved["dashboard"]["ok"])
        self.assertEqual(saved["run_id"], saved["dashboard"]["run_id"])

    def test_dashboard_gets_rows_and_save_result(self):
        self.fx.run()
        p = self.fx.pushes[0]
        self.assertEqual([r["id"] for r in p["rows"]], ["311", "313", "314", "317"])
        self.assertTrue(p["save"]["ok"])
        self.assertNotIn("action", p["rows"][0])

    def test_save_failure_is_failure_and_reported(self):
        self.fx.state.parent.mkdir(parents=True, exist_ok=True)
        self.fx.state.mkdir()  # ファイルの代わりにフォルダ → 書けない
        rc, st = self.fx.run()
        self.assertEqual((rc, st["result"]), (1, "failure"))
        self.assertFalse(st["save"]["ok"])
        self.assertIn("315-B 監視そのもの", self.fx.posts[0])

    def test_corrupt_previous_state_is_partial_not_silent(self):
        self.fx.state.parent.mkdir(parents=True, exist_ok=True)
        self.fx.state.write_text("{broken")
        rc, st = self.fx.run()
        self.assertEqual(st["result"], "partial")
        self.assertTrue(any("前回状態を読めない" in w for w in st["result_why"]))

    def test_save_failure_after_monitor_failure_does_not_claim_recovery(self):
        self.fx.config.write_text("broken: [", encoding="utf-8")
        self.fx.run()  # 監視そのもの: 読取不可を通知済み
        self.fx.config.write_text(CONFIG_TMPL, encoding="utf-8")
        self.fx.state.unlink()
        self.fx.state.mkdir()  # 今回は保存できない（前回状態も読めない）
        self.fx.posts.clear()
        _, st = self.fx.run(NOW + timedelta(minutes=1))
        self.assertEqual(st["result"], "failure")
        self.assertNotIn("回復", "".join(self.fx.posts))

    def test_dashboard_payload_has_no_secret_like_fields(self):
        self.fx.run()
        keys = set(self.fx.pushes[0])
        self.assertEqual(keys, {"run_id", "checked_at", "result", "result_why", "save", "rows", "notified", "pending"})


if __name__ == "__main__":
    unittest.main()
