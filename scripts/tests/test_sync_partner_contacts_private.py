import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sync_partner_contacts_for_dashboard as m  # noqa: E402


class BuildTest(unittest.TestCase):
    def setUp(self):
        self.pub = {"partners": [{"name": "A社", "folder": "P1_A", "emails": ["old@example.com"], "phones": [], "via_ambiguous": False}]}
        self.src = [
            {"name": "A社", "folder": "P1_A", "emails": ["a@example.com"], "phones": ["000-0000-0000"]},
            {"name": "新規社", "folder": "P2_N", "emails": ["n@example.com"], "phones": []},
        ]

    def test_public_has_no_contacts_and_no_new_partner(self):
        pub, priv = m.build(self.src, self.pub, {})
        text = json.dumps(pub, ensure_ascii=False)
        self.assertNotIn("@", text)
        self.assertNotIn("000-0000", text)
        self.assertEqual([p["folder"] for p in pub["partners"]], ["P1_A"])
        self.assertEqual(priv["emails_by_folder"]["P1_A"], ["a@example.com"])
        self.assertEqual(priv["emails_by_folder"]["P2_N"], ["n@example.com"])
        self.assertEqual(priv["phones_by_folder"]["P1_A"], ["000-0000-0000"])
        self.assertEqual(priv["extra_partners"], [{"name": "新規社", "folder": "P2_N"}])

    def test_keeps_private_folders_missing_from_source(self):
        _, priv = m.build([], self.pub, {"emails_by_folder": {"P9_X": ["x@example.com"]}})
        self.assertEqual(priv["emails_by_folder"]["P9_X"], ["x@example.com"])
        self.assertEqual(priv["emails_by_folder"]["P1_A"], ["old@example.com"])


if __name__ == "__main__":
    unittest.main()
