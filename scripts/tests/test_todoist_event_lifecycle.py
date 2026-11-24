#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""58_ 段階2: todoist_webhook_events の status（claimed/done/skipped/failed）を 317 L1 で回す。

本番 Supabase・Todoist・Slack には触らない（メモリ上の偽 PostgREST とモック）。
"""
from __future__ import annotations

import os
import sys
import unittest
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import jarvis_todoist_event_lifecycle as lcm  # noqa: E402
import jarvis_todoist_webhook_handle as wh  # noqa: E402

T0 = datetime(2026, 11, 25, 3, 0, 0, tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


class FakeSb:
    """必要な分だけの PostgREST もどき（eq/neq/in/is.null/gte/lt/order/limit）。"""

    def __init__(self, rows=None, meta=None, fail_get_meta=False):
        self.rows = {r["id"]: dict(r) for r in (rows or [])}
        self.meta = dict(meta or {})
        self.fail_get_meta = fail_get_meta
        self.calls: list[tuple[str, str]] = []

    @staticmethod
    def _match(row, key, op_val):
        op, _, val = op_val.partition(".")
        v = row.get(key)
        if op == "eq":
            return str(v) == val
        if op == "neq":
            return str(v) != val
        if op == "is" and val == "null":
            return v is None
        if op == "in":
            return str(v) in val.strip("()").split(",")
        if op in ("gte", "lt"):
            a, b = lcm.parse_ts(v), lcm.parse_ts(val)
            return a >= b if op == "gte" else a < b
        raise AssertionError(op_val)

    def __call__(self, method, path_qs, *, body=None, prefer=None):
        self.calls.append((method, path_qs))
        table, _, qs = path_qs.partition("?")
        params = urllib.parse.parse_qsl(qs, keep_blank_values=True)
        if table == "sync_meta":
            if method == "GET":
                if self.fail_get_meta:
                    raise OSError("boom")
                key = dict(params)["key"].split(".", 1)[1]
                return [{"value": self.meta[key]}] if key in self.meta else []
            for b in body:
                self.meta[b["key"]] = b["value"]
            return None
        assert table == "todoist_webhook_events"
        filters = [(k, v) for k, v in params if k not in ("select", "order", "limit", "on_conflict")]
        hits = [r for r in self.rows.values() if all(self._match(r, k, v) for k, v in filters)]
        if method == "GET":
            hits.sort(key=lambda r: r["created_at"])
            p = dict(params)
            if p.get("order", "").endswith(".desc"):
                hits.reverse()
            if "limit" in p:
                hits = hits[: int(p["limit"])]
            return [dict(h) for h in hits]
        if method == "PATCH":
            for h in hits:
                h.update(body)
            return [dict(h) for h in hits]
        raise AssertionError(method)


def _row(rid, created, *, event="note:added", content="おねがい", status="new", eid=None, **kw):
    r = {
        "id": rid,
        "delivery_id": f"d{rid}",
        "event_name": event,
        "user_id": "1",
        "event_data": {"id": f"c{rid}", "item_id": "t1", "content": content, "posted_uid": "999"},
        "initiator": {"id": "999"},
        "created_at": _iso(created),
        "processed_at": None,
        "event_id": eid or f"todoist:{event}:c{rid}",
        "status": status,
        "claimed_by": None,
        "attempts": 0,
        "last_error": None,
    }
    r.update(kw)
    return r


class TestBoundary(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {}, clear=False)
        self.env.start()
        for k in ("JARVIS_TODOIST_EVENT_LIFECYCLE_DISABLE", "JARVIS_TODOIST_EVENT_LIFECYCLE_SINCE"):
            os.environ.pop(k, None)

    def tearDown(self):
        self.env.stop()

    def test_missing_boundary_is_set_to_now(self):
        sb = FakeSb()
        lc = lcm.Lifecycle.load(sb, init_if_missing=True, log=lambda m: None)
        self.assertTrue(lc.active)
        self.assertIn(lcm.SINCE_META_KEY, sb.meta)

    def test_read_failure_is_not_treated_as_no_boundary(self):
        sb = FakeSb(fail_get_meta=True)
        lc = lcm.Lifecycle.load(sb, init_if_missing=True, log=lambda m: None)
        self.assertFalse(lc.active)
        self.assertNotIn(lcm.SINCE_META_KEY, sb.meta)

    def test_existing_boundary_kept(self):
        sb = FakeSb(meta={lcm.SINCE_META_KEY: _iso(T0)})
        lc = lcm.Lifecycle.load(sb, init_if_missing=True, log=lambda m: None)
        self.assertEqual(lc.since, T0)

    def test_disable(self):
        os.environ["JARVIS_TODOIST_EVENT_LIFECYCLE_DISABLE"] = "1"
        lc = lcm.Lifecycle.load(FakeSb(), init_if_missing=True, log=lambda m: None)
        self.assertFalse(lc.active)

    def test_postgrest_timestamp_form(self):
        self.assertEqual(
            lcm.parse_ts("2026-11-24 15:50:16.91508+00"),
            datetime(2026, 11, 24, 15, 50, 16, 915080, tzinfo=timezone.utc),
        )


class TestLifecycleUnit(unittest.TestCase):
    def _lc(self, sb, now):
        return lcm.Lifecycle(sb, since=T0, now=lambda: now)

    def test_claim_conflict(self):
        sb = FakeSb([_row(1, T0 + timedelta(minutes=1), status="claimed")])
        lc = self._lc(sb, T0 + timedelta(minutes=2))
        self.assertFalse(lc.claim({"id": 1}))

    def test_backoff_hides_row_until_elapsed(self):
        now = T0 + timedelta(minutes=10)
        failed_at = now - timedelta(minutes=2)
        sb = FakeSb([_row(1, T0 + timedelta(minutes=1), attempts=1, last_error=f"{_iso(failed_at)} x")])
        self.assertEqual(self._lc(sb, now).fetch(event_name="note:added", limit=10, select="id"), [])
        later = failed_at + timedelta(minutes=5)
        self.assertEqual(len(self._lc(sb, later).fetch(event_name="note:added", limit=10, select="id")), 1)

    def test_stale_claim_counts_as_failure(self):
        claimed = T0 + timedelta(minutes=1)
        sb = FakeSb([_row(1, claimed, status="claimed", claimed_by=f"317:mac@{_iso(claimed)}")])
        now = claimed + timedelta(minutes=20)
        rows = self._lc(sb, now).fetch(event_name="note:added", limit=10, select="id")
        self.assertEqual(rows, [])
        self.assertEqual(sb.rows[1]["status"], "new")
        self.assertEqual(sb.rows[1]["attempts"], 1)

    def test_fresh_claim_left_alone(self):
        claimed = T0 + timedelta(minutes=1)
        sb = FakeSb([_row(1, claimed, status="claimed", claimed_by=f"317:gha@{_iso(claimed)}")])
        self._lc(sb, claimed + timedelta(minutes=3)).fetch(event_name="note:added", limit=10, select="id")
        self.assertEqual(sb.rows[1]["status"], "claimed")
        self.assertEqual(sb.rows[1]["attempts"], 0)

    def test_item_completed_dedupe_only_near(self):
        sb = FakeSb(
            [
                _row(1, T0 + timedelta(minutes=1), event="item:completed", status="done", eid="todoist:item:completed:t1"),
                _row(2, T0 + timedelta(hours=5), event="item:completed", eid="todoist:item:completed:t1"),
            ]
        )
        lc = self._lc(sb, T0 + timedelta(hours=5))
        self.assertFalse(lc.already_done(sb.rows[2]))

    def test_ops_text_has_no_comment_body(self):
        text = lcm.build_ops_text([{"id": 5, "event_name": "note:added", "error": "reply HTTP 500"}])
        self.assertTrue(text.startswith("【ops】317"))
        self.assertIn("id 5", text)


class TestWebhookHandleMain(unittest.TestCase):
    """webhook_handle --reply を偽 Supabase で回す。"""

    def setUp(self):
        self.patches = [
            mock.patch.dict(
                os.environ,
                {
                    "JARVIS_TODOIST_EVENT_LIFECYCLE_SINCE": _iso(T0),
                    "TODOIST_JARVIS_USER_IDS": "60814751",
                },
            ),
            mock.patch.object(sys, "argv", ["x", "--reply"]),
            mock.patch.object(wh, "_process_item_completed", return_value=0),
            mock.patch.object(wh, "_post_ops", return_value=0),
            mock.patch.object(wh, "_todoist_comment"),
            # 表示ヒント（yaml 設定読み）は今回の対象外 → import させない
            mock.patch.dict(sys.modules, {"jarvis_watch_todoist_sync": None}),
        ]
        for p in self.patches:
            p.start()
        os.environ.pop("JARVIS_TODOIST_EVENT_LIFECYCLE_DISABLE", None)
        os.environ.pop("JARVIS_TODOIST_WEBHOOK_HANDLE_DISABLE", None)

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()

    def _run(self, sb):
        with mock.patch.object(wh, "_sb_req", sb), mock.patch.object(lcm, "_utcnow", lambda: T0 + timedelta(hours=1)):
            return wh.main()

    def test_new_row_claimed_then_done(self):
        sb = FakeSb([_row(1, T0 + timedelta(minutes=1))])
        rc = self._run(sb)
        self.assertEqual(rc, 0)
        r = sb.rows[1]
        self.assertEqual(r["status"], "done")
        self.assertIsNotNone(r["processed_at"])
        self.assertTrue(r["claimed_by"].startswith("317:"))
        wh._todoist_comment.assert_called_once()

    def test_legacy_row_only_processed_at(self):
        sb = FakeSb([_row(1, T0 - timedelta(days=1))])
        self._run(sb)
        r = sb.rows[1]
        self.assertIsNotNone(r["processed_at"])
        self.assertEqual(r["status"], "new")  # 古い行の status は触らない
        self.assertIsNone(r["claimed_by"])

    def test_old_other_event_types_untouched(self):
        sb = FakeSb([_row(1, T0 - timedelta(days=1), event="item:updated")])
        self._run(sb)
        self.assertIsNone(sb.rows[1]["processed_at"])
        self.assertEqual(sb.rows[1]["status"], "new")

    def test_duplicate_event_id_skipped(self):
        sb = FakeSb(
            [
                _row(1, T0 + timedelta(minutes=1), status="done", eid="todoist:note:added:c9", processed_at=_iso(T0)),
                _row(2, T0 + timedelta(minutes=2), eid="todoist:note:added:c9"),
            ]
        )
        self._run(sb)
        self.assertEqual(sb.rows[2]["status"], "skipped")
        self.assertIsNotNone(sb.rows[2]["processed_at"])
        wh._todoist_comment.assert_not_called()

    def test_reply_failure_retries_then_failed_with_one_ops(self):
        sb = FakeSb([_row(1, T0 + timedelta(minutes=1))])
        wh._todoist_comment.side_effect = RuntimeError("todoist down")
        now = T0 + timedelta(hours=1)
        for i in range(3):
            with mock.patch.object(wh, "_sb_req", sb), mock.patch.object(lcm, "_utcnow", lambda n=now: n):
                rc = wh.main()
            now += timedelta(hours=3)  # あけ時間を過ぎる
            self.assertEqual(sb.rows[1]["attempts"], i + 1)
            self.assertIsNone(sb.rows[1]["processed_at"])
        self.assertEqual(sb.rows[1]["status"], "failed")
        self.assertEqual(rc, 1)
        wh._post_ops.assert_called_once()
        self.assertIn("【ops】", wh._post_ops.call_args[0][0])
        # failed の行はもう取らない
        with mock.patch.object(wh, "_sb_req", sb), mock.patch.object(lcm, "_utcnow", lambda: now):
            wh.main()
        self.assertEqual(wh._todoist_comment.call_count, 3)
        wh._post_ops.assert_called_once()

    def test_self_comment_done_without_reply(self):
        r = _row(1, T0 + timedelta(minutes=1))
        r["event_data"]["posted_uid"] = "60814751"
        sb = FakeSb([r])
        self._run(sb)
        self.assertEqual(sb.rows[1]["status"], "done")
        wh._todoist_comment.assert_not_called()


if __name__ == "__main__":
    unittest.main()
