#!/usr/bin/env python3
"""2026-10-24 3か月レビュー是正の単体テスト（ネットワーク不要）。

- 315 鮮度監視: 古さ判定・新規／回復だけ通知・JSON の * パス
- オプチャ: 新着スレッド記録の保存／読込（古いものは落とす）
- 夜間トリアージ: 古い pending の自動期限切れ
- 部長→311: マイドライブ相対の draft_path を解決
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import jarvis_freshness_watch as fw  # noqa: E402

NOW = datetime(2026, 10, 24, 3, 0, tzinfo=timezone.utc)


class FreshnessTests(unittest.TestCase):
    CFG = {
        "products": [
            {"id": "a", "label": "A", "kind": "gha", "max_age_h": 30, "owner": "1", "action": "x"},
            {"id": "b", "label": "B", "kind": "gha", "max_age_h": 30, "owner": "2", "action": "y"},
            {"id": "c", "label": "C", "kind": "gha", "max_age_h": 30, "owner": "3", "action": "z"},
        ]
    }
    AGES = {"a": 2, "b": 40, "c": None}

    def getter(self, p):
        h = self.AGES[p["id"]]
        return (NOW - timedelta(hours=h), "") if h is not None else (None, "成功履歴なし")

    def test_stale_and_missing(self):
        rows = {r["id"]: r for r in fw.evaluate(self.CFG, NOW, getter=self.getter)}
        self.assertFalse(rows["a"]["stale"])
        self.assertTrue(rows["b"]["stale"])
        self.assertTrue(rows["c"]["stale"])

    def test_only_changes_are_reported(self):
        rows = fw.evaluate(self.CFG, NOW, getter=self.getter)
        newly, recovered = fw.diff_state(rows, {"b", "a"})
        self.assertEqual([r["id"] for r in newly], ["c"])
        self.assertEqual([r["id"] for r in recovered], ["a"])
        msg = fw.build_message(newly, recovered)
        self.assertTrue(msg.startswith("【ops】315"))
        self.assertIn("担当 3", msg)

    def test_json_star_path_takes_latest(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "h.json"
            p.write_text(
                json.dumps(
                    {"latest": {"routes": {
                        "r1": {"last_ok_at": "2026-09-30T21:19:43+09:00"},
                        "r2": {"last_ok_at": "2026-10-24T07:00:00+09:00"},
                        "r3": {"last_ok_at": None},
                    }}}
                ),
                encoding="utf-8",
            )
            t, why = fw.last_time(
                {"kind": "json_time", "file": "h.json", "path": "latest.routes.*.last_ok_at"},
                repo=Path(d),
            )
            self.assertEqual(why, "")
            self.assertEqual(t.isoformat(), "2026-10-24T07:00:00+09:00")


class ActiveThreadsFileTests(unittest.TestCase):
    def setUp(self):
        poc = REPO / "line_unofficial_poc"
        sys.path.insert(0, str(poc))
        try:
            import chrline_open_chat_to_md as oc  # noqa: F401
        except Exception as e:  # CHRLINE 依存が無い環境
            self.skipTest(f"chrline import 不可: {e}")
        self.oc = oc

    def test_roundtrip_and_expiry(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "active.json"
            old = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
            p.write_text(json.dumps({"routes": {"r1": {"t_old": old}}}), encoding="utf-8")
            n = self.oc._save_active_threads(p, {"r1": {"t_new"}, "r2": {"t_x"}})
            self.assertEqual(n, 2)
            got = self.oc._load_active_threads(p)
            self.assertEqual(got, {"r1": {"t_new"}, "r2": {"t_x"}})


class TriageExpireTests(unittest.TestCase):
    def test_old_pending_expires(self):
        import jarvis_night_triage as t

        now = datetime(2026, 10, 24, 12, 0, tzinfo=t.JST)
        items = [
            {"status": "pending", "received_at": "2026/07/06 13:28"},
            {"status": "pending", "received_at": "2026/10/20 09:00"},
            {"status": "sent", "received_at": "2026/06/01 09:00"},
            {"status": "pending", "received_at": ""},
        ]
        self.assertEqual(t.expire_stale_pending(items, now=now), 1)
        self.assertEqual(items[0]["status"], "skipped")
        self.assertEqual(items[0]["skip_reason"], "auto_expired_21d")
        self.assertEqual([i["status"] for i in items[1:]], ["pending", "sent", "pending"])


class HawkDraftPathTests(unittest.TestCase):
    def test_relative_to_my_drive(self):
        import jarvis_hawk_send_gate_311_apply as h

        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "Library/CloudStorage/GoogleDrive-x@example.com/マイドライブ"
            f = root / "【with Grok bot】/30_shared_working/a.txt"
            f.parent.mkdir(parents=True)
            f.write_text("x", encoding="utf-8")
            from unittest import mock

            with mock.patch.object(Path, "home", return_value=Path(d)):
                self.assertEqual(h.resolve_draft_path("【with Grok bot】/30_shared_working/a.txt"), str(f))
                self.assertEqual(h.resolve_draft_path("【with Grok bot】/none.txt"), "【with Grok bot】/none.txt")


if __name__ == "__main__":
    unittest.main()
