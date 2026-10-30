#!/usr/bin/env python3
"""天気お知らせの Slack レイアウト（ネットワーク不要）。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import jarvis_grok_slack_report_apply as g  # noqa: E402


class WeatherLayoutTests(unittest.TestCase):
    def test_weather_splits_parts_and_short_header(self):
        body = (
            "• 今日の天気: 晴のち曇（豊明）· 最高22℃/最低8℃ · 降水確率 10〜30%\n"
            "• 予定: なし"
        )
        meta = {"bot": "天気お知らせ", "title": "朝の天気と予定 10/29", "channel": "report"}
        text = g.build_text(meta, body, "x.md")
        self.assertTrue(text.startswith("【Grok定型報告】天気お知らせ\n"))
        self.assertNotIn("・種別", text)
        self.assertIn("• 今日の天気: 晴のち曇（豊明）\n最高22℃/最低8℃\n降水確率 10〜30%", text)
        self.assertIn("\n\n• 予定: なし", text)

    def test_non_weather_keeps_header(self):
        meta = {"bot": "Grok", "title": "週報", "channel": "report"}
        text = g.build_text(meta, "• A · B", "x.md")
        self.assertIn("・種別:", text)
        self.assertIn("A · B", text)


if __name__ == "__main__":
    unittest.main()
