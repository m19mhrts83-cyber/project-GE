#!/usr/bin/env python3
"""automation: off の判定（YAML の off は False と読まれる）。架空の設定だけ。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import jarvis_zaim_online_accounts as man  # noqa: E402


class AutomationOffTest(unittest.TestCase):
    def test_yaml_off_is_false_but_counts_as_off(self) -> None:
        acc = yaml.safe_load("id: x\nautomation: off\n")
        self.assertIs(acc["automation"], False)  # YAML の落とし穴の確認
        self.assertTrue(man.is_automation_off(acc))

    def test_quoted_off_and_other_spellings(self) -> None:
        for v in ('"off"', '"false"', '"no"', '"0"', "false"):
            acc = yaml.safe_load(f"automation: {v}\n")
            self.assertTrue(man.is_automation_off(acc), v)

    def test_not_off(self) -> None:
        self.assertFalse(man.is_automation_off({"id": "x"}))  # キー無し
        self.assertFalse(man.is_automation_off({"automation": "on"}))
        self.assertFalse(man.is_automation_off({"automation": True}))
        self.assertFalse(man.is_automation_off(None))


class ShigaThresholdTest(unittest.TestCase):
    def test_shiga_threshold_is_10_days(self) -> None:
        cfg = yaml.safe_load((REPO / "config" / "zaim_bank_sync_watch.yaml").read_text(encoding="utf-8"))
        shiga = next(a for a in cfg["accounts"] if a["id"] == "shiga")
        self.assertEqual(shiga["stale_days"], 10)


if __name__ == "__main__":
    unittest.main()
