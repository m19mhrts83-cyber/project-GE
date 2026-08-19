#!/usr/bin/env python3
"""MQ会計評価 — 月次自動更新（流動年度の全明細再取込→再集計）

Zaim CSV 週次成功後に相乗り。毎月5日以降の当月初回のみ実行。

  ~/selenium_env/venv/bin/python scripts/jarvis_mq_monthly_refresh.py
  ~/selenium_env/venv/bin/python scripts/jarvis_mq_monthly_refresh.py --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_mq_monthly_refresh.py --force
  ~/selenium_env/venv/bin/python scripts/jarvis_mq_monthly_refresh.py --reopen 2025
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
STATE_PATH = REPO / ".jarvis_state" / "mq_monthly_refresh.json"
PY = Path.home() / "selenium_env" / "venv" / "bin" / "python"
JST = ZoneInfo("Asia/Tokyo")
MQ_FROM_DAY = 5


def jst_now() -> datetime:
    return datetime.now(JST)


def load_state() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        return {"sealed_years": [], "last_success_cycle_month": None}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"sealed_years": [], "last_success_cycle_month": None}


def save_state(data: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def decide_years(
    now: datetime,
    sealed: list[int],
    reopen: list[int],
    last_cycle: str | None,
    force: bool,
) -> dict[str, Any]:
    y, m, d = now.year, now.month, now.day
    cycle = f"{y:04d}-{m:02d}"
    sealed_set = set(sealed) - set(reopen)

    if m == 1:
        candidates = [y - 1, y]
        to_seal: list[int] = []
        reason = "1月: 前年＋当年"
    elif m == 2:
        candidates = [y - 1, y]
        to_seal = [y - 1]
        reason = "2月: 前年最終更新→確定＋当年"
    else:
        candidates = [y]
        to_seal = []
        reason = "通常月: 当年のみ"

    years: list[int] = []
    sealed_skipped: list[int] = []
    for yr in candidates:
        if yr in sealed_set:
            sealed_skipped.append(yr)
        else:
            years.append(yr)
    for yr in reopen:
        if yr not in years:
            years.append(yr)
    years = sorted(set(years))
    to_seal = [yr for yr in to_seal if yr in years]

    in_window = d >= MQ_FROM_DAY
    already = last_cycle == cycle
    should = force or (in_window and not already and len(years) > 0)
    if not force:
        if not in_window:
            reason += f"（{MQ_FROM_DAY}日未満→スキップ可）"
        elif already:
            reason += "（当月サイクル済み）"

    return {
        "yearsToRefresh": years,
        "yearsToSeal": to_seal,
        "sealedSkipped": sealed_skipped,
        "cycleMonth": cycle,
        "shouldRunMonthly": should,
        "reason": reason,
    }


def sb_client() -> Any:
    from supabase import create_client

    url = os.environ.get("JARVIS_SUPABASE_URL")
    key = os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY が必要です")
    return create_client(url, key)


def ingest_finance_years(years: list[int], *, dry_run: bool) -> list[dict]:
    """指定年度の Zaim CSV のみ再取込"""
    sys.path.insert(0, str(REPO / "scripts"))
    # 遅延 import（同じリポ）
    import jarvis_kurashift_history_ingest as hi  # type: ignore

    sb = None if dry_run else hi.sb_client()
    results = []
    for year in years:
        raw = hi.TAX_DIR / f"{year}年度" / f"Zaim.{year}年度.csv"
        if not raw.is_file():
            results.append({"year": year, "ok": False, "error": f"csv_missing:{raw}"})
            print(f"# finance skip {year}: CSVなし {raw}", flush=True)
            continue
        if dry_run:
            n = sum(1 for _ in raw.open(encoding="utf-8-sig")) - 1
            results.append({"year": year, "ok": True, "dry_run": True, "rows": n})
            print(f"# finance dry-run {year}: rows≈{n}", flush=True)
            continue
        out = hi.ingest_zaim_raw(sb, year, raw, dry_run=False, push_metrics=False)
        results.append({"year": year, "ok": True, **out})
        print(f"# finance raw {year}: inserted={out.get('inserted', out.get('rows'))}", flush=True)
    return results


def mq_refresh_year(year: int, *, dry_run: bool, force: bool) -> dict:
    cmd = [
        "npx",
        "--yes",
        "tsx",
        "scripts/mqYearRefresh.ts",
        "--year",
        str(year),
    ]
    if dry_run:
        cmd.append("--dry-run")
    if force:
        cmd.append("--force")
    env = os.environ.copy()
    proc = subprocess.run(
        cmd,
        cwd=str(REPO / "apps" / "trade-desk"),
        capture_output=True,
        text=True,
        env=env,
    )
    raw = (proc.stdout or "").strip()
    if proc.returncode != 0:
        return {
            "year": year,
            "ok": False,
            "rc": proc.returncode,
            "stderr": (proc.stderr or "")[-800:],
            "stdout": raw[-800:],
        }
    try:
        # 最後の JSON オブジェクトを拾う
        data = json.loads(raw)
    except Exception:
        data = {"raw": raw[-1200:]}
    data["year"] = year
    data["ok"] = True
    return data


def push_sync_meta(summary: dict[str, Any]) -> None:
    try:
        sb = sb_client()
        now = jst_now().isoformat(timespec="seconds")
        sb.table("sync_meta").upsert(
            {
                "key": "mq_monthly_refresh",
                "value": summary,
                "updated_at": now,
            },
            on_conflict="key",
        ).execute()
    except Exception as e:
        print(f"# sync_meta warn: {e}", flush=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="MQ月次自動更新")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="日付・当月済みゲートを無視")
    ap.add_argument(
        "--reopen",
        default="",
        help="確定解除して再処理する年度（カンマ区切り）",
    )
    ap.add_argument("--skip-finance", action="store_true", help="CSV→TXN を省略（MQ再集計のみ）")
    args = ap.parse_args(argv)

    env_file = REPO / ".env.jarvis_private"
    if env_file.is_file():
        # 簡易 source（既に shell で source 済み想定。未設定キーだけ拾う）
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.strip().strip("'").strip('"')
            if k and k not in os.environ:
                os.environ[k] = v

    state = load_state()
    reopen = [int(x.strip()) for x in args.reopen.split(",") if x.strip()]
    now = jst_now()
    decision = decide_years(
        now,
        list(state.get("sealed_years") or []),
        reopen,
        state.get("last_success_cycle_month"),
        args.force,
    )

    print(f"# decision: {decision['reason']}", flush=True)
    print(
        f"# years={decision['yearsToRefresh']} seal={decision['yearsToSeal']} "
        f"skip_sealed={decision['sealedSkipped']} cycle={decision['cycleMonth']} "
        f"run={decision['shouldRunMonthly']}",
        flush=True,
    )

    if not decision["shouldRunMonthly"]:
        print("📎 MQ月次更新: スキップ（ウィンドウ外または当月済み）", flush=True)
        return 0

    years: list[int] = decision["yearsToRefresh"]
    finance_results: list[dict] = []
    if not args.skip_finance:
        finance_results = ingest_finance_years(years, dry_run=args.dry_run)

    mq_results = []
    for year in years:
        r = mq_refresh_year(year, dry_run=args.dry_run, force=False)
        mq_results.append(r)
        print(
            f"# mq {year}: ok={r.get('ok')} upserted={r.get('upserted')} "
            f"stale={r.get('deletedStale')} heuristic={r.get('heuristicRealestateCount')} "
            f"unmapped={r.get('unmappedTotal')} manual={r.get('skippedManual')} "
            f"txn={r.get('txnCount')} reasons={r.get('reasonCounts')}",
            flush=True,
        )
        if not r.get("ok"):
            print(f"# mq error {year}: {r.get('stderr') or r}", flush=True)

    ok_all = all(r.get("ok") for r in mq_results) if mq_results else False
    summary = {
        "at": now.isoformat(timespec="seconds"),
        "cycle_month": decision["cycleMonth"],
        "years": years,
        "years_to_seal": decision["yearsToSeal"],
        "sealed_skipped": decision["sealedSkipped"],
        "reason": decision["reason"],
        "dry_run": args.dry_run,
        "ok": ok_all,
        "finance": finance_results,
        "mq": [
            {
                "year": r.get("year"),
                "ok": r.get("ok"),
                "upserted": r.get("upserted"),
                "deletedStale": r.get("deletedStale"),
                "skippedManual": r.get("skippedManual"),
                "unmappedTotal": r.get("unmappedTotal"),
                "heuristicRealestateCount": r.get("heuristicRealestateCount"),
                "txnCount": r.get("txnCount"),
                "reasonCounts": r.get("reasonCounts"),
            }
            for r in mq_results
        ],
        "unmapped_total": sum(int(r.get("unmappedTotal") or 0) for r in mq_results),
        "heuristic_total": sum(
            int(r.get("heuristicRealestateCount") or 0) for r in mq_results
        ),
        "manual_protected": sum(int(r.get("skippedManual") or 0) for r in mq_results),
    }

    if ok_all and not args.dry_run:
        sealed = set(int(x) for x in (state.get("sealed_years") or []))
        for yr in decision["yearsToSeal"]:
            sealed.add(int(yr))
        for yr in reopen:
            sealed.discard(int(yr))
        state["sealed_years"] = sorted(sealed)
        state["last_success_cycle_month"] = decision["cycleMonth"]
        state["last_success_at"] = summary["at"]
        state["last_result"] = summary
        save_state(state)
        push_sync_meta(summary)
    elif args.dry_run:
        print("# dry-run: state / sync_meta は更新しません", flush=True)
    else:
        state["last_error_at"] = summary["at"]
        state["last_error"] = summary
        save_state(state)
        push_sync_meta({**summary, "status": "error"})

    status = "自動更新済み" if ok_all else "要確認"
    print(
        f"📎 MQ月次更新: {status} years={years} "
        f"heuristic={summary['heuristic_total']} unmapped={summary['unmapped_total']} "
        f"manual保護={summary['manual_protected']}",
        flush=True,
    )
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
