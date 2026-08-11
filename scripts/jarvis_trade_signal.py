#!/usr/bin/env python3
"""戦略: 平均回帰リズム（沈み検知 → 少量 → 確認買い増し → 確信買い増し → 崩れは一部撤退）。

  ナンピン（下落の追撃買い）はしない。買い増しは反発確認のときだけ。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_trade_signal.py
  ~/selenium_env/venv/bin/python scripts/jarvis_trade_signal.py --dry-run
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta
from typing import Any

from jarvis_trade_common import JST, sb_client, sma, today_jst
from jarvis_trade_strategy import (
    INVERSE_SYMBOL,
    REGIME_SYMBOL,
    decide_rhythm_exit,
    decide_scale_in,
    merge_params,
    pos_payload,
    score_probe,
    swing_low_since,
)

MODE = "paper"


def load_params(sb) -> dict[str, Any]:
    res = sb.table("trade_params").select("value").eq("id", "strategy_v1").limit(1).execute()
    rows = res.data or []
    if not rows:
        raise SystemExit("trade_params.strategy_v1 がありません")
    return merge_params(dict(rows[0]["value"]))


def load_closes(sb, symbol: str, limit: int = 120) -> list[dict[str, Any]]:
    res = (
        sb.table("trade_prices")
        .select("trade_date,open,high,low,close,volume")
        .eq("symbol", symbol)
        .order("trade_date", desc=True)
        .limit(limit)
        .execute()
    )
    return list(reversed(res.data or []))


def regime_of(sb, p: dict[str, Any]) -> tuple[str, str]:
    rows = load_closes(sb, REGIME_SYMBOL)
    c = closes_of(rows)
    fast = sma(c, int(p["sma_fast"]))
    slow = sma(c, int(p["sma_slow"]))
    if fast is None or slow is None:
        return "unknown", "日足不足で市況判定不可"
    if fast > slow:
        return "risk_on", f"日経ETF SMA{p['sma_fast']}={fast:.1f} > SMA{p['sma_slow']}={slow:.1f} → 買い相場"
    return "risk_off", f"日経ETF SMA{p['sma_fast']}={fast:.1f} <= SMA{p['sma_slow']}={slow:.1f} → 守り相場"


def open_positions(sb) -> list[dict[str, Any]]:
    res = (
        sb.table("trade_positions")
        .select("*")
        .eq("mode", MODE)
        .eq("status", "open")
        .execute()
    )
    return list(res.data or [])


def last_close(sb, symbol: str) -> float | None:
    rows = load_closes(sb, symbol, limit=2)
    if not rows:
        return None
    return float(rows[-1]["close"])


def mark_to_market(sb, positions: list[dict[str, Any]], cash: float) -> tuple[float, float]:
    unreal = 0.0
    mkt = 0.0
    for pos in positions:
        px = last_close(sb, pos["symbol"]) or float(pos["avg_price"])
        avg = float(pos["avg_price"])
        qty = int(pos["qty"])
        unreal += (px - avg) * qty
        mkt += px * qty
    return cash + mkt, unreal


def insert_fill(
    sb,
    as_of: date,
    symbol: str,
    side: str,
    qty: int,
    px: float,
    reason: str,
    score: float | None,
    regime: str | None,
    payload: dict[str, Any],
    dry: bool,
) -> None:
    if dry:
        return
    sig = {
        "signal_date": as_of.isoformat(),
        "symbol": symbol,
        "side": side,
        "score": score,
        "reason": reason,
        "regime": regime,
        "status": "paper",
        "payload": payload,
    }
    sres = sb.table("trade_signals").insert(sig).execute()
    sid = (sres.data or [{}])[0].get("id")
    sb.table("trade_orders").insert(
        {
            "signal_id": sid,
            "mode": MODE,
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "filled_price": px,
            "filled_at": datetime.now(JST).isoformat(),
            "status": "simulated",
            "broker": "paper",
            "reason": reason,
        }
    ).execute()


def apply_rhythm(
    sb,
    p: dict[str, Any],
    positions: list[dict[str, Any]],
    as_of: date,
    dry: bool,
) -> tuple[float, list[str]]:
    """リズム崩れは一部、再崩れ・平均到達・硬損切は残り。"""
    realized = 0.0
    notes: list[str] = []

    for pos in positions:
        rows = load_closes(sb, pos["symbol"])
        px = last_close(sb, pos["symbol"])
        if px is None:
            continue
        decided = decide_rhythm_exit(pos, px, rows, as_of, p)
        if not decided:
            continue
        reason, sell_qty, kind = decided
        avg = float(pos["avg_price"])
        qty = int(pos["qty"])
        pnl_pct = (px - avg) / avg
        pnl = (px - avg) * sell_qty
        realized += pnl
        notes.append(f"{pos['symbol']} {reason} qty={sell_qty} PnL={pnl:.0f}円")
        side = "inverse_sell" if pos["symbol"] == INVERSE_SYMBOL else "sell"
        insert_fill(
            sb,
            as_of,
            pos["symbol"],
            side,
            sell_qty,
            px,
            reason,
            None,
            None,
            {"exit": True, "kind": kind, "pnl": pnl, "pnl_pct": pnl_pct},
            dry,
        )
        if dry:
            continue
        pl = pos_payload(pos)
        prev_pnl = float(pos.get("realized_pnl") or 0)
        if kind.startswith("partial") and sell_qty < qty:
            pl["partial_done"] = True
            pl["last_partial_at"] = as_of.isoformat()
            sb.table("trade_positions").update(
                {"qty": qty - sell_qty, "payload": pl, "realized_pnl": prev_pnl + pnl}
            ).eq("id", pos["id"]).execute()
        else:
            sb.table("trade_positions").update(
                {
                    "status": "closed",
                    "closed_at": as_of.isoformat(),
                    "realized_pnl": prev_pnl + pnl,
                    "qty": 0,
                }
            ).eq("id", pos["id"]).execute()
    return realized, notes


def maybe_scale_in(
    sb,
    p: dict[str, Any],
    positions: list[dict[str, Any]],
    cash: float,
    capital: float,
    as_of: date,
    regime: str,
    dry: bool,
) -> tuple[float, list[str]]:
    """保有銘柄の確認・確信買い増し。下落中の追加はしない。"""
    notes: list[str] = []
    spent = 0.0
    fracs = list(p.get("scale_fracs") or [0.25, 0.35, 0.40])
    per = float(p["per_name_pct"])
    name_cap = capital * per

    for pos in positions:
        rows = load_closes(sb, pos["symbol"])
        px = last_close(sb, pos["symbol"])
        if px is None:
            continue
        decided = decide_scale_in(pos, px, rows, as_of, p)
        if not decided:
            continue
        next_level, tag, signs = decided
        avg = float(pos["avg_price"])
        gain = (px - avg) / avg
        pl = pos_payload(pos)

        budget = name_cap * float(fracs[next_level - 1])
        if cash - spent < budget * 0.5:
            continue
        qty = max(1, int(budget // px))
        cost = qty * px
        if cost > cash - spent:
            qty = int((cash - spent) // px)
            if qty < 1:
                continue
            cost = qty * px
        old_qty = int(pos["qty"])
        new_qty = old_qty + qty
        new_avg = (avg * old_qty + px * qty) / new_qty
        reason = f"{tag}(Lv{next_level}): +{gain*100:.1f}% 反発[{'・'.join(signs)}]"
        notes.append(f"{pos['symbol']} {reason} qty+{qty} @{px:.1f}")
        spent += cost
        insert_fill(
            sb,
            as_of,
            pos["symbol"],
            "buy",
            qty,
            px,
            reason,
            None,
            regime,
            {"scale_level": next_level, "name": pos["symbol"]},
            dry,
        )
        if dry:
            continue
        pl["scale_level"] = next_level
        pl["style"] = "mean_reversion_scale"
        sb.table("trade_positions").update(
            {
                "qty": new_qty,
                "avg_price": new_avg,
                "payload": pl,
                "stop_price": new_avg * (1 - float(p["stop_loss_pct"])),
                "take_profit_price": new_avg * (1 + float(p["take_profit_pct"])),
            }
        ).eq("id", pos["id"]).execute()
    return spent, notes


def maybe_entries(
    sb,
    p: dict[str, Any],
    regime: str,
    regime_note: str,
    cash: float,
    open_count: int,
    held_symbols: set[str],
    as_of: date,
    dry: bool,
) -> tuple[float, list[str]]:
    notes: list[str] = []
    spent = 0.0
    if regime == "unknown":
        return spent, ["市況不明のため新規見送り"]
    max_pos = int(p["max_positions"])
    per = float(p["per_name_pct"])
    fracs = list(p.get("scale_fracs") or [0.25, 0.35, 0.40])
    risk = sb.table("trade_risk_state").select("*").eq("id", MODE).limit(1).execute()
    state = (risk.data or [{}])[0]
    if state.get("kill_switch"):
        return spent, [f"kill switch: {state.get('kill_reason') or '停止中'}"]
    capital = float(state.get("capital_jpy") or 100000)

    inst = (
        sb.table("trade_instruments")
        .select("symbol,name,theme,asset_class")
        .eq("enabled", True)
        .execute()
    )
    candidates: list[tuple[float, dict, str, str]] = []
    if regime == "risk_on":
        for it in inst.data or []:
            if it.get("asset_class") in ("inverse_etf", "index"):
                continue
            if it.get("theme") == "index":
                continue
            if it["symbol"] in (REGIME_SYMBOL, INVERSE_SYMBOL):
                continue
            if it["symbol"] in held_symbols:
                continue
            rows = load_closes(sb, it["symbol"])
            scored = score_probe(rows, p)
            if not scored:
                continue
            score, reason = scored
            candidates.append((score, it, "buy", reason))
    else:
        if INVERSE_SYMBOL not in held_symbols:
            rows = load_closes(sb, INVERSE_SYMBOL)
            c = closes_of(rows)
            fast = sma(c, int(p["sma_fast"]))
            if fast and c and c[-1] >= fast * 0.99:
                reason = f"{regime_note}。インバースETF終値{c[-1]:.1f}がSMA近傍以上のためヘッジ打診"
                candidates.append((50.0, {"symbol": INVERSE_SYMBOL, "name": "日経インバース"}, "inverse_buy", reason))

    candidates.sort(key=lambda x: x[0], reverse=True)
    slots = max(0, max_pos - open_count)
    probe_budget = capital * per * float(fracs[0])
    for score, it, side, reason in candidates[:slots]:
        if cash - spent < probe_budget * 0.5:
            break
        px = last_close(sb, it["symbol"])
        if not px or px <= 0:
            continue
        qty = max(1, int(probe_budget // px))
        cost = qty * px
        if cost > cash - spent:
            qty = int((cash - spent) // px)
            if qty < 1:
                continue
            cost = qty * px
        notes.append(f"{it['symbol']} {it.get('name','')} {side} qty={qty} @{px:.1f} score={score:.1f} / {reason}")
        spent += cost
        insert_fill(
            sb,
            as_of,
            it["symbol"],
            side,
            qty,
            px,
            reason,
            score,
            regime,
            {"name": it.get("name"), "paper_fill": "same_day_close", "scale_level": 1},
            dry,
        )
        if dry:
            continue
        rows = load_closes(sb, it["symbol"])
        opened = as_of
        sw = swing_low_since(rows, opened) or px
        sb.table("trade_positions").insert(
            {
                "mode": MODE,
                "symbol": it["symbol"],
                "qty": qty,
                "avg_price": px,
                "opened_at": as_of.isoformat(),
                "status": "open",
                "stop_price": px * (1 - float(p["stop_loss_pct"])),
                "take_profit_price": px * (1 + float(p["take_profit_pct"])),
                "payload": {
                    "style": "mean_reversion_scale",
                    "scale_level": 1,
                    "swing_low": sw,
                    "name": it.get("name"),
                },
            }
        ).execute()
    return spent, notes


def week_realized(sb, as_of: date) -> float:
    start = as_of - timedelta(days=as_of.weekday())
    res = (
        sb.table("trade_positions")
        .select("realized_pnl,closed_at")
        .eq("mode", MODE)
        .eq("status", "closed")
        .gte("closed_at", start.isoformat())
        .lte("closed_at", as_of.isoformat())
        .execute()
    )
    return sum(float(r.get("realized_pnl") or 0) for r in (res.data or []))


def update_risk(sb, p: dict[str, Any], equity: float, as_of: date, dry: bool) -> dict[str, Any]:
    res = sb.table("trade_risk_state").select("*").eq("id", MODE).limit(1).execute()
    state = dict((res.data or [{}])[0])
    peak = float(state.get("peak_equity") or equity)
    if equity > peak:
        peak = equity
    dd = 0.0 if peak <= 0 else (peak - equity) / peak
    capital = float(state.get("capital_jpy") or 100000)
    kill = bool(state.get("kill_switch"))
    reason = state.get("kill_reason")
    wr = week_realized(sb, as_of)
    if wr <= -capital * float(p["weekly_loss_halt_pct"]):
        kill = True
        reason = f"週間実現損 {wr:.0f}円が運用枠の -{float(p['weekly_loss_halt_pct'])*100:.0f}% 超"
    if dd >= float(p["halt_pct"]):
        kill = True
        reason = f"ドローダウン {dd*100:.1f}% が撤退ライン {float(p['halt_pct'])*100:.0f}%"
    elif dd >= float(p["downgrade_pct"]):
        kill = True
        reason = f"ドローダウン {dd*100:.1f}% で新規停止（見直しライン）"
    patch = {
        "peak_equity": peak,
        "current_equity": equity,
        "drawdown_pct": dd,
        "kill_switch": kill,
        "kill_reason": reason,
        "updated_at": datetime.now(JST).isoformat(),
    }
    if not dry:
        sb.table("trade_risk_state").update(patch).eq("id", MODE).execute()
    state.update(patch)
    return state


def main() -> int:
    ap = argparse.ArgumentParser(description="Trade Desk 平均回帰リズム＋ペーパー約定")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    sb = sb_client()
    p = load_params(sb)
    as_of = today_jst()
    regime, regime_note = regime_of(sb, p)
    positions = open_positions(sb)
    risk0 = sb.table("trade_risk_state").select("*").eq("id", MODE).limit(1).execute()
    st0 = (risk0.data or [{}])[0]
    capital = float(st0.get("capital_jpy") or 100000)
    invested = sum(float(x["avg_price"]) * int(x["qty"]) for x in positions)
    closed = (
        sb.table("trade_positions")
        .select("realized_pnl")
        .eq("mode", MODE)
        .eq("status", "closed")
        .execute()
    )
    realized_all = sum(float(r.get("realized_pnl") or 0) for r in (closed.data or []))
    cash = capital + realized_all - invested

    realized_today, exit_notes = apply_rhythm(sb, p, positions, as_of, args.dry_run)
    if not args.dry_run:
        positions = open_positions(sb)
        invested = sum(float(x["avg_price"]) * int(x["qty"]) for x in positions)
        cash = capital + realized_all + realized_today - invested

    add_spent, add_notes = maybe_scale_in(
        sb, p, positions, cash, capital, as_of, regime, args.dry_run
    )
    cash = cash - add_spent
    if not args.dry_run:
        positions = open_positions(sb)

    spent, entry_notes = maybe_entries(
        sb,
        p,
        regime,
        regime_note,
        cash,
        len(positions),
        {p_["symbol"] for p_ in positions},
        as_of,
        args.dry_run,
    )
    cash_after = cash - spent
    if not args.dry_run:
        positions = open_positions(sb)
    equity, unreal = mark_to_market(sb, positions, cash_after)
    state = update_risk(sb, p, equity, as_of, args.dry_run)

    if not args.dry_run:
        sb.table("trade_daily_pnl").upsert(
            {
                "trade_date": as_of.isoformat(),
                "mode": MODE,
                "equity": equity,
                "cash": cash_after,
                "unrealized_pnl": unreal,
                "realized_pnl_day": realized_today,
                "drawdown_pct": state.get("drawdown_pct"),
                "tranche": state.get("tranche") or 1,
                "kill_switch": bool(state.get("kill_switch")),
                "payload": {"regime": regime, "regime_note": regime_note, "style": p.get("style")},
            },
            on_conflict="trade_date,mode",
        ).execute()

    print(f"📎 Trade Desk シグナル {as_of.isoformat()} {'DRY' if args.dry_run else 'paper'}")
    print(f"- 原理: 平均回帰リズム（probe 25% → confirm 35% → convince 40%）")
    print(f"- 市況: {regime} / {regime_note}")
    print(f"- 資金: cash={cash_after:,.0f} equity={equity:,.0f} DD={float(state.get('drawdown_pct') or 0)*100:.1f}%")
    print(f"- 建玉: {len(positions)}  kill={state.get('kill_switch')}")
    if exit_notes:
        print("- 決済:")
        for n in exit_notes:
            print(f"  - {n}")
    if add_notes:
        print("- 買い増し:")
        for n in add_notes:
            print(f"  - {n}")
    if entry_notes:
        print("- 新規:")
        for n in entry_notes:
            print(f"  - {n}")
    if not exit_notes and not add_notes and not entry_notes:
        print("- 本日の新規・買い増し・決済なし")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
