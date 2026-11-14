import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jarvis_agent_weekly_activity as w

JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 14, 9, 0, tzinfo=JST)
SINCE = NOW - timedelta(days=7)

POLL = """======== 2026-11-06 07:40:00 ========
--- inbox: old.md
overall=OK
inbox_done count=1 worst_exit=0
======== 2026-11-13 07:40:25 ========
--- inbox: a.md
overall=OK
inbox_done count=1 worst_exit=0
======== 2026-11-13 07:55:25 ========
inbox に処理対象 MD がありません
======== 2026-11-13 08:10:25 ========
inbox_done count=1 worst_exit=1
======== 2026-11-13 08:25:25 ========
--- inbox: b.md
overall=NG
inbox_done count=1 worst_exit=10
"""

SPEC_311 = {
    "header_regex": r"^======== (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) ========",
    "items_regex": r"^overall=(?:OK|NG)",
    "retry_regex": r"worst_exit=[1-9]",
    "ok_regex": r"^overall=OK",
    "ng_regex": r"^overall=NG",
    "fail_regex": r"^❌|Traceback",
}


class LogBlockTests(unittest.TestCase):
    def test_counts_runs_work_and_retries_in_window(self):
        r = w.count_log_blocks(POLL, SPEC_311, SINCE, NOW)
        self.assertEqual(r["runs"], 4)  # 11/06 は窓の外
        self.assertEqual(r["worked"], 2)
        self.assertEqual(r["items"], 2)
        self.assertEqual((r["ok"], r["ng"]), (1, 1))
        # 処理できずに持ち越した回だけ（NG で worst_exit=10 の回は数えない）
        self.assertEqual(r["retries"], 1)


class StampedFileTests(unittest.TestCase):
    def test_items_and_fail_from_per_run_files(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "gate114_20261113_111505.log").write_text('KURASHIFT_RESULT:{"ok": true, "count": 162}')
            (p / "gate114_20261112_111505.log").write_text("Traceback (most recent call last)")
            (p / "gate114_20261101_111505.log").write_text('KURASHIFT_RESULT:{"ok": true, "count": 9}')
            r = w.count_stamped_files(
                sorted(p.iterdir()), r"gate114_(\d{8}_\d{6})\.log$", SINCE, NOW,
                r'KURASHIFT_RESULT:\{"ok": true, "count": (\d+)', "Traceback")
        self.assertEqual((r["runs"], r["worked"], r["items"], r["fail"]), (2, 1, 162, 1))


class GhaTests(unittest.TestCase):
    def test_counts_success_and_failure_skips_cancelled(self):
        runs = [
            {"workflowName": "X", "conclusion": "success", "createdAt": "2026-11-12T02:50:00Z", "status": "completed"},
            {"workflowName": "X", "conclusion": "failure", "createdAt": "2026-11-13T02:50:00Z", "status": "completed"},
            {"workflowName": "X", "conclusion": "cancelled", "createdAt": "2026-11-13T03:50:00Z", "status": "completed"},
            {"workflowName": "Y", "conclusion": "success", "createdAt": "2026-11-13T02:50:00Z", "status": "completed"},
            {"workflowName": "X", "conclusion": "success", "createdAt": "2026-11-01T02:50:00Z", "status": "completed"},
        ]
        r = w.count_gha(runs, ["X"], SINCE, NOW)
        self.assertEqual((r["runs"], r["worked"], r["fail"]), (2, 1, 1))


class SlackTests(unittest.TestCase):
    BOTS = {"s9": {"code": "S9"}, "hawk": {"code": "H", "slack_regex": "ホーク"}}

    def test_attribution_by_first_line(self):
        ids = {"311", "211", "114", "516"}
        self.assertEqual(w.attribute_slack({"text": "📎 311 送信前品質ゲート\n判定: 🟢"}, ids, self.BOTS), ["311"])
        self.assertEqual(w.attribute_slack({"text": "【114・物件一次判定】C レーン（2026-11-14・146件）"}, ids, self.BOTS), ["114"])
        self.assertEqual(w.attribute_slack({"text": "[516 業者開拓フォロー] 見守り"}, ids, self.BOTS), ["516"])
        # 日付や金額は社員番号にしない
        self.assertEqual(w.attribute_slack({"text": "【日次】11/14\n判定: 🟢"}, ids, self.BOTS), [])
        self.assertEqual(w.attribute_slack({"text": "瀬戸市 470万 211件"}, ids, self.BOTS), [])
        self.assertEqual(w.attribute_slack({"text": "【報告】S9 管理会社開拓・候補取り込み"}, ids, self.BOTS), ["grok:s9"])
        self.assertEqual(w.attribute_slack({"text": "x", "username": "ホークアイ（参謀）"}, ids, self.BOTS), ["grok:hawk"])

    def test_signal_parsing(self):
        self.assertEqual(w.slack_signal("題\n判定: :large_green_circle: 回っています"), "🟢")
        self.assertEqual(w.slack_signal("題\n判定: 🔴 要対応"), "🔴")
        self.assertIsNone(w.slack_signal("題だけ"))


class GrokMailTests(unittest.TestCase):
    def test_kinds_and_outcomes(self):
        bot = {"subjects": {"調査": r"^\[Grok調査\]"}, "outcomes": {"聞く": "聞く", "保留": "保留", "見送り": "見送り"}}
        mails = [
            {"subject": "[Grok調査] 瀬戸市 470万（RC2階・ハザード色なし・聞く・📌今日一番）", "at": "2026-11-13T10:41:24+09:00"},
            {"subject": "[Grok調査] 津島市 200万（駐車なし・聞く（2番手））", "at": "2026-11-13T10:41:36+09:00"},
            {"subject": "[Grok調査] 稲沢市 485万（洪水・見送り）", "at": "2026-11-13T10:41:45+09:00"},
            {"subject": "[Grok部長] 日報 2026-11-13", "at": "2026-11-13T09:00:00+09:00"},
            {"subject": "[Grok調査] 古い", "at": "2026-11-01T09:00:00+09:00"},
        ]
        r = w.count_grok_mail(mails, bot, SINCE, NOW)
        self.assertEqual(r["kinds"], {"調査": 3})
        self.assertEqual(r["outcomes"], {"聞く": 2, "見送り": 1})


class JudgeTests(unittest.TestCase):
    def row(self, **kw):
        r = w.empty_row()
        r.update(kw)
        return r

    def test_signals(self):
        self.assertEqual(w.judge(self.row(), 7, False)[0], "⚪")
        self.assertEqual(w.judge(self.row(runs=0), 7, True)[0], "🔴")
        self.assertEqual(w.judge(self.row(runs=0), None, True)[0], "⚪")
        self.assertEqual(w.judge(self.row(), 7, True, measured=False)[0], "⚪")
        self.assertEqual(w.judge(self.row(runs=2, fail=2), 1, True)[0], "🔴")
        self.assertEqual(w.judge(self.row(runs=7, worked=7, retries=3), 7, True)[0], "🟡")
        self.assertEqual(w.judge(self.row(runs=3, worked=3), 7, True)[0], "🟡")
        self.assertEqual(w.judge(self.row(runs=7, worked=7, items=5), 7, True)[0], "🟢")
        sig, why = w.judge(self.row(runs=600, worked=0, items=0), 672, True)
        self.assertEqual(sig, "🟢")
        self.assertIn("空振り", why)


class ReportTests(unittest.TestCase):
    def test_build_report_end_to_end(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            logs = root / "Logs"
            (logs / "g").mkdir(parents=True)
            (logs / "g" / "poll.log").write_text(POLL, encoding="utf-8")
            out = root / "repo" / "out"
            out.mkdir(parents=True)
            (out / "gate_20261113_074025.json").write_text(json.dumps({"overall": "OK"}))
            (out / "gate_20261113_082525.json").write_text(json.dumps({"overall": "NG"}))
            (out / "gate_20261113_090000.json").write_text(json.dumps({"overall": "OK"}))
            cfg = {
                "agents": {
                    "311": {"log_blocks": {"path": "g/poll.log", **SPEC_311},
                            "output_files": {"glob": "out/gate_*.json", "pattern": r"gate_(\d{8}_\d{6})\.json$"},
                            "expected_per_week": 4},
                    "211": {"gha": {"workflows": ["jarvis-reply-draft-211.yml"]}, "expected_per_week": 7,
                            "slack_items_regex": r"起案:\s*(\d+)"},
                },
                "grok": {"bots": {"s1": {"name": "S1", "code": "S1", "subjects": {"調査": r"^\[Grok調査\]"},
                                         "expected": {"調査": 7}}}},
            }
            gha = [{"workflowName": "Jarvis Reply Draft 211 Morning", "conclusion": "success",
                    "createdAt": f"2026-11-{d:02d}T22:30:00Z", "status": "completed"} for d in range(7, 14)]
            slack = [{"ts": str(NOW.timestamp() - 3600), "text": "【報告】211 返信案内下書き・朝便\n判定: 🟢 回っています\n・起案: 1"}]
            mails = [{"subject": "[Grok調査] A（聞く）", "at": "2026-11-13T10:00:00+09:00"}]
            rep = w.build_report(cfg, NOW, gha_runs=gha, slack_msgs=slack, grok_mails=mails, errors=[],
                                 log_root=logs, repo=root / "repo")
        a = {r["id"]: r for r in rep["agents"]}
        self.assertEqual(a["311"]["items"], 3)  # 成果物ファイルで数え直す（経路B も入る）
        self.assertEqual((a["311"]["ok"], a["311"]["ng"]), (2, 1))
        self.assertEqual(a["311"]["signal"], "🟡")  # 再試行（詰まり）あり
        self.assertEqual(a["211"]["runs"], 7)
        self.assertEqual(a["211"]["items"], 1)
        self.assertEqual(a["211"]["slack_signals"], {"🟢": 1})
        self.assertEqual(a["211"]["signal"], "🟢")
        g = {r["id"]: r for r in rep["grok"]}
        self.assertEqual(g["grok:s1"]["runs"], 1)
        self.assertEqual(g["grok:s1"]["signal"], "🟡")  # 1/7
        self.assertTrue(any(x["id"] == "311" for x in rep["attention"]))
        rows = w.metric_rows(rep)
        self.assertTrue(all(r["metric"] == "agent_weekly_activity" for r in rows))
        self.assertIn("稼働: 機能した社員", w.slack_lines(rep)[0])


class WeeklyReview314Tests(unittest.TestCase):
    def test_activity_lines_only_for_same_day(self):
        import jarvis_weekly_review_314 as r314

        rep = {"until": "2026-11-14T09:00:00+09:00", "summary": {"🟢": 3, "🟡": 1, "🔴": 0, "⚪": 2},
               "worked_agents": 4, "total_agents": 6,
               "attention": [{"id": "311", "name": "送信前品質係", "signal": "🟡", "why": "処理できず再試行 3 回（詰まり）"}]}
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "latest.json"
            p.write_text(json.dumps(rep, ensure_ascii=False), encoding="utf-8")
            lines = r314.activity_lines("2026-11-14", p)
            self.assertIn("機能した社員 4/6", lines[0])
            self.assertTrue(any("311" in x for x in lines))
            self.assertEqual(r314.activity_lines("2026-11-21", p), [])
        facts = {"flags": [], "commits": {"count": 1}, "activity": lines}
        self.assertIn("機能した社員", r314.slack_text(facts))


if __name__ == "__main__":
    unittest.main()
