import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import kamiooya_target as kt  # noqa: E402

spec = importlib.util.spec_from_file_location("cutover", ROOT / "kamiooya_cutover_check.py")
cutover = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cutover)

NEW = "abcdefghijklmnopqrst"


class TargetTest(unittest.TestCase):
    def test_default_is_tokyo(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("KAMIOOYA_PROJECT_REF", None)
            self.assertEqual(kt.base_url(), "https://sufbsyddqgekvcgadhpv.supabase.co")
            self.assertEqual(kt.rewrite("x https://sufbsyddqgekvcgadhpv.supabase.co/y"), "x https://sufbsyddqgekvcgadhpv.supabase.co/y")

    def test_switch_by_env(self):
        with mock.patch.dict(os.environ, {"KAMIOOYA_PROJECT_REF": NEW}):
            self.assertEqual(kt.storage_url(), f"https://{NEW}.storage.supabase.co")
            self.assertTrue(kt.is_target_url(f"https://{NEW}.supabase.co/"))
            self.assertFalse(kt.is_target_url("https://sufbsyddqgekvcgadhpv.supabase.co"))
            self.assertEqual(kt.rewrite("'https://sufbsyddqgekvcgadhpv.supabase.co/functions/v1/a'"),
                             f"'https://{NEW}.supabase.co/functions/v1/a'")

    def test_bad_ref_rejected(self):
        with mock.patch.dict(os.environ, {"KAMIOOYA_PROJECT_REF": "https://evil"}):
            with self.assertRaises(ValueError):
                kt.base_url()


class CutoverCompareTest(unittest.TestCase):
    def snap(self, **over):
        tables = {t: 10 for t in cutover.TABLES}
        tables.update(over)
        return {"tables": tables, "buckets": [["community-attachments", False]],
                "functions": {f: 200 for f in cutover.FUNCTIONS}}

    def test_same_is_ok(self):
        self.assertEqual(cutover.compare(self.snap(), self.snap()), ([], []))

    def test_missing_rows_is_error(self):
        errors, _ = cutover.compare(self.snap(), self.snap(knowledge_chunks=9))
        self.assertEqual(len(errors), 1)

    def test_growing_log_is_warning(self):
        errors, warns = cutover.compare(self.snap(), self.snap(line_openchat_logs=12))
        self.assertEqual((len(errors), len(warns)), (0, 1))

    def test_missing_function_is_error(self):
        new = self.snap()
        new["functions"]["raimo-auth"] = 404
        errors, _ = cutover.compare(self.snap(), new)
        self.assertEqual(len(errors), 1)


if __name__ == "__main__":
    unittest.main()
