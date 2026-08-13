#!/usr/bin/env python3
"""③-A 計画補正プレビュー／スナップショット。

dry-run（既定）: RE-1b 相当の差分を計算して JSON を出すだけ。
apply=true: .jarvis_state と kurashift_plan_snapshots に保存（Numbers 直書きはしない）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
STATE = Path.home() / "git-repos" / ".jarvis_state" / "kurashift_re_revise"
sys.path.insert(0, str(REPO / "scripts"))


def sb_client():
    url = os.environ.get("JARVIS_SUPABASE_URL")
    key = os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        return None
    from supabase import create_client

    return create_client(url, key)


def emit_result(out: dict) -> None:
    print(json.dumps({"result": out}, ensure_ascii=False))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true", default=False)
    ap.add_argument("--apply", action="store_true", default=False)
    ap.add_argument(
        "--note",
        default="",
        help="承認メモ（Numbersで直すチェックリストなど）",
    )
    args = ap.parse_args()
    year = args.year or datetime.now().year
    apply = bool(args.apply) and not args.dry_run

    # 目標月次 CF（合算）50万。実績は finance category year の粗近似
    goal_month = 500_000
    months = max(1, datetime.now().month - 1) if datetime.now().year == year else 12
    plan_ytd = goal_month * months
    actual_ytd = 0
    sb = sb_client()
    if sb is not None:
        rows = (
            sb.table("kurashift_finance_category_year")
            .select("category, income_jpy, expense_jpy, fiscal_year")
            .eq("fiscal_year", year)
            .limit(500)
            .execute()
            .data
            or []
        )
        for r in rows:
            cat = (r.get("category") or "")
            if "19" in cat or "賃貸" in cat or "家賃" in cat:
                actual_ytd += int(float(r.get("income_jpy") or 0)) - int(
                    float(r.get("expense_jpy") or 0)
                )

    delta = actual_ytd - plan_ytd
    pct = round(actual_ytd / plan_ytd * 100, 1) if plan_ytd else None
    out = {
        "ok": True,
        "job": "re_revise_plan",
        "fiscal_year": year,
        "dry_run": not apply,
        "applied": False,
        "plan_month_yen": goal_month,
        "months": months,
        "plan_ytd_yen": plan_ytd,
        "actual_ytd_yen": actual_ytd,
        "delta_yen": delta,
        "pct": pct,
        "checklist": [
            "Numbers 19不動産の計画行を差分に合わせて直す（アプリは直書きしない）",
            "直したら buy_plan / lifeplan の再取込を検討",
            "翌年の月次計画に反映したら snapshot",
        ],
        "note": (args.note or "").strip() or None,
        "at": datetime.now(timezone.utc).isoformat(),
    }

    if apply:
        STATE.mkdir(parents=True, exist_ok=True)
        path = STATE / f"{year}_re_revise_plan.json"
        path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        out["artifacts"] = [{"kind": "state", "path": str(path)}]
        if sb is not None:
            sb.table("kurashift_plan_snapshots").insert(
                {
                    "label": f"re_revise_plan {year}",
                    "fiscal_year": year,
                    "metrics": out,
                    "notes": out.get("note")
                    or "Numbersは手動。dry-run→承認スナップ",
                }
            ).execute()
            out["snapshot"] = True
        out["applied"] = True
        out["dry_run"] = False

    print(json.dumps(out, ensure_ascii=False, indent=2))
    emit_result(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
