#!/usr/bin/env python3
"""Numbers → CSV → Zaim 予算反映のエントリポイント。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numbers_budget_extract as extract_mod
import zaim_budget_apply as apply_mod

SCRIPT_DIR = Path(__file__).resolve().parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Zaim 予算同期（Numbers → Zaim）")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_extract = sub.add_parser("extract", help="Numbers から中間 CSV を生成")
    p_extract.add_argument("--year", type=int, default=2026)
    p_extract.add_argument("--output", type=Path, default=None)

    p_preview = sub.add_parser("preview", help="CSV 反映プレビュー")
    p_preview.add_argument("--csv", type=Path, default=SCRIPT_DIR / "budget_2026.csv")
    p_preview.add_argument("--year", type=int, default=None)
    p_preview.add_argument("--month", default=None)

    p_login = sub.add_parser("login", help="Zaim ログインセッション保存")
    p_login.add_argument("--connect-cdp", default="http://127.0.0.1:9223")

    p_apply = sub.add_parser("apply", help="Zaim へ反映")
    p_apply.add_argument("--csv", type=Path, default=SCRIPT_DIR / "budget_2026.csv")
    p_apply.add_argument("--year", type=int, default=None)
    p_apply.add_argument("--month", default=None)
    p_apply.add_argument("--yes", action="store_true")
    p_apply.add_argument("--connect-cdp", default="http://127.0.0.1:9223")

    args = parser.parse_args(argv)

    if args.cmd == "extract":
        out = ["--year", str(args.year)]
        if args.output:
            out += ["--output", str(args.output)]
        return extract_mod.main(out)

    if args.cmd == "preview":
        out = ["--csv", str(args.csv), "--dry-run"]
        if args.year:
            out += ["--year", str(args.year)]
        if args.month:
            out += ["--month", args.month]
        return apply_mod.main(out)

    if args.cmd == "login":
        return apply_mod.main(["--login", "--connect-cdp", args.connect_cdp, "--login-method", "email"])

    if args.cmd == "apply":
        out = ["--csv", str(args.csv), "--apply", "--connect-cdp", args.connect_cdp, "--login-method", "email"]
        if args.yes:
            out.append("--yes")
        if args.year:
            out += ["--year", str(args.year)]
        if args.month:
            out += ["--month", args.month]
        return apply_mod.main(out)

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
