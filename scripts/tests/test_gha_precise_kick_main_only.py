"""jarvis_gha_precise_kick: 本便だけを「実行済み」と数える判定の単体テスト（gh は呼ばない）。"""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jarvis_gha_precise_kick as k  # noqa: E402

M = "Partner Gmail → OneDrive MD (Graph)"


def run(event, step_concl, status="completed", step_status="completed"):
    st = [{"name": "x", "conclusion": "success", "status": "completed"}]
    if step_concl is not None or step_status:
        st.append({"name": M, "conclusion": step_concl, "status": step_status})
    return {"event": event, "status": status, "jobs": [{"name": "triage", "steps": st}]}


class IsMainRun(unittest.TestCase):
    def test_daytime_skipped_is_not_main(self):
        self.assertFalse(k.is_main_run(run("schedule", "skipped"), M))

    def test_main_success(self):
        self.assertTrue(k.is_main_run(run("schedule", "success"), M))

    def test_main_in_progress_step(self):
        self.assertTrue(k.is_main_run(run("schedule", "", "in_progress", "in_progress"), M))

    def test_unreached_schedule_not_counted(self):
        self.assertFalse(k.is_main_run(run("schedule", "", "in_progress", "pending"), M))

    def test_unreached_dispatch_counted(self):
        self.assertTrue(k.is_main_run(run("workflow_dispatch", "", "queued", "pending"), M))


class RanSince(unittest.TestCase):
    def _gh(self, listing, views):
        def fake(args):
            out = mock.Mock(returncode=0, stderr="")
            if args[1] == "list":
                out.stdout = listing
            else:
                import json
                out.stdout = json.dumps(views[args[2]])
            return out
        return fake

    def test_only_daytime_today_still_kicks(self):
        with mock.patch.object(k, "_gh", self._gh("[1]", {"1": run("schedule", "skipped")})):
            self.assertFalse(k.ran_since("r", "w", "2026-11-24T15:00:00Z", M))

    def test_main_today_skips_kick(self):
        with mock.patch.object(k, "_gh", self._gh("[2,1]", {"2": run("schedule", "success"), "1": run("schedule", "skipped")})):
            self.assertTrue(k.ran_since("r", "w", "2026-11-24T15:00:00Z", M))

    def test_no_marker_keeps_old_behavior(self):
        with mock.patch.object(k, "_gh", return_value=mock.Mock(returncode=0, stdout="1\n")):
            self.assertTrue(k.ran_since("r", "w", "2026-11-24T15:00:00Z"))


class Config(unittest.TestCase):
    def test_only_triage_has_marker(self):
        import yaml
        cfg = yaml.safe_load(k.CONFIG.read_text(encoding="utf-8"))
        self.assertEqual(list(k.marker_steps(cfg)), ["jarvis-dashboard-gmail-triage.yml"])


if __name__ == "__main__":
    unittest.main()
