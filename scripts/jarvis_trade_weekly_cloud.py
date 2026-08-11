#!/usr/bin/env python3
"""Trade Desk 週次クラウド分（GHA）。ログインサイトは触らない。

  python scripts/jarvis_trade_weekly_cloud.py
  python scripts/jarvis_trade_weekly_cloud.py --skip-tavily
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def run(args: list[str]) -> int:
    print(f"# run {' '.join(args)}", flush=True)
    r = subprocess.run(args, cwd=str(REPO), check=False)
    return r.returncode


def main() -> int:
    ap = argparse.ArgumentParser(description="Trade Desk weekly cloud")
    ap.add_argument("--skip-prices", action="store_true")
    ap.add_argument("--skip-tavily", action="store_true")
    ap.add_argument("--skip-portfolio", action="store_true")
    args = ap.parse_args()
    exe = sys.executable
    rc = 0

    if not args.skip_prices:
        n = run([exe, str(REPO / "scripts" / "jarvis_trade_fetch_prices.py"), "--range", "3mo"])
        rc = rc or n

    if not args.skip_tavily:
        n = run([exe, str(REPO / "scripts" / "jarvis_trade_research_ingest.py"), "--tavily"])
        if n != 0:
            print("# tavily skipped/failed（キー未設定でも週次全体は止めない）", flush=True)

    if not args.skip_portfolio:
        n = run(
            [
                exe,
                str(REPO / "scripts" / "jarvis_portfolio_weekly.py"),
                "--cloud-only",
                "--force",
            ]
        )
        rc = rc or n

    print(f"📎 trade weekly cloud done rc={rc}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
