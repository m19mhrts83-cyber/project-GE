#!/usr/bin/env python3
"""Zaim（財務）の「SBI 証券」口座評価額を取る（インデックス枠の正本）。

SBI サイト直ログインは fragile なため、週次はこちらを正とする。
ファンド内訳は保険配分と同系統の拡張予定（Zaim/MF 詳細ページの probe）。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_zaim_sbi_balance.py --json
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_MATCH = "SBI 証券,SBI証券"


def main() -> int:
    match = (os.environ.get("ZAIM_SBI_ACCOUNT_MATCH") or DEFAULT_MATCH).strip()
    script = REPO / "scripts" / "jarvis_zaim_mhi_balance.py"
    cmd = [
        sys.executable,
        str(script),
        "--json",
        "--match",
        match,
        "--label",
        "SBI証券",
    ]
    if "--headed" in sys.argv:
        cmd.append("--headed")
    if "--list" in sys.argv:
        cmd.append("--list")
    return subprocess.call(cmd, cwd=str(REPO))


if __name__ == "__main__":
    raise SystemExit(main())
