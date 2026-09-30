#!/usr/bin/env python3
"""
Zaim 再接続オーケストレーション（P1/P2）。

  「再接続して」→ stale 口座の連携更新 →（任意）CSV → bank_sync_check →（任意）Todoist

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  /Users/matsunomasaharu2/selenium_env/venv/bin/python scripts/jarvis_zaim_reconnect.py --dry-run
  /Users/matsunomasaharu2/selenium_env/venv/bin/python scripts/jarvis_zaim_reconnect.py --from-stale
  /Users/matsunomasaharu2/selenium_env/venv/bin/python scripts/jarvis_zaim_reconnect.py --from-stale --with-csv --notify
  /Users/matsunomasaharu2/selenium_env/venv/bin/python scripts/jarvis_zaim_reconnect.py --from-stale --try-otp

OTP 値は標準出力に出さない。--try-otp は manual に渡し、画面へ半自動入力する。
画像認証は対象外。bank_sync_manual と CSV は zaim_playwright.lock を共有。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[1]
PY = Path.home() / "selenium_env" / "venv" / "bin" / "python"
if not PY.is_file():
    PY = Path(sys.executable)
STATE = REPO / ".jarvis_state" / "zaim_bank_sync.json"
CFG = REPO / "config" / "zaim_bank_sync_watch.yaml"
ZAIM_DIR = REPO / "215_kamiooya" / "C1_cursor" / "finance" / "zaim_budget_sync"
CSV_RUNNER = REPO / "launchd" / "zaim_csv_weekly_runner.sh"
CHANNEL_ALIASES = {
    "sms": "sms_messages",
    "sms_messages": "sms_messages",
    "gmail": "gmail_api",
    "gmail_api": "gmail_api",
    "none": "none",
    "off": "none",
    "": "none",
}


def normalize_otp_channel(raw: str | None) -> str:
    key = str(raw or "").strip().lower()
    return CHANNEL_ALIASES.get(key, key)


def run(cmd: list[str], *, dry: bool) -> int:
    print(f"# {' '.join(cmd)}", file=sys.stderr)
    if dry:
        return 0
    return subprocess.call(cmd, cwd=str(REPO))


def run_capture(cmd: list[str], *, dry: bool) -> tuple[int, str]:
    print(f"# {' '.join(cmd)}", file=sys.stderr)
    if dry:
        return 0, "[]"
    proc = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True)
    out = (proc.stdout or "").strip()
    if out:
        print(out)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)
    return proc.returncode, out


def try_otp_for_stale(*, dry: bool) -> list[dict[str, Any]]:
    """YAML otp_channel がある stale 口座だけ OTP 取得を試す（コードは出さない）。"""
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8")) if CFG.is_file() else {}
    bank = {}
    if STATE.is_file():
        try:
            bank = json.loads(STATE.read_text(encoding="utf-8"))
        except Exception:
            bank = {}
    reports: list[dict[str, Any]] = []
    sys.path.insert(0, str(REPO / "scripts"))
    for row in bank.get("stale") or []:
        match = str(row.get("match") or "")
        label = str(row.get("label") or match)
        acc = None
        for a in cfg.get("accounts") or []:
            m = str(a.get("match") or "")
            if m and (m in match or match in m):
                acc = a
                break
        if not acc:
            continue
        channel = normalize_otp_channel(acc.get("otp_channel"))
        if channel in ("", "none", "off"):
            reports.append({"label": label, "otp": "skipped_no_channel"})
            continue
        if channel not in ("sms_messages", "gmail_api"):
            reports.append(
                {"label": label, "otp": "unsupported_channel", "channel": channel}
            )
            continue
        hint = str(acc.get("otp_sender_hint") or "")
        if dry:
            reports.append({"label": label, "otp": "dry_run", "channel": channel})
            continue
        try:
            from jarvis_transfer_otp import OtpFetchError, NeedsUserOtp, fetch_otp

            fetch_otp(otp_channel=channel, sender_hint=hint, timeout_sec=45)
            # 値は出さない（画面入力は bank_sync_manual --try-otp）
            reports.append({"label": label, "otp": "obtained", "channel": channel})
        except NeedsUserOtp:
            reports.append({"label": label, "otp": "needs_user", "channel": channel})
        except OtpFetchError as e:
            reports.append(
                {"label": label, "otp": "failed", "channel": channel, "reason": str(e)}
            )
        except Exception as e:
            reports.append(
                {
                    "label": label,
                    "otp": "error",
                    "channel": channel,
                    "reason": type(e).__name__,
                }
            )
    return reports


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Zaim reconnect: stale update → check")
    ap.add_argument("--from-stale", action="store_true", default=True)
    ap.add_argument("--all-default", action="store_true", help="DEFAULT_NAMES を更新（stale 無視）")
    ap.add_argument("--with-csv", action="store_true", help="成功後に Mac CSV 週次 runner を実行")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-check", action="store_true")
    ap.add_argument("--notify", action="store_true", help="失敗／残留 stale で Todoist 起票")
    ap.add_argument(
        "--try-otp",
        action="store_true",
        help="OTP が出たら SMS/Gmail 取得→画面入力（値は出さない）。事前 probe も行う",
    )
    ap.add_argument(
        "--lock-wait",
        type=int,
        default=120,
        help="Playwright 共有ロック待ち秒（CSV と競合時）",
    )
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
                "try_otp": args.try_otp,
            },
            ensure_ascii=False,
        ),
        file=sys.stderr,
    )

    otp_reports: list[dict[str, Any]] = []
    if args.try_otp:
        otp_reports = try_otp_for_stale(dry=args.dry_run)
        print(json.dumps({"otp_probe": otp_reports}, ensure_ascii=False), file=sys.stderr)

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
    if args.try_otp:
        manual.append("--try-otp")
    if args.lock_wait:
        manual.extend(["--lock-wait", str(args.lock_wait)])

    rc, out = run_capture(manual, dry=args.dry_run)
    notify_reason = ""
    if rc == 4:
        print(
            json.dumps(
                {
                    "ok": False,
                    "reason": "playwright_lock_busy",
                    "next": "CSV週次と競合。数分後に再実行",
                },
                ensure_ascii=False,
            )
        )
        if args.notify:
            run(
                [
                    str(PY),
                    str(REPO / "scripts" / "jarvis_zaim_bank_notify.py"),
                    "--reason",
                    "update_failed",
                ],
                dry=args.dry_run,
            )
        return 4
    if rc == 2:
        notify_reason = "session_expired"
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
        if args.notify:
            run(
                [
                    str(PY),
                    str(REPO / "scripts" / "jarvis_zaim_bank_notify.py"),
                    "--reason",
                    "session_expired",
                ],
                dry=args.dry_run,
            )
        return 2
    if rc == 3:
        notify_reason = "otp_required"
        print(
            json.dumps(
                {
                    "ok": False,
                    "reason": "otp_required",
                    "next": "OTP/画像認証。--try-otp で SMS/Gmail を試し、値は Jarvis が入力（チャット禁止）",
                    "otp_probe": otp_reports,
                },
                ensure_ascii=False,
            )
        )
        if args.notify:
            run(
                [
                    str(PY),
                    str(REPO / "scripts" / "jarvis_zaim_bank_notify.py"),
                    "--reason",
                    "otp_required",
                ],
                dry=args.dry_run,
            )
        return 3
    if rc != 0 and not args.dry_run:
        notify_reason = "update_failed"
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
        if args.notify:
            run(
                [
                    str(PY),
                    str(REPO / "scripts" / "jarvis_zaim_bank_notify.py"),
                    "--reason",
                    "update_failed",
                ],
                dry=args.dry_run,
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

    summary: dict[str, Any] = {"ok": True, "stale_before": stale_n, "otp_probe": otp_reports}
    if STATE.is_file() and not args.dry_run:
        try:
            data = json.loads(STATE.read_text(encoding="utf-8"))
            summary["stale_after"] = len(data.get("stale") or [])
            summary["summary"] = data.get("summary")
            if summary["stale_after"] and args.notify:
                run(
                    [
                        str(PY),
                        str(REPO / "scripts" / "jarvis_zaim_bank_notify.py"),
                        "--reason",
                        "stale_persist",
                    ],
                    dry=False,
                )
        except Exception:
            pass
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
