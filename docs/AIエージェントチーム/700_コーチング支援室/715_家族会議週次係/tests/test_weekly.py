#!/usr/bin/env python3
"""715 家族会議週次係 — ネットワーク不要のスモークテスト。

  cd ~/git-repos && ~/selenium_env/venv/bin/python \
    docs/AIエージェントチーム/700_コーチング支援室/715_家族会議週次係/tests/test_weekly.py
"""
from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO / "scripts"))

import friday_family_meeting_weekly as f  # noqa: E402
import friday_notion_ops as n  # noqa: E402


class TestDates(unittest.TestCase):
    def test_latest_sunday_from_monday(self) -> None:
        self.assertEqual(f.latest_sunday(date(2026, 10, 19)), date(2026, 10, 18))

    def test_latest_sunday_from_sunday(self) -> None:
        self.assertEqual(f.latest_sunday(date(2026, 10, 25)), date(2026, 10, 25))

    def test_parse_date(self) -> None:
        self.assertEqual(f.parse_date("2026/10/18"), date(2026, 10, 18))
        self.assertEqual(f.parse_date("20261018"), date(2026, 10, 18))


class TestCorrection(unittest.TestCase):
    def test_aliases(self) -> None:
        out, used = f.correct_text("さあちゃんとまーくん", {"さあちゃん": "さわ", "まーくん": "たまき"})
        self.assertEqual(out, "さわとたまき")
        self.assertEqual(len(used), 2)

    def test_no_op(self) -> None:
        out, used = f.correct_text("そのまま", {"さあ": "さわ"})
        self.assertEqual(out, "そのまま")
        self.assertEqual(used, [])


class TestBlocks(unittest.TestCase):
    def test_md_to_blocks(self) -> None:
        blocks = n.md_to_blocks("## 見出し\n- 箇条書き\n1. 番号\n\n段落")
        types = [b["type"] for b in blocks]
        self.assertEqual(types, ["heading_3", "bulleted_list_item", "numbered_list_item", "paragraph"])

    def test_bold(self) -> None:
        rt = n.rich_text("**太字**と通常")
        self.assertTrue(any((it.get("annotations") or {}).get("bold") for it in rt))

    def test_dated_title(self) -> None:
        m = n.DATED_TITLE_RE.match("(2026/10/18) 家族会議")
        self.assertIsNotNone(m)
        self.assertEqual(m.groups(), ("2026", "10", "18"))


# 2026-11-08 / 11-01 / 10-25 に実際に #ops へ出たエラー文
ERR_1108 = (
    "gsk meeting 失敗: [WARN] API token rejected (HTTP 401) — invalid or expired. "
    "Server-provided commands were NOT loaded; if the command you need is missing, run `gsk login` to re-authenticate.\n"
    "error: unknown command 'meeting'\n\nUsage: gsk [options] [command]\n\n"
    "Genspark Tool CLI - Search, crawl, analyze, and generate media\n\nOptions:\n  -v, --version  output the version number"
)
ERR_1101 = (
    "NotebookLM source failed exit=1: # 候補ボタン: /tmp/notebooklm_add_source/no_add_source_button.buttons.txt"
    " / # debug: /tmp/notebooklm_add_source/no_add_source_button.png / .html"
)
ERR_1025 = "Notion に (2026/10/25) のページがありません。 先に前週ページを複製して日付を変えてください。"


class TestFailureHandoff(unittest.TestCase):
    def test_auth_expired_needs_human(self) -> None:
        info = f.classify_failure(ERR_1108, date(2026, 11, 8))
        self.assertEqual(info["cause"], "Genspark の認証切れ")
        self.assertTrue(info["human"])
        self.assertIn("gsk login", info["action"])

    def test_credit_shortage_needs_human(self) -> None:
        for err in ("gsk meeting 失敗: クレジット不足です", "gsk meeting 失敗: Insufficient credits"):
            info = f.classify_failure(err, date(2026, 11, 8))
            self.assertIn("クレジット不足", info["cause"])
            self.assertTrue(info["human"])

    def test_page_missing_needs_human(self) -> None:
        info = f.classify_failure(ERR_1025, date(2026, 10, 25))
        self.assertTrue(info["human"])
        self.assertIn("(2026/10/25)", info["action"])

    def test_notebooklm_waits_for_retry(self) -> None:
        info = f.classify_failure(ERR_1101, date(2026, 11, 1))
        self.assertFalse(info["human"])
        self.assertIn("NotebookLM", info["cause"])

    def test_unknown(self) -> None:
        self.assertEqual(f.classify_failure("boom", date(2026, 11, 8))["cause"], "原因不明の失敗")

    def test_short_error_drops_cli_noise(self) -> None:
        out = f.short_error(ERR_1108)
        self.assertIn("HTTP 401", out)
        self.assertNotIn("Usage", out)
        self.assertNotIn("Options", out)
        self.assertLessEqual(len(out), 240)


class TestReportFailure(unittest.TestCase):
    """#ai-hub へは同じ原因で1回だけ。人の手当てが要るものは初回から。"""

    def setUp(self) -> None:
        import tempfile

        self.tmp = Path(tempfile.mkdtemp())
        self.orig_state = f.STATE_PATH
        self.orig_slack = f.slack
        f.STATE_PATH = self.tmp / "state.json"
        self.posts: list[tuple[str, str]] = []
        f.slack = lambda ch, text: self.posts.append((ch, text))

    def tearDown(self) -> None:
        f.STATE_PATH = self.orig_state
        f.slack = self.orig_slack

    def channels(self) -> list[str]:
        return [ch for ch, _ in self.posts]

    def test_human_cause_escalates_once(self) -> None:
        d = date(2026, 11, 8)
        f.report_failure(d, ERR_1108, retry=False, stopped=True)
        f.report_failure(d, ERR_1108, retry=True, stopped=True)
        self.assertEqual(self.channels(), ["ops", "hub", "ops"])
        hub = self.posts[1][1]
        self.assertIn("【要手当て】715 家族会議週次 2026-11-08", hub)
        self.assertIn("715＝家族会議週次係", hub)
        self.assertIn("715＝家族会議週次係", self.posts[0][1])
        self.assertIn("番頭さん", hub)
        self.assertIn("ホーク", hub)
        state = f.load_state()["dates"]["2026-11-08"]
        self.assertEqual(state["status"], "pending")
        self.assertEqual(state["escalated_causes"], ["Genspark の認証切れ"])

    def test_machine_cause_waits_for_monday_retry(self) -> None:
        d = date(2026, 11, 1)
        f.report_failure(d, ERR_1101, retry=False)
        self.assertEqual(self.channels(), ["ops"])
        f.report_failure(d, ERR_1101, retry=True)
        self.assertEqual(self.channels(), ["ops", "ops", "hub"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
