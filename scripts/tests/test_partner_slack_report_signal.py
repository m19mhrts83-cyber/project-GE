import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jarvis_partner_slack_report as r  # noqa: E402


class PostCmdSignal(unittest.TestCase):
    def test_failure_night_adds_yellow(self):
        cmd = r._post_cmd("⚠️【111 係・夜】\n・失敗: x")
        self.assertEqual(cmd[-2:], ["--signal", "yellow"])
        self.assertIn("--channel", cmd)

    def test_no_failure_adds_nothing(self):
        cmd = r._post_cmd("【111 係・夜】\n・件数: a")
        self.assertNotIn("--signal", cmd)


if __name__ == "__main__":
    unittest.main()
