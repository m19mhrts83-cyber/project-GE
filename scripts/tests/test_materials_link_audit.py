import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jarvis_materials_link_audit as links


class MaterialsLinkAuditTests(unittest.TestCase):
    def test_current_catalog(self):
        import json
        data = json.loads(links.CATALOG.read_text(encoding="utf-8"))
        self.assertEqual(links.audit(data), [])

    def test_rejects_duplicate_bad_url_and_unknown_lane(self):
        data = {
            "lanes": [{"id": "a", "hub_url": "https://example.com/hub.md"}, {"id": "a", "hub_url": "bad"}],
            "items": [{"id": "x", "lane": "missing", "url": "file:///tmp/x"}],
        }
        errors = "\n".join(links.audit(data))
        self.assertIn("lane id が重複", errors)
        self.assertIn("URL不正", errors)
        self.assertIn("Markdown直リンク", errors)
        self.assertIn("lane未定義", errors)
