import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
import zipfile

spec = importlib.util.spec_from_file_location("attachments", Path(__file__).parents[1] / "jarvis_kamiooya_attachments.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class AttachmentTests(unittest.TestCase):
    def test_comment_link_and_stable_identity_without_tokens(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); path = root / "photo.jpg"; path.write_bytes(b"\xff\xd8\xffimage")
            row = {"comment_id": "comment-123", "local_path": str(path), "url": "https://westudy.co.jp/uploads/a.jpg?token=secret#x"}
            meta, data = mod.build_attachment(row, root)
            self.assertEqual(meta["comment_id"], "123")
            self.assertEqual(meta["source_url"], "https://westudy.co.jp/uploads/a.jpg")
            self.assertNotIn("local_path", meta)
            self.assertEqual(meta["sha256"], hashlib.sha256(data).hexdigest())
            row["url"] = "https://westudy.co.jp/uploads/a.jpg?token=rotated"
            self.assertEqual(meta["id"], mod.build_attachment(row, root)[0]["id"])

    def test_reject_html_missing_and_outside_root(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); bad = root / "login.jpg"; bad.write_text("<html>login</html>")
            with self.assertRaises(ValueError): mod.inspect_file(bad, root)
            with self.assertRaises(ValueError): mod.inspect_file(bad, root / "other")
            with self.assertRaises(ValueError): mod.canonical_url("https://user:pass@example.com/a")
            with self.assertRaises(ValueError): mod.normalize_comment_id("unknown")

    def test_xlsx_requires_workbook(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); path = root / "sheet.xlsx"
            with zipfile.ZipFile(path, "w") as z:
                z.writestr("[Content_Types].xml", "x"); z.writestr("xl/workbook.xml", "x")
            self.assertTrue(mod.inspect_file(path, root)[1].endswith("spreadsheetml.sheet"))
            path.write_bytes(b"PKnot-a-workbook")
            with self.assertRaises((ValueError, zipfile.BadZipFile)): mod.inspect_file(path, root)

    def test_unchanged_does_not_reupload_and_verifies_object(self):
        store = object.__new__(mod.Store); data = b"pdf"
        meta = {"id": "a", "sha256": hashlib.sha256(data).hexdigest(), "storage_path": "comments/1/a.pdf"}
        store.existing = Mock(return_value=meta)
        store.request = Mock(return_value=Mock(content=data))
        self.assertEqual(store.save(meta, data), "unchanged")
        self.assertEqual(store.request.call_count, 1)
        self.assertEqual(store.request.call_args.args[0], "GET")

    def test_corrupt_upload_never_publishes_metadata(self):
        store = object.__new__(mod.Store); data = b"pdf"
        meta = {"id": "a", "sha256": hashlib.sha256(data).hexdigest(), "storage_path": "comments/1/a.pdf", "content_type": "application/pdf"}
        store.existing = Mock(return_value=None)
        store.request = Mock(side_effect=[Mock(), Mock(content=b"wrong")])
        with self.assertRaisesRegex(ValueError, "stored_hash_mismatch"): store.save(meta, data)
        self.assertEqual(store.request.call_count, 2)

    def test_refuses_public_bucket(self):
        store = object.__new__(mod.Store)
        store.request = Mock(return_value=Mock(json=Mock(return_value=[{"id": mod.BUCKET, "public": True}])))
        with self.assertRaisesRegex(ValueError, "bucket_must_be_private"): store.ensure_bucket()


if __name__ == "__main__":
    unittest.main()
