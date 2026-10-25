"""Q08: 取得不能は正常・認証切れと断定せず、他の監視を継続。"""
import sys
import unittest
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock
import json

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jarvis_freshness_watch as fw


class UnknownTests(unittest.TestCase):
    def test_mirror_state_persists_without_age_limit(self):
        with tempfile.TemporaryDirectory() as d:
            cfg, state = Path(d) / "config.yaml", Path(d) / "state.json"
            cfg.write_text("products: []")
            row = dict(id="m", label="Mirror", last=None, age_h=None, stale=False, status="ok", why="内容一致", kind="mirror_content")
            with mock.patch.object(fw, "CONFIG", cfg), mock.patch.object(fw, "STATE", state), mock.patch.object(fw, "evaluate", return_value=[row]), mock.patch.object(sys, "argv", ["watch"]), mock.patch.dict(fw.os.environ, {"JARVIS_FRESHNESS_WATCH_DISABLE": "0"}):
                self.assertEqual(fw.main(), 0)
            saved = json.loads(state.read_text())
            self.assertEqual(saved["rows"][0]["status"], "ok")
            self.assertIsNone(saved["rows"][0]["max_age_h"])

    def test_mirror_content_checks_bytes_and_missing(self):
        with tempfile.TemporaryDirectory() as d:
            source, mirror = Path(d) / "source.md", Path(d) / "mirror.md"
            source.write_text("v2")
            mirror.write_text("v1")
            cfg = {"products": [{"id": "mirror", "kind": "mirror_content", "source": str(source), "mirror": str(mirror)}]}
            def status():
                return fw.evaluate(cfg, datetime.now(timezone.utc))[0]["status"]
            self.assertEqual(status(), "stale")
            mirror.write_text("v2")
            self.assertEqual(status(), "ok")
            mirror.unlink()
            self.assertEqual(status(), "unknown")

    def test_timeout_does_not_stop_other_products_or_leak_exception(self):
        now = datetime.now(timezone.utc)
        cfg = {"products": [dict(id=x, label=x, max_age_h=24, owner="315", action="確認") for x in ("a", "b")]}
        def getter(p):
            if p["id"] == "a":
                raise subprocess.TimeoutExpired("SECRET_SENTINEL", 1)
            return now, ""
        rows = fw.evaluate(cfg, now, getter)
        self.assertEqual([r["status"] for r in rows], ["unknown", "ok"])
        message = fw.build_message([rows[0]], [])
        self.assertIn("未確認", message)
        self.assertNotIn("SECRET_SENTINEL", message)

    def test_missing_timestamp_is_unknown(self):
        rows = fw.evaluate({"products": [{"id": "x", "max_age_h": 24}]}, datetime.now(timezone.utc), lambda _: (None, "成功履歴なし"))
        self.assertEqual(rows[0]["status"], "unknown")
        self.assertTrue(rows[0]["stale"])
