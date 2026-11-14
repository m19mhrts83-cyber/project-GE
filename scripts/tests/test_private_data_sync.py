# -*- coding: utf-8 -*-
"""非公開リポとの行き来（2026-11-14）: 上書きの有無と、main 追従で外してよいファイルの判定。"""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
spec = importlib.util.spec_from_file_location("private_data_sync", REPO / "scripts" / "private_data_sync.py")
pds = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(pds)


class CopyTest(unittest.TestCase):
    def test_push_overwrites_and_restore_keeps_local(self) -> None:
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            src, dst = Path(a), Path(b)
            (src / "x").mkdir()
            (src / "x/f.md").write_text("new", encoding="utf-8")
            (dst / "x").mkdir()
            (dst / "x/f.md").write_text("old", encoding="utf-8")
            self.assertEqual(pds.copy_newer(src, dst, ["x/f.md"], overwrite=True, dry=False), ["x/f.md"])
            self.assertEqual((dst / "x/f.md").read_text(encoding="utf-8"), "new")
            (dst / "x/f.md").write_text("private", encoding="utf-8")
            self.assertEqual(pds.copy_newer(dst, src, ["x/f.md"], overwrite=False, dry=False), [])
            self.assertEqual((src / "x/f.md").read_text(encoding="utf-8"), "new")
            (dst / "x/g.md").write_text("only private", encoding="utf-8")
            self.assertEqual(pds.copy_newer(dst, src, ["x/g.md"], overwrite=False, dry=False), ["x/g.md"])

    def test_private_dir_env(self) -> None:
        with mock.patch.dict(os.environ, {"PRIVATE_DATA_REPO_DIR": "/tmp/pp"}):
            self.assertEqual(pds.private_dir(), Path("/tmp/pp"))

    def test_skip_without_clone(self) -> None:
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"PRIVATE_DATA_REPO_DIR": d}), \
                mock.patch("builtins.print"):
            self.assertEqual(pds.main(["push"]), 0)


class ScopeTest(unittest.TestCase):
    """写す範囲: ブラウザのプロファイル等の実データは写さず、名前を出した記録だけ写す。"""

    def test_sync_list_skips_runtime_data(self) -> None:
        import subprocess
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            (root / "config").mkdir()
            (root / "config/private_sync_paths.txt").write_text(
                (REPO / "config/private_sync_paths.txt").read_text(encoding="utf-8"), encoding="utf-8")
            files = {
                ".jarvis_state/car_loan.json": True,
                ".jarvis_state/nagoya_water_card/07_done.png": True,
                ".jarvis_state/mf_me_browser_profile/Default/Cookies": False,
                ".jarvis_state/cursor_usage_chrome/Cache/data_0": False,
                "215_kamiooya/C2_ルーティン作業/a.md": True,
                "scripts/x.py": False,
            }
            for rel in files:
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text("x", encoding="utf-8")
            big = root / "215_kamiooya/C2_ルーティン作業/big.bin"
            with big.open("wb") as f:
                f.truncate(pds.MAX_BYTES + 1)
            with mock.patch.object(pds, "REPO", root), \
                    mock.patch.object(pds, "PATTERNS", root / "config/private_sync_paths.txt"):
                got = set(pds.public_files())
            self.assertEqual(got, {k for k, v in files.items() if v})


if __name__ == "__main__":
    unittest.main()
