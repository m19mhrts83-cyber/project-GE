#!/usr/bin/env python3
"""LINE グループの最後の発言者が自分なら未返信候補にしない（ネットワーク不要）。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

from jarvis_night_triage import chat_last_speaker_is_self, find_unreplied_chat  # noqa: E402

SELF_BODY = """<details>
<summary>本文</summary>

2026/10/28 20:12  松野真治  お疲れさまです！ ブロード担当は麓伊吹さんです。よろしくお願いします。

</details>"""

PARTNER_LAST = """2026/10/28 19:00  松野真治  確認お願いします
2026/10/28 20:30  本多拓人  確認しました、明日回答します"""

PLAIN = """内容確認しました！
101の方ですが、11月27日の退去予定になりました。"""


def _entry(body: str, at: str) -> dict:
    return {
        "folder": "P103_Tcell",
        "partner_name": "Tcell",
        "received_at": at,
        "channel": "LINE（グループ受信）",
        "summary": body.splitlines()[-1][:60],
        "subject": "",
        "body": body,
    }


class ChatSelfSpeakerTest(unittest.TestCase):
    def test_self_last(self) -> None:
        self.assertTrue(chat_last_speaker_is_self(SELF_BODY))

    def test_partner_last(self) -> None:
        self.assertFalse(chat_last_speaker_is_self(PARTNER_LAST))

    def test_no_speaker_lines(self) -> None:
        self.assertFalse(chat_last_speaker_is_self(PLAIN))

    def test_self_message_not_candidate(self) -> None:
        cands = find_unreplied_chat([_entry(SELF_BODY, "2026/10/28 20:12")], 0)
        self.assertEqual(cands, [])

    def test_partner_message_candidate(self) -> None:
        cands = find_unreplied_chat([_entry(PLAIN, "2026/10/28 21:00")], 0)
        self.assertEqual(len(cands), 1)


if __name__ == "__main__":
    unittest.main()
