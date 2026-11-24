#!/usr/bin/env python3
"""夜トリアージの LINE／iMessage 台帳書き足しのテスト（モック・ダミーデータのみ）。"""
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import jarvis_comm_hub as hub  # noqa: E402

JST = ZoneInfo("Asia/Tokyo")


def _entries():
    now = datetime.now(JST)
    t = lambda d: (now - timedelta(days=d)).strftime("%Y/%m/%d %H:%M")  # noqa: E731
    base = {"folder": "900_テスト先", "partner_name": "テスト先", "subject": "", "body": "ダミー本文"}
    return [
        {**base, "received_at": t(1), "channel": "LINE（相手から）", "summary": "ダミーA", "body": "ダミーA本文"},
        {**base, "received_at": t(2), "channel": "iMessage（相手から）", "summary": "ダミーB", "body": "ダミーB本文"},
        {**base, "received_at": t(2), "channel": "Gmail（相手から返信）", "summary": "ダミーC", "body": "メール"},
    ]


class NightChatSyncTest(unittest.TestCase):
    def test_dry_run_never_touches_db(self):
        es = _entries()
        with mock.patch.object(hub, "client", side_effect=AssertionError("db")):
            r = hub.sync_chat_entries(es, [], apply=False, lookback_days=90)
        self.assertFalse(r["apply"])
        self.assertEqual(r["items"], 2)  # Gmail は対象外
        self.assertEqual(r["by_channel"], {"line": 1, "imessage": 1})

    def test_duplicate_entries_collapse(self):
        es = _entries()
        r = hub.sync_chat_entries(es + es, [], apply=False, lookback_days=90)
        self.assertEqual(r["items"], 2)

    def test_apply_uses_existing_helpers_and_skips_known(self):
        es = _entries()
        known_row = hub.item_from_md_entry(es[0])
        known = {hub.dedupe_key(known_row): "id-known"}
        with mock.patch.object(hub, "existing_by_dedupe_key", return_value=known), \
             mock.patch.object(hub, "insert_items", side_effect=lambda sb, rows: {r["external_id"]: "id-new" for r in rows}) as ins, \
             mock.patch.object(hub, "mark_needs_reply") as mnr, \
             mock.patch.object(hub, "link_pending", return_value={"linked": 0}) as lp:
            r = hub.sync_chat_entries(es, es[:1], apply=True, lookback_days=90, sb=object())
        self.assertEqual(len(ins.call_args[0][1]), 1)
        self.assertEqual((r["new"], r["known"], r["needs_reply"]), (1, 1, 1))
        mnr.assert_called_once()
        lp.assert_called_once()


if __name__ == "__main__":
    unittest.main()
