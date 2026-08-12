#!/usr/bin/env python3
"""KURASHIFT lifeplan routine steps.

  --step ingest_actuals|revise_budget|update_century|push_zaim|snapshot
  --year 2025
  --dry-run
  --confirm-apply   # push_zaim のみ。Zaim 本番反映（承認必須）
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[1]
PLAYBOOK = REPO / "config" / "trade_theme_playbook.yaml"
STATE = REPO / ".jarvis_state" / "kurashift_lifeplan"
ZAIM_SYNC_DIR = (
    REPO / "215_kamiooya" / "C1_cursor" / "finance" / "zaim_budget_sync"
)
TAX_DIR = Path(
    "/Users/matsunomasaharu2/Library/CloudStorage/OneDrive-個人用/"
    "215_神・大家さん倶楽部/50_税金,確定申告"
).expanduser()
PY = Path("/Users/matsunomasaharu2/selenium_env/venv/bin/python")


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def playbook() -> dict:
    return yaml.safe_load(PLAYBOOK.read_text(encoding="utf-8")) or {}


def numbers_path() -> Path:
    p = Path((playbook().get("numbers") or {}).get("canonical_path") or "")
    return p


def emit_result(obj: dict) -> None:
    print("KURASHIFT_RESULT:" + json.dumps(obj, ensure_ascii=False))


def sb_client() -> Any | None:
    url = os.environ.get("JARVIS_SUPABASE_URL")
    key = os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        return None
    from supabase import create_client

    return create_client(url, key)


def find_zaim_summary(year: int) -> Path | None:
    year_dir = TAX_DIR / f"{year}年度"
    candidates = [
        year_dir / f"Zaim_ライフプラン_サマリー_{year}年度.csv",
        year_dir / f"Zaim_ライフプラン_サマリー_{year}年度.csv",  # NFKC ゆれ
    ]
    for p in candidates:
        if p.is_file():
            return p
    if year_dir.is_dir():
        for p in sorted(year_dir.glob("Zaim*サマリー*.csv")):
            return p
    return None


def find_zaim_raw(year: int) -> Path | None:
    p = TAX_DIR / f"{year}年度" / f"Zaim.{year}年度.csv"
    return p if p.is_file() else None


def parse_yen(raw: str) -> int:
    s = (raw or "").strip().replace(",", "").replace("円", "")
    if not s:
        return 0
    try:
        return int(round(float(s)))
    except ValueError:
        return 0


def classify_abg(category: str) -> str:
    """α貯蓄投資 / β生活 / γ自己・教育 / δ不動産 / other。"""
    c = (category or "").strip()
    cl = c.lower()
    # 明示プレフィックス（明細CSV）
    if c.startswith("α") or c.startswith("α.") or "α." in c[:4]:
        return "alpha"
    if c.startswith("β") or c.startswith("β.") or "β." in c[:4]:
        return "beta"
    if c.startswith("γ") or c.startswith("γ.") or "γ." in c[:4]:
        return "gamma"
    if c.startswith("δ") or "19" in c[:4] or c.startswith("19"):
        return "delta_re"
    # サマリー行
    if re.match(r"^0\.", c):
        return "income"
    if c.startswith("19") or "不動産" in c or "賃貸" in c or "不労所得" in c:
        return "delta_re"
    if c.startswith("B.") or "投資" in c:
        return "alpha"
    if any(
        x in c
        for x in (
            "6.2",
            "自己投資",
            "10.2",
            "こども教育",
            "こども学費",
            "21F",
            "AIリスキリング",
            "10.3",
            "学資",
        )
    ):
        return "gamma"
    if c.startswith("A.") or "会社費用" in c:
        return "other"
    if c.startswith("G.") or c.startswith("H.") or "借換" in c or "株売却" in c:
        return "other"
    # 生活費系
    if re.match(r"^(\d|1[0-7]|20)", c) or any(
        x in c for x in ("住まい", "食費", "水道", "通信", "医療", "交通", "保険", "帰省")
    ):
        return "beta"
    return "other"


def load_summary_csv(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            cat = (r.get("カテゴリ") or r.get("category") or "").strip()
            if not cat or cat == "合計" or cat.startswith("合計"):
                continue
            income = parse_yen(r.get("収入（円）") or r.get("収入") or "0")
            expense = parse_yen(r.get("支出（円）") or r.get("支出") or "0")
            rows.append(
                {
                    "category": cat,
                    "income": income,
                    "expense": expense,
                    "bucket": classify_abg(cat),
                }
            )
    return rows


def load_raw_zaim_abg(path: Path, year: int) -> dict[str, int]:
    """明細CSVのカテゴリ先頭 α/β/γ から支出合計（年フィルタ）。"""
    totals = {"alpha": 0, "beta": 0, "gamma": 0, "delta_re": 0, "other": 0}
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            dt = (r.get("日付") or "")[:4]
            if dt and dt.isdigit() and int(dt) != year:
                continue
            cat = (r.get("カテゴリ") or "").strip()
            exp = parse_yen(r.get("支出") or "0")
            if exp <= 0:
                continue
            b = classify_abg(cat)
            if b == "income":
                continue
            totals[b if b in totals else "other"] += exp
    return totals


def aggregate_abg(rows: list[dict[str, Any]]) -> dict[str, Any]:
    income_household = 0
    income_delta = 0
    expense = {"alpha": 0, "beta": 0, "gamma": 0, "delta_re": 0, "other": 0}
    by_cat: list[dict[str, Any]] = []

    for r in rows:
        b = r["bucket"]
        by_cat.append(r)
        if b == "income":
            income_household += int(r["income"])
            continue
        if b == "delta_re":
            income_delta += int(r["income"])
            expense["delta_re"] += int(r["expense"])
            continue
        key = b if b in expense else "other"
        expense[key] += int(r["expense"])

    living_base = income_household  # δ不動産を分母に含めない
    abg_spend = expense["alpha"] + expense["beta"] + expense["gamma"]
    pct = {}
    for k in ("alpha", "beta", "gamma"):
        pct[k] = round(100.0 * expense[k] / living_base, 1) if living_base else None

    targets = (playbook().get("lifeplan_routine") or {}).get("abg_targets") or {
        "alpha_save_pct": 20,
        "beta_living_pct": 60,
        "gamma_self_pct": 20,
    }
    return {
        "income_household_jpy": income_household,
        "income_delta_re_jpy": income_delta,
        "expense_alpha_jpy": expense["alpha"],
        "expense_beta_jpy": expense["beta"],
        "expense_gamma_jpy": expense["gamma"],
        "expense_delta_re_jpy": expense["delta_re"],
        "expense_other_jpy": expense["other"],
        "expense_abg_total_jpy": abg_spend,
        "alpha_pct": pct["alpha"],
        "beta_pct": pct["beta"],
        "gamma_pct": pct["gamma"],
        "targets": targets,
        "delta_excluded_from_denominator": True,
        "categories": by_cat,
    }


def save_snapshot(metrics: dict[str, Any], *, year: int, label: str, notes: str) -> bool:
    sb = sb_client()
    if not sb:
        return False
    sb.table("kurashift_plan_snapshots").insert(
        {
            "label": label,
            "fiscal_year": year,
            "snapshot_at": date.today().isoformat(),
            "metrics": metrics,
            "notes": notes,
        }
    ).execute()
    return True


def step_ingest_actuals(year: int, dry_run: bool) -> dict:
    np = numbers_path()
    summary = find_zaim_summary(year)
    raw = find_zaim_raw(year)
    source = None
    agg: dict[str, Any] | None = None

    if summary:
        rows = load_summary_csv(summary)
        agg = aggregate_abg(rows)
        source = str(summary)
    elif raw:
        totals = load_raw_zaim_abg(raw, year)
        living = sum(totals[k] for k in ("alpha", "beta", "gamma")) or 1
        targets = (playbook().get("lifeplan_routine") or {}).get("abg_targets") or {}
        agg = {
            "income_household_jpy": None,
            "expense_alpha_jpy": totals["alpha"],
            "expense_beta_jpy": totals["beta"],
            "expense_gamma_jpy": totals["gamma"],
            "expense_delta_re_jpy": totals["delta_re"],
            "expense_other_jpy": totals["other"],
            "alpha_pct": round(100.0 * totals["alpha"] / living, 1),
            "beta_pct": round(100.0 * totals["beta"] / living, 1),
            "gamma_pct": round(100.0 * totals["gamma"] / living, 1),
            "targets": targets,
            "note": "サマリー無しのため明細のαβγ支出比率（収入分母なし）",
            "delta_excluded_from_denominator": True,
        }
        source = str(raw)

    out: dict[str, Any] = {
        "step": "ingest_actuals",
        "fiscal_year": year,
        "numbers_exists": np.exists(),
        "numbers_path": str(np),
        "zaim_summary": str(summary) if summary else None,
        "zaim_raw": str(raw) if raw else None,
        "source": source,
        "metrics": {
            k: v
            for k, v in (agg or {}).items()
            if k != "categories"
        }
        if agg
        else None,
        "category_count": len((agg or {}).get("categories") or []) if agg else 0,
        "ready_for_revise": bool(agg),
        "note": (
            "Zaim 年度サマリーから αβγ を集計（δ不動産は分母外）。"
            "Numbers 表1への手転記は revise ステップ／相談で。"
            if agg
            else f"{year}年度の Zaim サマリー／明細が見つかりません。税フォルダへ CSV を置いて再実行。"
        ),
    }

    STATE.mkdir(parents=True, exist_ok=True)
    stamp = STATE / f"{year}_ingest_actuals.json"
    if not dry_run and agg:
        payload = {**out, "categories": (agg or {}).get("categories") or []}
        stamp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        out["artifacts"] = [{"kind": "state", "path": str(stamp)}]
        label = f"actuals_{year}_{date.today().isoformat()}"
        metrics = {
            "kind": "actuals",
            "fiscal_year": year,
            "source": source,
            **{k: v for k, v in agg.items() if k != "categories"},
            "ingested_at": now_iso(),
        }
        out["snapshot_saved"] = save_snapshot(
            metrics,
            year=year,
            label=label,
            notes="ingest_actuals from Zaim summary",
        )

    print(json.dumps(out, ensure_ascii=False, indent=2))
    emit_result(out)
    return out


def step_revise_budget(year: int, dry_run: bool) -> dict:
    abg = (playbook().get("lifeplan_routine") or {}).get("abg_targets") or {}
    stamp = STATE / f"{year}_ingest_actuals.json"
    prev = {}
    if stamp.is_file():
        try:
            prev = json.loads(stamp.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            prev = {}
    metrics = prev.get("metrics") or {}
    gaps = {}
    for key, target_key, label in (
        ("alpha_pct", "alpha_save_pct", "α"),
        ("beta_pct", "beta_living_pct", "β"),
        ("gamma_pct", "gamma_self_pct", "γ"),
    ):
        actual = metrics.get(key)
        target = abg.get(target_key)
        if actual is not None and target is not None:
            gaps[label] = {
                "actual_pct": actual,
                "target_pct": target,
                "delta_pp": round(float(actual) - float(target), 1),
            }
    out = {
        "step": "revise_budget",
        "fiscal_year": year,
        "abg_targets": abg,
        "from_actuals": bool(metrics),
        "gaps": gaps,
        "note": "補正は Numbers 正本で行い、固まったら push_zaim。ギャップはアプリでも表示。",
    }
    if not dry_run:
        p = STATE / f"{year}_revise_budget.json"
        STATE.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        out["artifacts"] = [{"kind": "state", "path": str(p)}]
    print(json.dumps(out, ensure_ascii=False, indent=2))
    emit_result(out)
    return out


def step_update_century(year: int, dry_run: bool) -> dict:
    out = {
        "step": "update_century",
        "fiscal_year": year,
        "numbers_path": str(numbers_path()),
        "numbers_exists": numbers_path().exists(),
        "note": "CF〜100歳の更新は Numbers 正本＋Jarvis相談。完了後に --step snapshot。",
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    emit_result(out)
    return out


def step_push_zaim(year: int, dry_run: bool, *, confirm_apply: bool) -> dict:
    np = numbers_path()
    extract = ZAIM_SYNC_DIR / "numbers_budget_extract.py"
    apply = ZAIM_SYNC_DIR / "zaim_budget_apply.py"
    out_csv = STATE / f"budget_{year}.csv"
    out: dict[str, Any] = {
        "step": "push_zaim",
        "fiscal_year": year,
        "numbers_exists": np.exists(),
        "extract_script": str(extract),
        "apply_script": str(apply),
        "csv_path": str(out_csv),
        "confirm_apply": confirm_apply,
        "applied": False,
        "live": False,
    }
    if dry_run:
        out["note"] = "dry-run: Numbers→CSV→Zaim は未実行"
        print(json.dumps(out, ensure_ascii=False, indent=2))
        emit_result(out)
        return out

    if not np.exists():
        out["error"] = "Numbers 正本が見つかりません"
        print(json.dumps(out, ensure_ascii=False, indent=2))
        emit_result(out)
        raise SystemExit(out["error"])

    STATE.mkdir(parents=True, exist_ok=True)
    py = str(PY if PY.exists() else sys.executable)
    proc = subprocess.run(
        [
            py,
            str(extract),
            "--year",
            str(year),
            "--numbers",
            str(np),
            "--output",
            str(out_csv),
        ],
        cwd=str(ZAIM_SYNC_DIR),
        capture_output=True,
        text=True,
        timeout=600,
    )
    out["extract_returncode"] = proc.returncode
    out["extract_log"] = ((proc.stdout or "") + (proc.stderr or ""))[-4000:]
    if proc.returncode != 0:
        out["error"] = "numbers_budget_extract failed"
        print(json.dumps(out, ensure_ascii=False, indent=2))
        emit_result(out)
        raise SystemExit(1)

    out["csv_exists"] = out_csv.is_file()
    out["artifacts"] = [{"kind": "csv", "path": str(out_csv)}]

    if not confirm_apply:
        out["note"] = (
            "CSV まで生成。Zaim 本番反映は payload.confirm_apply=true "
            "または --confirm-apply が必要（承認境界）。"
        )
        print(json.dumps(out, ensure_ascii=False, indent=2))
        emit_result(out)
        return out

    # 本番反映（明示承認時のみ）
    proc2 = subprocess.run(
        [
            py,
            str(apply),
            "--csv",
            str(out_csv),
            "--year",
            str(year),
            "--apply",
            "--yes",
        ],
        cwd=str(ZAIM_SYNC_DIR),
        capture_output=True,
        text=True,
        timeout=3600,
    )
    out["apply_returncode"] = proc2.returncode
    out["apply_log"] = ((proc2.stdout or "") + (proc2.stderr or ""))[-4000:]
    out["applied"] = proc2.returncode == 0
    out["live"] = True
    out["note"] = "Zaim 予算へ反映を実行した" if out["applied"] else "Zaim 反映失敗"
    print(json.dumps(out, ensure_ascii=False, indent=2))
    emit_result(out)
    if not out["applied"]:
        raise SystemExit(1)
    return out


def step_snapshot(year: int, dry_run: bool) -> dict:
    stamp = STATE / f"{year}_ingest_actuals.json"
    actuals = {}
    if stamp.is_file():
        try:
            actuals = (json.loads(stamp.read_text(encoding="utf-8")).get("metrics")) or {}
        except json.JSONDecodeError:
            actuals = {}
    metrics = {
        "kind": "plan",
        "alpha_target_pct": 20,
        "beta_target_pct": 60,
        "gamma_target_pct": 20,
        "label": f"plan_{year}_{date.today().isoformat()}",
        "actuals_ref": actuals,
    }
    out: dict[str, Any] = {
        "step": "snapshot",
        "fiscal_year": year,
        "metrics": metrics,
        "note": "Supabase kurashift_plan_snapshots へ書き込み（dry-run 以外）",
    }
    if not dry_run:
        out["saved"] = save_snapshot(
            metrics,
            year=year,
            label=metrics["label"],
            notes="auto from jarvis_kurashift_lifeplan.py snapshot",
        )
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
    ap.add_argument(
        "--confirm-apply",
        action="store_true",
        help="push_zaim で Zaim 本番反映を許可（未指定なら CSV 生成まで）",
    )
    args = ap.parse_args()

    if args.step == "push_zaim":
        step_push_zaim(args.year, args.dry_run, confirm_apply=args.confirm_apply)
        return 0

    fn = {
        "ingest_actuals": step_ingest_actuals,
        "revise_budget": step_revise_budget,
        "update_century": step_update_century,
        "snapshot": step_snapshot,
    }[args.step]
    fn(args.year, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
