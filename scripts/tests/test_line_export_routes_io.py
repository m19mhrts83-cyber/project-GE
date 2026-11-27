"""line_export_routes.yaml 読込の last_good フォールバック（架空の値のみ。OneDrive・LINE には触らない）。"""
import io
import stat
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "215_kamiooya" / "C1_cursor" / "1b_Cursorマニュアル"))
import line_export_routes_io as m  # noqa: E402

YAML = "routes:\n  - id: demo\n    folder: x\nline_oa:\n  group_ids:\n    demo: Cdummy\n"


class RoutesIoTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.dir = Path(self._td.name)
        self.src = self.dir / "routes.yaml"
        self.lg = self.dir / "sub" / "last_good.yaml"
        p = mock.patch.object(m.time, "sleep")
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(self._td.cleanup)

    def test_success_writes_copy_600(self):
        self.src.write_text(YAML, encoding="utf-8")
        self.assertEqual(m.read_routes_text(self.src, last_good=self.lg), YAML)
        self.assertEqual(self.lg.read_text(encoding="utf-8"), YAML)
        self.assertEqual(stat.S_IMODE(self.lg.stat().st_mode), 0o600)

    def test_oserror_falls_back_to_last_good(self):
        self.lg.parent.mkdir(parents=True)
        self.lg.write_text(YAML, encoding="utf-8")
        self.src.write_text("changed", encoding="utf-8")
        err = OSError(11, "Resource deadlock avoided")
        buf = io.StringIO()
        with mock.patch.object(Path, "read_text", side_effect=self._fail_src(err)), redirect_stdout(buf):
            self.assertEqual(m.read_routes_text(self.src, last_good=self.lg), YAML)
        self.assertIn(m.LAST_GOOD_MESSAGE, buf.getvalue())

    def test_retry_then_success(self):
        self.src.write_text(YAML, encoding="utf-8")
        real = Path.read_text
        calls = {"n": 0}

        def flaky(self_, *a, **k):
            calls["n"] += 1
            if calls["n"] < 3:
                raise OSError(11, "Resource deadlock avoided")
            return real(self_, *a, **k)

        with mock.patch.object(Path, "read_text", flaky):
            self.assertEqual(m.read_routes_text(self.src, last_good=self.lg), YAML)
        self.assertEqual(calls["n"], 3)

    def test_no_last_good_raises(self):
        err = OSError(11, "Resource deadlock avoided")
        with mock.patch.object(Path, "read_text", side_effect=err):
            with self.assertRaises(OSError):
                m.read_routes_text(self.src, last_good=self.lg)

    def _fail_src(self, err):
        real = Path.read_text
        src = self.src

        def f(self_, *a, **k):
            if self_ == src:
                raise err
            return real(self_, *a, **k)

        return f


if __name__ == "__main__":
    unittest.main()
