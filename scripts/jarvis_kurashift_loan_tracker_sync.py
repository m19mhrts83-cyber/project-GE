#!/usr/bin/env python3
"""借入残高トラッカー → KURASHIFT 投影（読取のみ）。

現状ブロッカー: estate の token に Drive scope が無く、
LOAN_TRACKER_DRIVE_FOLDER_ID / LOAN_TRACKER_SHEET_ID も未設定。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_loan_tracker_sync.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DISCOVER = REPO / "docs" / "KURASHIFT_loan_tracker_Discover.md"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    folder = (os.environ.get("LOAN_TRACKER_DRIVE_FOLDER_ID") or "").strip()
    sheet = (os.environ.get("LOAN_TRACKER_SHEET_ID") or "").strip()
    result = {
        "ok": False,
        "dry_run": args.dry_run,
        "blocker": "loan_tracker_not_wired",
        "has_folder_id": bool(folder),
        "has_sheet_id": bool(sheet),
        "next_steps": [
            "estate で Drive readonly OAuth を付与（token_estate は現状 Gmail のみ）",
            "LOAN_TRACKER_DRIVE_FOLDER_ID または LOAN_TRACKER_SHEET_ID を .env.jarvis_private に追記",
            "形式確定後に本スクリプトへ読取投影を実装",
            f"調査メモ: {DISCOVER}",
        ],
        "url": "https://loan-tracker-plum.vercel.app/",
        "google_account": "estate",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("KURASHIFT_RESULT:" + json.dumps(result, ensure_ascii=False))
    print(
        "取得失敗: 借入残高トラッカー同期は未配線です。"
        "docs/KURASHIFT_loan_tracker_Discover.md を参照し、"
        "Drive scope と LOAN_TRACKER_* を用意してください。",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
