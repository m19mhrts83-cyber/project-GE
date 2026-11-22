"""Slack 短報の控えは非公開（state）側へ（614 F8・2026-11-23）。値はすべて架空。"""
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import jarvis_points_rebate_slack_report as sr  # noqa: E402

REPO = SCRIPTS.parent
PUBLIC_REPORTS = (
    REPO / "docs" / "AIエージェントチーム" / "600_リソース・家計室" / "614_ポイント・還元ウォッチ係" / "reports"
)


def _snapshot() -> set:
    return {p.name for p in PUBLIC_REPORTS.glob("*")} if PUBLIC_REPORTS.exists() else set()


class ArchiveTest(unittest.TestCase):
    def test_all_kinds_go_to_state_not_public_docs(self):
        before = _snapshot()
        with tempfile.TemporaryDirectory() as d, \
             mock.patch.dict("os.environ", {"JARVIS_STATE_DIR": d}), \
             contextlib.redirect_stdout(io.StringIO()):
            for tag in ("etc_checked", "teiki_checked", "vpoint_partial"):
                sr._archive("本文（架空）", tag)
            sr._archive("本文（架空）", "card_benefit_checked")
            got = sorted(str(p.relative_to(d)) for p in Path(d).rglob("*.md"))
        self.assertEqual(len(got), 4)
        self.assertTrue(all(g.startswith(("points_rebate_reports/", "card_benefit_reports/")) for g in got))
        self.assertEqual(_snapshot(), before, "公開リポの reports/ に書いてはいけない")

    def test_dry_run_archive_has_separate_name(self):
        with tempfile.TemporaryDirectory() as d, \
             mock.patch.dict("os.environ", {"JARVIS_STATE_DIR": d}), \
             contextlib.redirect_stdout(io.StringIO()):
            sr._archive("本文（架空）", "etc_checked", dry_run=True)
            sr._archive("本文（架空）", "etc_checked")
            names = sorted(p.name for p in Path(d).rglob("*.md"))
        self.assertEqual(len(names), 2)
        self.assertTrue(any(n.endswith("_dryrun.md") for n in names))
        self.assertTrue(any(n.endswith("etc_checked.md") for n in names))

    def test_default_dir_is_gitignored_state_dir(self):
        with mock.patch.dict("os.environ", {"JARVIS_STATE_DIR": ""}):
            self.assertEqual(sr.reports_dir("etc_checked"), REPO / ".jarvis_state" / "points_rebate_reports")


if __name__ == "__main__":
    unittest.main()
