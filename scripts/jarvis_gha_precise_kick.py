#!/usr/bin/env python3
"""GHA 定刻キック — 時刻が要る workflow を Mac から workflow_dispatch で起動する（AI なし）。

GHA の schedule は混雑で 2〜6 時間遅れる（46_週次レビュー）。config/gha_precise_kick.yaml の
ジョブを定刻〜grace_min の間に 1 日 1 回だけ起動する。遅れて来た schedule 実行は
.github/workflows/_kick-guard.yml が skip するので二重にはならない。
Mac が寝ていて定刻を逃した日は grace を過ぎたら何もしない（schedule がそのまま保険になる）。

    ~/selenium_env/venv/bin/python scripts/jarvis_gha_precise_kick.py --dry-run
    ~/selenium_env/venv/bin/python scripts/jarvis_gha_precise_kick.py

入口: launchd 10 分おき（install_gha_precise_kick_launchd.sh）
状態: .jarvis_state/gha_precise_kick.json（その日にキックした workflow）
停止: JARVIS_GHA_PRECISE_KICK_DISABLE=1
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

REPO = Path(__file__).resolve().parents[1]
CONFIG = REPO / "config" / "gha_precise_kick.yaml"
STATE = REPO / ".jarvis_state" / "gha_precise_kick.json"
JST = ZoneInfo("Asia/Tokyo")
LOG = "📎 GHA 定刻キック"


def due_jobs(cfg: dict[str, Any], now: datetime, kicked: dict[str, str]) -> list[str]:
    """now（JST）時点で起動すべき workflow ファイル名。"""
    grace = timedelta(minutes=int(cfg.get("grace_min") or 90))
    today = now.strftime("%Y-%m-%d")
    out: list[str] = []
    for j in cfg.get("jobs") or []:
        wf = str(j["workflow"])
        days = j.get("weekdays")
        if days and now.isoweekday() not in days:
            continue
        hh, mm = (int(x) for x in str(j["time"]).split(":"))
        target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if not (target <= now <= target + grace):
            continue
        if kicked.get(wf) == today:
            continue
        out.append(wf)
    return out


def _gh(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["gh", *args], capture_output=True, text=True, timeout=60)


def ran_since(repo: str, wf: str, since_utc: str) -> bool:
    """schedule が定刻どおり来ていた等、今日すでに実行があれば True。"""
    r = _gh(
        [
            "run", "list", "-R", repo, "-w", wf, "-L", "5",
            "--json", "createdAt",
            "--jq", f'[.[] | select(.createdAt >= "{since_utc}")] | length',
        ]
    )
    return r.returncode == 0 and (r.stdout.strip() or "0") != "0"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if os.environ.get("JARVIS_GHA_PRECISE_KICK_DISABLE") == "1":
        print(f"{LOG}: disabled")
        return 0

    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}
    repo = str(cfg.get("repo") or "")
    now = datetime.now(JST)
    today = now.strftime("%Y-%m-%d")
    state: dict[str, Any] = {}
    if STATE.is_file():
        try:
            state = json.loads(STATE.read_text(encoding="utf-8"))
        except ValueError:
            state = {}
    kicked: dict[str, str] = {k: v for k, v in (state.get("kicked") or {}).items() if v == today}

    worst = 0
    for wf in due_jobs(cfg, now, kicked):
        since = now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(ZoneInfo("UTC"))
        since_s = since.strftime("%Y-%m-%dT%H:%M:%SZ")
        if ran_since(repo, wf, since_s):
            print(f"{LOG}: {wf} 今日は実行済み → キック不要")
            kicked[wf] = today
            continue
        if args.dry_run:
            print(f"{LOG}: dry-run {wf} を起動する予定")
            continue
        r = _gh(["workflow", "run", wf, "-R", repo, "--ref", "main"])
        if r.returncode == 0:
            print(f"{LOG}: kicked {wf}")
            kicked[wf] = today
        else:
            print(f"{LOG}: {wf} FAIL: {r.stderr.strip()[:300]}", file=sys.stderr)
            worst = 1

    if not args.dry_run:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(
            json.dumps({"kicked": kicked, "at": now.isoformat()}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return worst


if __name__ == "__main__":
    raise SystemExit(main())
