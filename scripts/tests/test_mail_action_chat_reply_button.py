"""メール要対応: Chatwork カードに「Chatworkで返信」（ルームを開く URL ボタン）を出す（2026-11-11）."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import jarvis_mail_action_slack_post as m  # noqa: E402

PARTNERS = [
    {
        "folder": "101_テスト社",
        "chatwork_room_id": ["111", "222"],
        "chatwork_rooms": {"111": "目黒 啓太", "222": "運営グループ"},
    },
    {"folder": "102_単独社", "chatwork_room_id": "333"},
    {"folder": "103_複数名なし", "chatwork_room_id": ["444", "555"]},
]


def _row(**kw):
    base = {
        "id": "gha-cw-abc",
        "kind": "chat",
        "channel": "Chatwork",
        "partner": "テスト社",
        "subject": "確認",
        "original_body": "ご確認お願いします",
    }
    base.update(kw)
    return base


class ChatworkRoomTest(unittest.TestCase):
    def test_room_by_name(self):
        r = _row(folder="101_テスト社", payload={"channel_raw": "Chatwork・運営グループ"})
        self.assertEqual(m.chatwork_room_id(r, PARTNERS), "222")
        self.assertEqual(m.chat_app_url(r, PARTNERS), "https://www.chatwork.com/#!rid222")

    def test_single_room(self):
        r = _row(folder="102_単独社")
        self.assertEqual(m.chatwork_room_id(r, PARTNERS), "333")

    def test_ambiguous_falls_back_to_top(self):
        r = _row(folder="103_複数名なし", payload={"channel_raw": "Chatwork"})
        self.assertEqual(m.chatwork_room_id(r, PARTNERS), "")
        self.assertEqual(m.chat_app_url(r, PARTNERS), "https://www.chatwork.com/")

    def test_buttons_chat_has_app_reply_first(self):
        for url_mode in (False, True):
            els = m._button_elements(
                "t1",
                url_mode=url_mode,
                chat=True,
                chat_url="https://www.chatwork.com/#!rid1",
                chat_label="Chatwork",
            )
            self.assertEqual(els[0]["text"]["text"], "Chatworkで返信")
            self.assertEqual(els[0]["url"], "https://www.chatwork.com/#!rid1")
            self.assertEqual(els[0]["action_id"], "mail_action_open_app")
            self.assertEqual(els[1]["text"]["text"], "返信済みにする")
            # primary は1つだけ
            self.assertEqual(sum(1 for e in els if e.get("style") == "primary"), 1)

    def test_buttons_mail_unchanged(self):
        els = m._button_elements("t1", url_mode=False)
        self.assertEqual(els[0]["text"]["text"], "返信する")
        self.assertEqual(els[0].get("style"), "primary")
        self.assertNotIn("mail_action_open_app", [e.get("action_id") for e in els])

    def test_buttons_mail_prep(self):
        # メールの後回しは「資料を集めて後回し」（ma:prep）。チャットは Todoist のまま
        els = m._button_elements("t1", url_mode=False)
        vals = [e.get("value") for e in els]
        self.assertIn("ma:prep:t1", vals)
        self.assertNotIn("ma:todoist:t1", vals)
        self.assertIn(m.PREP_LABEL, [e["text"]["text"] for e in els])
        chat = m._button_elements("t1", url_mode=False, chat=True)
        self.assertIn("ma:todoist:t1", [e.get("value") for e in chat])

    def test_compact_card_chatwork(self):
        m._CONTACT_PARTNERS_CACHE = PARTNERS
        try:
            row = _row(folder="102_単独社")
            pl = m.build_compact_payload(row, url_mode=False, rank=1, total=1)
        finally:
            m._CONTACT_PARTNERS_CACHE = None
        actions = [b for b in pl["blocks"] if b.get("type") == "actions"][0]
        self.assertEqual(actions["elements"][0]["text"]["text"], "Chatworkで返信")
        self.assertEqual(actions["elements"][0]["url"], "https://www.chatwork.com/#!rid333")


if __name__ == "__main__":
    unittest.main()
