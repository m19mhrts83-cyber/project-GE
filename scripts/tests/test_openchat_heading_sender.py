#!/usr/bin/env python3
"""オプチャ見出しから投稿者を正しく読むテスト（DB 不要）。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

from jarvis_kurashift_openchat_sync import fix_sender_names, parse_heading, parse_messages_from_md  # noqa: E402


class HeadingSenderTests(unittest.TestCase):
    def test_main(self):
        m = parse_heading("### 2026/11/16 09:04｜【メイン】｜25神コンセプト｜受信｜山田太郎｜仙台の新築")
        self.assertEqual(m["sender"], "山田太郎")
        self.assertEqual(m["thread_title"], "")
        self.assertEqual(m["summary"], "仙台の新築")
        self.assertEqual(m["id_sender"], "受信")  # id は旧来どおり

    def test_thread(self):
        m = parse_heading("### 2026/11/16 12:47｜【スレッド】｜25神コンセプト｜「看板の相談」｜受信｜鈴木｜貴重な情報")
        self.assertEqual(m["stream_type"], "thread")
        self.assertEqual(m["thread_title"], "「看板の相談」")
        self.assertEqual(m["sender"], "鈴木")
        self.assertEqual(m["id_sender"], "受信")

    def test_thread_reply(self):
        m = parse_heading("### 2026/11/16 07:50｜【スレッド返信】｜25神コンセプト｜受信｜2644西岡慎｜こちらに")
        self.assertEqual(m["stream_type"], "thread_reply")
        self.assertEqual(m["thread_title"], "")
        self.assertEqual(m["sender"], "2644西岡慎")
        self.assertEqual(m["id_sender"], "2644西岡慎")

    def test_send_and_summary_with_bar(self):
        m = parse_heading("### 2026/11/16 07:50｜【メイン】｜X｜送信｜自分｜a｜b")
        self.assertEqual(m["sender"], "自分")
        self.assertEqual(m["summary"], "a｜b")

    def test_unknown_format_falls_back(self):
        m = parse_heading("### 2026/10/01｜【メイン】｜X｜誰か｜要約")
        self.assertEqual(m["sender"], "誰か")

    def test_id_unchanged_by_fix(self):
        md = "### 2026/11/16 09:04｜【メイン】｜X｜受信｜山田｜本文\n\n本文です\n"
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.md"
            p.write_text(md, encoding="utf-8")
            e = parse_messages_from_md(p, "r1", "X")[0]
        import hashlib
        legacy = hashlib.sha256("r1_2026/11/16 09:04_受信_本文です".encode()).hexdigest()[:24]
        self.assertEqual(e["id"], f"oc_{legacy}")
        self.assertEqual(e["sender_name"], "山田")


    def test_fix_sender_names_groups(self):
        md = (
            "### 2026/11/16 09:04｜【メイン】｜X｜受信｜山田｜a\n\n本文1\n"
            "### 2026/11/16 09:05｜【スレッド返信】｜X｜受信｜田中｜b\n\n本文2\n"
            "### 2026/11/16 09:06｜【スレッド】｜X｜「T」｜受信｜山田｜c\n\n本文3\n"
        )
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.md"
            p.write_text(md, encoding="utf-8")
            entries = parse_messages_from_md(p, "r1", "X")
        calls = []

        class Q:
            def __init__(self):
                self.c = {}
            def table(self, t):
                return self
            def update(self, v):
                self.c["v"] = v
                return self
            def in_(self, k, ids):
                self.c["ids"] = ids
                return self
            def or_(self, f):
                self.c["or"] = f
                return self
            def execute(self):
                calls.append(self.c)
                self.c = {}

        n = fix_sender_names(Q(), entries, apply=True)
        self.assertEqual(n, 3)
        vals = sorted((c["v"]["sender_name"], c["v"]["thread_title"] or "") for c in calls)
        self.assertEqual(vals, [("山田", ""), ("山田", "「T」"), ("田中", "")])


if __name__ == "__main__":
    unittest.main()
