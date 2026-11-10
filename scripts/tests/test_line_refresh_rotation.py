"""LINE refreshToken のローテーション保存とロック（偽の応答。LINE には触らない）。"""
import multiprocessing as mp
import sys
import tempfile
import time
import unittest
from hashlib import md5
from pathlib import Path

POC = Path(__file__).resolve().parents[2] / "line_unofficial_poc"
sys.path.insert(0, str(POC))
import chrline_client_utils as u  # noqa: E402

A0, A1, A2 = "A" * 40, "B" * 40, "C" * 40
R0, R1 = "r" * 40, "s" * 40


class FakeCL:
    def __init__(self, token, resp):
        self.authToken = token
        self.resp = resp
        self.calls = []

    def refreshAccessToken(self, rt):
        self.calls.append(rt)
        return self.resp

    def checkAndGetValue(self, obj, name, idx):
        return obj.get(idx)


def seed(root: Path, access=A0, rt=R0):
    u.persist_auth_token(root, access)
    u.save_refresh_token(root, access, rt)


class RotationTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.root = Path(self.t.name)

    def tearDown(self):
        self.t.cleanup()

    def test_new_refresh_token_is_saved_not_old(self):
        seed(self.root)
        cl = FakeCL(A0, {1: A1, 5: R1})
        self.assertTrue(u.refresh_access_token_locked(cl, self.root))
        self.assertEqual(cl.calls, [R0])
        self.assertEqual(cl.authToken, A1)
        self.assertEqual((self.root / ".tokens" / "latest").read_text(), A1)
        self.assertEqual((self.root / ".refreshToken" / "latest").read_text(), R1)
        self.assertEqual((self.root / ".refreshToken" / md5(A1.encode()).hexdigest()).read_text(), R1)
        self.assertEqual(u.read_refresh_token_for(self.root, A1), R1)

    def test_no_new_refresh_token_keeps_current(self):
        seed(self.root)
        cl = FakeCL(A0, {1: A1})
        u.refresh_access_token_locked(cl, self.root)
        self.assertEqual(u.read_refresh_token_for(self.root, A1), R0)

    def test_already_refreshed_by_other_process_skips_line(self):
        seed(self.root)
        u.persist_auth_token(self.root, A2)  # 他プロセスが更新済み
        cl = FakeCL(A0, {1: A1, 5: R1})
        u.refresh_access_token_locked(cl, self.root)
        self.assertEqual(cl.calls, [])
        self.assertEqual(cl.authToken, A2)

    def test_missing_refresh_token_raises(self):
        u.persist_auth_token(self.root, A0)
        with self.assertRaises(ValueError):
            u.refresh_access_token_locked(FakeCL(A0, {1: A1}), self.root)

    def test_lock_is_reentrant_in_process(self):
        with u._refresh_lock(self.root):
            with u._refresh_lock(self.root):
                pass  # 固まらない

    def test_install_overrides_tryRefreshToken(self):
        seed(self.root)
        cl = u.install_rotation_safe_refresh(FakeCL(A0, {1: A1, 5: R1}), self.root)
        self.assertTrue(cl.tryRefreshToken())
        self.assertEqual(u.read_refresh_token_for(self.root, A1), R1)


def _hold(root, sec):
    sys.path.insert(0, str(POC))
    import chrline_client_utils as uu
    with uu._refresh_lock(Path(root)):
        time.sleep(sec)


class CrossProcessTests(unittest.TestCase):
    def test_second_process_waits_for_lock(self):
        with tempfile.TemporaryDirectory() as t:
            p = mp.get_context("spawn").Process(target=_hold, args=(t, 1.5))
            p.start()
            time.sleep(0.8)
            t0 = time.time()
            with u._refresh_lock(Path(t)):
                waited = time.time() - t0
            p.join()
            self.assertGreater(waited, 0.3)


if __name__ == "__main__":
    unittest.main()
