#!/usr/bin/env python3
"""KURASHIFT: enqueue / run allowed local jobs from kurashift_jobs.

App buttons insert status=queued rows. This worker (Mac) runs them.

  python scripts/jarvis_kurashift_job_worker.py --dry-run
  python scripts/jarvis_kurashift_job_worker.py
  python scripts/jarvis_kurashift_job_worker.py --once
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[1]
PLAYBOOK = REPO / "config" / "trade_theme_playbook.yaml"
PY = Path("/Users/matsunomasaharu2/selenium_env/venv/bin/python")


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def load_allowed() -> set[str]:
    data = yaml.safe_load(PLAYBOOK.read_text(encoding="utf-8")) or {}
    return set(data.get("allowed_jobs") or [])


def sb_client() -> Any:
    from supabase import create_client

    url = os.environ.get("JARVIS_SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
    key = os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY required")
    return create_client(url, key)


def command_for(job_type: str, payload: dict[str, Any]) -> list[str]:
    py = str(PY if PY.exists() else sys.executable)
    year = str(payload.get("fiscal_year") or datetime.now().year - 1)
    mapping = {
        "lifeplan_ingest_actuals": [
            py,
            str(REPO / "scripts" / "jarvis_kurashift_lifeplan.py"),
            "--step",
            "ingest_actuals",
            "--year",
            year,
        ],
        "lifeplan_revise_budget": [
            py,
            str(REPO / "scripts" / "jarvis_kurashift_lifeplan.py"),
            "--step",
            "revise_budget",
            "--year",
            year,
        ],
        "lifeplan_update_century": [
            py,
            str(REPO / "scripts" / "jarvis_kurashift_lifeplan.py"),
            "--step",
            "update_century",
            "--year",
            year,
        ],
        "lifeplan_push_zaim": [
            py,
            str(REPO / "scripts" / "jarvis_kurashift_lifeplan.py"),
            "--step",
            "push_zaim",
            "--year",
            year,
        ],
        "lifeplan_snapshot": [
            py,
            str(REPO / "scripts" / "jarvis_kurashift_lifeplan.py"),
            "--step",
            "snapshot",
            "--year",
            year,
        ],
        "tax_build_yayoi_csv": [
            py,
            str(REPO / "scripts" / "jarvis_kurashift_tax.py"),
            "--build-csv",
            "--year",
            year,
        ],
        "tax_ingest_accountant_mail": [
            py,
            str(REPO / "scripts" / "jarvis_kurashift_tax.py"),
            "--ingest-mail",
            "--year",
            year,
        ],
        "tax_export_evidence": [
            py,
            str(REPO / "scripts" / "jarvis_kurashift_tax.py"),
            "--export-evidence",
            "--year",
            year,
            "--evidence-id",
            str(payload.get("evidence_id") or ""),
        ],
        "portfolio_weekly": [py, str(REPO / "scripts" / "jarvis_portfolio_weekly.py"), "--cloud-only"],
        "theme_preview": [
            py,
            str(REPO / "scripts" / "jarvis_kurashift_theme.py"),
            "--preview",
            "--theme-id",
            str(payload.get("theme_id") or ""),
        ],
        "theme_propose_from_status": [
            py,
            str(REPO / "scripts" / "jarvis_kurashift_theme.py"),
            "--propose-from-status",
            "--limit",
            str(payload.get("limit") or 6),
        ],
    }
    cmd = mapping.get(job_type)
    if not cmd:
        raise ValueError(f"unsupported job_type: {job_type}")
    return cmd


def run_one(sb: Any, row: dict[str, Any], *, dry_run: bool) -> str:
    job_id = row["id"]
    job_type = row["job_type"]
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    allowed = load_allowed()
    if job_type not in allowed:
        err = f"job_type not allowed: {job_type}"
        if not dry_run:
            sb.table("kurashift_jobs").update(
                {
                    "status": "failed",
                    "error_text": err,
                    "finished_at": now_iso(),
                }
            ).eq("id", job_id).execute()
        return "denied"

    print(f"# job {job_id} type={job_type}")
    if dry_run:
        print("  dry-run:", " ".join(command_for(job_type, payload)))
        return "dry_run"

    sb.table("kurashift_jobs").update(
        {"status": "running", "started_at": now_iso(), "error_text": None}
    ).eq("id", job_id).execute()

    cmd = command_for(job_type, payload)
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=int(payload.get("timeout_sec") or 1800),
            env={**os.environ, "KURASHIFT_JOB_ID": str(job_id)},
        )
        log = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
        ok = proc.returncode == 0
        result: dict[str, Any] = {"returncode": proc.returncode, "cmd": cmd}
        # Optional JSON line from child: KURASHIFT_RESULT:{...}
        for line in (proc.stdout or "").splitlines():
            if line.startswith("KURASHIFT_RESULT:"):
                try:
                    result["parsed"] = json.loads(line[len("KURASHIFT_RESULT:") :])
                except json.JSONDecodeError:
                    pass
        sb.table("kurashift_jobs").update(
            {
                "status": "succeeded" if ok else "failed",
                "log_text": log[-50000:],
                "result": result,
                "error_text": None if ok else (proc.stderr or f"exit {proc.returncode}")[:4000],
                "artifacts": (result.get("parsed") or {}).get("artifacts") or [],
                "finished_at": now_iso(),
            }
        ).eq("id", job_id).execute()
        return "ok" if ok else "fail"
    except Exception as e:  # noqa: BLE001
        sb.table("kurashift_jobs").update(
            {
                "status": "failed",
                "error_text": str(e)[:4000],
                "finished_at": now_iso(),
            }
        ).eq("id", job_id).execute()
        return "error"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--once", action="store_true", help="process at most one queued job")
    ap.add_argument("--limit", type=int, default=5)
    args = ap.parse_args()

    sb = sb_client()
    q = (
        sb.table("kurashift_jobs")
        .select("*")
        .eq("status", "queued")
        .order("created_at")
        .limit(1 if args.once else args.limit)
    )
    rows = q.execute().data or []
    if not rows:
        print("# no queued jobs")
        return 0
    for row in rows:
        run_one(sb, row, dry_run=args.dry_run)
        if args.once:
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
