#!/usr/bin/env python3
"""317 日中便: 既存行（id か gmail_message_id が同じ）には触らず新着だけ入れる。ネットワーク不要。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import jarvis_gha_gmail_triage as gt  # noqa: E402


class _Q:
    def __init__(self, data):
        self.data = data
        self._col = None
        self._vals: list[str] = []

    def select(self, col):
        self._col = col
        return self

    def in_(self, col, vals):
        self._col = col
        self._vals = list(vals)
        return self

    def execute(self):
        class R:
            pass

        r = R()
        r.data = [x for x in self.data if str(x.get(self._col)) in self._vals]
        return r


class _SB:
    def __init__(self, data):
        self.data = data

    def table(self, _name):
        return _Q(self.data)


class NewOnlyTest(unittest.TestCase):
    def test_only_new_rows_drops_existing_id_and_message(self):
        rows = [
            {"id": "gha-a", "gmail_message_id": "m1"},  # id が既存
            {"id": "gha-b", "gmail_message_id": "m2"},  # Mac 側が gha- 無しで入れ済み
            {"id": "gha-c", "gmail_message_id": "m3"},  # 新着
            {"id": "gha-d", "gmail_message_id": None},  # message_id 無しの新着
        ]
        sb = _SB(
            [
                {"id": "gha-a", "gmail_message_id": "m1"},
                {"id": "b", "gmail_message_id": "m2"},
            ]
        )
        have_ids, have_gids = gt.existing_keys(sb, rows)
        out = gt.only_new_rows(rows, have_ids, have_gids)
        self.assertEqual([r["id"] for r in out], ["gha-c", "gha-d"])

    def test_empty(self):
        self.assertEqual(gt.only_new_rows([], set(), set()), [])


if __name__ == "__main__":
    unittest.main()
