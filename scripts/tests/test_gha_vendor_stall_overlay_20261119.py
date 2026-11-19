"""516 GHA: Secret の古い台帳に Supabase の行を重ねる（2026-11-19）。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import jarvis_gha_vendor_outreach_stall as g  # noqa: E402


class OverlayTest(unittest.TestCase):
    def test_rows_override_status_and_keep_yaml_only_keys(self):
        base = {
            "settings": {"daily_outreach_limit": 3, "phase": 2},
            "vendors": [
                {"id": "shiga-0098", "status": "pending", "contacted_at": None, "batch": "W47-r2"},
                {"id": "old-1", "status": "contacted", "contacted_at": "2026-10-07"},
            ],
        }
        rows = [
            {"id": "shiga-0098", "status": "contacted", "contacted_at": "2026-11-19",
             "notes": None, "synced_at": "2026-11-19T00:00:00Z"},
            {"id": "new-1", "status": "pending", "name": "新規"},
        ]
        out = g.overlay_vendors(base, rows)
        by = {v["id"]: v for v in out["vendors"]}
        self.assertEqual(by["shiga-0098"]["status"], "contacted")
        self.assertEqual(by["shiga-0098"]["contacted_at"], "2026-11-19")
        self.assertEqual(by["shiga-0098"]["batch"], "W47-r2")  # YAML だけの列は残す
        self.assertNotIn("synced_at", by["shiga-0098"])
        self.assertEqual(by["old-1"]["contacted_at"], "2026-10-07")  # 行が無い業者はそのまま
        self.assertIn("new-1", by)  # Secret に無い業者は足す
        self.assertEqual(out["settings"]["phase"], 2)

    def test_works_without_secret(self):
        out = g.overlay_vendors({}, [{"id": "a", "status": "pending"}])
        self.assertEqual(out["settings"], {})
        self.assertEqual([v["id"] for v in out["vendors"]], ["a"])

    def test_overlay_skips_without_supabase_env(self):
        import os
        old = {k: os.environ.pop(k, None) for k in ("JARVIS_SUPABASE_URL", "JARVIS_SUPABASE_SERVICE_ROLE_KEY")}
        try:
            self.assertEqual(g.overlay_from_supabase(Path("/nonexistent")), [])
        finally:
            for k, v in old.items():
                if v is not None:
                    os.environ[k] = v


if __name__ == "__main__":
    unittest.main()
