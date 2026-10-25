"""Slack 報告 FB（受けた → 対応した）の文面・未対応判定。"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import jarvis_slack_report_fb_lib as lib  # noqa: E402
import jarvis_slack_report_fb_poll as poll  # noqa: E402


class AckTextTest(unittest.TestCase):
    def test_unknown_does_not_ask_relabel(self) -> None:
        t = lib.build_ack_text("unknown", reply_preview="案件の間を空けて")
        self.assertTrue(t.startswith("【AIチーム】受けた"))
        self.assertNotIn("再送", t)
        self.assertNotIn("見栄え／内容／方針", t)
        self.assertNotIn("引用", t)

    def test_known_kind_has_label(self) -> None:
        self.assertIn("（見栄え）", lib.build_ack_text("layout"))

    def test_done_prefix(self) -> None:
        self.assertTrue(lib.build_done_text(summary="直した").startswith("【AIチーム】対応したよ"))


class OwnReplyTest(unittest.TestCase):
    def test_new_and_old_prefix_are_own(self) -> None:
        self.assertTrue(lib.is_ack_or_bot_reply({"text": "【AIチーム】受けた\n…"}))
        self.assertTrue(lib.is_ack_or_bot_reply({"text": "【Jarvis】対応したよ\n…"}))
        self.assertFalse(lib.is_ack_or_bot_reply({"text": "次と担当メモの間改行して"}))


class FooterTest(unittest.TestCase):
    def test_footer_off_by_default(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(lib.append_fb_footer("本文", channel="report"), "本文")

    def test_footer_opt_in(self) -> None:
        with mock.patch.dict(os.environ, {"JARVIS_SLACK_FB_FOOTER_ENABLE": "1"}, clear=True):
            self.assertIn(lib.FB_FOOTER_MARKER, lib.append_fb_footer("本文", channel="report"))


class PendingTest(unittest.TestCase):
    def test_is_pending(self) -> None:
        self.assertTrue(poll.is_pending({"kind": "unknown", "ack_ts": "1.2"}))
        self.assertTrue(poll.is_pending({"kind": "layout", "mark_only": True}))
        self.assertFalse(poll.is_pending({"kind": "skip_bot", "ack_ts": "1.2"}))
        self.assertFalse(poll.is_pending({"kind": "unknown", "ack_ts": "1.2", "done_at": "x"}))

    def test_prune_keeps_pending(self) -> None:
        processed = {f"report:{i}": {"kind": "skip_bot", "at": f"2026-10-25T{i:05d}"} for i in range(600)}
        processed["consult:old"] = {"kind": "unknown", "ack_ts": "1", "at": "2000-01-01"}
        out = poll.prune_processed(processed, keep=500)
        self.assertIn("consult:old", out)
        self.assertEqual(len(out), 500)


if __name__ == "__main__":
    unittest.main()
