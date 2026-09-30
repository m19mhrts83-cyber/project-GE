#!/usr/bin/env python3
"""
Zaim 銀行連携の失敗・残留 stale を Todoist に起票（要Jarvis連携）。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  /Users/matsunomasaharu2/selenium_env/venv/bin/python scripts/jarvis_zaim_bank_notify.py
  /Users/matsunomasaharu2/selenium_env/venv/bin/python scripts/jarvis_zaim_bank_notify.py --dry-run
  /Users/matsunomasaharu2/selenium_env/venv/bin/python scripts/jarvis_zaim_bank_notify.py --reason otp_required --accounts '★MUFG(アパート経営)'
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
CFG_PATH = REPO / "config" / "zaim_bank_sync_watch.yaml"
BANK_STATE = REPO / ".jarvis_state" / "zaim_bank_sync.json"
AUTO_STATE = REPO / ".jarvis_state" / "zaim_bank_auto.json"
PY = Path.home() / "selenium_env" / "venv" / "bin" / "python"
if not PY.is_file():
    PY = Path(sys.executable)


def now_iso() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S%z")


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_cfg() -> dict[str, Any]:
    return yaml.safe_load(CFG_PATH.read_text(encoding="utf-8")) or {}


def should_skip_dedupe(auto: dict[str, Any], fingerprint: str, days: int) -> bool:
    last = auto.get("last_todoist") or {}
    if str(last.get("fingerprint") or "") != fingerprint:
        return False
    at = str(last.get("at") or "")
    if len(at) < 10:
        return False
    try:
        dt = datetime.fromisoformat(at.replace("+0900", "+09:00"))
    except ValueError:
        return False
    return datetime.now(JST) - dt < timedelta(days=max(1, days))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--reason",
        default="",
        help="session_expired / otp_required / stale_persist / update_failed",
    )
    ap.add_argument("--accounts", default="", help="カンマ区切りの口座ラベル／match")
    ap.add_argument("--force", action="store_true", help="dedupe 無視")
    args = ap.parse_args(argv)

    cfg = load_cfg()
    notify = cfg.get("todoist_notify") or {}
    if not notify.get("enabled", True) and not args.force:
        print(json.dumps({"ok": True, "skipped": "todoist_notify.disabled"}))
        return 0

    bank = load_json(BANK_STATE)
    auto = load_json(AUTO_STATE)
    stale = list(bank.get("stale") or [])
    reason = (args.reason or "").strip()
    if not reason:
        if stale:
            reason = "stale_persist"
        else:
            print(json.dumps({"ok": True, "skipped": "nothing_to_notify"}))
            return 0

    labels = []
    if args.accounts.strip():
        labels = [x.strip() for x in args.accounts.split(",") if x.strip()]
    elif stale:
        labels = [str(s.get("label") or s.get("match") or "") for s in stale[:5]]

    fingerprint = f"{reason}|{'|'.join(sorted(labels))}"
    dedupe_days = int(notify.get("dedupe_days") or 5)
    if not args.force and should_skip_dedupe(auto, fingerprint, dedupe_days):
        print(
            json.dumps(
                {"ok": True, "skipped": "dedupe", "fingerprint": fingerprint},
                ensure_ascii=False,
            )
        )
        return 0

    lane = str(notify.get("lane") or "ai_raimo")
    extra_label = str(notify.get("label") or "要Jarvis連携,quick")
    title = f"[Zaim] 銀行連携要対応: {reason}"
    if labels:
        title = f"[Zaim] {reason} · {', '.join(labels[:3])}"
    note = (
        f"reason={reason}\n"
        f"accounts={', '.join(labels) or '—'}\n"
        f"bank_summary={bank.get('summary') or '—'}\n"
        f"next: scripts/jarvis_zaim_reconnect.py --from-stale\n"
        f"（OTP 値はチャットに出さない。env_hint / Messages から Jarvis が読む）"
    )
    comment = (
        "サマリ: Zaim 銀行連携の要再接続／OTP／セッション切れを検知したよ\n"
        "アウトプット:\n"
        "- [運用コマンド Zaim Watch](docs/運用コマンド一覧.md)\n"
        f"- reason: {reason}"
    )

    cmd = [
        str(PY),
        str(REPO / "scripts" / "jarvis_todoist_api.py"),
        "create-task",
        "--lane",
        lane,
        "--title",
        title[:200],
        "--note",
        note[:1500],
        "--label",
        extra_label,
        "--status",
        "オーナー確認",
        "--comment",
        comment,
        "--json",
    ]
    if args.dry_run:
        print(json.dumps({"ok": True, "dry_run": True, "cmd": cmd[2:]}, ensure_ascii=False, indent=2))
        return 0

    proc = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True)
    out = (proc.stdout or "").strip()
    print(out or proc.stderr)
    if proc.returncode != 0:
        return proc.returncode

    task_id = None
    try:
        task_id = json.loads(out).get("id")
    except Exception:
        pass
    auto["last_todoist"] = {
        "at": now_iso(),
        "fingerprint": fingerprint,
        "reason": reason,
        "task_id": task_id,
        "accounts": labels,
    }
    save_json(AUTO_STATE, auto)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
