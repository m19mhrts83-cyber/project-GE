#!/usr/bin/env python3
"""113 #deal-active 書き込み（実装①）の単体テスト（ネットワーク不要）。"""
from __future__ import annotations

import datetime as dt
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import kurashift_deal_active_113 as m  # noqa: E402

TODAY = dt.date(2026, 11, 6)


def deal(status="viewing", **sj):
    return {
        "id": "d1",
        "title": "瀬戸 西吉田町 戸建",
        "status": status,
        "area": "瀬戸市",
        "price_man": 400,
        "updated_at": "2026-11-01T10:00:00+09:00",
        "summary_json": sj,
    }


class FakeTable:
    def __init__(self, sb, name):
        self.sb, self.name, self.filters, self.payload = sb, name, [], None

    def select(self, *_a, **_k):
        return self

    def in_(self, col, vals):
        self.filters.append(("in", col, vals))
        return self

    def eq(self, col, val):
        self.filters.append(("eq", col, val))
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, *_a):
        return self

    def update(self, payload):
        self.payload = payload
        return self

    def execute(self):
        class R:
            pass

        r = R()
        if self.payload is not None:
            self.sb.updates.append((self.filters, self.payload))
            r.data = []
            return r
        if self.name == "kurashift_re_deals":
            rows = self.sb.deals
            for kind, col, val in self.filters:
                rows = [x for x in rows if (x.get(col) in val if kind == "in" else x.get(col) == val)]
            r.data = rows
        else:
            r.data = []
        return r


class FakeSB:
    def __init__(self, deals):
        self.deals, self.updates = deals, []

    def table(self, name):
        return FakeTable(self, name)


class FakeSlack:
    def __init__(self):
        self.calls = []

    def post(self, payload, thread_ts=None):
        self.calls.append(("post", thread_ts, payload))
        return "111.222"

    def update(self, ts, payload):
        self.calls.append(("update", ts, payload))


class TargetTests(unittest.TestCase):
    def test_statuses(self):
        self.assertTrue(m.is_target(deal("viewing")))
        self.assertTrue(m.is_target(deal("offer")))
        self.assertTrue(m.is_target(deal("loan")))
        self.assertFalse(m.is_target(deal("info")))
        self.assertFalse(m.is_target(deal("passed")))
        self.assertFalse(m.is_target(deal("purchased")))

    def test_pursue_info(self):
        self.assertTrue(m.is_target(deal("info", pursue=True)))
        self.assertTrue(m.is_target(deal("info", pursue_at="2026-11-01")))
        self.assertFalse(m.is_target(deal("info", pursue=True, pursue_exclude=True)))


class StageTests(unittest.TestCase):
    def test_labels(self):
        self.assertEqual(m.stage_label(deal("viewing")), "内見候補")
        self.assertEqual(m.stage_label(deal("viewing", viewing={"step": "scheduled"})), "内見日確定")
        self.assertEqual(m.stage_label(deal("offer", acquisition={"stage": "offer_submitted"})), "買付提出")
        self.assertEqual(m.stage_label(deal("loan")), "融資")
        self.assertEqual(m.stage_label(deal("info", pursue=True)), "フォロー中")

    def test_parent_has_four_lines_and_link(self):
        text = m.build_parent(deal("viewing"))["blocks"][0]["text"]["text"]
        self.assertIn("段階: 内見候補", text)
        self.assertIn("次の一手:", text)
        self.assertIn("期限:", text)
        self.assertIn("realestate/deals?deal=d1", text)


class PlanTests(unittest.TestCase):
    def test_new_deal_is_posted(self):
        acts = m.plan_actions(deal(), today=TODAY, moved=None)
        self.assertEqual(acts[0]["kind"], "post")
        self.assertEqual(acts[-1]["kind"], "save")

    def test_unchanged_is_noop(self):
        d = deal(slack_deal_active={"ts": "1.1", "stage_key": "viewing:candidate", "last_moved_at": "2026-11-01"})
        moved = m.parse_ts("2026-11-01T10:00:00+09:00")
        self.assertEqual(m.plan_actions(d, today=TODAY, moved=moved), [])

    def test_stage_change_updates_and_replies(self):
        d = deal(viewing={"step": "scheduled"}, slack_deal_active={"ts": "1.1", "stage_key": "viewing:candidate"})
        kinds = [a["kind"] for a in m.plan_actions(d, today=TODAY, moved=None)]
        self.assertEqual(kinds[:2], ["update", "reply"])

    def test_closed_is_left_alone(self):
        d = deal(slack_deal_active={"ts": "1.1", "state": "closed"})
        self.assertEqual(m.plan_actions(d, today=TODAY, moved=None), [])

    def test_checklist_eve_once(self):
        v = {"step": "scheduled", "date": "2026-11-07"}
        d = deal(viewing=v, slack_deal_active={"ts": "1.1", "stage_key": "viewing:scheduled"})
        self.assertIn("checklist", [a["kind"] for a in m.plan_actions(d, today=TODAY, moved=None)])
        d2 = deal(viewing=v, slack_deal_active={"ts": "1.1", "stage_key": "viewing:scheduled", "checklist_sent_for": "2026-11-07"})
        self.assertNotIn("checklist", [a["kind"] for a in m.plan_actions(d2, today=TODAY, moved=None)])

    def test_next_check_is_14_days_after_move(self):
        acts = m.plan_actions(deal(), today=TODAY, moved=m.parse_ts("2026-11-01T10:00:00+09:00"))
        st = m.next_state({}, acts, ts="9.9", today=TODAY)
        self.assertEqual(st["next_check_at"], "2026-11-15")
        self.assertEqual(st["ts"], "9.9")
        self.assertEqual(st["channel"], m.DEAL_ACTIVE_CHANNEL)

    def test_last_moved_takes_latest(self):
        got = m.last_moved_at(deal(), ["2026-11-03T00:00:00Z"], ["2026-11-04T12:00:00+09:00"])
        self.assertEqual(got.astimezone(m.JST).date().isoformat(), "2026-11-04")


class RunTests(unittest.TestCase):
    def test_apply_saves_ts_without_touching_updated_at(self):
        sb = FakeSB([deal("viewing"), deal("passed") | {"id": "d2"}])
        slack = FakeSlack()
        c = m.run(sb, slack, today=TODAY, apply=True, only=None)
        self.assertEqual(c["posted"], 1)
        self.assertEqual(len(sb.updates), 1)
        payload = sb.updates[0][1]
        self.assertNotIn("updated_at", payload)
        self.assertEqual(payload["summary_json"]["slack_deal_active"]["ts"], "111.222")

    def test_dry_run_writes_nothing(self):
        sb = FakeSB([deal("viewing")])
        m.run(sb, FakeSlack(), today=TODAY, apply=False, only=None)
        self.assertEqual(sb.updates, [])

    def test_max_posts_defers(self):
        sb = FakeSB([deal("viewing") | {"id": f"d{i}"} for i in range(3)])
        c = m.run(sb, FakeSlack(), today=TODAY, apply=False, only=None, max_posts=2)
        self.assertEqual(c["posted"], 2)
        self.assertEqual(c["deferred"], 1)


class AskTests(unittest.TestCase):
    def test_sig_matches_ts_side(self):
        # apps/jarvis-dashboard/tests/dealActive113.test.mjs と同じ値
        v = m.d113_value("s3cret", "pass", "11111111-2222-3333-4444-555555555555")
        self.assertEqual(v, "d113:pass:11111111-2222-3333-4444-555555555555:52900d74dc")

    def test_due_rules(self):
        self.assertTrue(m.is_due(deal(slack_deal_active={"ts": "1", "next_check_at": "2026-11-06"}), TODAY))
        self.assertFalse(m.is_due(deal(slack_deal_active={"ts": "1", "next_check_at": "2026-11-07"}), TODAY))
        self.assertFalse(m.is_due(deal(slack_deal_active={"ts": "1", "next_check_at": "2026-11-01", "state": "closed"}), TODAY))
        self.assertFalse(m.is_due(deal(slack_deal_active={"next_check_at": "2026-11-01"}), TODAY))

    def test_card_has_four_buttons_per_deal(self):
        d = deal(slack_deal_active={"ts": "1", "last_moved_at": "2026-10-20"})
        card = m.build_ask_card([d], TODAY, "s3cret")
        acts = [b for b in card["blocks"] if b["type"] == "actions"]
        self.assertEqual(len(acts), 1)
        self.assertEqual(acts[0]["block_id"], "d113_d1")
        self.assertEqual([e["action_id"] for e in acts[0]["elements"]], ["d113_continue", "d113_hold", "d113_pass", "d113_done"])
        self.assertIn("17日動きなし", card["blocks"][2]["text"]["text"])

    def test_asked_state_rechecks_next_week(self):
        st = m.asked_state({"ts": "1", "asked_count": 1}, TODAY, "9.9")
        self.assertEqual(st["state"], "needs_check")
        self.assertEqual(st["asked_count"], 2)
        self.assertEqual(st["next_check_at"], "2026-11-13")
        self.assertEqual(st["ask_card_ts"], "9.9")

    def test_sync_never_shortens_button_extension(self):
        acts = [{"kind": "save", "stage_key": "viewing:candidate", "last_moved_at": "2026-11-06"}]
        st = m.next_state({"ts": "1", "state": "hold", "next_check_at": "2026-12-06"}, acts, ts=None, today=TODAY)
        self.assertEqual(st["next_check_at"], "2026-12-06")
        self.assertEqual(st["state"], "hold")

    def test_run_ask_posts_one_card_and_saves(self):
        due = deal(slack_deal_active={"ts": "1", "next_check_at": "2026-11-01", "last_moved_at": "2026-10-20"})
        sb = FakeSB([due, deal() | {"id": "d2"}])
        slack = FakeSlack()
        c = m.run_ask(sb, slack, today=TODAY, apply=True, secret="s3cret")
        self.assertEqual(c["asked"], 1)
        self.assertEqual(len(slack.calls), 1)
        self.assertEqual(len(sb.updates), 1)


if __name__ == "__main__":
    unittest.main()
