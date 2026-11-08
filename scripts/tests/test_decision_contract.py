#!/usr/bin/env python3
"""判断ログ契約 v1 のテスト（ネットワーク不要）。

- TS の正本（apps/loopware）と Jarvis ダッシュボードの写しが一致しているか
- Python 経路（jarvis_owner_decision_log.contract_row）が同じ形を作るか
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import jarvis_owner_decision_log as odl  # noqa: E402

CANON = REPO / "apps/loopware/lib/decisionContract.ts"
COPIES = [REPO / "apps/jarvis-dashboard/lib/decisionContract.ts"]


class ContractSyncTests(unittest.TestCase):
    def test_copies_match_canon(self):
        canon = CANON.read_text(encoding="utf-8")
        for p in COPIES:
            self.assertEqual(
                p.read_text(encoding="utf-8"), canon,
                f"{p.relative_to(REPO)} が正本と違います。cp {CANON.relative_to(REPO)} {p.relative_to(REPO)}",
            )

    def test_python_outcomes_match_ts(self):
        ts = CANON.read_text(encoding="utf-8")
        start = ts.index("const OUTCOME_OF")
        block = ts[start: ts.index("};", start)]
        pairs = {}
        for line in block.splitlines():
            line = line.strip().rstrip(",")
            if ":" in line and line.endswith('"') and not line.startswith("const"):
                k, v = line.split(":", 1)
                pairs[k.strip()] = v.strip().strip('"')
        self.assertTrue(pairs)
        for action, outcome in pairs.items():
            self.assertEqual(odl.outcome_of(action), outcome, action)


class ContractRowTests(unittest.TestCase):
    def test_row_shape(self):
        row = odl.contract_row(
            surface="todoist_313", action="close", source="digest_apply",
            target_type="todoist_task", target_id="123", employee="313", now=60 * 1000,
        )
        self.assertEqual(row["source"], "script")
        pl = row["payload"]
        self.assertEqual(pl["v"], 1)
        self.assertEqual(pl["outcome"], "take")
        self.assertEqual(pl["source_detail"], "digest_apply")
        self.assertEqual(pl["idem_key"], "script:todoist_313:123:close:1000")

    def test_given_key_and_slack(self):
        row = odl.contract_row(
            surface="todoist_313", action="hesitated", source="slack_text_reply",
            target_type="todoist_task", target_id="9", idem_key="k-1",
        )
        self.assertEqual(row["source"], "slack")
        self.assertEqual(row["payload"]["idem_key"], "k-1")
        self.assertEqual(row["payload"]["outcome"], "hesitate")


if __name__ == "__main__":
    unittest.main()
