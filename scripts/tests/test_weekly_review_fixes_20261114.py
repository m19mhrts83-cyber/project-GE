# -*- coding: utf-8 -*-
"""314 週次レビュー 2026-11-14 の修正テスト。

① 部長ブリッジ: jarvis_bucho_bridge_lib を import したプロセスで Drive 未ダウンロードを読める設定を ON に
② 定額AIの係: Supabase 失敗中は 10 秒から倍々で最大 300 秒あける（3 秒ごとに打ち続けない）
③ 機械チェック: JSON の "streams_failed": 0 を失敗とみなさない
"""
from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    return mod


class BuchoBridgeDatalessTest(unittest.TestCase):
    def test_import_enables_dataless_materialization(self) -> None:
        fake = types.ModuleType("jarvis_cloud_file")
        calls: list[int] = []
        fake.enable_dataless_materialization = lambda: calls.append(1) or True  # type: ignore[attr-defined]
        with mock.patch.dict(sys.modules, {"jarvis_cloud_file": fake}):
            lib = _load("bucho_lib_test", "scripts/jarvis_bucho_bridge_lib.py")
        self.assertEqual(calls, [1])
        self.assertTrue(lib.DATALESS_ON)

    def test_import_survives_without_helper(self) -> None:
        with mock.patch.dict(sys.modules, {"jarvis_cloud_file": None}):
            lib = _load("bucho_lib_test2", "scripts/jarvis_bucho_bridge_lib.py")
        self.assertFalse(lib.DATALESS_ON)
        self.assertTrue(callable(lib.folder))


class FlatAiWorkerBackoffTest(unittest.TestCase):
    def setUp(self) -> None:
        self.w = _load("flat_worker_test", "scripts/jarvis_flat_ai_worker.py")

    def test_wait_doubles_up_to_300(self) -> None:
        got = [self.w.fail_wait_sec(n) for n in range(1, 9)]
        self.assertEqual(got, [10, 20, 40, 80, 160, 300, 300, 300])

    def test_loop_backs_off_and_resets_after_success(self) -> None:
        sleeps: list[float] = []
        results = iter([RuntimeError("402"), RuntimeError("402"), RuntimeError("402"), None, StopIteration()])

        def claim(_sb):
            r = next(results)
            if isinstance(r, StopIteration):
                raise KeyboardInterrupt  # ループを抜ける
            if isinstance(r, Exception):
                raise r
            return None

        with mock.patch.object(self.w, "client", return_value=object()), \
             mock.patch.object(self.w, "heartbeat"), \
             mock.patch.object(self.w, "housekeeping"), \
             mock.patch.object(self.w, "claim", side_effect=claim), \
             mock.patch.object(self.w.time, "sleep", side_effect=sleeps.append), \
             mock.patch("builtins.print"), \
             mock.patch.dict("os.environ", {"JARVIS_FLAT_AI_WORKER_DISABLE": ""}):
            with self.assertRaises(KeyboardInterrupt):
                self.w.main([])
        # 失敗 3 回は 10→20→40 秒、成功後は通常の 3 秒
        self.assertEqual(sleeps, [10, 20, 40, self.w.POLL_SEC])

    def test_once_returns_error_code_on_failure(self) -> None:
        with mock.patch.object(self.w, "client", return_value=object()), \
             mock.patch.object(self.w, "heartbeat", side_effect=RuntimeError("down")), \
             mock.patch.object(self.w.time, "sleep") as sl, \
             mock.patch("builtins.print"), \
             mock.patch.dict("os.environ", {"JARVIS_FLAT_AI_WORKER_DISABLE": ""}):
            self.assertEqual(self.w.main(["--once"]), 1)
        sl.assert_not_called()


class WeeklyReviewZeroCountTest(unittest.TestCase):
    def setUp(self) -> None:
        self.m = _load("wr314_test", "scripts/jarvis_weekly_review_314.py")

    def _is_error(self, line: str) -> bool:
        return bool(self.m.ERROR_RE.search(self.m.ZERO_COUNT_RE.sub("", line)))

    def test_json_streams_failed_zero_is_not_error(self) -> None:
        line = '{"scan": {"streams_ok": 12, "streams_failed": 0, "messages": 40}}'
        self.assertFalse(self._is_error(line))

    def test_nonzero_still_error(self) -> None:
        self.assertTrue(self._is_error('{"scan": {"streams_failed": 2}}'))
        self.assertTrue(self._is_error("# done ok=0 fail=3 shots=x"))
        self.assertTrue(self._is_error("failed=10"))

    def test_plain_zero_counts_still_ok(self) -> None:
        self.assertFalse(self._is_error("copied=4 unchanged=651 failed=0"))
        self.assertFalse(self._is_error("errors: なし"))


if __name__ == "__main__":
    unittest.main()
