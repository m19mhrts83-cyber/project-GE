#!/usr/bin/env python3
"""パートナー連絡整理係・夜枠パイプライン（111）

20:30 以降（または --force）に Mac で:
  ダッシュボードを開く → LINE 公式エクスポート取込 → CHRLINE sync（オプチャ除外）
  → 更新があるときだけ Slack #report（frame=night）

例:
  set -a && source .env.jarvis_private && set +a
  python scripts/jarvis_partner_night_pipeline.py --apply --dry-run-slack
  python scripts/jarvis_partner_night_pipeline.py --apply --push
  python scripts/jarvis_partner_night_pipeline.py --force --skip-line --dry-run-slack
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
PY = sys.executable
STATE = REPO / ".jarvis_state" / "partner_111_night.json"
REPORT = REPO / "scripts" / "jarvis_partner_slack_report.py"
POC = REPO / "line_unofficial_poc"
RUN_PATCH = POC / "run_patch.sh"
MANUAL = REPO / "215_kamiooya" / "C1_cursor" / "1b_Cursorマニュアル"
JST = ZoneInfo("Asia/Tokyo")

_LINE_APPEND_RE = re.compile(r"#\s*やり取り追記:\s*(\d+)\s*件")


def _now() -> datetime:
    return datetime.now(JST)


def _load_state() -> dict:
    if not STATE.is_file():
        return {}
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(data: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _mac_line_running() -> bool:
    try:
        r = subprocess.run(
            [
                "pgrep",
                "-f",
                r"application\.jp\.naver\.line\.mac|/Applications/LINE\.app",
            ],
            capture_output=True,
            check=False,
        )
        return r.returncode == 0
    except OSError:
        return False


def _run_capture(cmd: list[str], *, cwd: Path | None = None) -> tuple[int, str]:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd or REPO),
        text=True,
        capture_output=True,
        check=False,
    )
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    sys.stdout.write(proc.stdout or "")
    sys.stderr.write(proc.stderr or "")
    return int(proc.returncode), out


def _open_dashboard() -> str:
    url = (os.environ.get("JARVIS_DASHBOARD_URL") or "").strip()
    if not url:
        url = "https://jarvis-dashboard-amber.vercel.app/"
    try:
        subprocess.run(["open", url], check=False, timeout=30)
        print(f"📎 dashboard open: {url}")
        return url
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"⚠️ dashboard open failed: {e}", file=sys.stderr)
        return ""


def _parse_line_appended(blob: str) -> int:
    n = 0
    for m in _LINE_APPEND_RE.finditer(blob):
        n += int(m.group(1))
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="取込を実行（無いと dry）")
    ap.add_argument("--push", action="store_true", help="更新時 Slack #report")
    ap.add_argument("--dry-run-slack", action="store_true")
    ap.add_argument(
        "--force",
        action="store_true",
        help="時刻・当日済みチェックを無視",
    )
    ap.add_argument("--skip-dashboard", action="store_true")
    ap.add_argument("--skip-line", action="store_true")
    ap.add_argument("--skip-export", action="store_true")
    ap.add_argument(
        "--after-hour",
        type=int,
        default=20,
        help="この時以降（JST）のみ本線（既定20＝20:30窓は分も見る）",
    )
    ap.add_argument("--after-minute", type=int, default=30)
    args = ap.parse_args()

    now = _now()
    today = now.strftime("%Y-%m-%d")
    state = _load_state()

    if not args.force:
        if (now.hour, now.minute) < (args.after_hour, args.after_minute):
            print(
                f"⏭ 夜枠前（いま {now.strftime('%H:%M')} JST / "
                f"開始 {args.after_hour:02d}:{args.after_minute:02d}）"
            )
            return 0
        if state.get("last_ok_date") == today:
            print(f"⏭ 今夜は実施済み（{today}）")
            return 0

    fails: list[str] = []
    line_n = 0
    export_n = 0
    rc = 0

    if not args.skip_dashboard:
        _open_dashboard()

    # 公式エクスポート（Gmail inbox → yoritoori）— 定常 poll の取りこぼし保険
    if args.apply and not args.skip_export:
        gmail_ex = MANUAL / "line_export_gmail_to_inbox.py"
        inbox_ex = MANUAL / "line_export_inbox_to_yoritoori.py"
        for label, path in (("export_gmail", gmail_ex), ("export_inbox", inbox_ex)):
            if not path.is_file():
                print(f"⚠️ missing {path.name}", file=sys.stderr)
                continue
            code, blob = _run_capture([PY, str(path)], cwd=MANUAL)
            if code != 0:
                fails.append(f"{label} exit={code}")
                rc = code or rc
            for m in re.finditer(r"appended[=:]\s*(\d+)", blob, re.I):
                export_n += int(m.group(1))

    if args.apply and not args.skip_line:
        if _mac_line_running():
            fails.append("Mac版LINE起動中（トークン保護でLINEスキップ）")
            print(
                "# line: Mac版LINE 起動中のためスキップ（トークン保護）",
                file=sys.stderr,
            )
        elif not RUN_PATCH.is_file():
            fails.append("run_patch.sh missing")
            rc = 2
        else:
            cmd = [
                str(RUN_PATCH),
                "chrline_yoritoori_inbox_fetch.py",
                "--allow-qr-login",
                "--skip-open-chat",
            ]
            code, blob = _run_capture(cmd, cwd=POC)
            line_n = _parse_line_appended(blob)
            if code != 0:
                fails.append(f"line exit={code}")
                rc = code or rc
    elif not args.apply:
        print("# dry: LINE / 公式エクスポートは未実行（--apply で実行）")

    total_line = line_n + export_n
    print(
        f"📎 night_pipeline counts: line={line_n} export={export_n} "
        f"fails={fails or 'なし'}"
    )

    if not args.push and not args.dry_run_slack:
        if args.apply and not fails:
            state.update(
                {
                    "last_ok_date": today,
                    "last_run_at": now.isoformat(),
                    "last_line": line_n,
                    "last_export": export_n,
                }
            )
            _save_state(state)
        return rc

    if not REPORT.is_file():
        print(f"❌ missing {REPORT}", file=sys.stderr)
        return 2

    report_cmd = [
        PY,
        str(REPORT),
        "--frame",
        "night",
        "--gmail",
        "0",
        "--chatwork",
        "0",
        "--line",
        str(total_line),
        "--failures",
        "／".join(fails) if fails else "なし",
        "--next",
        "ダッシュボードと 5.やり取り.md を確認",
    ]
    if args.dry_run_slack:
        report_cmd.append("--dry-run")
        # dry-run では文面確認のためゼロでも表示
        report_cmd.append("--force")
    elif fails and total_line == 0:
        report_cmd.append("--force")

    code, _ = _run_capture(report_cmd)
    if args.apply and (not fails or total_line > 0) and code == 0:
        state.update(
            {
                "last_ok_date": today,
                "last_run_at": now.isoformat(),
                "last_line": line_n,
                "last_export": export_n,
                "last_fails": fails,
            }
        )
        _save_state(state)

    if rc:
        return rc
    return code


if __name__ == "__main__":
    raise SystemExit(main())
