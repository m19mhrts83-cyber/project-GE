import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jarvis_ai_usage_weekly as u

SINCE = datetime(2026, 11, 1, tzinfo=timezone.utc)
UNTIL = datetime(2026, 11, 8, tzinfo=timezone.utc)


def asst(mid, ts, out, model="claude-opus-5-5", sid="s1"):
    return {"type": "assistant", "timestamp": ts, "sessionId": sid, "entrypoint": "cli",
            "message": {"id": mid, "model": model, "content": [{"type": "text", "text": "SECRET"}],
                        "usage": {"input_tokens": 1, "output_tokens": out,
                                  "cache_creation_input_tokens": 10, "cache_read_input_tokens": 100}}}


def tc(ts, total, last, rl=None):
    return {"type": "event_msg", "timestamp": ts, "payload": {"type": "token_count", "info": {
        "total_token_usage": {"input_tokens": total, "output_tokens": 0, "total_tokens": total},
        "last_token_usage": {"input_tokens": last, "output_tokens": 0, "total_tokens": last}},
        "rate_limits": rl}}


class ClaudeTests(unittest.TestCase):
    def test_dedupes_split_messages_and_window(self):
        recs = [
            asst("m1", "2026-11-02T00:00:00Z", 50),
            asst("m1", "2026-11-02T00:00:01Z", 50),  # 同じ応答の分割行
            asst("m2", "2026-11-03T00:00:00Z", 20, model="claude-sonnet-5-5", sid="s2"),
            asst("m3", "2026-10-20T00:00:00Z", 999),  # 窓の外
        ]
        r = u.summarize_claude(recs, SINCE, UNTIL)
        self.assertEqual(r["requests"], 2)
        self.assertEqual(r["sessions"], 2)
        self.assertEqual(r["tokens"]["output"], 70)
        self.assertNotIn("SECRET", str(r))

    def test_limit_hits_from_api_error_and_synthetic(self):
        recs = [
            {"type": "assistant", "timestamp": "2026-11-02T10:00:00Z", "apiError": "usage_limit_reached",
             "apiErrorParams": {"rate_limit_info": {"rateLimitType": "seven_day", "resetsAt": 1793743200}},
             "message": {"model": "<synthetic>", "content": [{"type": "text", "text": "You've hit your weekly limit"}]}},
            {"type": "assistant", "timestamp": "2026-11-04T14:30:00Z",
             "message": {"model": "<synthetic>", "content": [{"type": "text", "text": "You've hit your 5-hour limit"}],
                         "usage": {"output_tokens": 0}}},
        ]
        r = u.summarize_claude(recs, SINCE, UNTIL)
        self.assertEqual([h["type"] for h in r["limit_hits"]], ["seven_day", "five_hour"])
        self.assertEqual(r["requests"], 0)


class CodexTests(unittest.TestCase):
    def test_cumulative_deltas_only_inside_window(self):
        rl = {"limit_id": "codex", "plan_type": "plus",
              "primary": {"used_percent": 30.0, "window_minutes": 300, "resets_at": 1793031475},
              "secondary": {"used_percent": 60.0, "window_minutes": 10080, "resets_at": 1793618275}}
        recs = [
            tc("2026-10-31T00:00:00Z", 100, 100),        # 窓の外（基準になる）
            tc("2026-11-02T00:00:00Z", 150, 50, rl),
            tc("2026-11-02T00:01:00Z", 150, 50),         # 重複（差分0）
            tc("2026-11-03T00:00:00Z", 30, 30),          # 累計が戻った → last を使う
        ]
        s = u.summarize_codex_session(recs, SINCE, UNTIL)
        self.assertEqual(s["tokens"]["total_tokens"], 80)
        self.assertEqual(s["turns"], 2)
        lim = u.summarize_codex_limits(s["limits"])
        self.assertEqual(lim["limits_latest"]["weekly"]["used_pct"], 60.0)
        self.assertEqual(lim["plan_type"], "plus")


class ManualTests(unittest.TestCase):
    def test_manual_and_rows(self):
        with tempfile.TemporaryDirectory() as d:
            u.MANUAL_PATH = Path(d) / "m.json"
            u.CURSOR_PATH = Path(d) / "none.json"
            u.CLAUDE_DIRS = [Path(d) / "c"]
            u.CODEX_DIRS = [Path(d) / "x"]
            u.set_manual("gencode", 95, "目視")
            rep = u.build_report(7, now=UNTIL)
            rows = {r["tool"]: r for r in rep["rows"]}
            self.assertEqual(rows["GenCode（フライデー）"]["level"], "attention")
            self.assertFalse(rep["tools"]["claude_code"]["available"])
            self.assertFalse(rep["llm_used"])
            self.assertIn("| ツール |", u.render_md(rep))
            mrows = u.metric_rows(rep)
            self.assertEqual([(r["metric"], r["entity"], r["value"]) for r in mrows],
                             [("ai_usage_weekly_pct", "gencode", 95.0)])
            self.assertEqual(mrows[0]["recorded_at"], rep["period"]["until"][:10])


if __name__ == "__main__":
    unittest.main()
