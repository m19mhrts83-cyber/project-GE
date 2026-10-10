#!/usr/bin/env python3
"""パートナー連絡整理係・昼枠パイプライン（111）

Gmail＋Chatwork 取込 → 追記件数を集計 → 更新があるときだけ Slack #report。

例（ローカル）:
  set -a && source .env.jarvis_private && set +a
  python scripts/jarvis_partner_day_pipeline.py --apply --push
  python scripts/jarvis_partner_day_pipeline.py --apply --dry-run-slack
"""
from __future__ import annotations

import argparse
import ast
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PY = sys.executable
GMAIL = REPO / "scripts" / "jarvis_gha_partner_gmail_yoritoori.py"
CHATWORK = REPO / "scripts" / "jarvis_gha_partner_chatwork_yoritoori.py"
REPORT = REPO / "scripts" / "jarvis_partner_slack_report.py"

_STATS_RE = re.compile(r"📎 partner (gmail|chatwork)→md:\s*(\{.*\})")


def _run_capture(cmd: list[str], *, env: dict[str, str] | None = None) -> tuple[int, str]:
    proc = subprocess.run(
        cmd,
        cwd=str(REPO),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    sys.stdout.write(proc.stdout or "")
    sys.stderr.write(proc.stderr or "")
    return int(proc.returncode), out


def _parse_appended(blob: str, kind: str) -> int:
    """stdout/stderr から 📎 partner {kind}→md: {stats} の appended を取る。"""
    for m in _STATS_RE.finditer(blob):
        if m.group(1) != kind:
            continue
        try:
            stats = ast.literal_eval(m.group(2))
        except (SyntaxError, ValueError):
            continue
        if isinstance(stats, dict):
            return int(stats.get("appended") or 0)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="OneDrive へ追記（無いと dry-run 取込）")
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--skip-gmail", action="store_true")
    ap.add_argument("--skip-chatwork", action="store_true")
    ap.add_argument(
        "--push",
        action="store_true",
        help="更新があるとき Slack #report へ投稿",
    )
    ap.add_argument(
        "--dry-run-slack",
        action="store_true",
        help="Slack 本文だけ表示（投稿しない）",
    )
    ap.add_argument("--frame", default="day", choices=("day", "night", "manual"))
    args = ap.parse_args()

    env = os.environ.copy()
    # GHA と同型: 1b マニュアルを import path に
    man = REPO / "215_kamiooya" / "C1_cursor" / "1b_Cursorマニュアル"
    env["PYTHONPATH"] = f"{REPO / 'scripts'}:{man}:{env.get('PYTHONPATH', '')}"

    gmail_n = 0
    cw_n = 0
    fails: list[str] = []
    rc = 0

    if not args.skip_gmail:
        if not GMAIL.is_file():
            print(f"❌ missing {GMAIL}", file=sys.stderr)
            return 2
        cmd = [PY, str(GMAIL), "--limit", str(args.limit)]
        cmd.append("--apply" if args.apply else "--dry-run")
        code, blob = _run_capture(cmd, env=env)
        gmail_n = _parse_appended(blob, "gmail")
        if code != 0:
            fails.append(f"gmail exit={code}")
            rc = code

    if not args.skip_chatwork:
        if not CHATWORK.is_file():
            print(f"❌ missing {CHATWORK}", file=sys.stderr)
            return 2
        cmd = [PY, str(CHATWORK)]
        cmd.append("--apply" if args.apply else "--dry-run")
        code, blob = _run_capture(cmd, env=env)
        cw_n = _parse_appended(blob, "chatwork")
        if code != 0:
            fails.append(f"chatwork exit={code}")
            rc = code or rc

    print(f"📎 day_pipeline counts: gmail={gmail_n} chatwork={cw_n} fails={fails or 'なし'}")

    if not args.push and not args.dry_run_slack:
        # 取込失敗は非ゼロ。Slack を出さないモードでも失敗は検知する
        return rc

    if not REPORT.is_file():
        print(f"❌ missing {REPORT}", file=sys.stderr)
        return 2

    report_cmd = [
        PY,
        str(REPORT),
        "--frame",
        args.frame,
        "--gmail",
        str(gmail_n),
        "--chatwork",
        str(cw_n),
        "--failures",
        "／".join(fails) if fails else "なし",
    ]
    if args.dry_run_slack:
        report_cmd.append("--dry-run")
    # 片方失敗でも件数>0 なら報告は出す（失敗行に残す）
    if fails and (gmail_n + cw_n) == 0:
        report_cmd.append("--force")

    code, _ = _run_capture(report_cmd, env=env)
    # Slack まで進んだあとは: 取込失敗があれば非ゼロ、なければ Slack 結果
    if rc:
        return rc
    return code


if __name__ == "__main__":
    raise SystemExit(main())
