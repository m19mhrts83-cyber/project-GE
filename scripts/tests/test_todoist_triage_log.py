#!/usr/bin/env python3
"""Todoist ふるい分けの判断ログ（surface=todoist_triage）のテスト（ネットワーク不要・架空データ）。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import jarvis_learned_rules as lr  # noqa: E402
import jarvis_loopware_weekly as lw  # noqa: E402
import jarvis_owner_decision_log as odl  # noqa: E402
import jarvis_todoist_triage_log as tl  # noqa: E402


def task(i="t1", done=False):
    return {"id": i, "content": "架空タスク", "checked": done, "completed_at": "2026-11-25T00:00:00Z" if done else None}


def cm(body, at="2026-11-24T15:50:00Z"):
    return {"content": body, "posted_at": at}


H = "【300 ラス隊長 11/25 期日超過のふるい】\n"


class DecideTests(unittest.TestCase):
    def test_keep_with_next_step(self):
        d = tl.decide_task(task(), [
            cm(H + "判定: 残す（まだ対応が要る）\n理由: 完了の証跡なし\n根拠: メール1通のみ、通知は無し"),
            cm("【300 ラス隊長 11/25 追記】通知は無し\nあと一手（2分）: ログインできるか見るだけ", "2026-11-24T15:58:00Z"),
        ], run_id="r")
        self.assertEqual(d["action"], "keep")
        self.assertEqual(d["payload"]["next_step"], "ログインできるか見るだけ")
        self.assertEqual(d["payload"]["evidence_kind"], "mail")
        self.assertEqual(d["payload"]["rule_tag"], "no_trace_keep")
        self.assertNotIn("owner_reason", d["payload"])

    def test_drop_candidate_completed_is_flagged_weak(self):
        d = tl.decide_task(task(done=True), [cm(H + "判定: やめる候補（松野さんの一括判断待ち）\n理由: 任意の案内。期限切れ\n根拠: gmail 販促案内")], run_id="r")
        self.assertEqual(d["action"], "drop_candidate")
        self.assertTrue(d["payload"]["closed_without_basis"])
        self.assertEqual(d["payload"]["rule_tag"], "stale_notice")

    def test_close_with_pr_evidence(self):
        d = tl.decide_task(task(done=True), [cm("【300 ラス隊長 11/25 3周目】済み → 閉じます（違っていたら戻して）\n根拠: 直しは PR #1 でマージ・CI緑")], run_id="r")
        self.assertEqual(d["action"], "close")
        self.assertEqual(d["payload"]["evidence_kind"], "github")
        self.assertEqual(d["payload"]["rule_tag"], "done_by_pr")
        self.assertNotIn("closed_without_basis", d["payload"])

    def test_owner_decision_wins_and_reason_is_transcribed_only(self):
        d = tl.decide_task(task(done=True), [
            cm(H + "判定: 残す\n理由: 迷い\n根拠: x"),
            cm("【300 ラス隊長 11/25】松野さん判断: 試用は有料で続ける（11/25）。→ 閉じます", "2026-11-24T21:52:00Z"),
        ], run_id="r")
        self.assertEqual(d["action"], "owner_close")
        self.assertEqual(d["payload"]["owner_reason"], "試用は有料で続ける（11/25）")
        self.assertEqual(d["payload"]["evidence_kind"], "owner")
        self.assertEqual(d["payload"]["rule_tag"], "trial_decided")

    def test_ignores_other_authors_and_progress_only(self):
        self.assertIsNone(tl.decide_task(task(), [cm("【Miss Lemon】要判断")], run_id="r"))
        self.assertIsNone(tl.decide_task(task(), [cm("【300 ラス隊長 11/25 追記】調べました")], run_id="r"))


class RowTests(unittest.TestCase):
    def test_row_is_contract_v1_and_idempotent(self):
        d = tl.decide_task(task(done=True), [cm("【300 ラス隊長】松野さん判断: 気にしなくてよい。送信ガード済み。→ 閉じます")], run_id="run1")
        r = tl.build_row(d)
        r2 = tl.build_row(d)
        self.assertEqual(r["surface"], "todoist_triage")
        self.assertEqual(r["payload"]["v"], 1)
        self.assertEqual(r["payload"]["outcome"], "take")  # owner_close は採った判断
        self.assertEqual(r["payload"]["idem_key"], "todoist_triage:t1:owner_close")
        self.assertEqual(r["payload"]["idem_key"], r2["payload"]["idem_key"])
        self.assertEqual(r["payload"]["run_id"], "run1")
        self.assertEqual(r["decided_at"], "2026-11-24T15:50:00Z")

    def test_outcomes(self):
        self.assertEqual(odl.outcome_of("owner_close"), "take")
        self.assertEqual(odl.outcome_of("close"), "take")
        self.assertEqual(odl.outcome_of("keep"), "note")
        self.assertEqual(odl.outcome_of("drop_candidate"), "note")


class WeeklyAndContextTests(unittest.TestCase):
    def rows(self, n_owner=1, n_close=1, tag="trial_decided"):
        out = []
        for i in range(n_owner):
            out.append({"id": 10 + i, "surface": "todoist_triage", "action": "owner_close", "payload": {"rule_tag": tag, "outcome": "take"}})
        for i in range(n_close):
            out.append({"id": 20 + i, "surface": "todoist_triage", "action": "close", "payload": {"rule_tag": tag, "outcome": "take"}})
        return out

    def test_two_same_kind_make_candidate(self):
        cands = lw.hypotheses(self.rows())
        c = [x for x in cands if x["kind"] == "triage_guide"]
        self.assertEqual(len(c), 1)
        self.assertEqual(c[0]["employee"], "313")
        self.assertEqual(c[0]["rule_line"], "rewrite | * | scope=always")
        self.assertIn("本人の判断 1 回", c[0]["why"])

    def test_single_or_untagged_makes_nothing(self):
        self.assertEqual([x for x in lw.hypotheses(self.rows(1, 0)) if x["kind"] == "triage_guide"], [])
        self.assertEqual([x for x in lw.hypotheses(self.rows(tag="")) if x["kind"] == "triage_guide"], [])

    def test_ai_only_is_marked_unconfirmed(self):
        c = [x for x in lw.hypotheses(self.rows(0, 2)) if x["kind"] == "triage_guide"][0]
        self.assertIn("本人未確認", c["why"])

    def test_adopted_rule_is_readable_by_context(self):
        c = [x for x in lw.hypotheses(self.rows()) if x["kind"] == "triage_guide"][0]
        line = f"- R313-001 | {c['rule_line']} | v1 2026-11-28 | {c['text']}"
        book = lr.parse_rulebook("## 確定ルール\n" + line + "\n")
        self.assertEqual(book.warnings, [])
        txt = tl.context_text([{"decided_at": "2026-11-25", "action": "keep", "payload": {"evidence_kind": "mail", "rule_tag": "no_trace_keep", "evidence_note": "n"}}], book)
        self.assertIn("R313-001", txt)
        self.assertIn(c["text"], txt)
        self.assertIn("最近の判断", txt)

    def test_context_without_db(self):
        self.assertIn("DBに接続できない", tl.context_text(None, lr.RuleBook(path="", rules=[], warnings=[])))

    def test_employee_313_has_rulebook(self):
        p = lr.rulebook_path("313")
        self.assertTrue(p and p.exists())
        self.assertEqual(lr.load_rulebook("313").warnings, [])


class QueueCardTests(unittest.TestCase):
    def test_drop_card_shape(self):
        from datetime import datetime
        c = tl.drop_card({"id": "t9", "content": "架空", "added_at": "2026-11-01T00:00:00Z", "priority": 1}, "理由", datetime(2026, 11, 25))
        self.assertEqual((c["suggest"], c["origin"], c["id"]), ("drop", "313", "t9"))
        self.assertEqual(c["age_days"], 24)

    def test_cleanup_bulk_merges_triage_queue(self):
        import jarvis_todoist_cleanup_bulk as cb
        from datetime import datetime, timedelta
        now = datetime.now(cb.JST)
        q = {"published": True, "generated_at": now.isoformat(), "cards": [{"id": "a", "title": "x", "suggest": "drop"}, {"id": "gone"}]}
        out = cb.merge_313_cards([], q, active_by_id={"a": {"content": "実タイトル"}}, held=set(), now=now)
        self.assertEqual([x["id"] for x in out], ["a"])
        self.assertEqual(out[0]["origin"], "313")
        self.assertEqual(out[0]["title"], "実タイトル")


if __name__ == "__main__":
    unittest.main()
