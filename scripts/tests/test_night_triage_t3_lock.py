"""night_triage T3 の同時起動ガード（モックのみ・Slack 送信なし）。"""
from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import jarvis_night_triage as nt  # noqa: E402


def _fake_ok(*a, **k):
    return subprocess.CompletedProcess(a, 0, "", "")


def test_second_concurrent_start_skips(tmp_path):
    lock = tmp_path / "t3.lock"
    calls: list[int] = []
    inside = threading.Event()
    release = threading.Event()

    def slow_runner(*a, **k):
        calls.append(1)
        inside.set()
        release.wait(5)
        return _fake_ok()

    first: list = []
    t = threading.Thread(
        target=lambda: first.append(
            nt.run_mail_action_slack_locked(Path("x.py"), lock_path=lock, runner=slow_runner)
        )
    )
    t.start()
    assert inside.wait(5)
    second = nt.run_mail_action_slack_locked(Path("x.py"), lock_path=lock, runner=_fake_ok)
    release.set()
    t.join()
    assert second is None
    assert first[0].returncode == 0
    assert len(calls) == 1


def test_lock_released_after_run(tmp_path):
    lock = tmp_path / "t3.lock"
    assert nt.run_mail_action_slack_locked(Path("x.py"), lock_path=lock, runner=_fake_ok)
    assert nt.run_mail_action_slack_locked(Path("x.py"), lock_path=lock, runner=_fake_ok)


def test_lock_released_on_runner_error(tmp_path):
    lock = tmp_path / "t3.lock"

    def boom(*a, **k):
        raise RuntimeError("x")

    try:
        nt.run_mail_action_slack_locked(Path("x.py"), lock_path=lock, runner=boom)
    except RuntimeError:
        pass
    assert nt.run_mail_action_slack_locked(Path("x.py"), lock_path=lock, runner=_fake_ok)
