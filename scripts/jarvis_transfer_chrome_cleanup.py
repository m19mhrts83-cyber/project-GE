#!/usr/bin/env python3
"""送金アシスト用 Chrome を閉じる（互換エントリ）。

本体: jarvis_automation_chrome_cleanup.py（自動化 Chrome 全体）
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from jarvis_automation_chrome_cleanup import main  # noqa: E402

if __name__ == "__main__":
    # 旧 --ports は無視（DEFAULT_PORTS に送金分を含む）
    sys.argv = [sys.argv[0], *[a for a in sys.argv[1:] if not a.startswith("--ports")]]
    cleaned: list[str] = [sys.argv[0]]
    skip = False
    for a in sys.argv[1:]:
        if skip:
            skip = False
            continue
        if a == "--ports":
            skip = True
            continue
        cleaned.append(a)
    sys.argv = cleaned
    raise SystemExit(main())
