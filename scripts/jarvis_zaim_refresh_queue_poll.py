#!/usr/bin/env python3
"""
/zaim「今すぐ更新」キュー（watch_status.payload.refresh_request）の完了／実行。

  # キューがあれば CSV check まで実行して done にする（Mac）
  python scripts/jarvis_zaim_refresh_queue_poll.py --apply
  # push 済みの鮮度を見て queued → done にするだけ（GHA 末尾）
  python scripts/jarvis_zaim_refresh_queue_poll.py --ack-only
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PY = Path.home() / "selenium_env" / "venv" / "bin" / "python"
if not PY.is_file():
    PY = Path(sys.executable)
WATCH_ID = "zaim_quality"


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sb_client():
    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        return None
    from supabase import create_client

    return create_client(url, key)


def get_payload(sb) -> dict:
    res = sb.table("watch_status").select("id,payload").eq("id", WATCH_ID).maybe_single().execute()
    data = res.data if hasattr(res, "data") else res
    if not data:
        return {}
    p = data.get("payload") if isinstance(data, dict) else None
    return dict(p) if isinstance(p, dict) else {}


def set_payload(sb, payload: dict) -> None:
    sb.table("watch_status").update(
        {"payload": payload, "updated_at": now_iso()}
    ).eq("id", WATCH_ID).execute()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ack-only", action="store_true", help="queued/running を done にするだけ")
    ap.add_argument("--apply", action="store_true", help="キュー時に check（＋任意で CSV）を実行")
    ap.add_argument("--with-csv", action="store_true", help="--apply 時に Mac CSV runner も")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    if not args.ack_only and not args.apply:
        args.ack_only = True

    sb = sb_client()
    if not sb:
        print(json.dumps({"ok": False, "reason": "no_supabase_env"}))
        return 0

    payload = get_payload(sb)
    req = payload.get("refresh_request")
    if not isinstance(req, dict):
        print(json.dumps({"ok": True, "note": "no refresh_request"}))
        return 0
    st = str(req.get("status") or "")
    if st not in ("queued", "running"):
        print(json.dumps({"ok": True, "note": f"status={st or 'empty'}"}))
        return 0

    if args.dry_run:
        print(json.dumps({"ok": True, "dry_run": True, "status": st}, ensure_ascii=False))
        return 0

    if args.apply and not args.ack_only:
        req["status"] = "running"
        req["started_at"] = now_iso()
        payload["refresh_request"] = req
        set_payload(sb, payload)
        if args.with_csv:
            subprocess.call(
                ["/bin/zsh", str(REPO / "launchd" / "zaim_csv_weekly_runner.sh")],
                cwd=str(REPO),
            )
        else:
            subprocess.call(
                [str(PY), str(REPO / "scripts" / "jarvis_zaim_bank_sync_check.py")],
                cwd=str(REPO),
            )
            subprocess.call(
                [str(PY), str(REPO / "scripts" / "jarvis_situation_watch.py"), "--write"],
                cwd=str(REPO),
            )
            subprocess.call(
                [
                    str(PY),
                    str(REPO / "scripts" / "jarvis_dashboard_push.py"),
                    "--watch-only",
                ],
                cwd=str(REPO),
            )

    # re-read in case push overwrote
    payload = get_payload(sb)
    req = dict(payload.get("refresh_request") or {})
    req["status"] = "done"
    req["finished_at"] = now_iso()
    payload["refresh_request"] = req
    set_payload(sb, payload)
    print(json.dumps({"ok": True, "status": "done"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
