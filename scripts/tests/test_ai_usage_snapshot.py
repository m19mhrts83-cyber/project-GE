"""AI 使用量スナップショット（ブラウザ・ネット不要の部分）。"""
import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jarvis_ai_usage_snapshot as s  # noqa: E402

NOW = 1795350000.0
DAY = 86400


def raw(claude_weekly=50, claude_age=5, reset_in_days=2.3, cursor=100):
    return {
        "claude": {"five_hour": {"used_percent": 30, "resets_at_ts": NOW + 3600},
                   "weekly": {"used_percent": claude_weekly, "resets_at_ts": NOW + reset_in_days * DAY},
                   "age_min": claude_age},
        "codex": {"five_hour": {"used_percent": 12, "resets_at_ts": NOW + 3600},
                  "weekly": {"used_percent": 18, "resets_at_ts": NOW + 6 * DAY}, "age_min": 10},
        "cursor": {"monthly": {"used_percent": cursor, "resets_at_ts": NOW + 14 * DAY, "message": "hit"}, "age_min": 0},
        "antigravity": {"error": "RuntimeError: x"},
    }


def verdict(rep, agent):
    return next(v for v in rep["verdicts"] if v["agent"] == agent)


class JudgeTests(unittest.TestCase):
    def test_claude_half_used_midweek_needs_max(self):
        rep = s.build(raw(), {}, NOW)
        v = verdict(rep, "claude")
        self.assertEqual(v["level"], "keep")
        # 4.7日で50% → 7日で約74%、Pro の約3.7倍
        self.assertAlmostEqual(v["pace_percent"], 74.5, delta=1.0)
        self.assertAlmostEqual(v["pro_multiple"], 3.7, delta=0.1)

    def test_claude_low_week_fits_pro(self):
        rep = s.build(raw(claude_weekly=8), {}, NOW)
        self.assertEqual(verdict(rep, "claude")["level"], "ok")

    def test_stale_claude_is_unknown_not_ok(self):
        rep = s.build(raw(claude_weekly=6, claude_age=5514), {}, NOW)
        self.assertEqual(verdict(rep, "claude")["level"], "unknown")

    def test_early_week_has_no_pace(self):
        rep = s.build(raw(claude_weekly=3, reset_in_days=6.8), {}, NOW)
        self.assertIsNone(verdict(rep, "claude")["pace_percent"])

    def test_cursor_limited_is_warn(self):
        self.assertEqual(verdict(s.build(raw(), {}, NOW), "cursor")["level"], "warn")

    def test_streak_counts_closed_low_weeks_only(self):
        hist = {"claude.weekly": [
            {"resets_at_ts": NOW - 15 * DAY, "peak": 60},
            {"resets_at_ts": NOW - 8 * DAY, "peak": 12},
            {"resets_at_ts": NOW - 1 * DAY, "peak": 15},
        ]}
        self.assertEqual(verdict(s.build(raw(), hist, NOW), "claude")["streak_weeks"], 2)

    def test_unreadable_agent_becomes_error_row(self):
        rows = s.normalize(raw(), NOW)
        err = [r for r in rows if r["agent"] == "antigravity"]
        self.assertEqual(err[0]["window"], "error")


class HistoryTests(unittest.TestCase):
    def test_peak_is_kept_and_same_window_merged(self):
        h = s.update_history({}, s.normalize(raw(claude_weekly=50), NOW), NOW)
        h = s.update_history(h, s.normalize(raw(claude_weekly=40), NOW), NOW)  # 低い値では下げない
        h = s.update_history(h, s.normalize(raw(claude_weekly=62), NOW), NOW)
        self.assertEqual(len(h["claude.weekly"]), 1)
        self.assertEqual(h["claude.weekly"][0]["peak"], 62)
        self.assertNotIn("claude.five_hour", h)

    def test_stale_or_passed_value_is_not_recorded(self):
        h = s.update_history({}, s.normalize(raw(claude_age=5514), NOW), NOW)
        self.assertNotIn("claude.weekly", h)
        h = s.update_history({}, s.normalize(raw(reset_in_days=-1), NOW), NOW)
        self.assertNotIn("claude.weekly", h)


class SetClaudeTests(unittest.TestCase):
    def test_written_file_is_read_back_with_model_window(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "claude.json"
            args = argparse.Namespace(weekly=50.0, weekly_reset="2026-11-24T22:00:00Z", five_hour=30.0,
                                      five_hour_reset="2026-11-22T15:20:00Z", model_weekly=30.0, model_label="Fable")
            s.set_claude(args, NOW, p)
            self.assertNotIn("token", json.dumps(json.loads(p.read_text())).lower())
            out = s.read_claude_all(NOW, p)
            self.assertEqual(out["weekly"]["used_percent"], 50.0)
            self.assertEqual(out["extra"][0]["label"], "Fable")
            self.assertEqual(out["age_min"], 0)


if __name__ == "__main__":
    unittest.main()
