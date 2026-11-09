#!/usr/bin/env python3
"""下書きの「まとめて直す」ワーカーのテスト（ネットワーク・Cursor 不要）。"""
from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import jarvis_draft_revise_worker as w  # noqa: E402


class _Q:
    def __init__(self, db, table):
        self.db, self.table, self.filters, self.op, self.payload = db, table, [], "select", None

    def select(self, *_a):
        return self

    def eq(self, k, v):
        self.filters.append((k, v))
        return self

    def limit(self, *_a):
        return self

    def update(self, patch):
        self.op, self.payload = "update", patch
        return self

    def insert(self, row):
        self.op, self.payload = "insert", row
        return self

    def execute(self):
        rows = self.db.setdefault(self.table, [])
        if self.op == "insert":
            rows.append(copy.deepcopy(self.payload))
            return type("R", (), {"data": [self.payload]})
        hit = [r for r in rows if all((r.get(k) if "->>" not in k else r.get("payload", {}).get(k.split("->>")[1])) == v for k, v in self.filters)]
        if self.op == "update":
            for r in hit:
                r.update(copy.deepcopy(self.payload))
        return type("R", (), {"data": copy.deepcopy(hit)})


class FakeSB:
    def __init__(self, rows):
        self.db = {"draft_reviews": rows, "owner_decisions": []}

    def table(self, name):
        return _Q(self.db, name)


def draft():
    return {
        "id": "d1", "case_name": "テスト", "recipient": "今村さん", "channel": "chatwork", "context": None,
        "status": "open", "updated_at": "2026-11-09T00:00:00+00:00",
        "versions": [{"label": "v1", "text": "いつもお世話になっております。\n費用は高いです。\n", "at": "x", "by": "agent"}],
        "revise_request": {"status": "queued", "base": "v1", "requested_at": "r1",
                           "comments": [{"id": "c123456", "quote": "費用は高いです。", "text": "柔らかく", "via": "voice", "target": "paragraph"}]},
    }


class WorkerTests(unittest.TestCase):
    def test_prompt_has_spot_and_comment(self):
        p = w.build_prompt(text="本文", comments=draft()["revise_request"]["comments"], recipient="今村さん", channel="chatwork", context="ルールA")
        self.assertIn("「費用は高いです。」の箇所: 柔らかく", p)
        self.assertIn("ルールA", p)

    def test_parse_result(self):
        r = w.parse_result('```json\n{"text":"新","changes":[{"before":"a","after":"b","why":"c"}],"rule_hint":" x "}\n```')
        self.assertEqual(r["text"], "新")
        self.assertEqual(r["rule_hint"], "x")
        self.assertIsNone(w.parse_result("だめ"))
        self.assertIsNone(w.parse_result('{"text":""}'))

    def test_process_adds_version_and_logs(self):
        sb = FakeSB([draft()])
        w.rules_context = lambda _r: None  # DB を見に行かない
        new_text = "いつもお世話になっております。\n費用は少しかかります。\n"
        out = w.process(sb, draft(), lambda _p: json.dumps({"text": new_text, "changes": [], "rule_hint": "金額は柔らかく"}, ensure_ascii=False))
        self.assertEqual(out, "done v1->v2")
        row = sb.db["draft_reviews"][0]
        self.assertEqual(row["versions"][-1]["label"], "v2")
        self.assertEqual(row["versions"][-1]["by"], "ai")
        self.assertEqual(row["revise_request"]["status"], "done")
        log = sb.db["owner_decisions"][0]
        self.assertEqual(log["surface"], "draft_review")
        self.assertEqual(log["payload"]["idem_key"], "draft:d1:v1->v2:revise")
        self.assertEqual(log["payload"]["rule_hint"], "金額は柔らかく")

    def test_process_error_when_unchanged(self):
        sb = FakeSB([draft()])
        w.rules_context = lambda _r: None
        out = w.process(sb, draft(), lambda _p: json.dumps({"text": draft()["versions"][0]["text"]}))
        self.assertTrue(out.startswith("error"))
        self.assertEqual(sb.db["draft_reviews"][0]["revise_request"]["status"], "error")

    def test_cancelled_request_is_skipped(self):
        d = draft()
        d2 = draft()
        d2["revise_request"]["requested_at"] = "other"
        sb = FakeSB([d2])
        self.assertEqual(w.process(sb, d, lambda _p: "{}"), "skip")


if __name__ == "__main__":
    unittest.main()
