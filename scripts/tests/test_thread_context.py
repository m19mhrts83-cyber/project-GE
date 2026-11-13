#!/usr/bin/env python3
"""判断デスクの「1つ前のやりとり」（compact_context）のテスト。ネットワーク不要。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import jarvis_thread_context as tc  # noqa: E402


def msg(at, inbound, body, subject="件名"):
    return {"received_at": at, "inbound": inbound, "subject": subject, "body": body}


class CompactContextTests(unittest.TestCase):
    def test_drops_current_mail_and_marks_mine(self):
        ctx = [
            msg("2026/11/12 21:39", False, "山本様\nご注文ありがとうございます。\nお礼まで。"),
            msg("2026/11/13 09:00", True, "松野様\n承知しました。"),
        ]
        out = tc.compact_context(ctx, "松野様\n承知しました。")
        self.assertEqual(len(out), 1)
        self.assertTrue(out[0]["mine"])
        self.assertIn("ご注文ありがとうございます", out[0]["body"])

    def test_keeps_older_inbound_and_limits_count(self):
        ctx = [msg(f"2026/11/{d:02d} 10:00", d % 2 == 0, f"本文{d}") for d in range(1, 8)]
        out = tc.compact_context(ctx, "", max_msgs=3)
        # 最後が受信（7日=奇数→受信ではない）なので、そのまま新しい3通
        self.assertEqual([o["body"] for o in out], ["本文5", "本文6", "本文7"])

    def test_cuts_quote_and_length(self):
        long = "あ" * 2000
        ctx = [msg("t", False, "本文です\n> 引用の行\n> もう1行"), msg("t2", False, long)]
        out = tc.compact_context(ctx, "x")
        self.assertEqual(out[0]["body"], "本文です")
        self.assertEqual(len(out[1]["body"]), tc.MAX_CHARS)

    def test_bad_input_is_empty(self):
        self.assertEqual(tc.compact_context(None), [])
        self.assertEqual(tc.compact_context([1, "a", None]), [])
        self.assertEqual(tc.compact_context([msg("t", False, "")], ""), [])


if __name__ == "__main__":
    unittest.main()
