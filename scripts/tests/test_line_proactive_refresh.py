"""LINE 先回り延長（2026-11-18 案A＋B）。偽の応答だけで確かめる。LINE には触らない。"""
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

POC = Path(__file__).resolve().parents[2] / "line_unofficial_poc"
sys.path.insert(0, str(POC))
import chrline_client_utils as u  # noqa: E402

A0, A1 = "A" * 40, "B" * 40
R0, R1 = "r" * 40, "s" * 40
HOUR = 3600.0


class FakeCL:
    def __init__(self, token, resp=None, exc=None):
        self.authToken = token
        self.resp = resp
        self.exc = exc
        self.calls = []
        self.logged = []

    def refreshAccessToken(self, rt):
        self.calls.append(rt)
        if self.exc:
            raise self.exc
        return self.resp

    def checkAndGetValue(self, obj, name, idx):
        return obj.get(idx)

    def log(self, text, debugOnly=False):
        self.logged.append(text)


def seed(root: Path, access=A0, rt=R0):
    u.persist_auth_token(root, access)
    u.save_refresh_token(root, access, rt)


class ProactiveTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.root = Path(self.t.name)
        self.env = mock.patch.dict(os.environ, {}, clear=False)
        self.env.start()
        for k in (
            "LINE_PROACTIVE_REFRESH_RATIO",
            "LINE_PROACTIVE_REFRESH_DEFAULT_HOURS",
            "LINE_PROACTIVE_REFRESH_MIN_GAP_MINUTES",
        ):
            os.environ.pop(k, None)

    def tearDown(self):
        self.env.stop()
        self.t.cleanup()

    def test_refresh_writes_schedule_from_response(self):
        seed(self.root)
        now = time.time()
        cl = FakeCL(A0, {1: A1, 2: 10 * HOUR, 4: int(now), 5: R1})
        u.refresh_access_token_locked(cl, self.root)
        d = u.read_refresh_schedule(self.root)
        self.assertEqual(d["duration_sec"], 10 * HOUR)
        self.assertAlmostEqual(d["next_due_at"], now + 5 * HOUR, delta=5)  # 既定 50%
        text = (self.root / u.REFRESH_SCHEDULE_FILE).read_text()
        for secret in (A0, A1, R0, R1):
            self.assertNotIn(secret, text)  # トークン値は書かない

    def test_schedule_without_duration_uses_default(self):
        now = 1_000_000.0
        d = u.write_refresh_schedule(self.root, duration_sec=None, now=now)
        self.assertEqual(d["next_due_at"], now + 24 * HOUR)

    def test_schedule_never_shorter_than_min_gap(self):
        now = 1_000_000.0
        d = u.write_refresh_schedule(self.root, duration_sec=60, now=now)
        self.assertEqual(d["next_due_at"], now + HOUR)

    def test_not_due_does_nothing(self):
        seed(self.root)
        now = time.time()
        u.write_refresh_schedule(self.root, duration_sec=10 * HOUR, now=now)
        cl = FakeCL(A0, {1: A1, 5: R1})
        self.assertEqual(u.maybe_proactive_refresh(cl, self.root, now=now + HOUR), "")
        self.assertEqual(cl.calls, [])

    def test_due_refreshes_and_saves_new_refresh_token(self):
        seed(self.root)
        now = time.time()
        u.write_refresh_schedule(self.root, duration_sec=10 * HOUR, now=now - 6 * HOUR)
        cl = FakeCL(A0, {1: A1, 2: 10 * HOUR, 5: R1})
        self.assertEqual(u.maybe_proactive_refresh(cl, self.root, now=now), "ok:due")
        self.assertEqual(cl.calls, [R0])
        self.assertEqual((self.root / ".refreshToken" / "latest").read_text(), R1)
        self.assertEqual((self.root / ".tokens" / "latest").read_text(), A1)

    def test_failure_is_recorded_and_backs_off(self):
        seed(self.root)
        now = time.time()
        u.write_refresh_schedule(self.root, duration_sec=2 * HOUR, now=now - 2 * HOUR)
        cl = FakeCL(A0, exc=Exception("Invalid response status code: 404"))
        self.assertEqual(u.maybe_proactive_refresh(cl, self.root, now=now), "fail:due")
        d = u.read_refresh_schedule(self.root)
        self.assertIn("404", d["last_error"])
        # 直後はもう叩かない（1 時間あける）
        self.assertEqual(u.maybe_proactive_refresh(cl, self.root, now=now + 60), "")
        self.assertEqual(len(cl.calls), 1)
        self.assertEqual(u.maybe_proactive_refresh(cl, self.root, now=now + HOUR + 1), "fail:due")

    def test_refresh_required_header_triggers_refresh(self):
        seed(self.root)
        now = time.time()
        u.write_refresh_schedule(self.root, duration_sec=100 * HOUR, now=now - 2 * HOUR)
        cl = FakeCL(A0, {1: A1, 2: 100 * HOUR, 5: R1})
        u.install_rotation_safe_refresh(cl, self.root)
        cl.log("[HTTP] unhandled header:  x-line-access-refresh-required => 1")
        self.assertTrue(cl.logged)  # 元の記録も残る
        self.assertEqual(u.maybe_proactive_refresh(cl, self.root, now=now), "ok:refresh_required")
        self.assertEqual(cl._lp_refresh_required_at, 0.0)  # 延長したら印を下ろす
        self.assertEqual(u.maybe_proactive_refresh(cl, self.root, now=now + 60), "")

    def test_other_headers_do_not_trigger(self):
        seed(self.root)
        u.write_refresh_schedule(self.root, duration_sec=100 * HOUR)
        cl = FakeCL(A0, {1: A1})
        u.install_refresh_required_hook(cl)
        cl.log("[HTTP] unhandled header:  x-something => 1")
        self.assertEqual(u.maybe_proactive_refresh(cl, self.root), "")

    def test_hook_installs_once(self):
        cl = FakeCL(A0)
        u.install_refresh_required_hook(cl)
        first = cl.log
        u.install_refresh_required_hook(cl)
        self.assertIs(cl.log, first)

    def test_no_schedule_counts_from_saved_refresh_token(self):
        seed(self.root)
        cl = FakeCL(A0, {1: A1, 5: R1})
        latest = self.root / ".refreshToken" / "latest"
        now = latest.stat().st_mtime
        self.assertEqual(u.maybe_proactive_refresh(cl, self.root, now=now + HOUR), "")
        self.assertEqual(u.maybe_proactive_refresh(cl, self.root, now=now + 25 * HOUR), "ok:no_schedule")

    def test_other_process_already_refreshed_skips_line(self):
        seed(self.root)
        now = time.time()
        u.write_refresh_schedule(self.root, duration_sec=2 * HOUR, now=now - 2 * HOUR)
        u.persist_auth_token(self.root, A1)  # 他プロセスが延長済み
        cl = FakeCL(A0, {1: "X" * 40})
        self.assertEqual(u.maybe_proactive_refresh(cl, self.root, now=now), "ok:due")
        self.assertEqual(cl.calls, [])
        self.assertEqual(cl.authToken, A1)


if __name__ == "__main__":
    unittest.main()
