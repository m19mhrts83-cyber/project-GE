#!/usr/bin/env python3
"""
Jarvis: 電力・太陽光キャッシュフロー収集

  買電: エネワンでんき（サイサン／ポータルワン）— Zaim 円＋任意でポータルワン kWh
  売電: 中部電力パワーグリッド（Zaim 0.7太陽光発電、kWh は FIT 単価で推定可）
  ローン: OTHER_LOAN_SOLAR_MONTHLY / Zaim オリコ

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  python scripts/jarvis_energy_cf_collect.py
  python scripts/jarvis_energy_cf_collect.py --fetch-portalone  # 要 PORTALONE_*
  python scripts/jarvis_energy_cf_collect.py --push
  python scripts/jarvis_energy_cf_collect.py --dry-run
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
CFG_PATH = REPO / "config" / "energy_cf.yaml"
OUT_PATH = REPO / ".jarvis_state" / "energy_cf.json"
STATE = REPO / ".jarvis_state"


def now_iso() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def load_cfg() -> dict[str, Any]:
    return yaml.safe_load(CFG_PATH.read_text(encoding="utf-8")) or {}


def _zen_to_int(s: str) -> int:
    t = s.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    return int(t)


def parse_usage_month(item: str, pay_date: date, regex: str) -> str:
    """『12月分』→ 支払年を補正した YYYY-MM。無ければ支払月。"""
    m = re.search(regex, item or "")
    if not m:
        return f"{pay_date.year:04d}-{pay_date.month:02d}"
    month = _zen_to_int(m.group(1))
    year = pay_date.year
    # 1月払いで12月分 → 前年
    if month > pay_date.month + 1:
        year -= 1
    if month < 1 or month > 12:
        return f"{pay_date.year:04d}-{pay_date.month:02d}"
    return f"{year:04d}-{month:02d}"


def zaim_paths(cfg: dict[str, Any]) -> list[Path]:
    base = Path(cfg.get("zaim", {}).get("base_dir") or "").expanduser()
    years_back = int(cfg.get("zaim", {}).get("years_back") or 3)
    y_now = datetime.now(JST).year
    out: list[Path] = []
    for y in range(y_now - years_back + 1, y_now + 1):
        p = base / f"{y}年度" / f"Zaim.{y}年度.csv"
        if p.is_file():
            out.append(p)
    return out


def read_zaim(path: Path) -> list[dict[str, str]]:
    for enc in ("utf-8-sig", "cp932", "utf-8"):
        try:
            text = path.read_text(encoding=enc)
            break
        except UnicodeDecodeError:
            text = ""
    else:
        return []
    return list(csv.DictReader(text.splitlines()))


def yen_field(row: dict[str, str], field: str) -> float:
    try:
        return float(str(row.get(field) or "0").replace(",", "") or 0)
    except ValueError:
        return 0.0


def empty_month() -> dict[str, Any]:
    return {
        "buy_yen": None,
        "buy_kwh": None,
        "buy_unit": None,
        "sell_yen": None,
        "sell_kwh": None,
        "sell_unit": None,
        "loan_yen": None,
        "net_cf": None,
        "sources": [],
    }


def finalize_month(m: dict[str, Any]) -> dict[str, Any]:
    buy_yen = m.get("buy_yen")
    buy_kwh = m.get("buy_kwh")
    sell_yen = m.get("sell_yen")
    sell_kwh = m.get("sell_kwh")
    loan_yen = m.get("loan_yen")
    if buy_yen is not None and buy_kwh and buy_kwh > 0:
        m["buy_unit"] = round(float(buy_yen) / float(buy_kwh), 2)
    if sell_yen is not None and sell_kwh and sell_kwh > 0:
        m["sell_unit"] = round(float(sell_yen) / float(sell_kwh), 2)
    parts = []
    if sell_yen is not None:
        parts.append(float(sell_yen))
    if buy_yen is not None:
        parts.append(-float(buy_yen))
    if loan_yen is not None:
        parts.append(-float(loan_yen))
    if parts:
        m["net_cf"] = round(sum(parts), 0)
    return m


def collect_from_zaim(cfg: dict[str, Any]) -> dict[str, dict[str, Any]]:
    months: dict[str, dict[str, Any]] = {}
    z = cfg.get("zaim") or {}
    buy_needles = list(z.get("buy_item_contains") or ["エネワン"])
    buy_legacy = list(z.get("buy_legacy_item_contains") or [])
    buy_legacy_cat = str(z.get("buy_legacy_category_contains") or "")
    buy_exclude_cats = list(z.get("buy_exclude_category_contains") or [])
    buy_re = str(z.get("buy_month_regex") or r"([0-9０-９]{1,2})\s*月分")
    sell_cfg = cfg.get("sell") or {}
    sell_cat = str(sell_cfg.get("zaim_category_contains") or "")
    sell_items = list(sell_cfg.get("zaim_item_contains") or [])
    fit = float(
        (cfg.get("fit") or {}).get("current_yen_per_kwh")
        or sell_cfg.get("fit_yen_per_kwh")
        or 0
    )
    loan_cfg = cfg.get("loan") or {}
    loan_cat = str(loan_cfg.get("zaim_category_contains") or "")
    loan_items = list(loan_cfg.get("zaim_item_contains") or [])
    monthly_env = (loan_cfg.get("monthly_env") or "OTHER_LOAN_SOLAR_MONTHLY").strip()
    default_loan = None
    try:
        raw = (os.environ.get(monthly_env) or "").strip()
        if raw:
            default_loan = float(raw)
    except ValueError:
        default_loan = None

    for path in zaim_paths(cfg):
        for row in read_zaim(path):
            d = (row.get("日付") or "").strip()
            if len(d) < 10:
                continue
            try:
                dt = datetime.strptime(d[:10], "%Y-%m-%d").date()
            except ValueError:
                continue
            cat = row.get("カテゴリ") or ""
            item = "".join(
                [
                    row.get("品目") or "",
                    row.get("メモ") or "",
                    row.get("お店") or "",
                ]
            )
            income = yen_field(row, "収入")
            expense = yen_field(row, "支出")
            method = (row.get("方法") or "").strip()

            # buy エネワン or 切替前の自宅中部電力（賃貸δ除外）
            # 同一月でエネワンがある場合は legacy を足さない（後段で整理）
            is_eneone = any(n in item for n in buy_needles) and expense > 0
            is_legacy = (
                expense > 0
                and buy_legacy
                and any(n in item for n in buy_legacy)
                and (not buy_legacy_cat or buy_legacy_cat in cat)
                and not any(ex in cat for ex in buy_exclude_cats)
            )
            if is_eneone or is_legacy:
                ym = parse_usage_month(item, dt, buy_re)
                m = months.setdefault(ym, empty_month())
                if is_eneone:
                    m["_buy_eneone"] = round((m.get("_buy_eneone") or 0) + expense, 0)
                if is_legacy:
                    m["_buy_legacy"] = round((m.get("_buy_legacy") or 0) + expense, 0)
                if "zaim_buy" not in m["sources"]:
                    m["sources"].append("zaim_buy")

            # sell FIT
            sell_hit = (sell_cat and sell_cat in cat) or any(n in item for n in sell_items)
            if sell_hit and (method == "income" or income > 0):
                ym = f"{dt.year:04d}-{dt.month:02d}"
                m = months.setdefault(ym, empty_month())
                m["sell_yen"] = round((m.get("sell_yen") or 0) + income, 0)
                if fit > 0 and m["sell_yen"]:
                    # 金額が単価で割り切れるときだけ推定 kWh
                    if abs(m["sell_yen"] / fit - round(m["sell_yen"] / fit)) < 0.01:
                        m["sell_kwh"] = round(m["sell_yen"] / fit, 1)
                        m["sell_kwh_estimated"] = True
                if "zaim_sell" not in m["sources"]:
                    m["sources"].append("zaim_sell")

            # loan orico
            if loan_cat in cat and any(n in item for n in loan_items) and expense > 0:
                ym = f"{dt.year:04d}-{dt.month:02d}"
                m = months.setdefault(ym, empty_month())
                m["loan_yen"] = round((m.get("loan_yen") or 0) + expense, 0)
                if "zaim_loan" not in m["sources"]:
                    m["sources"].append("zaim_loan")

    # ローン欠落月は env 月額で埋める（買電 or 売電がある月）
    if default_loan is not None:
        for ym, m in months.items():
            if m.get("loan_yen") is None and (
                m.get("buy_yen") is not None
                or m.get("_buy_eneone") is not None
                or m.get("_buy_legacy") is not None
                or m.get("sell_yen") is not None
            ):
                m["loan_yen"] = default_loan
                if "env_loan" not in m["sources"]:
                    m["sources"].append("env_loan")

    # 買電: エネワン優先。無い月だけ legacy（切替前中部電力）
    for ym, m in months.items():
        ene = m.pop("_buy_eneone", None)
        leg = m.pop("_buy_legacy", None)
        if ene is not None:
            m["buy_yen"] = ene
        elif leg is not None:
            m["buy_yen"] = leg

    for ym in months:
        months[ym] = finalize_month(months[ym])
    return months


PORTALONE_STATE = STATE / "energy_portalone.json"


def merge_portalone_kwh(months: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """`.jarvis_state/energy_portalone.json` があれば buy_kwh / buy_yen を上書きマージ。"""
    info: dict[str, Any] = {"merged_months": 0, "path": str(PORTALONE_STATE)}
    if not PORTALONE_STATE.is_file():
        info["status"] = "no_cache"
        return info
    try:
        data = json.loads(PORTALONE_STATE.read_text(encoding="utf-8"))
    except Exception as e:
        info["status"] = "read_error"
        info["error"] = str(e)
        return info
    portal_months = data.get("months") or {}
    n = 0
    for ym, pm in portal_months.items():
        if not isinstance(pm, dict):
            continue
        m = months.setdefault(ym, empty_month())
        if "sources" not in m or m["sources"] is None:
            m["sources"] = []
        if pm.get("buy_kwh") is not None:
            m["buy_kwh"] = float(pm["buy_kwh"])
            m["buy_kwh_source"] = "portalone"
            if "portalone_kwh" not in m["sources"]:
                m["sources"].append("portalone_kwh")
            n += 1
        if pm.get("buy_yen") is not None and m.get("buy_yen") is None:
            m["buy_yen"] = float(pm["buy_yen"])
            m["buy_yen_source"] = "portalone"
            if "portalone_yen" not in m["sources"]:
                m["sources"].append("portalone_yen")
        months[ym] = finalize_month(m)
    info["status"] = "merged" if n else "empty_cache"
    info["merged_months"] = n
    info["fetched_at"] = data.get("fetched_at")
    info["ok"] = data.get("ok")
    return info


def try_portalone_note(cfg: dict[str, Any], merge_info: dict[str, Any] | None = None) -> dict[str, Any]:
    """ポータルワン: 認証があれば fetch 可。キャッシュがあれば kWh マージ済み。"""
    retail = cfg.get("retail") or {}
    user_k = retail.get("env_user") or "PORTALONE_USER"
    pass_k = retail.get("env_password") or "PORTALONE_PASSWORD"
    has = bool(os.environ.get(user_k) and os.environ.get(pass_k))
    mi = merge_info or {}
    if not has:
        fetch = "skipped_no_credentials"
        note = (
            "kWh は PORTALONE_USER/PASSWORD 追記後に "
            "`jarvis_energy_portalone_fetch.py` → collect で埋める。"
            "当面 Zaim で円のみ（売電 kWh は FIT 推定）"
        )
    elif mi.get("merged_months"):
        fetch = "merged_from_cache"
        note = f"ポータルワンキャッシュから {mi['merged_months']}ヶ月の buy_kwh を反映"
    elif PORTALONE_STATE.is_file():
        fetch = "cache_present_no_kwh"
        note = "ポータルワンキャッシュありだが kWh なし（画面パース要調整の可能性）"
    else:
        fetch = "ready_run_fetch"
        note = "認証あり。`python scripts/jarvis_energy_portalone_fetch.py` を実行してから collect"
    return {
        "portalone_credentials": "present" if has else "missing",
        "portalone_fetch": fetch,
        "portalone_merge": mi,
        "note": note,
    }


def build_state(
    cfg: dict[str, Any],
    months: dict[str, dict[str, Any]],
    merge_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    portal = try_portalone_note(cfg, merge_info)
    fit = cfg.get("fit") or {}
    thr = cfg.get("thresholds") or {}
    # level
    level = "ok"
    details: list[str] = []
    today = datetime.now(JST).date()
    prev = date(today.year, today.month, 1)
    # previous calendar month
    if prev.month == 1:
        prev_ym = f"{prev.year - 1:04d}-12"
    else:
        prev_ym = f"{prev.year:04d}-{prev.month - 1:02d}"
    if thr.get("missing_prev_month_attention", True):
        pm = months.get(prev_ym) or {}
        if pm.get("buy_yen") is None and pm.get("sell_yen") is None:
            # 月初〜中旬は請求／Zaim未反映が普通。15日未満は info に留める
            if today.day < 15:
                details.append(
                    f"{prev_ym} の買電/売電は未反映（請求・Zaim待ち。月初は正常）"
                )
                if level == "ok":
                    level = "info"
            else:
                level = "attention"
                details.append(f"{prev_ym} の買電/売電なし（Zaim未反映 or 未収集）")

    # YoY kWh
    ratio = float(thr.get("buy_kwh_yoy_warn_ratio") or 1.25)
    for ym, m in months.items():
        kwh = m.get("buy_kwh")
        if kwh is None:
            continue
        y, mo = ym.split("-")
        prev_y = f"{int(y) - 1:04d}-{mo}"
        pk = (months.get(prev_y) or {}).get("buy_kwh")
        if pk and pk > 0 and float(kwh) / float(pk) >= ratio:
            level = "warn"
            details.append(f"{ym} 消費kWh が前年同月比 ≥{ratio}倍")

    step = (fit.get("stepdown_ym") or "").strip()
    attn_m = int(thr.get("fit_stepdown_attention_months") or 6)
    if step:
        try:
            sy, sm = map(int, step.split("-")[:2])
            step_d = date(sy, sm, 1)
            months_left = (step_d.year - today.year) * 12 + (step_d.month - today.month)
            if 0 <= months_left <= attn_m:
                if level == "ok":
                    level = "attention"
                details.append(f"FIT改定予定 {step}（残り約{months_left}ヶ月）")
        except ValueError:
            pass

    # summary from latest month with any data
    latest_ym = sorted(months.keys())[-1] if months else None
    latest = months.get(latest_ym or "", {}) if latest_ym else {}
    def fyen(v: Any) -> str:
        return f"¥{int(v):,}" if v is not None else "—"

    def funit(v: Any) -> str:
        return f"{v}円/kWh" if v is not None else "—"

    summary = (
        f"{latest_ym or '—'}: 買電{fyen(latest.get('buy_yen'))}"
        f" / 売電{fyen(latest.get('sell_yen'))}"
        f" / ローン{fyen(latest.get('loan_yen'))}"
        f" / ネット{fyen(latest.get('net_cf'))}"
        f" · 買電単価{funit(latest.get('buy_unit'))}"
        f" · 売電単価{funit(latest.get('sell_unit'))}"
    )

    return {
        "updated_at": now_iso(),
        "level": level,
        "summary": summary,
        "detail": " / ".join(details),
        "latest_ym": latest_ym,
        "fit": {
            "current_yen_per_kwh": fit.get("current_yen_per_kwh"),
            "start_ym": fit.get("start_ym") or "",
            "stepdown_ym": fit.get("stepdown_ym") or "",
            "note": fit.get("note") or "",
        },
        "portal": portal,
        "last_fetch_at": now_iso(),
        "source": "zaim+env+portalone_cache",
        "months": {k: months[k] for k in sorted(months)},
    }


def metrics_rows(cfg: dict[str, Any], state: dict[str, Any]) -> list[dict[str, Any]]:
    names = (cfg.get("metrics") or {}).get("names") or {}
    entity = (cfg.get("metrics") or {}).get("entity") or "home"
    rows: list[dict[str, Any]] = []
    mapping = [
        ("buy_yen", "JPY"),
        ("buy_kwh", "kWh"),
        ("buy_unit", "JPY/kWh"),
        ("sell_yen", "JPY"),
        ("sell_kwh", "kWh"),
        ("sell_unit", "JPY/kWh"),
        ("loan_yen", "JPY"),
        ("net_cf", "JPY"),
    ]
    for ym, m in (state.get("months") or {}).items():
        for key, unit in mapping:
            val = m.get(key)
            metric = names.get(key) or f"energy_{key}"
            if val is None:
                continue
            rows.append(
                {
                    "metric": metric,
                    "value": float(val),
                    "unit": unit,
                    "entity": entity,
                    "recorded_at": f"{ym}-01",
                    "payload": {
                        "sources": m.get("sources") or [],
                        "sell_kwh_estimated": bool(m.get("sell_kwh_estimated")),
                    },
                }
            )
    return rows


def push_supabase(cfg: dict[str, Any], state: dict[str, Any]) -> int:
    from supabase import create_client

    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_* 未設定")
    sb = create_client(url, key)
    rows = metrics_rows(cfg, state)
    n = 0
    for i in range(0, len(rows), 80):
        chunk = rows[i : i + 80]
        sb.table("metrics").upsert(
            chunk, on_conflict="metric,entity,recorded_at"
        ).execute()
        n += len(chunk)
    sb.table("sync_meta").upsert(
        {
            "key": "energy_cf_pushed_at",
            "value": now_iso(),
            "updated_at": now_iso(),
        }
    ).execute()
    return n


def refresh_situation_watch() -> None:
    subprocess.run(
        [sys.executable, str(REPO / "scripts" / "jarvis_situation_watch.py")],
        cwd=str(REPO),
        check=False,
    )


def run_portalone_fetch(*, headed: bool = False) -> int:
    cmd = [sys.executable, str(REPO / "scripts" / "jarvis_energy_portalone_fetch.py")]
    if headed:
        cmd.append("--headed")
    return subprocess.run(cmd, cwd=str(REPO), check=False).returncode


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--push", action="store_true", help="Supabase metrics upsert")
    ap.add_argument("--no-watch", action="store_true")
    ap.add_argument(
        "--fetch-portalone",
        action="store_true",
        help="Playwright でポータルワン取得してから Zaim とマージ（要 PORTALONE_*）",
    )
    ap.add_argument("--headed", action="store_true", help="--fetch-portalone 時にブラウザ表示")
    args = ap.parse_args(argv)

    if args.fetch_portalone:
        rc = run_portalone_fetch(headed=args.headed)
        if rc == 2:
            print("# portalone: credentials missing — Zaim のみ続行", file=sys.stderr)
        elif rc != 0:
            print(f"# portalone fetch rc={rc} — キャッシュがあればマージ継続", file=sys.stderr)

    cfg = load_cfg()
    months = collect_from_zaim(cfg)
    merge_info = merge_portalone_kwh(months)
    state = build_state(cfg, months, merge_info)

    if args.dry_run:
        print(
            json.dumps(
                {
                    "summary": state.get("summary"),
                    "months": len(months),
                    "level": state.get("level"),
                    "portal": state.get("portal"),
                    "fit": state.get("fit"),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        print(json.dumps({k: months[k] for k in sorted(months)[-3:]}, ensure_ascii=False, indent=2))
        return 0

    STATE.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"# wrote {OUT_PATH} months={len(months)} level={state.get('level')}", file=sys.stderr)
    print(state.get("summary") or "")

    if args.push:
        n = push_supabase(cfg, state)
        print(f"# metrics upserted {n}", file=sys.stderr)

    if not args.no_watch:
        refresh_situation_watch()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
