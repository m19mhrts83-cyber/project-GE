#!/usr/bin/env python3
"""
Jarvis 入口: Zaim Web で集計設定を直す（承認後）。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  python scripts/jarvis_zaim_money_apply.py --from-watch --dry-run
  python scripts/jarvis_zaim_money_apply.py --from-watch --apply --yes --limit 3
"""
from __future__ import annotations

import sys
from pathlib import Path

SYNC = (
    Path(__file__).resolve().parents[1]
    / "215_kamiooya"
    / "C1_cursor"
    / "finance"
    / "zaim_budget_sync"
)
sys.path.insert(0, str(SYNC))

import zaim_money_edit  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    return zaim_money_edit.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
