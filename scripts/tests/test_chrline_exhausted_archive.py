"""retry キュー exhausted の退避と、exhausted 警告の差分判定（ダミーデータのみ）。"""
from __future__ import annotations

import importlib
import json
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path

POC = Path(__file__).resolve().parents[2] / "line_unofficial_poc"


def _load(name: str):
    sys.path.insert(0, str(POC))
    try:
        return importlib.import_module(name)
    finally:
        sys.path.remove(str(POC))


def _load_health():
    # CHRLINE/dotenv が無い環境でも評価ロジックだけ試せるよう、重い依存をスタブ化する
    stubs = {
        "chrline_client_utils": types.SimpleNamespace(save_root_from_env=lambda: Path(".")),
        "chrline_placeholder_inventory": types.SimpleNamespace(
            _line_default_md_paths=lambda: [], build_inventory=lambda **k: {}
        ),
    }
    saved = {k: sys.modules.get(k) for k in stubs}
    sys.modules.update(stubs)
    try:
        sys.modules.pop("chrline_line_health", None)
        return _load("chrline_line_health")
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


arc = _load("chrline_retry_queue_archive")
health = _load_health()
NOW = time.time()
DAY = 86400


def item(dk, *, status="exhausted", days_ago=10, route="/nonexistent-dummy/dir/5.md"):
    return {"dk": dk, "status": status, "route_path": route, "ts": int((NOW - days_ago * DAY) * 1000),
            "date_part": "2026/01/01", "body_raw": "dummy"}


class ClassifyTest(unittest.TestCase):
    def test_reasons(self):
        with tempfile.TemporaryDirectory() as d:
            ok_route = str(Path(d) / "5.md")
            self.assertEqual(arc.classify(item("a"), now=NOW, older_than_days=180), "missing_dir")
            self.assertEqual(arc.classify(item("b", days_ago=200, route=ok_route), now=NOW, older_than_days=180), "old")
            self.assertIsNone(arc.classify(item("c", days_ago=10, route=ok_route), now=NOW, older_than_days=180))

    def test_active_never_targeted(self):
        self.assertIsNone(arc.classify(item("a", status="active", days_ago=999), now=NOW, older_than_days=180))


class ArchiveTest(unittest.TestCase):
    def _setup(self, d):
        root = Path(d)
        ok_route = str(root / "5.md")
        items = {
            "x1": item("x1"),                                   # フォルダなし
            "x2": item("x2", days_ago=300, route=ok_route),     # 古い
            "x3": item("x3", days_ago=5, route=ok_route),       # 残る exhausted
            "a1": item("a1", status="active", route=ok_route),  # active
        }
        (root / arc.QUEUE_FILENAME).write_text(json.dumps({"items": items}), encoding="utf-8")
        return root, items

    def test_dry_run_changes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            root, _ = self._setup(d)
            before = (root / arc.QUEUE_FILENAME).read_bytes()
            self.assertEqual(arc.main(["--save-root", d]), 0)
            self.assertEqual((root / arc.QUEUE_FILENAME).read_bytes(), before)
            self.assertFalse((root / arc.ARCHIVE_FILENAME).exists())
            self.assertEqual(list(root.glob("*.bak_*")), [])

    def test_apply_archives_with_backup_and_keeps_active(self):
        with tempfile.TemporaryDirectory() as d:
            root, items = self._setup(d)
            before = (root / arc.QUEUE_FILENAME).read_bytes()
            self.assertEqual(arc.main(["--save-root", d, "--apply"]), 0)
            q = json.loads((root / arc.QUEUE_FILENAME).read_text())["items"]
            a = json.loads((root / arc.ARCHIVE_FILENAME).read_text())["items"]
            self.assertEqual(sorted(q), ["a1", "x3"])
            self.assertEqual(sorted(a), ["x1", "x2"])
            self.assertEqual(q["a1"], items["a1"])
            self.assertEqual(a["x1"]["archive_reason"], "missing_dir")
            self.assertEqual(a["x2"]["archive_reason"], "old")
            backups = list(root.glob(arc.QUEUE_FILENAME + ".bak_*"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), before)

    def test_apply_twice_is_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            root, _ = self._setup(d)
            arc.main(["--save-root", d, "--apply"])
            arc.main(["--save-root", d, "--apply"])
            a = json.loads((root / arc.ARCHIVE_FILENAME).read_text())["items"]
            self.assertEqual(sorted(a), ["x1", "x2"])


class AlertTest(unittest.TestCase):
    def test_no_alert_when_exhausted_unchanged(self):
        self.assertEqual([a for a in health.evaluate_alerts({"queue_exhausted": 146}, {"queue_exhausted": 146}) if "exhausted" in a], [])

    def test_alert_on_increase_only(self):
        al = health.evaluate_alerts({"queue_exhausted": 150}, {"queue_exhausted": 146})
        self.assertTrue(any("+4" in a for a in al))

    def test_decrease_after_archive_is_quiet(self):
        self.assertEqual(health.evaluate_alerts({"queue_exhausted": 0}, {"queue_exhausted": 146}), [])

    def test_no_baseline_uses_remaining_count(self):
        self.assertTrue(any("exhausted 3" in a for a in health.evaluate_alerts({"queue_exhausted": 3}, None)))
        self.assertTrue(any("exhausted 3" in a for a in health.evaluate_alerts({"queue_exhausted": 3}, {})))
        self.assertEqual(health.evaluate_alerts({"queue_exhausted": 0}, None), [])


if __name__ == "__main__":
    unittest.main()
