#!/usr/bin/env python3
"""オプチャ見出しの投稿者名パース（受信/送信を投稿者にしない）の単体テスト（DB 不要）。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

from jarvis_kurashift_openchat_sync import (  # noqa: E402
    parse_heading,
    parse_messages_from_md,
    plan_name_fixes,
)


class ParseHeadingTest(unittest.TestCase):
    def test_main_with_sender(self):
        h = parse_heading("### 2026/11/10 21:26｜【メイン】｜30空室相談G【神大家】｜受信｜1001山田太郎｜要約です")
        self.assertEqual(h["sender"], "1001山田太郎")
        self.assertEqual(h["summary"], "要約です")
        self.assertEqual(h["thread_title"], "")

    def test_thread_with_title_and_sender(self):
        h = parse_heading("### 2026/11/12 15:30｜【スレッド】｜30空室相談G【神大家】｜「題」｜受信｜202 佐藤花子【サポート担当】｜要約")
        self.assertEqual(h["thread_title"], "「題」")
        self.assertEqual(h["sender"], "202 佐藤花子【サポート担当】")
        self.assertEqual(h["summary"], "要約")

    def test_thread_reply_has_no_title(self):
        h = parse_heading("### 2026/11/10 15:29｜【スレッド返信】｜30空室相談G【神大家】｜受信｜303田中一郎｜ありがとうございます")
        self.assertEqual(h["thread_title"], "")
        self.assertEqual(h["sender"], "303田中一郎")

    def test_sent_by_self(self):
        h = parse_heading("### 2026/08/02｜【メイン】｜01運営より全体周知G【神大家】｜送信｜自分｜告知")
        self.assertEqual(h["sender"], "自分")

    def test_legacy_heading_without_sender(self):
        h = parse_heading("### 2026/07/02｜【メイン】｜30空室相談G【神大家】｜受信｜昨日入居完了しました")
        self.assertEqual(h["sender"], "")
        self.assertEqual(h["summary"], "昨日入居完了しました")

    def test_summary_with_bar_is_kept(self):
        h = parse_heading("### 2026/10/28 17:20｜【メイン】｜14-1北海道G｜受信｜404 高橋次郎 【物件紹介担当】｜築30年｜満室")
        self.assertEqual(h["sender"], "404 高橋次郎 【物件紹介担当】")
        self.assertEqual(h["summary"], "築30年｜満室")

    def test_direction_never_becomes_sender(self):
        for d in ("受信", "送信"):
            h = parse_heading(f"### 2026/11/10｜【スレッド返信】｜G｜{d}｜名前｜要約")
            self.assertNotIn(h["sender"], ("受信", "送信"))
            self.assertNotIn(h["thread_title"], ("受信", "送信"))


class StableIdTest(unittest.TestCase):
    def test_id_matches_legacy_key(self):
        import hashlib

        md = "### 2026/11/10 21:26｜【メイン】｜G｜受信｜1001山田太郎｜要約\n\n本文です\n"
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.md"
            p.write_text(md, encoding="utf-8")
            [e] = parse_messages_from_md(p, "r1", "G")
        # 旧パーサーは sender=受信 で id を作っていた。投稿者名の修正で id を変えない
        legacy = hashlib.sha256("r1_2026/11/10 21:26_受信_本文です".encode()).hexdigest()[:24]
        self.assertEqual(e["id"], f"oc_{legacy}")
        self.assertEqual(e["sender_name"], "1001山田太郎")


class PlanNameFixesTest(unittest.TestCase):
    def test_groups_only_changed_columns(self):
        parsed = [
            {"id": "a", "sender_name": "名前A", "thread_title": None},
            {"id": "b", "sender_name": "名前A", "thread_title": "「題」"},
            {"id": "c", "sender_name": "名前C", "thread_title": None},
            {"id": "new", "sender_name": "X", "thread_title": None},
        ]
        existing = {
            "a": {"sender_name": "受信", "thread_title": "受信"},
            "b": {"sender_name": "受信", "thread_title": "「題」"},
            "c": {"sender_name": "名前C", "thread_title": ""},
        }
        g = plan_name_fixes(parsed, existing)
        self.assertEqual(sorted(g[("sender_name", "名前A")]), ["a", "b"])
        self.assertEqual(g[("thread_title", None)], ["a"])
        self.assertNotIn(("sender_name", "名前C"), g)
        self.assertNotIn(("sender_name", "X"), g)


if __name__ == "__main__":
    unittest.main()
