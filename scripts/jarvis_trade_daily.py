#!/usr/bin/env python3
"""Trade Desk 日次: 日足取得 → シグナル／ペーパー約定。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PY = sys.executable


def run(script: str, extra: list[str] | None = None) -> int:
    cmd = [PY, str(REPO / "scripts" / script), *(extra or [])]
    print(f"# run {' '.join(cmd)}", flush=True)
    return subprocess.call(cmd, cwd=str(REPO))


def main() -> int:
    extra = sys.argv[1:]
    rc = run("jarvis_trade_fetch_prices.py")
    if rc != 0:
        print(f"# fetch exit={rc} — シグナルは続行", flush=True)
    rc2 = run("jarvis_trade_signal.py", extra)
    return rc2 or rc


if __name__ == "__main__":
    raise SystemExit(main())
