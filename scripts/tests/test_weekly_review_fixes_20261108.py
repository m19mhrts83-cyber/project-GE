# -*- coding: utf-8 -*-
"""314 機械チェック 2026-11-08: ネット不通の回を黙って exit 0 にしない。"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))


def _load():
    spec = importlib.util.spec_from_file_location("wr314", REPO / "scripts/jarvis_weekly_review_314.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    return mod


class RetryTests(unittest.TestCase):
    def setUp(self):
        self.m = _load()
        self.slept: list[int] = []

    def test_with_retry_recovers(self):
        calls = {"n": 0}

        def fn():
            calls["n"] += 1
            if calls["n"] < 3:
                raise RuntimeError("dns")
            return "ok"

        self.assertEqual(self.m.with_retry(fn, (1, 2), sleep=self.slept.append), "ok")
        self.assertEqual(self.slept, [1, 2])

    def test_with_retry_raises_last(self):
        def fn():
            raise RuntimeError("down")

        with self.assertRaises(RuntimeError):
            self.m.with_retry(fn, (1,), sleep=self.slept.append)
        self.assertEqual(self.slept, [1])

    def test_post_slack_retries_then_fails(self):
        runs = []

        def run(cmd, **_kw):
            runs.append(cmd)
            return SimpleNamespace(returncode=1)

        ok = self.m.post_slack(["x"], waits=(5, 6), sleep=self.slept.append, run=run)
        self.assertFalse(ok)
        self.assertEqual(len(runs), 3)
        self.assertEqual(self.slept, [5, 6])

    def test_post_slack_ok_second_try(self):
        rcs = iter([1, 0])
        ok = self.m.post_slack(
            ["x"], waits=(5, 6), sleep=self.slept.append,
            run=lambda cmd, **kw: SimpleNamespace(returncode=next(rcs)),
        )
        self.assertTrue(ok)
        self.assertEqual(self.slept, [5])


if __name__ == "__main__":
    unittest.main()
