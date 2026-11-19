# -*- coding: utf-8 -*-
"""GHA の調査用ファイルを非公開バケットへ（2026-11-20）: 集め方・鍵なし時の扱い。"""
from __future__ import annotations

import importlib.util
import io
import os
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("gha_private_artifact_t", REPO / "scripts" / "gha_private_artifact.py")
m = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(m)


class CollectPackTest(unittest.TestCase):
    def test_collect_dirs_and_globs(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "a").mkdir()
            (root / "a" / "x.csv").write_text("1")
            (root / "a" / "sub").mkdir()
            (root / "a" / "sub" / "y.png").write_bytes(b"p")
            (root / "z_1.json").write_text("{}")
            files = m._collect([str(root / "a"), str(root / "z_*.json"), str(root / "none/")])
            self.assertEqual(sorted(p.name for p in files), ["x.csv", "y.png", "z_1.json"])
            blob = m._pack(files)
            with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as t:
                self.assertEqual(len(t.getnames()), 3)

    def test_no_files_is_noop(self) -> None:
        self.assertEqual(m.main(["--name", "t", "/nonexistent/**/*.csv"]), 0)

    def test_missing_keys_warns_but_exits_zero(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".log") as f:
            env = {k: v for k, v in os.environ.items() if "SUPABASE" not in k}
            with mock.patch.dict(os.environ, env, clear=True):
                self.assertEqual(m.main(["--name", "t", f.name]), 0)


if __name__ == "__main__":
    unittest.main()
