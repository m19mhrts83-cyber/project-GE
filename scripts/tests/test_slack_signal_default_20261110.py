import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jarvis_slack_webhook_post as W


class SignalDefaultTests(unittest.TestCase):
    def setUp(self):
        os.environ.pop("JARVIS_SLACK_SIGNAL_DISABLE", None)

    def test_report_is_green_on_second_line(self):
        out = W.ensure_signal("【報告】613 Zaim\n本文", "report")
        self.assertEqual(out.splitlines()[1], "判定: 🟢 回っています")
        self.assertEqual(out.splitlines()[0], "【報告】613 Zaim")

    def test_consult_ops_and_tags_are_red(self):
        self.assertIn("🔴", W.ensure_signal("【配車案】5件\n1.", "consult"))
        self.assertIn("🔴", W.ensure_signal("【ops】211 朝便\n止まり", "report"))
        self.assertIn("🔴", W.ensure_signal("【115 円相場｜失敗】\n・x", "report"))

    def test_explicit_level_and_existing_line(self):
        self.assertIn("🟡 遅れ気味", W.ensure_signal("【報告】x\ny", "report", "yellow"))
        already = "【ops】315\n判定: 🟢OK\nz"
        self.assertEqual(W.ensure_signal(already, "ops"), already)

    def test_hub_deal_and_disable(self):
        self.assertEqual(W.ensure_signal("【AIチーム】見たよ", "hub"), "【AIチーム】見たよ")
        self.assertEqual(W.ensure_signal("案件", "deal"), "案件")
        os.environ["JARVIS_SLACK_SIGNAL_DISABLE"] = "1"
        self.assertEqual(W.ensure_signal("【報告】x", "report"), "【報告】x")

    def test_single_line(self):
        self.assertEqual(W.ensure_signal("【報告】x", "report"), "【報告】x\n判定: 🟢 回っています")

    def test_body_icons_and_untagged_ops(self):
        txt = "【ops】315 鮮度\n🟢 回復 Gmail: 最終成功 2時間前"
        self.assertIn("判定: 🟢", W.ensure_signal(txt, "ops"))
        txt = "【ops】315 鮮度\n🟡 LINE: 未確認\n🟢 回復 Gmail"
        self.assertIn("判定: 🟡", W.ensure_signal(txt, "ops"))
        self.assertIn("判定: 🟢", W.ensure_signal("動画の週次取込\n・新規 3", "ops"))
        self.assertIn("判定: 🔴", W.ensure_signal("動画の週次取込\n・失敗: 字幕", "ops"))

    def test_quiet_green_after_a_week(self):
        g = "【ops】315\n判定: 🟢OK\nz"
        r = "【ops】315\n判定: 🔴未解決\nz"
        self.assertFalse(W.quiet_green(g, "2026-11-05", today="2026-11-10"))  # 立ち上げ1週間は出す
        self.assertTrue(W.quiet_green(g, "2026-10-27", today="2026-11-10"))   # 安定後は出さない
        self.assertFalse(W.quiet_green(r, "2026-10-27", today="2026-11-10"))  # 赤はいつでも出す
        self.assertFalse(W.quiet_green(g, None, today="2026-11-10"))          # 指定なしは従来どおり


if __name__ == "__main__":
    unittest.main()
