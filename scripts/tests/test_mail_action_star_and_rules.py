#!/usr/bin/env python3
"""116 判断B（スター付き・Todoist済は出さない）と判断C（ルール帳を読めない回の印）。ネットワーク不要。"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import jarvis_learned_rules as lr  # noqa: E402
import jarvis_mail_action_slack_post as ma  # noqa: E402


class _Exec:
    def __init__(self, value):
        self.value = value

    def execute(self):
        if isinstance(self.value, Exception):
            raise self.value
        return self.value


class FakeGmail:
    """messages().get の偽物（labels は _svc が返す）"""

    def __init__(self, labels_by_msg: dict[str, list[str]], *, labels=None, fail_get=False):
        self.labels_by_msg = labels_by_msg
        self.labels = labels if labels is not None else [{"id": "Label_9", "name": "Todoist済"}]
        self.fail_get = fail_get
        self.get_calls = 0

    def get(self, userId, id, format):  # noqa: A002 — Gmail API と同じ名前
        self.get_calls += 1
        if self.fail_get:
            return _Exec(RuntimeError("boom"))
        return _Exec({"id": id, "labelIds": self.labels_by_msg.get(id, ["INBOX"])})


def _svc(fake):
    class S:
        def users(self_inner):
            class U:
                def labels(self2):
                    class L:
                        def list(self3, userId):
                            return _Exec({"labels": fake.labels})

                    return L()

                def messages(self2):
                    return fake

            return U()

    return S()


def row(i: str, gid: str | None, **kw):
    return {"id": i, "gmail_message_id": gid, "account": "admin", **kw}


class StarFilterTests(unittest.TestCase):
    def test_excludes_starred_and_todoist_done(self):
        fake = FakeGmail({"g1": ["INBOX", "STARRED"], "g2": ["INBOX", "Label_9"], "g3": ["INBOX"]})
        kept, st = ma.filter_star_or_todoist_done(
            [row("a", "g1"), row("b", "g2"), row("c", "g3")], service_for=lambda t: _svc(fake)
        )
        self.assertEqual([r["id"] for r in kept], ["c"])
        self.assertEqual(st["star_excluded"], 2)
        self.assertEqual(st["star_checked"], 3)

    def test_no_todoist_label_in_box_only_star_counts(self):
        fake = FakeGmail({"g2": ["INBOX", "Label_9"]}, labels=[])
        kept, st = ma.filter_star_or_todoist_done([row("b", "g2")], service_for=lambda t: _svc(fake))
        self.assertEqual([r["id"] for r in kept], ["b"])
        self.assertEqual(st["star_excluded"], 0)

    def test_gmail_unavailable_keeps_rows(self):
        def boom(_t):
            raise FileNotFoundError("token missing")

        kept, st = ma.filter_star_or_todoist_done([row("a", "g1"), row("b", "g2")], service_for=boom)
        self.assertEqual([r["id"] for r in kept], ["a", "b"])
        self.assertEqual(st["star_check_unavailable"], 2)

    def test_get_failure_keeps_row(self):
        fake = FakeGmail({}, fail_get=True)
        kept, st = ma.filter_star_or_todoist_done([row("a", "g1")], service_for=lambda t: _svc(fake))
        self.assertEqual([r["id"] for r in kept], ["a"])
        self.assertEqual(st["star_check_unavailable"], 1)

    def test_rows_without_gmail_id_and_reply_wait_skip_check(self):
        fake = FakeGmail({"g1": ["STARRED"]})
        kept, st = ma.filter_star_or_todoist_done(
            [row("a", None), row("w", "g1", _reply_wait=True)], service_for=lambda t: _svc(fake)
        )
        self.assertEqual([r["id"] for r in kept], ["a", "w"])
        self.assertEqual(fake.get_calls, 0)

    def test_disabled_by_env(self):
        fake = FakeGmail({"g1": ["STARRED"]})
        with mock.patch.dict(os.environ, {"JARVIS_MAIL_ACTION_STAR_CHECK": "0"}):
            kept, _ = ma.filter_star_or_todoist_done([row("a", "g1")], service_for=lambda t: _svc(fake))
        self.assertEqual([r["id"] for r in kept], ["a"])


class RulesUnavailableTests(unittest.TestCase):
    def test_load_rulebook_missing_file_is_unavailable(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(lr, "rulebook_path", return_value=Path(d) / "none.md"):
                book = lr.load_rulebook("116")
        self.assertTrue(book.unavailable)
        self.assertEqual(book.rules, [])

    def test_load_rulebook_ok_is_available(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "learned_rules.md"
            p.write_text("## 確定ルール\n\n- R116-001 | hide | from:a@example.com | scope=partner | v1 2026-11-09 | 根拠 1 | x\n", encoding="utf-8")
            with mock.patch.object(lr, "rulebook_path", return_value=p):
                book = lr.load_rulebook("116")
        self.assertFalse(book.unavailable)
        self.assertEqual(len(book.confirmed), 1)

    def test_repo_rulebook_is_readable(self):
        book = lr.load_rulebook("116")
        self.assertFalse(book.unavailable, book.warnings)

    def test_stamp_marks_and_clears(self):
        on = ma._stamp_posted_payload({}, score=1, summary="", slack_channel=None, slack_ts=None,
                                      digest_channel=None, digest_ts=None, rules_unavailable=True)
        self.assertTrue(on["rules_unavailable"])
        off = ma._stamp_posted_payload(on, score=1, summary="", slack_channel=None, slack_ts=None,
                                       digest_channel=None, digest_ts=None)
        self.assertNotIn("rules_unavailable", off)

    def test_digest_shows_mark_only_when_unavailable(self):
        rows = [{"id": "a", "partner": "P", "subject": "件名"}]
        plain = ma.build_digest_payload(rows)
        self.assertNotIn("ルール未適用", str(plain["blocks"]))
        marked = ma.build_digest_payload([{**rows[0], "_rules_unavailable": True}])
        self.assertIn("ルール未適用", str(marked["blocks"]))

    def test_ops_text_has_signal_and_reason(self):
        t = ma.rules_unavailable_ops_text(["読めません: x"])
        self.assertTrue(t.startswith("🟡【ops】116"))
        self.assertIn("読めません", t)

    def test_ops_due_without_db(self):
        self.assertTrue(ma.rules_unavailable_ops_due(None))


class GreenReportTests(unittest.TestCase):
    def test_due_until_inclusive(self):
        with mock.patch.dict(os.environ, {"JARVIS_MAIL_ACTION_GREEN_UNTIL": "2026-11-22"}):
            self.assertTrue(ma.green_report_due("2026-11-22"))
            self.assertFalse(ma.green_report_due("2026-11-23"))

    def test_text_green_and_yellow(self):
        ok = ma.run_report_text(0, {"posted": 3, "stats": {"rules": 1}})
        self.assertTrue(ok.startswith("🟢【報告】116"))
        self.assertIn("カード 3件", ok)
        ng = ma.run_report_text(0, {"posted": 0, "stats": {"rules_unavailable": True}})
        self.assertTrue(ng.startswith("🟡"))
        self.assertIn("未適用", ng)

    def test_no_post_on_dry_run(self):
        with mock.patch.object(ma, "RUN_SUMMARY", {"from_triage": True, "dry_run": True}), \
                mock.patch("subprocess.run") as run:
            ma.post_run_report(0)
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
