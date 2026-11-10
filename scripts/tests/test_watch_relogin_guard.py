import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

POC = Path(__file__).resolve().parents[2] / "line_unofficial_poc"
sys.path.insert(0, str(POC))
import watch_relogin_guard as g  # noqa: E402


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.m = Path(self.tmp.name) / "marker.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_mark_keeps_created_and_clear(self):
        self.assertIsNone(g.read_marker(self.m))
        g.write_marker("403", self.m)
        first = g.read_marker(self.m)["created_at"]
        g.write_marker("403 again", self.m)
        self.assertEqual(g.read_marker(self.m)["created_at"], first)
        self.assertTrue(g.clear_marker(self.m))
        self.assertFalse(g.clear_marker(self.m))

    def test_notify_once_text_and_dedupe(self):
        self.assertEqual(g.notify_once(dry_run=True, path=self.m), "no_marker")
        g.write_marker("403", self.m)
        self.assertEqual(g.notify_once(dry_run=True, path=self.m), "dry_run")
        t = g.notify_text(g.read_marker(self.m))
        self.assertEqual(t.splitlines()[1], "判定: 🔴 要対応")
        self.assertIn("--allow-qr-login", t)
        d = g.read_marker(self.m)
        d["notified_at"] = "2026-11-10T09:00:00+09:00"
        self.m.write_text(json.dumps(d), encoding="utf-8")
        self.assertEqual(g.notify_once(dry_run=False, path=self.m), "already_notified")

    def test_check_exit_codes(self):
        env = {**os.environ, "LINE_WATCH_RELOGIN_MARKER": str(self.m)}
        cmd = [sys.executable, str(POC / "watch_relogin_guard.py"), "--check"]
        self.assertEqual(subprocess.run(cmd, env=env).returncode, 0)
        g.write_marker("403", self.m)
        self.assertEqual(subprocess.run(cmd, env=env).returncode, 3)


class RunnerTests(unittest.TestCase):
    """runner を偽の run_patch.sh で動かす（LINE には触らない・投稿もしない）。"""

    def _runner(self, d: Path, fake_rc: int, mark: bool) -> Path:
        (d / "launchd").mkdir()
        src = (POC / "launchd" / "open_chat_watch_runner.sh").read_text(encoding="utf-8")
        src = src.replace("while /usr/bin/pgrep", "while false && /usr/bin/pgrep")  # Mac版LINE待ちは飛ばす
        (d / "launchd" / "open_chat_watch_runner.sh").write_text(src, encoding="utf-8")
        (d / "open_chat_routes.yaml").write_text("x: 1\n", encoding="utf-8")
        (d / "watch_relogin_guard.py").write_text((POC / "watch_relogin_guard.py").read_text(encoding="utf-8"))
        body = "#!/bin/zsh\necho ran >> \"$RAN_LOG\"\n"
        if mark:
            body += f"/usr/bin/python3 -c 'import sys; sys.path.insert(0, \"{d}\"); import watch_relogin_guard as g; g.write_marker(\"403\")'\n"
        body += f"exit {fake_rc}\n"
        (d / "run_patch.sh").write_text(body, encoding="utf-8")
        for f in ("run_patch.sh", "launchd/open_chat_watch_runner.sh"):
            os.chmod(d / f, 0o755)
        return d / "launchd" / "open_chat_watch_runner.sh"

    def test_token_invalid_then_wait_without_touching_line(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            env = {**os.environ, "LINE_WATCH_RELOGIN_MARKER": str(d / "m.json"), "RAN_LOG": str(d / "ran.log"),
                   "LINE_WATCH_NOTIFY_DRY_RUN": "1", "LINE_WATCH_RELOGIN_POLL_SEC": "1"}
            r = self._runner(d, fake_rc=2, mark=True)
            p = subprocess.run(["/bin/zsh", str(r)], env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(p.returncode, 0)              # 印が付いたら 0 で静かに終わる
            self.assertIn("判定: 🔴 要対応", p.stdout)     # 知らせ（dry-run）
            self.assertTrue((d / "m.json").is_file())
            # 2 回目の起動: 印がある間は run_patch を呼ばずに待つ
            with self.assertRaises(subprocess.TimeoutExpired):
                subprocess.run(["/bin/zsh", str(r)], env=env, capture_output=True, text=True, timeout=4)
            self.assertEqual((d / "ran.log").read_text().count("ran"), 1)

    def test_normal_exit_passes_rc_through(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            env = {**os.environ, "LINE_WATCH_RELOGIN_MARKER": str(d / "m.json"), "RAN_LOG": str(d / "ran.log"),
                   "LINE_WATCH_NOTIFY_DRY_RUN": "1"}
            r = self._runner(d, fake_rc=1, mark=False)
            p = subprocess.run(["/bin/zsh", str(r)], env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(p.returncode, 1)
            self.assertFalse((d / "m.json").exists())


if __name__ == "__main__":
    unittest.main()
