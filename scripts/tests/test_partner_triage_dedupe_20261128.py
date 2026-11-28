"""111 候補の絞り込み: IMP-002（見送り済みの同じ発言を出さない）と IMP-005（送信後の候補を出さない）。架空文のみ。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import jarvis_gha_partner_triage as m  # noqa: E402

CH_A = "Chatwork・テスト部屋A（相手から返信）"
CH_B = "Chatwork・テスト部屋B（相手から返信）"


def _cand(body="次回の打ち合わせはいつにしますか", ch=CH_A, folder="P000_架空社", at="2026/11/20 10:00"):
    return {"folder": folder, "channel": "Chatwork", "channel_raw": ch, "body": body, "received_at": at}


class Imp002(unittest.TestCase):
    def test_same_message_dropped(self):
        c = _cand()
        keys = {m.chat_message_key(c["folder"], c["channel_raw"], c["body"])}
        kept, dropped = m.drop_already_skipped([c, _cand(body="別の発言です")], keys)
        self.assertEqual(len(dropped), 1)
        self.assertEqual(kept[0]["body"], "別の発言です")

    def test_other_room_same_text_kept(self):
        keys = {m.chat_message_key("P000_架空社", CH_A, "こんにちは")}
        kept, dropped = m.drop_already_skipped([_cand(body="こんにちは", ch=CH_B)], keys)
        self.assertEqual((len(kept), len(dropped)), (1, 0))

    def test_lookup_failure_keeps_all(self):
        kept, dropped = m.drop_already_skipped([_cand()], None)
        self.assertEqual((len(kept), len(dropped)), (1, 0))

    def test_load_failure_returns_none(self):
        class Boom:
            def table(self, _):
                raise RuntimeError("x")

        self.assertIsNone(m.load_skipped_chat_keys(Boom()))

    def test_load_builds_same_key_as_candidate(self):
        c = _cand()

        class Q:
            def __getattr__(self, _n):
                return lambda *a, **k: self

            def execute(self):
                return type("R", (), {"data": [{"folder": c["folder"], "original_body": c["body"], "payload": {"channel_raw": c["channel_raw"]}}]})()

        class SB:
            def table(self, _):
                return Q()

        keys = m.load_skipped_chat_keys(SB())
        kept, dropped = m.drop_already_skipped([c], keys)
        self.assertEqual(len(dropped), 1)


class Imp005(unittest.TestCase):
    def test_outbound_after_in_md_drops(self):
        out = [{"folder": "P000_架空社", "channel": "メール（自分から送信）", "inbound": False, "received_at": "2026/11/21 09:00"}]
        kept, dropped = m.drop_replied_after([_cand()], out, None)
        self.assertEqual((len(kept), len(dropped)), (0, 1))

    def test_outbound_before_keeps(self):
        out = [{"folder": "P000_架空社", "channel": "メール（自分から送信）", "inbound": False, "received_at": "2026/11/19 09:00"}]
        kept, _ = m.drop_replied_after([_cand()], out, None)
        self.assertEqual(len(kept), 1)

    def test_other_partner_keeps(self):
        out = [{"folder": "P111_別社", "channel": "（自分から送信）", "inbound": False, "received_at": "2026/11/21 09:00"}]
        kept, _ = m.drop_replied_after([_cand()], out, None)
        self.assertEqual(len(kept), 1)

    def test_sent_row_after_drops(self):
        rows = [{"folder": "P000_架空社", "payload": {"sent_at": "2026-11-21T00:30:00.000Z"}, "updated_at": ""}]
        kept, dropped = m.drop_replied_after([_cand()], [], rows)
        self.assertEqual((len(kept), len(dropped)), (0, 1))

    def test_date_only_same_day_keeps(self):
        out = [{"folder": "P000_架空社", "channel": "（自分から送信）", "inbound": False, "received_at": "2026/11/20 18:00"}]
        kept, _ = m.drop_replied_after([_cand(at="2026/11/20")], out, None)
        self.assertEqual(len(kept), 1)

    def test_no_records_keeps(self):
        kept, _ = m.drop_replied_after([_cand()], [], None)
        self.assertEqual(len(kept), 1)


if __name__ == "__main__":
    unittest.main()
