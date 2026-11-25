#!/usr/bin/env python3
"""日報メールの --mark 取込（mgmt 振り分け・失敗再取込・冪等・日付）の単体テスト。

実台帳・Gmail・Slack は使わない（一時 YAML とモックのみ。id・社名は架空）。
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import jarvis_grok_bucho_mail_apply as bucho  # noqa: E402
import jarvis_kurashift_mgmt_vendor_list as mgmt  # noqa: E402
import jarvis_kurashift_repair_vendor_list as repair  # noqa: E402
import jarvis_kurashift_vendor_list as relist  # noqa: E402


def _write(path: Path, vendors: list[dict]) -> None:
    path.write_text(
        yaml.safe_dump({"settings": {}, "vendors": vendors}, allow_unicode=True),
        encoding="utf-8",
    )


def _read(path: Path) -> dict[str, dict]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {v["id"]: v for v in data["vendors"]}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.re_p, self.mg_p, self.rp_p = d / "re.yaml", d / "mgmt.yaml", d / "repair.yaml"
        _write(self.re_p, [{"id": "chubu-900", "status": "pending", "notes": ""}])
        _write(self.mg_p, [
            {"id": "mgmt-sample-a", "status": "pending"},
            {"id": "mgmt-sample-b", "status": "contacted",
             "contacted_at": "2026-11-14", "precheck_sent_at": "2026-11-14", "notes": "初回送信"},
        ])
        _write(self.rp_p, [{"id": "repair-sample-a", "status": "pending"}])
        for mod, p in ((relist, self.re_p), (mgmt, self.mg_p), (repair, self.rp_p)):
            patcher = mock.patch.object(mod, "LIST_PATH", p)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)


class ApplyMarksTests(Base):
    def test_mixed_mgmt_re_repair_ids(self):
        text = (
            '--mark mgmt-sample-a --status contacted --note "送信 2026-11-20"\n'
            "--mark chubu-900 --status contacted --note ok\n"
            "--mark repair-sample-a --status contacted\n"
        )
        out = relist.apply_marks_from_text(text, dry_run=False, default_date="2026-11-24")
        self.assertTrue(out["ok"])
        self.assertEqual(out["applied"], 3)
        m = _read(self.mg_p)["mgmt-sample-a"]
        self.assertEqual((m["status"], m["contacted_at"], m["precheck_sent_at"]),
                         ("contacted", "2026-11-20", "2026-11-20"))  # note の日付が優先
        self.assertEqual(_read(self.re_p)["chubu-900"]["contacted_at"], "2026-11-24")
        self.assertEqual(_read(self.rp_p)["repair-sample-a"]["status"], "contacted")

    def test_note_date_absent_uses_default_date(self):
        relist.apply_marks_from_text("--mark mgmt-sample-a --status contacted", dry_run=False,
                                     default_date="2026-11-24")
        self.assertEqual(_read(self.mg_p)["mgmt-sample-a"]["contacted_at"], "2026-11-24")

    def test_repost_line_keeps_dates_and_notes(self):
        before = _read(self.mg_p)["mgmt-sample-b"]
        text = '--mark mgmt-sample-b --status contacted --note "11/14 送信済み・再掲 2026-11-14"'
        out = relist.apply_marks_from_text(text, dry_run=False, default_date="2026-11-25")
        self.assertTrue(out["ok"])
        after = _read(self.mg_p)["mgmt-sample-b"]
        for k in ("status", "contacted_at", "precheck_sent_at"):
            self.assertEqual(after[k], before[k])
        # 再掲でも別の note なら 1 回だけ追記、同じ行の再取込では増えない
        notes1 = after["notes"]
        relist.apply_marks_from_text(text, dry_run=False, default_date="2026-11-26")
        relist.apply_marks_from_text(text, dry_run=False, default_date="2026-11-27")
        after2 = _read(self.mg_p)["mgmt-sample-b"]
        self.assertEqual(after2["notes"], notes1)
        self.assertEqual(after2["contacted_at"], "2026-11-14")

    def test_reapply_is_idempotent(self):
        text = '--mark mgmt-sample-a --status contacted --note "送信"'
        relist.apply_marks_from_text(text, dry_run=False, default_date="2026-11-20")
        first = _read(self.mg_p)["mgmt-sample-a"]
        out = relist.apply_marks_from_text(text, dry_run=False, default_date="2026-11-25")
        self.assertEqual(out["applied"], 0)
        self.assertEqual(out["unchanged"], 1)
        self.assertEqual(_read(self.mg_p)["mgmt-sample-a"], first)

    def test_mgmt_only(self):
        out = relist.apply_marks_from_text("--mark mgmt-sample-a --status contacted", dry_run=False,
                                           default_date="2026-11-24")
        self.assertTrue(out["ok"])
        self.assertEqual(out["applied_items"][0]["ledger"], "mgmt")
        self.assertEqual(_read(self.re_p)["chubu-900"].get("contacted_at") or "", "")

    def test_re_only(self):
        out = relist.apply_marks_from_text("--mark chubu-900 --status contacted", dry_run=False,
                                           default_date="2026-11-24")
        self.assertTrue(out["ok"])
        self.assertEqual(out["applied_items"][0]["ledger"], "re")
        self.assertEqual(_read(self.mg_p)["mgmt-sample-a"]["status"], "pending")

    def test_unknown_id_is_failed(self):
        out = relist.apply_marks_from_text("--mark mgmt-nope --status contacted", dry_run=False)
        self.assertFalse(out["ok"])
        self.assertEqual(out["failed"], 1)


def _msg(mid: str, body: str) -> dict:
    return {"id": mid, "subject": "[Grok部長] test", "date": "Tue, 24 Nov 2026 23:30:00 +0000",
            "label_ids": [], "body": body}


class MailFlowTests(Base):
    def setUp(self):
        super().setUp()
        d = Path(self.tmp.name)
        for target, val in (
            (bucho, {"STATE_PATH": d / "state.json"}),
        ):
            for k, v in val.items():
                p = mock.patch.object(target, k, v)
                p.start()
                self.addCleanup(p.stop)
        env = mock.patch.dict(os.environ, {"JARVIS_GROK_BUCHO_KEEP_INBOX": "1"})
        env.start()
        self.addCleanup(env.stop)
        p = mock.patch.object(bucho, "gmail_service", return_value=mock.MagicMock())
        p.start()
        self.addCleanup(p.stop)
        self.msgs: list[dict] = []
        p = mock.patch.object(bucho, "fetch_bucho_messages", side_effect=lambda *a, **k: self.msgs)
        p.start()
        self.addCleanup(p.stop)
        self.notify = mock.Mock(return_value=True)

    def run_apply(self):
        with mock.patch("builtins.print"):
            return bucho.apply_from_gmail(dry_run=False, days=14, reprocess=False,
                                          notify_fn=self.notify)

    def test_failed_mail_not_processed_then_succeeds(self):
        self.msgs = [_msg("m1",
            '--mark mgmt-sample-a --status contacted\n--mark mgmt-late --status contacted\n')]
        s1 = self.run_apply()
        self.assertEqual(s1["marks_failed"], 1)
        self.assertNotIn("m1", bucho.load_state()["processed_ids"])
        # 台帳に追加された後の再取込で成功し、処理済みになる
        _write(self.mg_p, list(_read(self.mg_p).values()) + [{"id": "mgmt-late", "status": "pending"}])
        s2 = self.run_apply()
        self.assertEqual(s2["marks_failed"], 0)
        self.assertIn("m1", bucho.load_state()["processed_ids"])
        got = _read(self.mg_p)
        self.assertEqual(got["mgmt-late"]["status"], "contacted")
        # メール日付（UTC 23:30 → JST 翌日）で記録
        self.assertEqual(got["mgmt-sample-a"]["contacted_at"], "2026-11-25")
        self.notify.assert_not_called()

    def test_three_failures_notify_once(self):
        self.msgs = [_msg("m2", "--mark mgmt-missing --status contacted\n")]
        for _ in range(5):
            self.run_apply()
        self.assertEqual(self.notify.call_count, 1)
        self.assertNotIn("m2", bucho.load_state()["processed_ids"])

    def test_notify_waits_until_third(self):
        self.msgs = [_msg("m3", "--mark mgmt-missing --status contacted\n")]
        self.run_apply()
        self.run_apply()
        self.notify.assert_not_called()
        self.run_apply()
        self.notify.assert_called_once()


if __name__ == "__main__":
    unittest.main()
