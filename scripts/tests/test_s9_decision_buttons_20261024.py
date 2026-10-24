#!/usr/bin/env python3
"""S9 候補の Slack ボタン（採用／見送り）と台帳反映のテスト（ネットワーク不要）。"""
from __future__ import annotations

import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import jarvis_s9_decision_apply as dec  # noqa: E402
import jarvis_s9_slack_blocks as blk  # noqa: E402

ITEM = {
    "n": 1,
    "name": "株式会社ユニホー（天白営業所）",
    "area": "天白区",
    "url": "https://www.uniho.co.jp/kanri/tempaku/",
    "contact_url": "https://www.uniho.co.jp/kanri/tempaku/#contact",
    "channel": "web_form",
    "memo": "大手",
    "why": "メモに「大手」",
    "md_date": "2026-10-23",
    "source_md": "2026-10-23_s9_candidates.md",
}


class BlockTests(unittest.TestCase):
    def test_buttons_per_candidate(self):
        with patch.dict(os.environ, {"PROPERTY_GATE_ACTION_TOKEN": "test-secret"}):
            payload = blk.build_decision_blocks([ITEM], url_mode=False)
        actions = [b for b in payload["blocks"] if b["type"] == "actions"]
        self.assertEqual(len(actions), 1)
        ids = [e["action_id"] for e in actions[0]["elements"]]
        self.assertEqual(ids, ["s9_adopt", "s9_skip"])
        self.assertTrue(actions[0]["elements"][0]["style"] == "primary")
        self.assertTrue(actions[0]["elements"][0]["value"].startswith("s9:adopt:"))
        self.assertTrue(actions[0]["elements"][1]["value"].startswith("s9:skip:"))

    def test_url_mode(self):
        with patch.dict(os.environ, {"PROPERTY_GATE_ACTION_TOKEN": "test-secret"}):
            payload = blk.build_decision_blocks([ITEM], url_mode=True)
        actions = [b for b in payload["blocks"] if b["type"] == "actions"][0]
        urls = [e["url"] for e in actions["elements"]]
        self.assertIn("/api/g/s9/adopt/n1?", urls[0])
        self.assertIn("/api/g/s9/skip/n1?", urls[1])

    def test_no_long_url_in_text(self):
        """iPhone で折り返さないよう、URL はリンク化して本文に出さない。"""
        with patch.dict(os.environ, {"PROPERTY_GATE_ACTION_TOKEN": "test-secret"}):
            payload = blk.build_decision_blocks([ITEM], url_mode=False)
        text = "\n".join(
            b["text"]["text"] for b in payload["blocks"] if b["type"] == "section"
        )
        self.assertIn(f"<{ITEM['contact_url']}|", text)
        self.assertIn("フォーム", text)
        visible = re.sub(r"<[^|>]+\|([^>]*)>", r"\1", text)
        self.assertNotIn("http", visible)

    def test_plain_text_fallback(self):
        text = blk.build_consult_text([ITEM], md_note="2026-10-23_s9_candidates.md")
        self.assertIn("採用／見送りは上のボタンで", text)
        self.assertIn("次: Jarvisに依頼", text)


class DecisionApplyTests(unittest.TestCase):
    def _ledger(self, d: str) -> Path:
        p = Path(d) / "list.yaml"
        p.write_text(
            yaml.safe_dump(
                {"settings": {}, "vendors": [{"id": "mgmt-001", "name": "既存A", "url": "", "status": "skip"}]},
                allow_unicode=True,
            ),
            encoding="utf-8",
        )
        return p

    def _vendors(self, p: Path) -> list[dict]:
        return yaml.safe_load(p.read_text(encoding="utf-8"))["vendors"]

    def test_adopt_adds_pending(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._ledger(d)
            payload = {"decision": "adopt", **{k: v for k, v in ITEM.items() if k != "n"}, "ch": "web_form", "cu": ITEM["contact_url"], "dt": "2026-10-23"}
            res = dec.apply_decision(payload, list_path=p)
            self.assertTrue(res["ok"])
            self.assertEqual(res["status"], "pending")
            rows = {v["name"]: v for v in self._vendors(p)}
            self.assertEqual(rows[ITEM["name"]]["status"], "pending")
            self.assertEqual(rows[ITEM["name"]]["property_lane"], "midori_caramel")

    def test_skip_adds_skip(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._ledger(d)
            payload = {"decision": "skip", "name": "見送り商事", "area": "緑区", "ch": "web_form"}
            res = dec.apply_decision(payload, list_path=p)
            self.assertEqual(res["status"], "skip")
            rows = {v["name"]: v for v in self._vendors(p)}
            self.assertEqual(rows["見送り商事"]["status"], "skip")
            self.assertIn("S9 Slack 見送り", rows["見送り商事"]["notes"])

    def test_adopt_flips_existing_skip(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._ledger(d)
            payload = {"decision": "adopt", "name": "既存A", "area": "緑区"}
            res = dec.apply_decision(payload, list_path=p)
            self.assertEqual(res["action"], "updated")
            rows = {v["name"]: v for v in self._vendors(p)}
            self.assertEqual(rows["既存A"]["status"], "pending")

    def test_bad_decision(self):
        with self.assertRaises(SystemExit):
            dec._row_from_payload({"decision": "maybe", "name": "X"})


if __name__ == "__main__":
    unittest.main()
