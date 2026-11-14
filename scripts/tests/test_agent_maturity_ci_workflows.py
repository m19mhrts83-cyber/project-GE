# -*- coding: utf-8 -*-
"""CI 通過率は PR 時のチェック全部（2026-11-14 に分割）を合計する。まだ無いワークフローの 404 は飛ばす。"""
from __future__ import annotations

import importlib.util
import io
import os
import sys
import unittest
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
spec = importlib.util.spec_from_file_location("maturity_ci_test", REPO / "scripts" / "jarvis_agent_maturity.py")
m = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(m)


class CiPassRateTest(unittest.TestCase):
    def test_sums_all_pr_workflows_and_skips_missing(self) -> None:
        def gh(path, params=None):
            if "/search/" in path:
                return {"items": []}
            if "pr-loopware.yml" in path:
                raise urllib.error.HTTPError(path, 404, "nf", {}, io.BytesIO())
            if "pr-checks.yml" in path:
                return {"workflow_runs": [{"conclusion": "success"}] * 3 + [{"conclusion": "failure"}]}
            if "pr-jarvis-dashboard.yml" in path:
                return {"workflow_runs": [{"conclusion": "success"}]}
            return {"workflow_runs": []}

        out: dict = {}
        missing: dict = {}
        meta = {"fix_pr_ratio": {"min_n": 99}, "ci_pass_rate": {"min_n": 1}}
        with mock.patch.object(m, "gh", side_effect=gh), mock.patch.dict(os.environ, {"GITHUB_TOKEN": "x"}):
            m.m_github(datetime(2026, 11, 1, tzinfo=timezone.utc), out, missing, meta)
        self.assertIn("ci_pass_rate", out, missing)
        self.assertEqual((out["ci_pass_rate"].get("num"), out["ci_pass_rate"].get("den")), (4, 5))


if __name__ == "__main__":
    unittest.main()
