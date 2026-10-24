#!/usr/bin/env python3
"""2026-10-24 週次レビュー是正の単体テスト（ネットワーク不要）。

- CloudStorage の EDEADLK で 1 ファイル読めなくてもジョブを落とさない
- KURASHIFT Obsidian 同期: deal_id「未取得」を uuid 照会しない
- GHA 定刻キック: 定刻〜猶予の間に 1 日 1 回だけ・曜日指定を守る
- Ops Fail autofix: 同じ失敗には Cloud Agent を 1 回だけ
"""
from __future__ import annotations

import errno
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import jarvis_cloud_file as cf  # noqa: E402
import jarvis_gha_precise_kick as kick  # noqa: E402
import jarvis_kurashift_obsidian_pick_sync as pick  # noqa: E402
import jarvis_ops_fail_watch as ofw  # noqa: E402


class CloudFileTests(unittest.TestCase):
    def test_retry_then_success(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.md"
            p.write_text("ok", encoding="utf-8")
            real = Path.read_text
            calls = {"n": 0}

            def flaky(self, *a, **k):
                calls["n"] += 1
                if calls["n"] == 1:
                    raise OSError(errno.EDEADLK, "Resource deadlock avoided")
                return real(self, *a, **k)

            with mock.patch.object(Path, "read_text", flaky):
                self.assertEqual(cf.read_text_cloud(p, wait_sec=0), "ok")
            self.assertEqual(calls["n"], 2)

    def test_give_up_returns_none(self):
        def always(self, *a, **k):
            raise OSError(errno.EDEADLK, "Resource deadlock avoided")

        with mock.patch.object(Path, "read_text", always):
            self.assertIsNone(cf.read_text_cloud(Path("/x/y.md"), wait_sec=0))

    def test_missing_is_none(self):
        self.assertIsNone(cf.read_text_cloud(Path("/no/such/file.md"), wait_sec=0))


class _Q:
    def __init__(self, calls: list):
        self.calls = calls

    def select(self, *a):
        return self

    def eq(self, k, v):
        self.calls.append((k, v))
        return self

    def in_(self, *a):
        return self

    def maybe_single(self):
        return self

    def execute(self):
        class R:
            data = [{"id": "d1", "title": "瀬戸市 松原町 アパート", "status": "info"}]

        return R()


class _SB:
    def __init__(self):
        self.calls: list = []

    def table(self, _name):
        return _Q(self.calls)


class PickSyncTests(unittest.TestCase):
    def test_placeholder_deal_id_falls_back_to_address(self):
        sb = _SB()
        got = pick.find_matching_deal(
            sb,
            {"deal_id": "未取得", "address": "愛知県瀬戸市松原町", "filename": "2026-09-30_瀬戸市_松原町3丁目_S3.md"},
        )
        self.assertEqual(got["id"], "d1")
        self.assertEqual(sb.calls, [])


class PreciseKickTests(unittest.TestCase):
    CFG = {
        "grace_min": 90,
        "jobs": [
            {"workflow": "noon.yml", "time": "12:30", "weekdays": [1, 2, 3, 4, 5]},
            {"workflow": "daily.yml", "time": "11:50"},
        ],
    }

    def at(self, d, hh, mm):
        from datetime import datetime

        return datetime(2026, 10, d, hh, mm, tzinfo=kick.JST)

    def test_weekday_noon(self):
        self.assertEqual(kick.due_jobs(self.CFG, self.at(26, 12, 35), {}), ["noon.yml", "daily.yml"])

    def test_sunday_skips_weekday_job(self):
        self.assertEqual(kick.due_jobs(self.CFG, self.at(25, 12, 35), {}), ["daily.yml"])

    def test_before_and_after_window(self):
        self.assertEqual(kick.due_jobs(self.CFG, self.at(26, 11, 0), {}), [])
        self.assertEqual(kick.due_jobs(self.CFG, self.at(26, 14, 5), {}), [])

    def test_once_per_day(self):
        got = kick.due_jobs(self.CFG, self.at(26, 12, 35), {"noon.yml": "2026-10-26", "daily.yml": "2026-10-26"})
        self.assertEqual(got, [])


class OpsAutofixOnceTests(unittest.TestCase):
    ITEM = {"id": "gha_workflow_fail", "level": "attention", "payload": {"fail_run_ids": ["39083633301"]}}

    def run_autofix(self, launched):
        calls = []
        fake_mod = mock.MagicMock()
        fake_mod.launch_cloud_agent = lambda **k: calls.append(k) or {"ok": True, "url": "u"}
        with mock.patch.dict(sys.modules, {"jarvis_cloud_agent_launch": fake_mod}), \
                mock.patch.object(ofw, "_sb_client", return_value=None), \
                mock.patch.object(ofw, "_existing_ops_status", return_value="done"), \
                mock.patch.object(ofw, "_patch_ops_payload") as patch:
            ofw.run_autofix([dict(self.ITEM)], launched)
        return calls, patch

    def test_same_failure_not_relaunched(self):
        calls, _ = self.run_autofix({"gha_workflow_fail": {"39083633301"}})
        self.assertEqual(calls, [])

    def test_new_failure_launches_and_records(self):
        calls, patch = self.run_autofix({"gha_workflow_fail": {"111"}})
        self.assertEqual(len(calls), 1)
        self.assertEqual(patch.call_args.kwargs["launched_ids"], ["111", "39083633301"])

    def test_carry_forward(self):
        items = [dict(self.ITEM)]
        ofw._carry_launched(items, {"gha_workflow_fail": {"1", "2"}})
        self.assertEqual(items[0]["payload"]["autofix_launched_ids"], ["1", "2"])


if __name__ == "__main__":
    unittest.main()
