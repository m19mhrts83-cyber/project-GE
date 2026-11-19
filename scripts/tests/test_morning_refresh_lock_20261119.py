"""朝バンドルの実行中ロック（116 の朝の二重投稿対策・2026-11-19）。"""
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import jarvis_morning_mac_refresh as mr  # noqa: E402


class RunLockTest(unittest.TestCase):
    def test_second_process_cannot_take_lock_while_first_holds_it(self):
        with tempfile.TemporaryDirectory() as d:
            lock = Path(d) / "x.lock"
            self.assertTrue(mr.acquire_run_lock(lock))
            code = textwrap.dedent(f"""
                import sys; sys.path.insert(0, {str(SCRIPTS)!r})
                import jarvis_morning_mac_refresh as mr
                from pathlib import Path
                print(mr.acquire_run_lock(Path({str(lock)!r})))
            """)
            out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
            self.assertEqual(out.stdout.strip(), "False")
            mr._RUN_LOCK_FD.close()
            mr._RUN_LOCK_FD = None
            out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
            self.assertEqual(out.stdout.strip(), "True")


if __name__ == "__main__":
    unittest.main()
