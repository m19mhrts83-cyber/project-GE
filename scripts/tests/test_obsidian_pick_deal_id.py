#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S3 frontmatter の deal_id が「未取得」等の非 UUID でも同期全体を落とさない."""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _load():
    path = SCRIPTS / "jarvis_kurashift_obsidian_pick_sync.py"
    spec = importlib.util.spec_from_file_location("jarvis_kurashift_obsidian_pick_sync", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ops = _load()

_UUID = "3f2b8c1e-9a4d-4e6f-8b7a-1c2d3e4f5a6b"


def _write(tmp: Path, deal_id: str) -> Path:
    p = tmp / "2026-09-30_瀬戸市_松原町3丁目_S3.md"
    p.write_text(
        "---\n"
        "type: s3_supply\n"
        "verdict: hold\n"
        "address: 愛知県瀬戸市松原町3丁目\n"
        f"deal_id: {deal_id}\n"
        "---\n本文\n",
        encoding="utf-8",
    )
    return p


class TestDealIdParse(unittest.TestCase):
    def test_placeholder_becomes_none(self):
        with tempfile.TemporaryDirectory() as d:
            data = ops.parse_s3_file(_write(Path(d), "未取得"))
        self.assertIsNotNone(data)
        self.assertIsNone(data["deal_id"])

    def test_uuid_kept(self):
        with tempfile.TemporaryDirectory() as d:
            data = ops.parse_s3_file(_write(Path(d), _UUID))
        self.assertEqual(data["deal_id"], _UUID)


if __name__ == "__main__":
    unittest.main()
