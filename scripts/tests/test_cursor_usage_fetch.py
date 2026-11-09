import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jarvis_cursor_usage_fetch as f

RAW = {
    "summary": {"status": 200, "json": {
        "billingCycleEnd": "2026-12-06T06:13:49.000Z", "membershipType": "pro",
        "individualUsage": {"plan": {"autoPercentUsed": 37.3355, "apiPercentUsed": 1.2,
                                     "totalPercentUsed": 35.61},
                            "onDemand": {"enabled": False}},
        "sessionToken": "SECRET"}},
    "grok": {"status": 200, "json": {"usagePercent": 96.172226,
                                     "nextResetTimestampUtc": "2026-11-14T02:17:05.228Z"}},
}


class CursorFetchTests(unittest.TestCase):
    def test_parse_numbers_only(self):
        v = f.parse_usage(RAW)
        self.assertEqual(v["cursor_models_pct_used"], 37.3)
        self.assertEqual(v["other_models_pct_used"], 1.2)
        self.assertEqual(v["total_pct_used"], 35.6)
        self.assertEqual(v["billing_cycle_end"], "2026-12-06")
        self.assertEqual(v["plan"], "pro")
        self.assertFalse(v["on_demand_enabled"])
        self.assertEqual(v["grok_bot_weekly_pct"], 96.2)
        self.assertTrue(v["grok_bot_resets_at"].startswith("2026-11-14T11:17"))
        self.assertNotIn("SECRET", str(v))

    def test_failure_keeps_manual_values(self):
        manual = {"cursor_models_pct_used": 37.0, "other_models_pct_used": 1.0, "fetch_source": "manual"}
        raw = {"summary": {"status": 401}, "grok": {"status": 401}}
        out = f.apply_to_state(manual, f.parse_usage(raw), f.statuses(raw))
        self.assertEqual(out["cursor_models_pct_used"], 37.0)
        self.assertEqual(out["fetch_source"], "manual")
        self.assertEqual(out["last_fetch_error"]["status"], {"summary": 401, "grok": 401})

    def test_success_marks_auto(self):
        out = f.apply_to_state({"last_fetch_error": {"x": 1}}, f.parse_usage(RAW), f.statuses(RAW))
        self.assertEqual(out["fetch_source"], "auto")
        self.assertNotIn("last_fetch_error", out)

    def test_changed_shape_is_safe(self):
        self.assertEqual(f.parse_usage({"summary": {"status": 200, "json": {"x": 1}}}), {})


if __name__ == "__main__":
    unittest.main()
