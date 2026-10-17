#!/usr/bin/env python3
"""互換ラッパー — 614 ポイント・還元ウォッチ係（テイチャン短報）。

正本: jarvis_points_rebate_slack_report.py --kind teiki
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
POST = REPO / "scripts" / "jarvis_points_rebate_slack_report.py"


def main() -> int:
    if not POST.is_file():
        print(f"❌ missing {POST}", file=sys.stderr)
        return 2
    # 旧 CLI をそのまま転送（--kind teiki を先頭に）
    argv = [sys.executable, str(POST), "--kind", "teiki", *sys.argv[1:]]
    return int(subprocess.run(argv, cwd=str(REPO), check=False).returncode)


if __name__ == "__main__":
    raise SystemExit(main())
