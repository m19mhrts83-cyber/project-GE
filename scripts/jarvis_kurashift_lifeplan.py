#!/usr/bin/env python3
"""KURASHIFT lifeplan routine steps (scaffold → deepen later).

  --step ingest_actuals|revise_budget|update_century|push_zaim|snapshot
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
PLAYBOOK = REPO / "config" / "trade_theme_playbook.yaml"
STATE = REPO / ".jarvis_state" / "kurashift_lifeplan"
ZAIM_SYNC = (
    REPO
    / "215_kamiooya"
    / "C1_cursor"
    / "finance"
    / "zaim_budget_sync"
    / "numbers_budget_extract.py"
)


def playbook() -> dict:
    return yaml.safe_load(PLAYBOOK.read_text(encoding="utf-8")) or {}


def numbers_path() -> Path:
    p = Path((playbook().get("numbers") or {}).get("canonical_path") or "")
    return p


def emit_result(obj: dict) -> None:
    print("KURASHIFT_RESULT:" + json.dumps(obj, ensure_ascii=False))


def step_ingest_actuals(year: int, dry_run: bool) -> dict:
    """Phase1: record intent + Numbers path check. Full finance→table1 later."""
    np = numbers_path()
    out = {
        "step": "ingest_actuals",
        "fiscal_year": year,
        "numbers_exists": np.exists(),
        "numbers_path": str(np),
        "note": "財務実績の自動転記は次フェーズ。ここでは正本パスと年次ジョブ枠を確立。",
    }
    STATE.mkdir(parents=True, exist_ok=True)
    stamp = STATE / f"{year}_ingest_actuals.json"
    if not dry_run:
        stamp.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        out["artifacts"] = [{"kind": "state", "path": str(stamp)}]
    print(json.dumps(out, ensure_ascii=False, indent=2))
    emit_result(out)
    return out


def step_revise_budget(year: int, dry_run: bool) -> dict:
    abg = (playbook().get("lifeplan_routine") or {}).get("abg_targets") or {}
    out = {
        "step": "revise_budget",
        "fiscal_year": year,
        "abg_targets": abg,
        "note": "実績差分の補正UIはアプリ側。ここでは目標%を確認。",
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    emit_result(out)
    return out


def step_update_century(year: int, dry_run: bool) -> dict:
    out = {
        "step": "update_century",
        "fiscal_year": year,
        "note": "CF〜100歳の更新は Numbers 正本＋相談。スナップショット保存は --step snapshot。",
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    emit_result(out)
    return out


def step_push_zaim(year: int, dry_run: bool) -> dict:
    """Call existing extract dry path; full Zaim apply stays behind explicit flags later."""
    np = numbers_path()
    cmd_note = f"numbers_budget_extract.py --numbers {np}"
    out = {
        "step": "push_zaim",
        "fiscal_year": year,
        "extract_script": str(ZAIM_SYNC),
        "numbers_exists": np.exists(),
        "command_hint": f"numbers_budget_extract.py --numbers {np}",
        "note": "本番 Zaim 反映は既存 zaim_budget_sync を承認後に実行。このステップでは正本パス確認のみ。",
    }
    if not dry_run and not np.exists():
        print(json.dumps(out, ensure_ascii=False, indent=2))
        emit_result(out)
        raise SystemExit("Numbers 正本が見つかりません")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    emit_result(out)
    return out


def step_snapshot(year: int, dry_run: bool) -> dict:
    metrics = {
        "alpha_target_pct": 20,
        "beta_target_pct": 60,
        "gamma_target_pct": 20,
        "label": f"plan_{year}_{date.today().isoformat()}",
    }
    out = {
        "step": "snapshot",
        "fiscal_year": year,
        "metrics": metrics,
        "note": "Supabase kurashift_plan_snapshots へ書き込み（dry-run 以外）",
    }
    if not dry_run:
        url = os.environ.get("JARVIS_SUPABASE_URL")
        key = os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY")
        if url and key:
            from supabase import create_client

            sb = create_client(url, key)
            row = {
                "label": metrics["label"],
                "fiscal_year": year,
                "snapshot_at": date.today().isoformat(),
                "metrics": metrics,
                "notes": "auto from jarvis_kurashift_lifeplan.py",
            }
            sb.table("kurashift_plan_snapshots").insert(row).execute()
            out["saved"] = True
    print(json.dumps(out, ensure_ascii=False, indent=2))
    emit_result(out)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--step",
        required=True,
        choices=[
            "ingest_actuals",
            "revise_budget",
            "update_century",
            "push_zaim",
            "snapshot",
        ],
    )
    ap.add_argument("--year", type=int, default=date.today().year - 1)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    fn = {
        "ingest_actuals": step_ingest_actuals,
        "revise_budget": step_revise_budget,
        "update_century": step_update_century,
        "push_zaim": step_push_zaim,
        "snapshot": step_snapshot,
    }[args.step]
    fn(args.year, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
