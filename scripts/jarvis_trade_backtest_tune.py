#!/usr/bin/env python3
"""平均回帰の「理論は固定・バランスだけ変える」比較。

  大量グリッドは過学習するので、セオリーから外さない少数案だけ回す。
  価格は1回だけ取り、同じ足で全案を比較する。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_trade_backtest_tune.py --range max
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from jarvis_trade_backtest import STATE_DIR, load_bars, run_sim, tradable_jp
from jarvis_trade_common import load_watchlist
from jarvis_trade_strategy import INVERSE_SYMBOL, REGIME_SYMBOL, merge_params

OUT_JSON = STATE_DIR / "trade_backtest_tune.json"
HIGH_PRICE = {"8035.T", "6857.T", "6920.T"}  # 10万枠では1株が枠超えやすい
ETF_ONLY = {"1545.T", "1546.T"}


def variants() -> list[dict[str, Any]]:
    return [
        {
            "id": "A_old_force_lot",
            "note": "前回1年と同じ（高値株1株強制買い）",
            "force_lot": True,
            "skip_inverse": False,
            "params": {},
        },
        {
            "id": "B_sized",
            "note": "枠に1株入らない銘柄は見送り（サイズ修正）",
            "force_lot": False,
            "skip_inverse": False,
            "params": {},
        },
        {
            "id": "C_drop_10_18",
            "note": "沈み帯を10–18%に狭める",
            "force_lot": False,
            "skip_inverse": False,
            "params": {"drop_min_pct": 0.10, "drop_max_pct": 0.18},
        },
        {
            "id": "D_rebound3",
            "note": "反発サインを3つ要求",
            "force_lot": False,
            "skip_inverse": False,
            "params": {"rebound_min_signs": 3},
        },
        {
            "id": "E_hold40",
            "note": "保有上限20日→40日（回帰待ちを長く）",
            "force_lot": False,
            "skip_inverse": False,
            "params": {"max_hold_days": 40},
        },
        {
            "id": "F_no_inverse",
            "note": "リスクオフでもインバースを買わない",
            "force_lot": False,
            "skip_inverse": True,
            "params": {"hedge_inverse": False},
        },
        {
            "id": "G_etf_only",
            "note": "1545/1546だけ（1株が枠に入る）",
            "force_lot": False,
            "skip_inverse": True,
            "allow": ETF_ONLY,
            "params": {},
        },
        {
            "id": "H_no_tel_class",
            "note": "TEL/アドバンテスト/レーザーテック除外",
            "force_lot": False,
            "skip_inverse": False,
            "deny": HIGH_PRICE,
            "params": {},
        },
        {
            "id": "I_combo",
            "note": "サイズ+沈み10-18+保有40+インバース無し",
            "force_lot": False,
            "skip_inverse": True,
            "params": {"drop_min_pct": 0.10, "drop_max_pct": 0.18, "max_hold_days": 40},
        },
    ]


def _dd(curve: list[tuple[str, float]]) -> float:
    peak = None
    max_dd = 0.0
    for _, eq in curve:
        if peak is None or eq > peak:
            peak = eq
        if peak:
            max_dd = max(max_dd, (peak - eq) / peak)
    return round(max_dd * 100, 2)


def split_window(res: dict[str, Any], mid: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """同一ランのエクイティを前半/後半に分けて評価（指標のウォームアップを壊さない）。"""
    curve = list(res.get("equity_curve") or [])
    is_c = [(d, e) for d, e in curve if d <= mid]
    oos_c = [(d, e) for d, e in curve if d > mid]
    trades = [t for t in res.get("trades") or [] if t.get("status") == "filled" and t.get("side") == "sell"]

    def pack(c: list[tuple[str, float]], sells: list[dict[str, Any]], start_eq: float) -> dict[str, Any]:
        if not c:
            return {
                "from": None,
                "to": None,
                "return_pct": None,
                "max_drawdown_pct": None,
                "win_rate_pct": None,
                "round_trips": 0,
                "fills": 0,
                "final_equity": None,
                "quality_bar": False,
            }
        end_eq = c[-1][1]
        ret = (end_eq / start_eq - 1) * 100 if start_eq else 0.0
        pnls = [float(t.get("pnl") or 0) for t in sells]
        wins = [x for x in pnls if x > 0]
        return {
            "from": c[0][0],
            "to": c[-1][0],
            "return_pct": round(ret, 2),
            "max_drawdown_pct": _dd(c),
            "win_rate_pct": round(100 * len(wins) / len(pnls), 1) if pnls else None,
            "round_trips": len(pnls),
            "fills": len(sells),
            "final_equity": round(end_eq, 0),
            "quality_bar": _dd(c) < 20 and ret > 0,
        }

    is_sells = [t for t in trades if str(t.get("fill_day") or "") <= mid]
    oos_sells = [t for t in trades if str(t.get("fill_day") or "") > mid]
    is_start = is_c[0][1] if is_c else float(res["capital"])
    oos_start = oos_c[0][1] if oos_c else (is_c[-1][1] if is_c else float(res["capital"]))
    return pack(is_c, is_sells, is_start), pack(oos_c, oos_sells, oos_start)


def summarize_run(label: str, note: str, res: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": label,
        "note": note,
        "from": res["from"],
        "to": res["to"],
        "return_pct": res["return_pct"],
        "max_drawdown_pct": res["max_drawdown_pct"],
        "win_rate_pct": res["win_rate_pct"],
        "round_trips": res["round_trips"],
        "fills": res["fills"],
        "avg_win": res["avg_win"],
        "avg_loss": res["avg_loss"],
        "skipped_lot": res["skipped_lot"],
        "final_equity": res["final_equity"],
        "quality_bar": res["max_drawdown_pct"] < 20 and res["return_pct"] > 0,
    }


def run_variant(
    bars: dict[str, list],
    equities: list[dict[str, Any]],
    v: dict[str, Any],
    capital: float,
) -> dict[str, Any]:
    allow = set(v["allow"]) if v.get("allow") else None
    names = equities
    if v.get("deny"):
        names = [it for it in names if it["symbol"] not in v["deny"]]
    return run_sim(
        bars,
        names,
        merge_params(v.get("params")),
        capital,
        force_lot=bool(v.get("force_lot")),
        skip_inverse=bool(v.get("skip_inverse")),
        allow_symbols=allow,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Trade Desk バックテスト比較（少数案）")
    ap.add_argument("--range", default="max", help="Yahoo range（max / 10y / 5y）")
    ap.add_argument("--capital", type=float, default=100000)
    args = ap.parse_args()

    instruments = load_watchlist()
    equities = [it for it in instruments if tradable_jp(it)]
    symbols = [REGIME_SYMBOL, INVERSE_SYMBOL, *[it["symbol"] for it in equities]]
    print(f"# tune range={args.range} capital={args.capital:.0f} names={len(equities)}", flush=True)
    bars = load_bars(args.range, symbols)
    nikkei = bars.get(REGIME_SYMBOL) or []
    if len(nikkei) < 70:
        print("# 日経ETFの日足が足りません", file=sys.stderr)
        return 2

    cal = [str(r["trade_date"])[:10] for r in nikkei]
    first, last = cal[0], cal[-1]
    mid = cal[int(len(cal) * 0.70)]
    print(f"# data {first} → {last}  mid(70%)={mid}", flush=True)

    rows_all: list[dict[str, Any]] = []
    rows_is: list[dict[str, Any]] = []
    rows_oos: list[dict[str, Any]] = []

    for v in variants():
        print(f"# run {v['id']} …", flush=True)
        try:
            full = run_variant(bars, equities, v, args.capital)
            ins, oos = split_window(full, mid)
        except Exception as e:
            print(f"# FAIL {v['id']}: {e}", file=sys.stderr)
            continue
        rows_all.append(summarize_run(v["id"], v["note"], full))
        rows_is.append({"id": v["id"], "note": v["note"], **ins})
        rows_oos.append({"id": v["id"], "note": v["note"], **oos})
        print(
            f"  full {full['return_pct']:+.1f}% DD{full['max_drawdown_pct']:.1f}% "
            f"WR{full['win_rate_pct']}%  oos {oos.get('return_pct')}% DD{oos.get('max_drawdown_pct')}%",
            flush=True,
        )

    payload = {
        "range": args.range,
        "capital": args.capital,
        "data_from": first,
        "data_to": last,
        "is_to": mid,
        "note": (
            "理論（上昇平均への一時沈み・反発確認・ナンピン禁止）は固定。"
            "バランスとサイズだけ変えた少数案。後半30%は未使用データ（OOS）。"
            "OOSでプラスかつDD<20%ならペーパー候補。"
        ),
        "full": rows_all,
        "in_sample": rows_is,
        "out_of_sample": rows_oos,
    }
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print("📎 Trade Desk チューニング比較")
    print(f"- データ: {first} → {last}（{args.range}） / 分割 {mid}")
    print("- 全期間 / 前半70% / 後半30%(OOS)")
    for r in rows_all:
        o = next((x for x in rows_oos if x["id"] == r["id"]), {})
        bar = "✅" if o.get("quality_bar") else "—"
        print(
            f"  {r['id']}: 全{r['return_pct']:+.1f}% DD{r['max_drawdown_pct']:.1f}% WR{r['win_rate_pct']}% "
            f"| OOS {o.get('return_pct')}% DD{o.get('max_drawdown_pct')}% {bar}  {r['note']}"
        )
    print(f"- 保存: {OUT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
