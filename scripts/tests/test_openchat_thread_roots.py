"""オプチャのスレッド元投稿: LINE 応答の読み取りと DB へ渡す形（2026-11-18）。"""
import importlib.util
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# chrline_client_utils は CHRLINE 本体を要するので、テストでは差し替える
_stub = types.ModuleType("chrline_client_utils")
_stub.build_logged_in_client = lambda *a, **k: None
_stub.chrline_throttle = lambda: None
_stub.save_root_from_env = lambda: Path(".")
sys.modules.setdefault("chrline_client_utils", _stub)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


roots = _load("chrline_openchat_thread_roots", ROOT / "line_unofficial_poc/chrline_openchat_thread_roots.py")
apply_mod = _load("jarvis_openchat_thread_roots_apply", ROOT / "scripts/jarvis_openchat_thread_roots_apply.py")


class ParseThreadResponseTest(unittest.TestCase):
    def test_root_message_fields(self):
        # 2026-11-18 に実際に返った形（番号キー）
        res = {
            1: {1: "t19496735cb2523c2d056b7467cf76aab", 2: "m3c6", 4: "641008238686634227"},
            3: {1: {1: "p2585", 4: "641008238686634227", 5: 1794901987649, 10: "物件名変えてリニューアル募集したら"}},
        }
        out = roots.parse_thread_response(res)
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["root_message_id"], "641008238686634227")
        self.assertEqual(out["root_text"], "物件名変えてリニューアル募集したら")
        self.assertTrue(out["root_posted_at"].startswith("2026-11-17T07:53:07"))

    def test_image_root_has_no_text(self):
        out = roots.parse_thread_response({1: {4: "1"}, 3: {1: {4: "1", 5: 1794901987649}}})
        self.assertEqual(out["status"], "ok")
        self.assertIsNone(out["root_text"])

    def test_empty_response(self):
        self.assertEqual(roots.parse_thread_response({})["status"], "no_root")

    def test_deleted_error(self):
        self.assertEqual(roots._classify_error(RuntimeError("Code: 404, Message: 此討論串已被刪除。")), "deleted")
        self.assertEqual(roots._classify_error(RuntimeError("timeout")), "error")


class BuildPayloadTest(unittest.TestCase):
    def test_keys_match_line_openchat_logs_thread_title(self):
        self.assertEqual(apply_mod.thread_keys("t19496735cb2523c2d056b7467cf76aab", None), ["「t1949673…」"])
        self.assertEqual(
            apply_mod.thread_keys("t19496735cb2523c2d056b7467cf76aab", "物件名の相談"),
            ["「t1949673…」", "「物件名の相談」"],
        )

    def test_only_final_statuses_are_sent(self):
        data = {
            "threads": {
                "t1111111111111111": {"status": "ok", "chat_title": "A", "root_text": "x"},
                "t2222222222222222": {"status": "deleted", "chat_title": "A"},
                "t3333333333333333": {"status": "error", "chat_title": "A"},
                "t4444444444444444": {"status": "ok", "chat_title": ""},
            }
        }
        payload = apply_mod.build_payload(data)
        self.assertEqual([p["thread_mid"] for p in payload], ["t1111111111111111", "t2222222222222222"])


class DeletedRetryTest(unittest.TestCase):
    def _at(self, s):
        from datetime import datetime, timezone
        return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)

    def test_retry_once_after_20h_within_30d(self):
        rec = {"status": "deleted", "fetched_at": "2026-11-18T00:00:00+00:00"}
        self.assertFalse(roots.deleted_retry_due(rec, self._at("2026-11-18T10:00:00")))
        self.assertTrue(roots.deleted_retry_due(rec, self._at("2026-11-18T21:00:00")))
        self.assertFalse(roots.deleted_retry_due({**rec, "retries": 1}, self._at("2026-11-18T21:00:00")))

    def test_no_retry_after_30_days_or_other_status(self):
        rec = {"status": "deleted", "fetched_at": "2026-11-18T00:00:00+00:00", "first_fetched_at": "2026-10-01T00:00:00+00:00"}
        self.assertFalse(roots.deleted_retry_due(rec, self._at("2026-11-19T00:00:00")))
        self.assertFalse(roots.deleted_retry_due({"status": "ok", "fetched_at": "2026-11-01T00:00:00+00:00"}, self._at("2026-11-19T00:00:00")))


if __name__ == "__main__":
    unittest.main()
