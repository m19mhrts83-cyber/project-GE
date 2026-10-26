import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jarvis_ask_usage_summary as usage


class AskUsageSummaryTests(unittest.TestCase):
    def test_ignores_non_usage_and_does_not_copy_text(self):
        events = usage.parse_events([
            'prefix {"event":"ask_usage","engine":"auto","via":"gemini","outcome":"answered","cache_hit":false,"input_chars":12,"elapsed_ms":20,"tokens":null,"cost":null}\n',
            '{"event":"other","prompt":"SECRET"}\n',
            'bad json\n',
        ])
        result = usage.summarize(events)
        self.assertEqual(result["events"], 1)
        self.assertEqual(result["by_via"], {"gemini": 1})
        self.assertEqual(result["measurement"], "tokens_and_cost_unavailable")
        self.assertNotIn("SECRET", str(result))

    def test_reports_known_totals_only_when_complete(self):
        result = usage.summarize([
            {"engine": "auto", "via": "cloud", "outcome": "answered", "tokens": 10, "cost": 0.01},
            {"engine": "auto", "via": "cloud", "outcome": "answered", "tokens": 5, "cost": 0.02},
        ])
        self.assertEqual(result["tokens"], 15)
        self.assertEqual(result["cost"], 0.03)
        self.assertEqual(result["measurement"], "complete")
