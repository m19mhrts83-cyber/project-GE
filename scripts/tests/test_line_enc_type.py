"""CHRLINE の送信方式（2026-11-18 LINE が /enc を閉鎖 → LEGY 直送を既定に）。LINE には触らない。"""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "line_unofficial_poc"))
import chrline_client_utils as u  # noqa: E402


class EncTypeTests(unittest.TestCase):
    def test_default_is_direct_legy(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LINE_CHRLINE_ENC_TYPE", None)
            self.assertEqual(u.chrline_enc_type_from_env(), 0)
            self.assertEqual(u.chrline_constructor_kwargs()["encType"], 0)

    def test_env_can_restore_enc_gateway(self):
        with mock.patch.dict(os.environ, {"LINE_CHRLINE_ENC_TYPE": "1"}):
            self.assertEqual(u.chrline_constructor_kwargs()["encType"], 1)

    def test_unknown_value_falls_back_to_direct(self):
        with mock.patch.dict(os.environ, {"LINE_CHRLINE_ENC_TYPE": "x"}):
            self.assertEqual(u.chrline_enc_type_from_env(), 0)


if __name__ == "__main__":
    unittest.main()
