import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ai_usage_cli as c

NOW = 1795220000.0


def ev(ts, limit_id, primary, secondary):
    return json.dumps({"timestamp": ts, "payload": {"rate_limits": {
        "limit_id": limit_id, "primary": primary, "secondary": secondary}}})


class CodexTests(unittest.TestCase):
    def test_skips_null_premium_event_and_uses_codex_window(self):
        lines = [
            ev("2026-11-21T01:00:00Z", "codex", {"used_percent": 60.0, "resets_at": NOW + 3600},
               {"used_percent": 98.0, "resets_at": NOW + 99999}),
            ev("2026-11-21T02:00:00Z", "premium", None, None),  # 後ろにある空の枠は無視
        ]
        best, err = c.pick_codex([(lines, NOW)], NOW)
        self.assertEqual(best[0]["primary"]["used_percent"], 60.0)
        self.assertIsNone(err)

    def test_usage_limit_error_detected(self):
        lines = [json.dumps({"timestamp": "2026-11-21T03:00:00Z",
                             "msg": "hit your usage limit. try again at 2:20 AM."})]
        best, err = c.pick_codex([(lines, NOW)], NOW)
        self.assertIsNone(best)
        self.assertEqual(err["retry"], "2:20 AM")

    def test_no_none_percent_text(self):
        out = {"codex": {"five_hour": {"used_percent": None, "resets_at_ts": None},
                         "weekly": {"used_percent": None, "resets_at_ts": None}, "age_min": 5}}
        text = c.render(out, NOW)
        self.assertNotIn("None", text)
        self.assertIn("読めない", text)


class DisplayTests(unittest.TestCase):
    def test_stale_marked_unusable(self):
        w = {"used_percent": 10, "resets_at_ts": NOW + 100}
        t = c.line_text("claude", [("5時間枠", w)], NOW, 3285)
        self.assertIn("古い", t)
        self.assertIn("割り振りに使えない", t)

    def test_limited_and_recovered(self):
        self.assertIn("制限中", c.window_text("週枠", {"used_percent": 100, "resets_at_ts": NOW + 100}, NOW, 1))
        self.assertIn("回復済み", c.window_text("週枠", {"used_percent": 100, "resets_at_ts": NOW - 100}, NOW, 1))

    def test_cursor_parse(self):
        r = c.parse_cursor({"billingCycleEnd": "1796537629000", "planUsage": {"totalPercentUsed": 100},
                            "displayMessage": "x"})
        self.assertEqual(r["used_percent"], 100)
        self.assertEqual(r["resets_at_ts"], 1796537629)



class CursorTokenExpiryTest(unittest.TestCase):
    @staticmethod
    def _jwt(exp):
        import base64
        b = lambda o: base64.urlsafe_b64encode(json.dumps(o).encode()).decode().rstrip("=")
        return f"{b({'alg': 'none'})}.{b({'exp': exp})}.sig"

    def test_fresh_token_not_expiring(self):
        self.assertFalse(c._cursor_token_expiring(self._jwt(2000), now=1000))

    def test_near_expiry_is_expiring(self):
        self.assertTrue(c._cursor_token_expiring(self._jwt(1100), now=1000))

    def test_expired_is_expiring(self):
        self.assertTrue(c._cursor_token_expiring(self._jwt(900), now=1000))

    def test_unreadable_token_is_expiring(self):
        self.assertTrue(c._cursor_token_expiring("opaque-token", now=1000))

if __name__ == "__main__":
    unittest.main()
