# -*- coding: utf-8 -*-
"""公開リポ ガード（2026-11-14）: 非公開の場所・個人情報らしきものを止め、見本は通す。"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from unittest import mock
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("public_guard_t", REPO / "scripts" / "public_repo_guard.py")
g = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(g)
PAT = g.load_patterns()


class PrivatePathTest(unittest.TestCase):
    def test_private_paths(self) -> None:
        for p in [
            "215_kamiooya/C2_ルーティン作業/26_パートナー社への相談/X/5.やり取り.md",
            "215_kamiooya/C1_cursor/1c_神・大家さん倶楽部_AI推進/採点自動化/元ネタ/forum_comments_a.csv",
            "215_kamiooya/C1_cursor/1c_神・大家さん倶楽部_AI推進/採点自動化/forum_comments_a.csv",
            ".jarvis_state/openchat_join_qr_missing/01.png",
            ".jarvis_state/car_loan.json",
            "215_kamiooya/C1_cursor/1b_Cursorマニュアル/連絡先一覧.snapshot.yaml",
        ]:
            self.assertTrue(g.is_private(p, PAT), p)

    def test_public_paths(self) -> None:
        for p in [
            ".jarvis_state/car_loan.example.json",
            ".jarvis_state/night_triage/config.example.json",
            "215_kamiooya/C1_cursor/1c_神・大家さん倶楽部_AI推進/採点自動化/02_得点基準_seed.csv",
            "scripts/jarvis_comm_hub.py",
            "docs/kamiooya-ai.html",
        ]:
            self.assertFalse(g.is_private(p, PAT), p)

    def test_gitignore_has_same_rules(self) -> None:
        gi = (REPO / ".gitignore").read_text(encoding="utf-8").splitlines()
        for pat in PAT:
            self.assertIn(pat, gi, f".gitignore に {pat} が無い")


class LineScanTest(unittest.TestCase):
    def test_detects_personal_info(self) -> None:
        self.assertTrue(g.scan_line("連絡先 taro.yamada@gmail.com", set()))
        self.assertTrue(g.scan_line("TEL 052-913-2741", set()))
        self.assertTrue(g.scan_line("携帯 09031427788", set()))
        self.assertTrue(g.scan_line("振込先 口座番号 3914276", set()))
        self.assertTrue(g.scan_line('"10","2026-01-01","名前","x@x.jp","本文","","153.126.4.20"', set()))

    def test_passes_samples(self) -> None:
        for s in [
            "user@example.com", "a@x.jp", "sender@b.jp", "foo@bar.test", "noreply@company.com",
            "TEL 03-1234-5678", "口座 0000000", "127.0.0.1 192.168.1.10 203.0.113.5",
            "npm i @types/node@20.1.0", "real@gmail.com  # public-ok: 公式窓口",
            "ver 1.2.3", "support@github.com",
        ]:
            self.assertEqual(g.scan_line(s, g.load_allow()), [], s)

    def test_check_flags_private_file_and_csv_header(self) -> None:
        names = ["215_kamiooya/C2_ルーティン作業/a.md", "data/members.csv", "docs/rec.srt"]
        added = {"data/members.csv": [(1, "投稿者名,投稿者メール,本文")]}
        probs = g.check(names, added, PAT, set())
        self.assertEqual(len(probs), 3, probs)

    def test_media_fixture_is_allowed(self) -> None:
        self.assertEqual(g.check(["app/fixtures/notta/with_ts.srt"], {}, PAT, set()), [])

    def test_tree_mode_on_head(self) -> None:
        with mock.patch("builtins.print"):
            self.assertEqual(g.main(["--tree", "HEAD"]), 0)


if __name__ == "__main__":
    unittest.main()
