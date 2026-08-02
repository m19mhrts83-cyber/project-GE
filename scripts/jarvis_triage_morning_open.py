#!/usr/bin/env python3
"""
Mac を開いた最初のタイミングで、トリアージダッシュボードを開く（1日1回）。
既定は pending がなくても開く（習慣化）。軌道後は
JARVIS_MORNING_OPEN_REQUIRE_PENDING=1 で pending≥1 のみに戻せる。
並行して Mac 必須の最新化バンドル（catchup・Gmail 差分・push）を裏実行する。

夜間バッチは判定・下書きのみ。表示はこのスクリプト側。

  python scripts/jarvis_triage_morning_open.py
  python scripts/jarvis_triage_morning_open.py --dry-run
  python scripts/jarvis_triage_morning_open.py --force
  python scripts/jarvis_triage_morning_open.py --with-line
  python scripts/jarvis_triage_morning_open.py --no-refresh
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from jarvis_night_triage import open_dashboard_browser, pending_items, pending_partner_hint

REPO = Path(__file__).resolve().parents[1]
REFRESH = Path(__file__).resolve().parent / "jarvis_morning_mac_refresh.py"
LOG_DIR = Path.home() / "Library" / "Logs" / "jarvis_night_triage"


def spawn_mac_refresh(*, force: bool, with_line: bool, dry_run: bool) -> None:
    """朝バンドルをバックグラウンド起動（ブラウザオープンをブロックしない）。"""
    if not REFRESH.is_file():
        print(f"# mac refresh missing: {REFRESH}", file=sys.stderr)
        return
    cmd = [sys.executable, "-u", str(REFRESH)]
    if force:
        cmd.append("--force")
    if with_line:
        cmd.append("--with-line")
    if dry_run:
        cmd.append("--dry-run")
        # dry-run は同期で短く結果を出す
        subprocess.run(cmd, cwd=str(REPO), check=False)
        return
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    out = open(LOG_DIR / "mac_morning_refresh.out.log", "a", encoding="utf-8")
    err = open(LOG_DIR / "mac_morning_refresh.err.log", "a", encoding="utf-8")
    try:
        subprocess.Popen(
            cmd,
            cwd=str(REPO),
            stdout=out,
            stderr=err,
            start_new_session=True,
            env=os.environ.copy(),
        )
        print("# mac refresh: spawned in background")
    except Exception as e:
        print(f"# mac refresh spawn failed: {e}", file=sys.stderr)
        out.close()
        err.close()


def main() -> int:
    ap = argparse.ArgumentParser(description="First-open-of-day dashboard for night triage")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--force",
        action="store_true",
        help="同一日の再オープン／再 refresh 抑制を無視",
    )
    ap.add_argument(
        "--with-line",
        action="store_true",
        help="裏の Mac refresh に CHRLINE／オプチャを含める",
    )
    ap.add_argument(
        "--no-refresh",
        action="store_true",
        help="裏の Mac 必須バンドルを起動しない（オープンのみ）",
    )
    args = ap.parse_args()

    with_line = args.with_line or (
        (os.environ.get("JARVIS_MORNING_WITH_LINE") or "").strip() in ("1", "true", "yes")
    )

    items = pending_items()
    n = len(items)
    hint = pending_partner_hint(items)
    print(f"# pending={n}" + (f" ({hint})" if hint else ""))

    # 先に裏更新を起動（操作中に投影が追いつく）
    if not args.no_refresh:
        spawn_mac_refresh(force=args.force, with_line=with_line, dry_run=args.dry_run)

    opened, msg = open_dashboard_browser(force=args.force, dry_run=args.dry_run)
    print(f"# {msg}")
    # スキップは正常（0件・本日済・時間外）
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
