import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jarvis_agent_stage_review as s

JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 21, 9, 0, tzinfo=JST)
CFG = s.load_cfg()


def wk(*sigs, runs=7):
    days = ["2026-11-21", "2026-11-14", "2026-11-07", "2026-10-31", "2026-10-24"]
    return [{"day": days[i], "signal": x, "why": "回っている" if x == "🟢" else "x", "runs": runs, "items": 3}
            for i, x in enumerate(sigs)]


AGENTS = [
    {"id": "114", "name": "物件一次判定係", "status": "運用確認"},
    {"id": "311", "name": "送信前品質係", "status": "運用確認"},
    {"id": "814", "name": "UI点検係", "status": "設計中"},
    {"id": "615", "name": "為替見張り係", "status": "設計中"},
    {"id": "900", "name": "定常係", "status": "運用"},
]


def dec(emp, action, days_ago=1, surface="triage", **pl):
    return {"id": hash((emp, action, days_ago)) % 10000, "employee": emp, "action": action, "surface": surface,
            "decided_at": (NOW - timedelta(days=days_ago)).isoformat(), "note": pl.pop("note", None), "payload": pl}


class ProposeTests(unittest.TestCase):
    def run_(self, hist, decisions=()):
        return s.build(AGENTS, hist, list(decisions), CFG, NOW)

    def test_promote_after_two_green_weeks(self):
        rep = self.run_({"114": wk("🟢", "🟢"), "311": wk("🟡", "🟢")})
        keys = [p["key"] for p in rep["proposals"]]
        self.assertIn("114:運用確認>運用", keys)
        self.assertNotIn("311:運用確認>運用", keys)
        w = {p["key"]: p for p in rep["watch"]}
        self.assertIn("🟢 が 0/2 週", w["311:運用確認>運用"]["blockers"][0])

    def test_one_week_is_not_enough(self):
        rep = self.run_({"114": wk("🟢")})
        self.assertEqual([p for p in rep["proposals"] if p["id"] == "114"], [])

    def test_owner_ng_rate_blocks(self):
        ds = [dec("114", "skipped", i) for i in range(4)] + [dec("114", "sent", i) for i in range(3)]
        rep = self.run_({"114": wk("🟢", "🟢")}, ds)
        w = {p["key"]: p for p in rep["watch"]}
        self.assertIn("意図とずれ", w["114:運用確認>運用"]["blockers"][-1])

    def test_red_in_window_blocks(self):
        rep = self.run_({"114": wk("🟢", "🟢", "🔴")})
        self.assertFalse(any(p["id"] == "114" for p in rep["proposals"]))

    def test_design_to_check_when_running(self):
        rep = self.run_({"814": wk("🟢"), "615": wk("⚪", runs=0)})
        keys = [p["key"] for p in rep["proposals"]]
        self.assertIn("814:設計中>運用確認", keys)
        self.assertNotIn("615:設計中>運用確認", keys)

    def test_demote_after_two_red_weeks(self):
        rep = self.run_({"900": wk("🔴", "🔴")})
        p = [x for x in rep["proposals"] if x["id"] == "900"][0]
        self.assertEqual((p["kind"], p["to"]), ("down", "運用確認"))
        self.assertEqual(rep["proposals"][0]["id"], "900")  # 戻す提案を先に

    def test_skip_cooldown_and_defer(self):
        hist = {"114": wk("🟢", "🟢")}
        skipped = dec("114", "skip", 7, surface=s.SURFACE, key="114:運用確認>運用", note="まだ様子見")
        rep = self.run_(hist, [skipped])
        self.assertFalse(any(p["id"] == "114" for p in rep["proposals"]))
        w = {p["key"]: p for p in rep["watch"]}
        self.assertIn("まだ様子見", w["114:運用確認>運用"]["blockers"][0])
        deferred = dec("114", "defer", 7, surface=s.SURFACE, key="114:運用確認>運用")
        self.assertTrue(any(p["id"] == "114" for p in self.run_(hist, [deferred])["proposals"]))
        old = dec("114", "skip", 40, surface=s.SURFACE, key="114:運用確認>運用")
        self.assertTrue(any(p["id"] == "114" for p in self.run_(hist, [old])["proposals"]))

    def test_adopted_waits_for_apply(self):
        ad = dec("114", "adopt", 1, surface=s.SURFACE, key="114:運用確認>運用", agent_id="114", **{"from": "運用確認", "to": "運用"})
        rep = self.run_({"114": wk("🟢", "🟢")}, [ad])
        w = {p["key"]: p for p in rep["watch"]}
        self.assertIn("314 が反映", w["114:運用確認>運用"]["blockers"][0])
        self.assertEqual(len(s.pending_adoptions([ad])), 1)

    def test_slack_lines(self):
        rep = self.run_({"114": wk("🟢", "🟢")})
        lines = s.slack_lines(rep)
        self.assertIn("提案 1 件", lines[0])
        self.assertIn("114", lines[1])


class HistoryTests(unittest.TestCase):
    def test_rows_to_history(self):
        rows = [
            {"entity": "114", "recorded_at": "2026-11-21", "value": 3, "payload": {"signal": "🟢", "runs": 7}},
            {"entity": "114", "recorded_at": "2026-11-14", "value": 3, "payload": {"signal": "🟡", "runs": 4}},
        ]
        h = s.history_from_rows(rows, 6)
        self.assertEqual([x["signal"] for x in h["114"]], ["🟢", "🟡"])


class RegistryTests(unittest.TestCase):
    TEXT = "hub: x\nagents:\n  '114':\n    name: 物件一次判定係\n    status: 運用確認\n    note: a\n  '311':\n    name: 送信前品質係\n    status: 運用確認\ngrok: {}\n"

    def test_set_status_only_in_that_block(self):
        new, ok = s.set_registry_status(self.TEXT, "311", "運用確認", "運用")
        self.assertTrue(ok)
        self.assertIn("  '114':\n    name: 物件一次判定係\n    status: 運用確認", new)
        self.assertIn("  '311':\n    name: 送信前品質係\n    status: 運用", new)

    def test_refuses_when_status_moved(self):
        _, ok = s.set_registry_status(self.TEXT, "311", "設計中", "運用確認")
        self.assertFalse(ok)

    def test_real_registry_parses(self):
        ids = {a["id"] for a in s.load_agents()}
        self.assertIn("311", ids)


class WeeklyReview314StageTests(unittest.TestCase):
    def test_stage_lines_same_day_only(self):
        import json
        import tempfile
        import jarvis_weekly_review_314 as r314

        rep = s.build(AGENTS, {"114": wk("🟢", "🟢")}, [], CFG, NOW)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "latest.json"
            p.write_text(json.dumps(rep, ensure_ascii=False), encoding="utf-8")
            lines = r314.stage_lines("2026-11-21", p)
            self.assertIn("提案 1 件", lines[0])
            self.assertIn("review#stage", lines[-1])
            self.assertEqual(r314.stage_lines("2026-11-28", p), [])


if __name__ == "__main__":
    unittest.main()
