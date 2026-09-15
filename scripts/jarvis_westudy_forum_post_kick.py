#!/usr/bin/env python3
"""WeStudy グルコン投稿 watch を即ドレイン（SIGUSR1）。

常駐 watch が生きていればキュー待ちを待たずに起こす。
死んでいれば worker を直接1回実行。

  ~/selenium_env/venv/bin/python scripts/jarvis_westudy_forum_post_kick.py
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PID_PATH = REPO / ".jarvis_state" / "westudy_forum_post_watch.pid"
PY = Path("/Users/matsunomasaharu2/selenium_env/venv/bin/python")
WORKER = REPO / "scripts" / "jarvis_westudy_forum_post_worker.py"


def main() -> int:
    if PID_PATH.is_file():
        try:
            pid = int(PID_PATH.read_text(encoding="utf-8").strip() or "0")
        except ValueError:
            pid = 0
        if pid:
            try:
                os.kill(pid, 0)
                os.kill(pid, signal.SIGUSR1)
                print(f"# kicked watch pid={pid} SIGUSR1")
                return 0
            except OSError as e:
                print(f"# watch pid={pid} not alive: {e}")
    py = str(PY if PY.exists() else sys.executable)
    print("# watch not running → worker --i-confirm-post")
    return subprocess.call(
        [py, str(WORKER), "--i-confirm-post", "--limit", "5"],
        cwd=str(REPO),
    )


if __name__ == "__main__":
    raise SystemExit(main())
