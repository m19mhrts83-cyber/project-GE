#!/usr/bin/env python3
"""
Jarvis: Zaim CSV → 法人/個人別の月次財務メトリクス（ローカルJSON＋任意で Supabase）

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  python scripts/jarvis_finance_metrics.py
  python scripts/jarvis_finance_metrics.py --year 2026 --month 7
  python scripts/jarvis_finance_metrics.py --push
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
MAP_PATH = REPO / "config" / "finance_entity_map.yaml"
OUT_PATH = REPO / ".jarvis_state" / "finance_metrics.json"
DEFAULT_CSV = Path(
    "~/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/50_税金,確定申告"
).expanduser()


def load_map() -> dict[str, Any]:
    return yaml.safe_load(MAP_PATH.read_text(encoding="utf-8")) or {}


def resolve_csv(year: int) -> Path:
    p = DEFAULT_CSV / f"{year}年度" / f"Zaim.{year}年度.csv"
    return p


def match_rule(text: str, rules: list[dict[str, Any]]) -> dict[str, Any] | None:
    t = text or ""
    for r in rules:
        m = str(r.get("match") or "")
        if m and m in t:
            return r
    return None


def classify_row(row: dict[str, str], cfg: dict[str, Any]) -> tuple[str, str]:
    """returns (entity, kind)"""
    method = (row.get("方法") or "").strip()
    if method in (cfg.get("exclude_methods") or []):
        return "skip", "transfer"
    cat = (row.get("カテゴリ") or "").strip()
    pay = (row.get("支払元") or "").strip()
    dep = (row.get("入金先") or "").strip()

    cr = match_rule(cat, cfg.get("category_rules") or [])
    if cr:
        return str(cr.get("entity") or "personal"), str(cr.get("kind") or "other")

    ar = match_rule(pay, cfg.get("account_rules") or []) or match_rule(
        dep, cfg.get("account_rules") or []
    )
    entity = str((ar or {}).get("entity") or "personal")
    defaults = cfg.get("defaults") or {}
    if method == "income":
        kind = str(defaults.get("income_kind") or "other_income")
    else:
        kind = str(defaults.get("expense_kind") or "other_expense")
    # soft repair detect
    if "修繕" in cat or "修繕" in (row.get("品目") or "") or "修繕" in (row.get("メモ") or ""):
        kind = "repair"
    if "家賃" in cat:
        kind = "rent_income" if method == "income" else kind
    return entity, kind


def yen(row: dict[str, str], field: str) -> float:
    try:
        return float(str(row.get(field) or "0").replace(",", "") or 0)
    except ValueError:
        return 0.0


def aggregate(csv_path: Path, cfg: dict[str, Any], year: int, month: int | None) -> dict[str, Any]:
    buckets: dict[tuple[str, str, str], float] = defaultdict(float)
    # key: (ym, entity, metric)
    skipped = 0
    used = 0
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            d = (row.get("日付") or "").strip()
            if len(d) < 7:
                continue
            try:
                dt = datetime.strptime(d[:10], "%Y-%m-%d").date()
            except ValueError:
                continue
            if dt.year != year:
                continue
            if month is not None and dt.month != month:
                continue
            ym = f"{dt.year:04d}-{dt.month:02d}"
            entity, kind = classify_row(row, cfg)
            if entity == "skip":
                skipped += 1
                continue
            method = (row.get("方法") or "").strip()
            income = yen(row, "収入")
            expense = yen(row, "支出")
            used += 1
            if method == "income" or income > 0:
                buckets[(ym, entity, "income_total")] += income
                if kind == "rent_income":
                    buckets[(ym, entity, "rent_income")] += income
                else:
                    buckets[(ym, entity, kind)] += income
            if method == "payment" or expense > 0:
                buckets[(ym, entity, "expense_total")] += expense
                if kind == "repair":
                    buckets[(ym, entity, "repair_expense")] += expense
                elif kind.startswith("rental") or kind == "rental_expense":
                    buckets[(ym, entity, "rental_expense")] += expense
                else:
                    buckets[(ym, entity, "other_expense")] += expense

    # cashflow = income - expense per entity/month
    months = sorted({k[0] for k in buckets})
    entities = ("corporate", "personal")
    for ym in months:
        for ent in entities:
            inc = buckets.get((ym, ent, "income_total"), 0.0)
            exp = buckets.get((ym, ent, "expense_total"), 0.0)
            buckets[(ym, ent, "cashflow")] = inc - exp

    metrics = []
    for (ym, ent, metric), value in sorted(buckets.items()):
        metrics.append(
            {
                "metric": metric,
                "entity": ent,
                "recorded_at": f"{ym}-01",
                "value": round(value, 0),
                "unit": "JPY",
            }
        )
    return {
        "updated_at": datetime.now(JST).isoformat(),
        "source": str(csv_path),
        "year": year,
        "month": month,
        "rows_used": used,
        "rows_skipped_transfer": skipped,
        "metrics": metrics,
    }


def push_supabase(result: dict[str, Any]) -> int:
    from supabase import create_client

    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_* 未設定")
    sb = create_client(url, key)
    rows = []
    for m in result.get("metrics") or []:
        rows.append(
            {
                "metric": m["metric"],
                "value": m["value"],
                "unit": m.get("unit") or "JPY",
                "entity": m["entity"],
                "recorded_at": m["recorded_at"],
                "payload": {},
            }
        )
    # soft metrics（Vポイント残高・ETC還元）も同梱
    today = date.today().isoformat()
    state = REPO / ".jarvis_state"
    try:
        cad = json.loads((state / "vpoint_cadence.json").read_text(encoding="utf-8"))
        if cad.get("last_balance_pt") is not None:
            rows.append(
                {
                    "metric": "vpoint_balance",
                    "value": float(cad["last_balance_pt"]),
                    "unit": "pt",
                    "entity": "personal",
                    "recorded_at": today,
                    "payload": {},
                }
            )
    except Exception:
        pass
    try:
        etc = json.loads((state / "etc_monthly.json").read_text(encoding="utf-8"))
        rb = (etc.get("last_result_b") or {}).get("rebate_yen")
        if rb is not None:
            rows.append(
                {
                    "metric": "etc_rebate_last",
                    "value": float(rb),
                    "unit": "JPY",
                    "entity": "personal",
                    "recorded_at": today,
                    "payload": {
                        "target_month": (etc.get("last_result_b") or {}).get(
                            "target_month"
                        )
                    },
                }
            )
    except Exception:
        pass

    n = 0
    for i in range(0, len(rows), 80):
        chunk = rows[i : i + 80]
        sb.table("metrics").upsert(
            chunk, on_conflict="metric,entity,recorded_at"
        ).execute()
        n += len(chunk)
    sb.table("sync_meta").upsert(
        {
            "key": "finance_pushed_at",
            "value": datetime.now(JST).isoformat(),
            "updated_at": datetime.now(JST).isoformat(),
        },
        on_conflict="key",
    ).execute()
    return n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=datetime.now(JST).year)
    ap.add_argument("--month", type=int, default=None, help="指定月のみ。省略で年全月")
    ap.add_argument("--csv", type=Path, default=None)
    ap.add_argument("--push", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    cfg = load_map()
    csv_path = args.csv or resolve_csv(args.year)
    if not csv_path.is_file():
        print(f"# CSV なし: {csv_path}", file=sys.stderr)
        return 1
    result = aggregate(csv_path, cfg, args.year, args.month)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"# wrote {OUT_PATH} metrics={len(result['metrics'])}", file=sys.stderr)

    # short report: latest month cashflow
    by_ym: dict[str, dict[str, float]] = defaultdict(dict)
    for m in result["metrics"]:
        if m["metric"] in ("cashflow", "rent_income", "expense_total"):
            by_ym[m["recorded_at"][:7]][f"{m['entity']}.{m['metric']}"] = m["value"]
    for ym in sorted(by_ym)[-3:]:
        d = by_ym[ym]
        print(
            f"  {ym} 法人CF={d.get('corporate.cashflow', 0):,.0f} "
            f"個人CF={d.get('personal.cashflow', 0):,.0f} "
            f"法人家賃={d.get('corporate.rent_income', 0):,.0f} "
            f"個人家賃={d.get('personal.rent_income', 0):,.0f}"
        )

    if args.push:
        n = push_supabase(result)
        print(f"# pushed {n}", file=sys.stderr)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
