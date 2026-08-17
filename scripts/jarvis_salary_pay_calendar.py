#!/usr/bin/env python3
"""給与・賞与の着金日と余り見積（カード引落バッファ連携）。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_salary_pay_calendar.py
  ~/selenium_env/venv/bin/python scripts/jarvis_salary_pay_calendar.py --json
  ~/selenium_env/venv/bin/python scripts/jarvis_salary_pay_calendar.py --month 2026-08

ルール:
  - 給与: 毎月20日。土日祝なら直前の平日（多くは金曜）
  - 余り着金: Olive／SMBC刈谷（2026-08〜）。固定3口座は触らない
  - 大型資金移動は余り着金確認後（config.card_settlement.wait_for_salary_before_xfer）
  - 賞与: 名目1日だが実績はZaim正（2026夏は6/24）
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from statistics import median
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO / "config" / "salary_pay_calendar.yaml"
DEFAULT_CSV = Path.home() / (
    "Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/"
    "50_税金,確定申告/2026年度/Zaim.2026年度.csv"
)

# 内閣府ベースの固定祝日＋春分/秋分の目安（年ごと要確認）。jpholiday 未導入時のフォールバック。
_JP_HOLIDAYS_EXTRA: dict[date, str] = {
    date(2026, 1, 1): "元日",
    date(2026, 1, 12): "成人の日",
    date(2026, 2, 11): "建国記念の日",
    date(2026, 2, 23): "天皇誕生日",
    date(2026, 3, 20): "春分の日",
    date(2026, 4, 29): "昭和の日",
    date(2026, 5, 3): "憲法記念日",
    date(2026, 5, 4): "みどりの日",
    date(2026, 5, 5): "こどもの日",
    date(2026, 5, 6): "振替休日",
    date(2026, 7, 20): "海の日",
    date(2026, 8, 11): "山の日",
    date(2026, 9, 21): "敬老の日",
    date(2026, 9, 22): "国民の休日",
    date(2026, 9, 23): "秋分の日",
    date(2026, 10, 12): "スポーツの日",
    date(2026, 11, 3): "文化の日",
    date(2026, 11, 23): "勤労感謝の日",
    date(2027, 1, 1): "元日",
    date(2027, 1, 11): "成人の日",
    date(2027, 2, 11): "建国記念の日",
    date(2027, 2, 23): "天皇誕生日",
    date(2027, 3, 21): "春分の日",
    date(2027, 4, 29): "昭和の日",
    date(2027, 5, 3): "憲法記念日",
    date(2027, 5, 4): "みどりの日",
    date(2027, 5, 5): "こどもの日",
    date(2027, 7, 19): "海の日",
    date(2027, 8, 11): "山の日",
}


def load_config() -> dict[str, Any]:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}


def is_jp_holiday(d: date) -> bool:
    try:
        import jpholiday  # type: ignore

        return bool(jpholiday.is_holiday(d))
    except Exception:
        return d in _JP_HOLIDAYS_EXTRA


def is_bank_non_business_day(d: date) -> bool:
    return d.weekday() >= 5 or is_jp_holiday(d)


def previous_business_day(d: date) -> date:
    cur = d
    while is_bank_non_business_day(cur):
        cur -= timedelta(days=1)
    return cur


def salary_pay_date(year: int, month: int, nominal_day: int = 20) -> date:
    """指定月の給与着金日（20日が非営業日なら直前の営業日）。"""
    # 月末越え防止
    import calendar

    last = calendar.monthrange(year, month)[1]
    day = min(nominal_day, last)
    return previous_business_day(date(year, month, day))


def bonus_pay_date_nominal(year: int, month: int, nominal_day: int = 1) -> date:
    """名目の賞与日（1日）。実績は Zaim を正とし、この関数はカレンダー用。"""
    import calendar

    last = calendar.monthrange(year, month)[1]
    day = min(nominal_day, last)
    return previous_business_day(date(year, month, day))


def _parse_yen(raw: str) -> int:
    try:
        return int(float(raw or 0))
    except ValueError:
        return 0


def load_salary_rows(csv_path: Path) -> list[dict[str, Any]]:
    if not csv_path.is_file():
        return []
    out: list[dict[str, Any]] = []
    with csv_path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            d = row.get("日付") or ""
            item = (
                (row.get("品目") or "")
                + (row.get("お店") or "")
                + (row.get("メモ") or "")
            )
            if "ミツビシジユウコウ" not in item and "三菱重工" not in item:
                # 給与行は会社名付きが多い。フォールバックで「給与」のみは固定振分にも付く
                if "給与" not in item and "賞与" not in item:
                    continue
            inc = _parse_yen(row.get("収入") or "0")
            if inc <= 0:
                continue
            kind = "bonus" if ("賞与" in item or "ボーナス" in item) else "salary"
            if kind == "salary" and "給与" not in item and "賞与" not in item:
                continue
            out.append(
                {
                    "date": d,
                    "month": d[:7],
                    "amount_jpy": inc,
                    "to": row.get("入金先") or "",
                    "item": item.strip(),
                    "kind": kind,
                }
            )
    return out


def remainer_rows(
    rows: list[dict[str, Any]], *, legacy_match: str, current_match: str
) -> list[dict[str, Any]]:
    """固定3口座以外の余り行（SBI旧 or SMBC/Olive新）。"""
    fixed_hints = ("大垣", "名古屋", "東海労金")
    out = []
    for r in rows:
        if r["kind"] != "salary":
            continue
        to = r["to"]
        if any(h in to for h in fixed_hints):
            continue
        if legacy_match in to or current_match in to or "Olive" in to or "三井住友" in to:
            out.append(r)
        elif "住信SBI" in to or "住信 SBI" in to:
            out.append(r)
    return out


def estimate_remainer(
    rows: list[dict[str, Any]],
    *,
    as_of: date,
    prefer_last_month: bool,
    lookback_months: int,
    legacy_match: str,
    current_match: str,
) -> dict[str, Any]:
    rem = remainer_rows(rows, legacy_match=legacy_match, current_match=current_match)
    # 対象月: as_of の前月まで
    months: list[str] = []
    y, m = as_of.year, as_of.month
    for _ in range(lookback_months + 1):
        m -= 1
        if m <= 0:
            m = 12
            y -= 1
        months.append(f"{y:04d}-{m:02d}")
    by_month: dict[str, int] = {}
    for r in rem:
        mk = r["month"]
        if mk in months or mk == f"{as_of.year:04d}-{as_of.month:02d}":
            by_month[mk] = by_month.get(mk, 0) + r["amount_jpy"]

    last_m = months[0] if months else None
    last_amt = by_month.get(last_m) if last_m else None
    series = [by_month[m] for m in months if m in by_month]
    med = int(median(series)) if series else None
    estimate = last_amt if (prefer_last_month and last_amt) else med
    return {
        "estimate_jpy": estimate,
        "last_month": last_m,
        "last_month_jpy": last_amt,
        "median_jpy": med,
        "by_month": by_month,
        "source": "zaim_csv",
    }


def build_snapshot(
    *,
    as_of: date | None = None,
    month: str | None = None,
    csv_path: Path | None = None,
) -> dict[str, Any]:
    cfg = load_config()
    sal = cfg.get("salary") or {}
    bon = cfg.get("bonus") or {}
    today = as_of or date.today()
    if month:
        y, m = map(int, month.split("-"))
    else:
        y, m = today.year, today.month

    nominal = int(sal.get("nominal_day") or 20)
    pay = salary_pay_date(y, m, nominal)
    csv_p = csv_path or DEFAULT_CSV
    rows = load_salary_rows(csv_p)
    est = estimate_remainer(
        rows,
        as_of=date(y, m, min(today.day, 28)) if (y, m) == (today.year, today.month) else date(y, m, 28),
        prefer_last_month=bool((sal.get("estimate") or {}).get("prefer_last_month", True)),
        lookback_months=int((sal.get("estimate") or {}).get("lookback_months") or 6),
        legacy_match=str(sal.get("remainer_zaim_match_legacy") or ""),
        current_match=str(sal.get("remainer_zaim_match_current") or "三井住友"),
    )

    # 賞与: 直近の実績
    bonuses = [r for r in rows if r["kind"] == "bonus" and r["amount_jpy"] >= 10_000]
    last_bonus = max(bonuses, key=lambda r: r["date"]) if bonuses else None

    return {
        "as_of": today.isoformat(),
        "target_month": f"{y:04d}-{m:02d}",
        "salary": {
            "nominal_day": nominal,
            "pay_date": pay.isoformat(),
            "pay_date_weekday": pay.strftime("%A"),
            "shifted_from_nominal": pay.day != nominal,
            "remainer_account_id": sal.get("remainer_account_id"),
            "remainer_account_label": sal.get("remainer_account_label"),
            "estimate_remainer_jpy": est.get("estimate_jpy"),
            "estimate_detail": est,
            "fixed_splits": sal.get("fixed_splits") or [],
            "wait_for_credit_before_xfer": bool(
                (cfg.get("card_settlement") or {}).get("wait_for_salary_before_xfer", True)
            ),
        },
        "bonus": {
            "nominal_day": int(bon.get("nominal_day") or 1),
            "note": bon.get("note"),
            "last_actual": last_bonus,
        },
        "config_path": str(CONFIG_PATH),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="給与着金カレンダー")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--month", help="YYYY-MM")
    ap.add_argument("--csv", type=Path, default=None)
    args = ap.parse_args()
    snap = build_snapshot(month=args.month, csv_path=args.csv)
    if args.json:
        print(json.dumps(snap, ensure_ascii=False, indent=2))
        return 0
    sal = snap["salary"]
    print("📎 給与着金カレンダー")
    print(f"- 対象月: {snap['target_month']}")
    print(
        f"- 着金日: {sal['pay_date']}（名目{sal['nominal_day']}日"
        f"{'・前倒し' if sal['shifted_from_nominal'] else ''}）"
    )
    print(f"- 余り先: {sal['remainer_account_label']}")
    est = sal.get("estimate_remainer_jpy")
    print(f"- 余り見積: {est:,}円" if isinstance(est, int) else "- 余り見積: —")
    det = sal.get("estimate_detail") or {}
    if det.get("last_month_jpy"):
        print(
            f"  （先月 {det.get('last_month')}: {det['last_month_jpy']:,} / "
            f"中央値 {det.get('median_jpy')}）"
        )
    print(
        "- 資金移動: "
        + (
            "余り着金確認後に実行"
            if sal.get("wait_for_credit_before_xfer")
            else "制約なし"
        )
    )
    b = snap.get("bonus") or {}
    lb = b.get("last_actual")
    if lb:
        print(f"- 賞与直近実績: {lb['date']} {lb['amount_jpy']:,}円 → {lb['to'][:40]}")
    print(f"- note: {(b.get('note') or '')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
