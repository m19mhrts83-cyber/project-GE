#!/usr/bin/env python3
"""CHRLINE が import できるかだけ確認する（ログインはしない）。"""
from __future__ import annotations

import sys


def main() -> int:
    try:
        import CHRLINE  # noqa: F401

        ver = getattr(CHRLINE, "__version__", "?")
        print(f"OK: CHRLINE {ver}")
        return 0
    except Exception as e:
        print(f"NG: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
