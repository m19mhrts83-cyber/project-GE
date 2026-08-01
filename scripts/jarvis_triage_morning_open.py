#!/usr/bin/env python3
"""
Mac を開いた最初のタイミングで、pending があればトリアージダッシュボードを開く（1日1回）。

夜間バッチは判定・下書きのみ。表示はこのスクリプト側。

  python scripts/jarvis_triage_morning_open.py
  python scripts/jarvis_triage_morning_open.py --dry-run
  python scripts/jarvis_triage_morning_open.py --force
"""
from __future__ import annotations

import argparse
import sys

from jarvis_night_triage import open_dashboard_browser, pending_items, pending_partner_hint


def main() -> int:
    ap = argparse.ArgumentParser(description="First-open-of-day dashboard for night triage")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--force",
        action="store_true",
        help="同一日の再オープン抑制を無視",
    )
    args = ap.parse_args()
    items = pending_items()
    n = len(items)
    hint = pending_partner_hint(items)
    print(f"# pending={n}" + (f" ({hint})" if hint else ""))
    opened, msg = open_dashboard_browser(force=args.force, dry_run=args.dry_run)
    print(f"# {msg}")
    # スキップは正常（0件・本日済・時間外）
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
