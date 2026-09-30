#!/usr/bin/env python3
"""
Zaim 再接続オーケストレーション（P1）。

  「再接続して」→ stale 口座の連携更新 →（任意）CSV → bank_sync_check

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  /Users/matsunomasaharu2/selenium_env/venv/bin/python scripts/jarvis_zaim_reconnect.py --dry-run
  /Users/matsunomasaharu2/selenium_env/venv/bin/python scripts/jarvis_zaim_reconnect.py --from-stale
  /Users/matsunomasaharu2/selenium_env/venv/bin/python scripts/jarvis_zaim_reconnect.py --from-stale --with-csv

OTP / 画像認証は自動化しない。セッション切れは login を促して止まる。
値（パスワード）は標準出力に出さない。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PY = Path.home() / "selenium_env" / "venv" / "bin" / "python"
if not PY.is_file():
    PY = Path(sys.executable)
STATE = REPO / ".jarvis_state" / "zaim_bank_sync.json"
ZAIM_DIR = REPO / "215_kamiooya" / "C1_cursor" / "finance" / "zaim_budget_sync"
CSV_RUNNER = REPO / "launchd" / "zaim_csv_weekly_runner.sh"


def run(cmd: list[str], *, dry: bool) -> int:
    print(f"# {' '.join(cmd)}", file=sys.stderr)
    if dry:
        return 0
    return subprocess.call(cmd, cwd=str(REPO))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Zaim reconnect: stale update → check")
    ap.add_argument("--from-stale", action="store_true", default=True)
    ap.add_argument("--all-default", action="store_true", help="DEFAULT_NAMES を更新（stale 無視）")
    ap.add_argument("--with-csv", action="store_true", help="成功後に Mac CSV 週次 runner を実行")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-check", action="store_true")
    args = ap.parse_args(argv)

    stale_n = 0
    if STATE.is_file():
        try:
            stale_n = len(json.loads(STATE.read_text(encoding="utf-8")).get("stale") or [])
        except Exception:
            stale_n = 0
    print(
        json.dumps(
            {
                "phase": "start",
                "stale_n": stale_n,
                "with_csv": args.with_csv,
                "dry_run": args.dry_run,
            },
            ensure_ascii=False,
        ),
        file=sys.stderr,
    )

    manual = [
        str(PY),
        str(REPO / "scripts" / "jarvis_zaim_bank_sync_manual.py"),
    ]
    if args.all_default:
        pass
    else:
        manual.append("--from-stale")
    if args.headless:
        manual.append("--headless")

    rc = run(manual, dry=args.dry_run)
    if rc == 2:
        print(
            json.dumps(
                {
                    "ok": False,
                    "reason": "session_expired",
                    "next": f"cd {ZAIM_DIR} && {PY} zaim_budget_apply.py --login --login-method email",
                },
                ensure_ascii=False,
            )
        )
        return 2
    if rc != 0 and not args.dry_run:
        print(
            json.dumps(
                {
                    "ok": False,
                    "reason": "bank_update_failed",
                    "rc": rc,
                    "next": "OTP/UI 失敗の可能性。Zaim online_accounts を手動確認",
                },
                ensure_ascii=False,
            )
        )
        return rc

    if args.with_csv:
        if not CSV_RUNNER.is_file():
            print(json.dumps({"ok": False, "reason": "csv_runner_missing"}), file=sys.stderr)
            return 1
        crc = run(["/bin/zsh", str(CSV_RUNNER)], dry=args.dry_run)
        if crc != 0 and not args.dry_run:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "reason": "csv_export_failed",
                        "rc": crc,
                        "next": "Resource deadlock / ログイン切れをログで確認",
                    },
                    ensure_ascii=False,
                )
            )
            return crc

    if not args.skip_check:
        run(
            [str(PY), str(REPO / "scripts" / "jarvis_zaim_bank_sync_check.py")],
            dry=args.dry_run,
        )
        run(
            [str(PY), str(REPO / "scripts" / "jarvis_situation_watch.py"), "--write"],
            dry=args.dry_run,
        )
        run(
            [
                str(PY),
                str(REPO / "scripts" / "jarvis_dashboard_push.py"),
                "--watch-only",
            ],
            dry=args.dry_run,
        )

    summary = {"ok": True, "stale_before": stale_n}
    if STATE.is_file() and not args.dry_run:
        try:
            data = json.loads(STATE.read_text(encoding="utf-8"))
            summary["stale_after"] = len(data.get("stale") or [])
            summary["summary"] = data.get("summary")
        except Exception:
            pass
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
