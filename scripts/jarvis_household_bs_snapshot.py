#!/usr/bin/env python3
"""家計B/S 月次スナップ — MQ月次更新と同サイクル

  ~/selenium_env/venv/bin/python scripts/jarvis_household_bs_snapshot.py
  ~/selenium_env/venv/bin/python scripts/jarvis_household_bs_snapshot.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    env_file = REPO / ".env.jarvis_private"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.strip().strip("'").strip('"')
            if k and k not in os.environ:
                os.environ[k] = v

    cmd = ["npx", "--yes", "tsx", "scripts/householdBsSnapshot.ts"]
    if args.year:
        cmd.extend(["--year", str(args.year)])
    if args.dry_run:
        cmd.append("--dry-run")

    proc = subprocess.run(
        cmd,
        cwd=str(REPO / "apps" / "trade-desk"),
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )
    raw = (proc.stdout or "").strip()
    if proc.returncode != 0:
        print(f"# household-bs snapshot failed: {(proc.stderr or '')[-500:]}", flush=True)
        return proc.returncode
    try:
        data = json.loads(raw.splitlines()[-1])
    except Exception:
        data = {"ok": True, "raw": raw[-300:]}
    print(f"📎 家計B/Sスナップ: ok={data.get('ok')} month={data.get('as_of_month')} year={data.get('fiscal_year')}", flush=True)
    return 0 if data.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
