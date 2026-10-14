#!/usr/bin/env python3
"""upload_csv_to_supabase の 2026-09-27 床。ネットワーク不要。"""

from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone

import upload_csv_to_supabase as up


SINCE = datetime(2026, 9, 27, tzinfo=timezone.utc)


def rec(comment_id: str, posted_at: str | None) -> dict:
    return {"comment_id": comment_id, "posted_at": posted_at, "content": "x"}


class SelectRecordsSinceTest(unittest.TestCase):
    def test_keeps_on_or_after_floor(self) -> None:
        rows = [
            rec("old", "2026-09-26T21:51:00+00:00"),
            rec("boundary", "2026-09-27T00:00:00+00:00"),
            rec("new", "2026-10-11T09:48:00+00:00"),
            rec("undated", None),
        ]
        kept, skipped = up.select_records_since(rows, SINCE, bootstrap=False)
        self.assertEqual([r["comment_id"] for r in kept], ["boundary", "new"])
        self.assertEqual(skipped, 2)

    def test_bootstrap_ignores_floor(self) -> None:
        rows = [rec("old", "2020-06-01T17:20:00+00:00"), rec("undated", None)]
        kept, skipped = up.select_records_since(rows, SINCE, bootstrap=True)
        self.assertEqual(len(kept), 2)
        self.assertEqual(skipped, 0)

    def test_no_since_keeps_all(self) -> None:
        rows = [rec("old", "2026-09-20T15:56:00+00:00")]
        kept, skipped = up.select_records_since(rows, None, bootstrap=False)
        self.assertEqual(len(kept), 1)
        self.assertEqual(skipped, 0)

    def test_parse_since_date_only(self) -> None:
        self.assertEqual(up.parse_since("2026-09-27"), SINCE)
        self.assertIsNone(up.parse_since(""))
        self.assertIsNone(up.parse_since("  "))


class _Resp:
    def __init__(self, data: list[dict]) -> None:
        self.data = data


class _Query:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows
        self.ids: set[str] = set()

    def select(self, *_a, **_k):
        return self

    def in_(self, _col, ids):
        self.ids = set(ids)
        return self

    def is_(self, _col, _val):
        return self

    def limit(self, _n):
        return self

    def execute(self):
        data = [
            r
            for r in self.rows
            if r["comment_id"] in self.ids and r["embedding"] is None
        ]
        return _Resp(data)


class _Client:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows

    def table(self, _name):
        return _Query(self.rows)


class MissingEmbeddingLineTest(unittest.TestCase):
    def test_one_line_counts_only_null_embeddings(self) -> None:
        client = _Client(
            [
                {"comment_id": "a", "embedding": None},
                {"comment_id": "b", "embedding": [0.1]},
                {"comment_id": "c", "embedding": None},
            ]
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            up.report_missing_embeddings(client, ["a", "b", "c"], since_active=True)
        self.assertEqual(buf.getvalue().strip(), "emb未付与: 2")

    def test_since_inactive_prints_nothing(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            up.report_missing_embeddings(_Client([]), ["a"], since_active=False)
        self.assertEqual(buf.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
