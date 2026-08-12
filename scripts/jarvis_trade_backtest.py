#!/usr/bin/env python3
"""平均回帰リズムの過去シミュレーション（お金は動かさない・DBにも書かない）。

  約定は「翌営業日の始値」（当日終値シグナルの先読みを避ける）。
  実弾・ペーパー口座には触れない。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_trade_backtest.py
  ~/selenium_env/venv/bin/python scripts/jarvis_trade_backtest.py --range 10y --capital 100000
  ~/selenium_env/venv/bin/python scripts/jarvis_trade_backtest_tune.py --range max
"""
from __future__ import annotations

import argparse
import bisect
import json
import sys
from datetime import date
from typing import Any

from jarvis_trade_common import fetch_yahoo_daily, load_watchlist, sleep_polite
from jarvis_trade_strategy import (
    INVERSE_SYMBOL,
    REGIME_SYMBOL,
    decide_rhythm_exit,
    decide_scale_in,
    merge_params,
    pos_payload,
    regime_from_rows,
    score_probe,
)

from pathlib import Path

STATE_DIR = Path.home() / "git-repos" / ".jarvis_state"
OUT_JSON = STATE_DIR / "trade_backtest_last.json"
HIST_TAIL = 90  # SMA60 + rising_mean 20 + 余裕


def load_bars(range_: str, symbols: list[str]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for i, sym in enumerate(symbols):
        try:
            rows = fetch_yahoo_daily(sym, range_=range_)
            out[sym] = rows
            print(f"# {sym} bars={len(rows)}", flush=True)
        except Exception as e:
            print(f"# FAIL {sym}: {e}", file=sys.stderr)
            out[sym] = []
        if i + 1 < len(symbols):
            sleep_polite()
    return out


def history_until(rows: list[dict[str, Any]], day: str) -> list[dict[str, Any]]:
    return [r for r in rows if str(r["trade_date"])[:10] <= day]


def _dates_of(rows: list[dict[str, Any]]) -> list[str]:
    return [str(r["trade_date"])[:10] for r in rows]


def history_until_idx(rows: list[dict[str, Any]], dates: list[str], day: str) -> list[dict[str, Any]]:
    i = bisect.bisect_right(dates, day)
    if i <= 0:
        return []
    start = max(0, i - HIST_TAIL)
    return rows[start:i]


def next_open(rows: list[dict[str, Any]], dates: list[str], day: str) -> tuple[str, float] | None:
    i = bisect.bisect_right(dates, day)
    if i >= len(rows):
        return None
    r = rows[i]
    px = r.get("open") if r.get("open") is not None else r.get("close")
    if px is None:
        return None
    return str(r["trade_date"])[:10], float(px)


def mark_equity(
    positions: list[dict[str, Any]],
    bars: dict[str, list],
    date_ix: dict[str, list[str]],
    day: str,
    cash: float,
) -> float:
    mkt = 0.0
    for pos in positions:
        hist = history_until_idx(bars.get(pos["symbol"], []), date_ix.get(pos["symbol"], []), day)
        if not hist:
            mkt += float(pos["avg_price"]) * int(pos["qty"])
            continue
        mkt += float(hist[-1]["close"]) * int(pos["qty"])
    return cash + mkt


def tradable_jp(it: dict[str, Any]) -> bool:
    if it.get("enabled", True) is False:
        return False
    if str(it.get("currency") or "JPY").upper() != "JPY":
        return False
    if it.get("asset_class") in ("inverse_etf", "index"):
        return False
    if it.get("theme") == "index":
        return False
    if it["symbol"] in (REGIME_SYMBOL, INVERSE_SYMBOL):
        return False
    return it.get("asset_class") in ("equity", "etf")


def run_sim(
    bars: dict[str, list[dict[str, Any]]],
    equities: list[dict[str, Any]],
    p: dict[str, Any],
    capital: float,
    *,
    force_lot: bool = False,
    skip_inverse: bool = False,
    allow_symbols: set[str] | None = None,
) -> dict[str, Any]:
    """1セットのパラメータで全期間を回す。DB・実弾は触らない。"""
    p = merge_params(p)
    if allow_symbols:
        equities = [it for it in equities if it["symbol"] in allow_symbols]
    date_ix = {sym: _dates_of(rows) for sym, rows in bars.items()}
    calendar = sorted(set(date_ix.get(REGIME_SYMBOL) or []))
    if len(calendar) < 80:
        raise RuntimeError(f"日経ETFの日足が足りません（{len(calendar)}本）")
    start_i = 60
    cash = float(capital)
    positions: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    equity_curve: list[tuple[str, float]] = []
    peak = float(capital)
    max_dd = 0.0
    pending: list[dict[str, Any]] = []
    skipped_lot = 0

    fracs = list(p["scale_fracs"])
    per = float(p["per_name_pct"])
    max_pos = int(p["max_positions"])

    def sized_qty(budget: float, px: float) -> int:
        nonlocal skipped_lot
        if px <= 0:
            return 0
        qty = int(budget // px)
        if qty < 1:
            if force_lot:
                skipped_lot += 0
                return 1
            skipped_lot += 1
            return 0
        return qty

    def fill_pending(day: str) -> None:
        nonlocal cash
        still: list[dict[str, Any]] = []
        for od in pending:
            fill = next_open(bars.get(od["symbol"], []), date_ix.get(od["symbol"], []), od["signal_day"])
            if not fill:
                still.append(od)
                continue
            fill_day, px = fill
            if fill_day > day:
                still.append(od)
                continue
            side = od["side"]
            qty = int(od["qty"])
            if side in ("buy", "inverse_buy"):
                cost = qty * px
                if cost > cash:
                    qty = int(cash // px)
                    if qty < 1:
                        trades.append({**od, "status": "skipped_cash", "fill_day": fill_day})
                        continue
                    cost = qty * px
                cash -= cost
                if od.get("add_to"):
                    pos = next(x for x in positions if x["id"] == od["add_to"])
                    old_q = int(pos["qty"])
                    avg = float(pos["avg_price"])
                    pos["qty"] = old_q + qty
                    pos["avg_price"] = (avg * old_q + px * qty) / pos["qty"]
                    pl = pos_payload(pos)
                    pl["scale_level"] = od["scale_level"]
                    pos["payload"] = pl
                    pos.pop("_pending_add", None)
                else:
                    positions.append(
                        {
                            "id": f"{od['symbol']}-{fill_day}-{len(positions)}",
                            "symbol": od["symbol"],
                            "qty": qty,
                            "avg_price": px,
                            "opened_at": fill_day,
                            "status": "open",
                            "realized_pnl": 0.0,
                            "payload": {
                                "style": "mean_reversion_scale",
                                "scale_level": od.get("scale_level") or 1,
                                "swing_low": px,
                            },
                        }
                    )
                trades.append({**od, "status": "filled", "fill_day": fill_day, "fill": px, "qty": qty})
            else:
                pos = next((x for x in positions if x["id"] == od["pos_id"]), None)
                if not pos or int(pos["qty"]) <= 0:
                    continue
                sell_qty = min(qty, int(pos["qty"]))
                pnl = (px - float(pos["avg_price"])) * sell_qty
                cash += sell_qty * px
                pos["qty"] = int(pos["qty"]) - sell_qty
                pos["realized_pnl"] = float(pos.get("realized_pnl") or 0) + pnl
                pos.pop("_pending_exit", None)
                if pos["qty"] <= 0 or od.get("kind") == "full":
                    pos["status"] = "closed"
                    pos["qty"] = 0
                else:
                    pl = pos_payload(pos)
                    pl["partial_done"] = True
                    pos["payload"] = pl
                trades.append(
                    {
                        **od,
                        "status": "filled",
                        "fill_day": fill_day,
                        "fill": px,
                        "qty": sell_qty,
                        "pnl": pnl,
                    }
                )
        pending[:] = still
        positions[:] = [x for x in positions if x.get("status") != "closed"]

    for day in calendar[start_i:]:
        fill_pending(day)
        as_of = date.fromisoformat(day)
        regime_rows = history_until_idx(bars[REGIME_SYMBOL], date_ix[REGIME_SYMBOL], day)
        regime = regime_from_rows(regime_rows, p)

        for pos in list(positions):
            if pos.get("_pending_exit") or pos.get("_pending_add"):
                continue
            hist = history_until_idx(bars.get(pos["symbol"], []), date_ix.get(pos["symbol"], []), day)
            if not hist:
                continue
            px = float(hist[-1]["close"])
            decided = decide_rhythm_exit(pos, px, hist, as_of, p)
            if decided:
                reason, sell_qty, kind = decided
                pending.append(
                    {
                        "side": "sell",
                        "symbol": pos["symbol"],
                        "qty": sell_qty,
                        "signal_day": day,
                        "reason": reason,
                        "pos_id": pos["id"],
                        "kind": kind,
                    }
                )
                pos["_pending_exit"] = True
                continue
            add = decide_scale_in(pos, px, hist, as_of, p)
            if add:
                next_level, tag, signs = add
                budget = capital * per * float(fracs[next_level - 1])
                qty = sized_qty(budget, px)
                if qty < 1:
                    continue
                pending.append(
                    {
                        "side": "buy",
                        "symbol": pos["symbol"],
                        "qty": qty,
                        "signal_day": day,
                        "reason": f"{tag}(Lv{next_level}) {'・'.join(signs)}",
                        "add_to": pos["id"],
                        "scale_level": next_level,
                    }
                )
                pos["_pending_add"] = True

        held = {x["symbol"] for x in positions}
        open_count = len(positions)
        if regime == "risk_on" and open_count < max_pos:
            cands: list[tuple[float, dict, str]] = []
            for it in equities:
                if it["symbol"] in held:
                    continue
                hist = history_until_idx(bars.get(it["symbol"], []), date_ix.get(it["symbol"], []), day)
                scored = score_probe(hist, p)
                if not scored:
                    continue
                score, reason = scored
                cands.append((score, it, reason))
            cands.sort(key=lambda x: x[0], reverse=True)
            slots = max_pos - open_count
            probe_budget = capital * per * float(fracs[0])
            for score, it, reason in cands[:slots]:
                hist = history_until_idx(bars[it["symbol"]], date_ix[it["symbol"]], day)
                px = float(hist[-1]["close"])
                qty = sized_qty(probe_budget, px)
                if qty < 1:
                    continue
                pending.append(
                    {
                        "side": "buy",
                        "symbol": it["symbol"],
                        "qty": qty,
                        "signal_day": day,
                        "reason": reason,
                        "scale_level": 1,
                    }
                )
                held.add(it["symbol"])
                open_count += 1
        elif (
            not skip_inverse
            and p.get("hedge_inverse", False)
            and regime == "risk_off"
            and INVERSE_SYMBOL not in held
            and open_count < max_pos
        ):
            hist = history_until_idx(bars.get(INVERSE_SYMBOL, []), date_ix.get(INVERSE_SYMBOL, []), day)
            if hist:
                px = float(hist[-1]["close"])
                qty = sized_qty(capital * per * fracs[0], px)
                if qty >= 1:
                    pending.append(
                        {
                            "side": "inverse_buy",
                            "symbol": INVERSE_SYMBOL,
                            "qty": qty,
                            "signal_day": day,
                            "reason": "risk_off hedge probe",
                            "scale_level": 1,
                        }
                    )

        eq = mark_equity(positions, bars, date_ix, day, cash)
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak if peak else 0.0
        if dd > max_dd:
            max_dd = dd
        equity_curve.append((day, eq))

    last_day = calendar[-1]
    fill_pending(last_day)
    final_eq = mark_equity(positions, bars, date_ix, last_day, cash)
    closed = [t for t in trades if t.get("status") == "filled" and t.get("side") in ("sell",)]
    pnls = [float(t.get("pnl") or 0) for t in closed]
    wins = [x for x in pnls if x > 0]
    ret = (final_eq - capital) / capital if capital else 0.0
    return {
        "from": calendar[start_i],
        "to": last_day,
        "calendar_days": len(calendar) - start_i,
        "capital": capital,
        "final_equity": round(final_eq, 0),
        "return_pct": round(ret * 100, 2),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "fills": len([t for t in trades if t.get("status") == "filled"]),
        "round_trips": len(pnls),
        "win_rate_pct": round(100 * len(wins) / len(pnls), 1) if pnls else None,
        "avg_win": round(sum(wins) / len(wins), 0) if wins else 0,
        "avg_loss": round(sum(x for x in pnls if x <= 0) / max(1, len(pnls) - len(wins)), 0) if pnls else 0,
        "skipped_lot": skipped_lot,
        "open_positions": [
            {"symbol": x["symbol"], "qty": x["qty"], "avg": x["avg_price"]} for x in positions
        ],
        "trades": trades,
        "equity_curve": equity_curve,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Trade Desk 過去シミュレーション")
    ap.add_argument("--range", default="1y", help="Yahoo range (1y/2y/5y/10y/max)")
    ap.add_argument("--capital", type=float, default=100000)
    ap.add_argument("--params-json", default="", help="DEFAULT_PARAMS を上書きする JSON")
    ap.add_argument("--force-lot", action="store_true", help="予算不足でも1株買う（旧挙動・非推奨）")
    ap.add_argument("--skip-inverse", action="store_true")
    ap.add_argument("--no-save", action="store_true")
    args = ap.parse_args()

    extra = json.loads(args.params_json) if args.params_json else {}
    p = merge_params(extra)
    instruments = load_watchlist()
    equities = [it for it in instruments if tradable_jp(it)]
    symbols = [REGIME_SYMBOL, INVERSE_SYMBOL, *[it["symbol"] for it in equities]]
    print(
        f"# backtest range={args.range} capital={args.capital:.0f} names={len(equities)} force_lot={args.force_lot}",
        flush=True,
    )
    bars = load_bars(args.range, symbols)
    if len(bars.get(REGIME_SYMBOL) or []) < 70:
        print("# 日経ETFの日足が足りません", file=sys.stderr)
        return 2

    result = run_sim(
        bars,
        equities,
        p,
        args.capital,
        force_lot=args.force_lot,
        skip_inverse=args.skip_inverse,
    )
    summary = {
        "range": args.range,
        **{k: v for k, v in result.items() if k not in ("trades", "equity_curve")},
        "fill_model": "next_open",
        "force_lot": args.force_lot,
        "note": "過去検証。先読み回避のため翌営業日始値。1株が枠を超える銘柄は見送り（--force-lot で旧挙動）。",
    }
    if not args.no_save:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        OUT_JSON.write_text(
            json.dumps({"summary": summary, "trades": result["trades"][-80:]}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    print("📎 Trade Desk バックテスト")
    print(f"- 期間: {summary['from']} → {summary['to']}（{args.range}）")
    print(f"- 仮想元手: {args.capital:,.0f}円 → 期末 {summary['final_equity']:,.0f}円（{summary['return_pct']:+.1f}%）")
    print(f"- 最大DD: {summary['max_drawdown_pct']:.1f}%")
    print(
        f"- 約定: {summary['fills']}件 / 決済ラウンド {summary['round_trips']} / 勝率 {summary['win_rate_pct']}%"
    )
    print(f"- 枠不足スキップ: {summary['skipped_lot']}回")
    print("- 約定モデル: 翌営業日始値（当日終値で判断）")
    if not args.no_save:
        print(f"- 保存: {OUT_JSON}")
    print("- これはシミュレーション。実弾はトランシェ1までユーザー判断後")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
