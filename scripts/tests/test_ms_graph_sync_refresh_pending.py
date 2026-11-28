"""python3 -m unittest scripts/tests/test_ms_graph_sync_refresh_pending.py
pending（回転した鍵）は GHA push 成功後だけ消えること。トークン値はテスト用ダミー。"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jarvis_ms_graph_sync_refresh as m  # noqa: E402
import jarvis_ms_graph_secrets_to_gha as g  # noqa: E402


class PendingTest(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.priv = self.d / "private.env"
        self.priv.write_text("MS_GRAPH_REFRESH_TOKEN='old'\n", encoding="utf-8")
        self.pend = self.d / "pending.env"
        self.pend.write_text("MS_GRAPH_REFRESH_TOKEN=dummy-new\n", encoding="utf-8")
        self.patches = [
            mock.patch.object(m, "PRIVATE", self.priv),
            mock.patch.object(m, "NEW_REFRESH", self.pend),
            mock.patch.dict(os.environ, {}, clear=False),
        ]
        for p in self.patches:
            p.start()
        os.environ.pop("JARVIS_MS_GRAPH_USE_SYNC_META", None)

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def _run(self, rc):
        cp = subprocess.CompletedProcess([], rc, stdout="", stderr="")
        return mock.patch.object(m.subprocess, "run", return_value=cp)

    def test_push_failure_keeps_pending(self):
        with self._run(1):
            with self.assertRaises(SystemExit):
                m.apply_rotated_refresh(push_gha=True)
        self.assertTrue(self.pend.is_file())
        self.assertIn("dummy-new", self.priv.read_text())

    def test_push_success_removes_pending(self):
        with self._run(0):
            m.apply_rotated_refresh(push_gha=True)
        self.assertFalse(self.pend.exists())

    def test_find_gh_uses_home_bin(self):
        home = self.d / "home"
        (home / "bin").mkdir(parents=True)
        gh = home / "bin" / "gh"
        gh.write_text("#!/bin/sh\n")
        gh.chmod(0o755)
        with mock.patch.object(g.shutil if hasattr(g, "shutil") else __import__("shutil"), "which", return_value=None), \
                mock.patch.object(g.Path, "home", return_value=home):
            self.assertEqual(g.find_gh(), str(gh))


if __name__ == "__main__":
    unittest.main()
