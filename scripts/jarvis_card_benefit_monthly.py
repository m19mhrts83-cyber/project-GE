#!/usr/bin/env python3
"""614 年間特典ウォッチ — 月次の自動実行本体（launchd／朝オープン取りこぼしから）。

  1. jarvis_card_benefit_watch.py --refresh（Olive=Gmail 月次メール／Bonvoy=Zaim）
  2. jarvis_points_rebate_slack_report.py --kind card_benefit --from-state（#report）
  失敗は --outcome failed で #ops。成功した月だけ state に印（取りこぼし判定用）。

  python scripts/jarvis_card_benefit_monthly.py [--dry-run] [--force]

停止: JARVIS_CARD_BENEFIT_DISABLE=1（短報だけ止める時は JARVIS_CARD_BENEFIT_SLACK_REPORT_DISABLE=1）
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jarvis_card_benefit_watch as cbw  # noqa: E402

REPO = cbw.REPO
SLACK = REPO / "scripts" / "jarvis_points_rebate_slack_report.py"
WATCH = REPO / "scripts" / "jarvis_card_benefit_watch.py"
RUN_DAY = 28


def disabled() -> bool:
    return (os.environ.get("JARVIS_CARD_BENEFIT_DISABLE") or "").strip().lower() in ("1", "true", "yes")


def this_month() -> str:
    return datetime.now(cbw.JST).strftime("%Y-%m")


def needs_catchup(now: datetime | None = None) -> bool:
    """朝オープン取りこぼし: 28日以降で、今月まだ成功していない時。"""
    if disabled():
        return False
    now = now or datetime.now(cbw.JST)
    if now.day < RUN_DAY:
        return False
    return cbw.load_state().get("last_monthly_run") != now.strftime("%Y-%m")


def _slack(*extra: str) -> int:
    return subprocess.run(
        [sys.executable, str(SLACK), "--kind", "card_benefit", *extra], cwd=str(REPO), check=False
    ).returncode


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="取り込みは行い、Slack は投稿せず表示だけ")
    ap.add_argument("--force", action="store_true", help="28日前・実行済みでも動かす")
    args = ap.parse_args(argv)

    if disabled():
        print("⏭ JARVIS_CARD_BENEFIT_DISABLE=1 — 実行スキップ")
        return 0
    if not args.force and datetime.now(cbw.JST).day < RUN_DAY:
        print("⏭ 28日前のためスキップ（--force で実行）")
        return 0

    print(f"# start {datetime.now(cbw.JST).isoformat(timespec='seconds')}")
    proc = subprocess.run(
        [sys.executable, str(WATCH), "--refresh", "--mask"],
        cwd=str(REPO), capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "取込失敗").strip().splitlines()[-1][:120]
        print(f"❌ refresh failed: {err}", file=sys.stderr)
        _slack("--outcome", "failed", "--error", f"年間特典の取込に失敗（{err}）", *(["--dry-run"] if args.dry_run else []))
        return 1
    print(proc.stdout.strip())  # 金額は --mask で伏せ済み

    rc = _slack("--from-state", *(["--dry-run"] if args.dry_run else []))
    if rc != 0:
        _slack("--outcome", "failed", "--error", f"短報の投稿に失敗（exit {rc}）", *(["--dry-run"] if args.dry_run else []))
        return rc
    if not args.dry_run:
        st = cbw.load_state()
        st["last_monthly_run"] = this_month()
        cbw.save_state(st)
    print("# end ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
