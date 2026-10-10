#!/usr/bin/env python3
"""パートナー連絡整理係・昼枠パイプライン（111）

Gmail＋Chatwork 取込（並列）→ 追記件数を集計 → 更新があるときだけ Slack #report。
LLM は使わない（件数テンプレのみ・トークン節約）。

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
from concurrent.futures import ThreadPoolExecutor, as_completed
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


def _job_gmail(
    *, apply: bool, limit: int, newer_days: int, env: dict[str, str]
) -> tuple[str, int, int, str]:
    cmd = [
        PY,
        str(GMAIL),
        "--limit",
        str(limit),
        "--newer-days",
        str(newer_days),
    ]
    cmd.append("--apply" if apply else "--dry-run")
    code, blob = _run_capture(cmd, env=env)
    return "gmail", _parse_appended(blob, "gmail"), code, blob


def _job_chatwork(*, apply: bool, env: dict[str, str]) -> tuple[str, int, int, str]:
    cmd = [PY, str(CHATWORK)]
    cmd.append("--apply" if apply else "--dry-run")
    code, blob = _run_capture(cmd, env=env)
    return "chatwork", _parse_appended(blob, "chatwork"), code, blob


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="OneDrive へ追記（無いと dry-run 取込）")
    ap.add_argument(
        "--limit",
        type=int,
        default=25,
        help="Gmail 最大件数（朝 triage と二度取りするため既定25・狭め）",
    )
    ap.add_argument(
        "--newer-days",
        type=int,
        default=2,
        help="Gmail newer_than 日数（既定2・スキャン短縮）",
    )
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
    man = REPO / "215_kamiooya" / "C1_cursor" / "1b_Cursorマニュアル"
    env["PYTHONPATH"] = f"{REPO / 'scripts'}:{man}:{env.get('PYTHONPATH', '')}"

    gmail_n = 0
    cw_n = 0
    fails: list[str] = []
    rc = 0

    jobs = []
    if not args.skip_gmail:
        if not GMAIL.is_file():
            print(f"❌ missing {GMAIL}", file=sys.stderr)
            return 2
        jobs.append(
            (
                "gmail",
                lambda: _job_gmail(
                    apply=args.apply,
                    limit=args.limit,
                    newer_days=args.newer_days,
                    env=env,
                ),
            )
        )
    if not args.skip_chatwork:
        if not CHATWORK.is_file():
            print(f"❌ missing {CHATWORK}", file=sys.stderr)
            return 2
        jobs.append(
            (
                "chatwork",
                lambda: _job_chatwork(apply=args.apply, env=env),
            )
        )

    # I/O 待ちが主なので並列（Gmail API と Chatwork API）
    if len(jobs) == 1:
        kind, n, code, _ = jobs[0][1]()
        if kind == "gmail":
            gmail_n = n
        else:
            cw_n = n
        if code != 0:
            fails.append(f"{kind} exit={code}")
            rc = code
    elif jobs:
        with ThreadPoolExecutor(max_workers=2) as ex:
            futs = {ex.submit(fn): name for name, fn in jobs}
            for fut in as_completed(futs):
                kind, n, code, _ = fut.result()
                if kind == "gmail":
                    gmail_n = n
                else:
                    cw_n = n
                if code != 0:
                    fails.append(f"{kind} exit={code}")
                    rc = code or rc

    print(
        f"📎 day_pipeline counts: gmail={gmail_n} chatwork={cw_n} "
        f"fails={fails or 'なし'} (limit={args.limit} newer_days={args.newer_days})"
    )

    if not args.push and not args.dry_run_slack:
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
    if fails and (gmail_n + cw_n) == 0:
        report_cmd.append("--force")

    code, _ = _run_capture(report_cmd, env=env)
    if rc:
        return rc
    return code


if __name__ == "__main__":
    raise SystemExit(main())
