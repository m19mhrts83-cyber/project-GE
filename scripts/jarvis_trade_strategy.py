"""平均回帰リズムの純ロジック（DB非依存）。ペーパー・バックテスト共通。"""
from __future__ import annotations

import json
from datetime import date
from typing import Any

from jarvis_trade_common import rsi, sma

REGIME_SYMBOL = "1321.T"
INVERSE_SYMBOL = "1357.T"
MEAN_N = 60

DEFAULT_PARAMS: dict[str, Any] = {
    "style": "mean_reversion_scale",
    "sma_fast": 20,
    "sma_slow": 60,
    "rsi_period": 14,
    "rsi_buy_low": 25,
    "rsi_buy_high": 48,
    "drop_min_pct": 0.08,
    "drop_max_pct": 0.22,
    "rebound_min_signs": 2,
    "scale_fracs": [0.25, 0.35, 0.40],
    "confirm_gain_pct": 0.02,
    "convince_rsi": 50,
    "partial_exit_frac": 0.5,
    "rhythm_fail_pct": 0.03,
    "mean_target_band": 0.015,
    "take_profit_pct": 0.12,
    "stop_loss_pct": 0.08,
    "max_hold_days": 20,
    "max_positions": 4,
    "per_name_pct": 0.20,
    "weekly_loss_halt_pct": 0.05,
    "downgrade_pct": 0.10,
    "halt_pct": 0.20,
    "promote_weeks": 8,
    "promote_max_dd_pct": 0.08,
    "rising_mean_lookback": 20,
    "rising_mean_min_ratio": 0.98,
}


def merge_params(raw: dict[str, Any] | None) -> dict[str, Any]:
    p = dict(DEFAULT_PARAMS)
    if raw:
        p.update(raw)
    return p


def closes_of(rows: list[dict[str, Any]]) -> list[float]:
    return [float(r["close"]) for r in rows if r.get("close") is not None]


def regime_from_rows(rows: list[dict[str, Any]], p: dict[str, Any]) -> str:
    c = closes_of(rows)
    fast = sma(c, int(p["sma_fast"]))
    slow = sma(c, int(p["sma_slow"]))
    if fast is None or slow is None:
        return "unknown"
    return "risk_on" if fast > slow else "risk_off"


def rebound_signs(rows: list[dict[str, Any]], p: dict[str, Any]) -> tuple[int, list[str]]:
    if len(rows) < 6:
        return 0, []
    last, prev = rows[-1], rows[-2]
    signs: list[str] = []
    lc, lo = last.get("close"), last.get("open")
    pc = prev.get("close")
    if lc is not None and pc is not None and float(lc) > float(pc):
        signs.append("陽転")
    if lc is not None and lo is not None and float(lc) > float(lo):
        signs.append("陽線")
    last_low = last.get("low")
    recent = [float(r["low"]) for r in rows[-6:-1] if r.get("low") is not None]
    if last_low is not None and recent and float(last_low) > min(recent):
        signs.append("安値切り上げ")
    c = closes_of(rows)
    n = int(p["rsi_period"])
    r_now = rsi(c, n)
    r_prev = rsi(c[:-1], n) if len(c) > n + 2 else None
    if r_now is not None and r_prev is not None and r_now > r_prev:
        signs.append("RSI上向き")
    return len(signs), signs


def mean_is_rising(rows: list[dict[str, Any]], p: dict[str, Any]) -> bool:
    """長期平均が上がっている／横ばいなら True。金持ちがさらに金持ち、の実装。"""
    c = closes_of(rows)
    n = int(p.get("sma_slow") or MEAN_N)
    lb = int(p.get("rising_mean_lookback") or 20)
    now = sma(c, n)
    prev = sma(c[:-lb], n) if len(c) > n + lb else None
    if now is None or prev is None or prev <= 0:
        return False
    return now >= prev * float(p.get("rising_mean_min_ratio") or 0.98)


def falling_knife(rows: list[dict[str, Any]], p: dict[str, Any]) -> bool:
    c = closes_of(rows)
    now = sma(c, int(p["sma_fast"]))
    prev = sma(c[:-5], int(p["sma_fast"])) if len(c) > 25 else None
    if now is None or prev is None:
        return False
    return now < prev * 0.97


def stretch_stats(rows: list[dict[str, Any]], p: dict[str, Any]) -> dict[str, float] | None:
    c = closes_of(rows)
    mean = sma(c, int(p.get("sma_slow") or MEAN_N))
    if mean is None or not c:
        return None
    last = c[-1]
    high20 = max(c[-20:]) if len(c) >= 20 else max(c)
    drop_mean = (mean - last) / mean
    drop_high = (high20 - last) / high20 if high20 else 0.0
    r = rsi(c, int(p["rsi_period"]))
    return {
        "last": last,
        "mean": mean,
        "drop_mean": drop_mean,
        "drop_high": drop_high,
        "stretch": max(drop_mean, drop_high),
        "rsi": r if r is not None else -1.0,
    }


def score_probe(rows: list[dict[str, Any]], p: dict[str, Any]) -> tuple[float, str] | None:
    st = stretch_stats(rows, p)
    if not st:
        return None
    if falling_knife(rows, p):
        return None
    if not mean_is_rising(rows, p):
        return None
    lo, hi = float(p["drop_min_pct"]), float(p["drop_max_pct"])
    if not (lo <= st["stretch"] <= hi):
        return None
    if not (float(p["rsi_buy_low"]) <= st["rsi"] <= float(p["rsi_buy_high"])):
        return None
    n_signs, signs = rebound_signs(rows, p)
    if n_signs < int(p["rebound_min_signs"]):
        return None
    score = st["stretch"] * 100 + n_signs * 5 + max(0.0, 40.0 - abs(st["rsi"] - 35.0))
    reason = (
        f"平均回帰プローブ: 終値{st['last']:.1f} 平均{st['mean']:.1f}から"
        f"{st['drop_mean']*100:.1f}%沈み（高値比{st['drop_high']*100:.1f}%）、"
        f"RSI{st['rsi']:.1f}、上昇平均の一時沈み、反発[{'・'.join(signs)}]"
    )
    return score, reason


def pos_payload(pos: dict[str, Any]) -> dict[str, Any]:
    raw = pos.get("payload") or {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = {}
    return dict(raw)


def swing_low_since(rows: list[dict[str, Any]], opened: date) -> float | None:
    lows: list[float] = []
    for r in rows:
        d = date.fromisoformat(str(r["trade_date"])[:10])
        if d >= opened and r.get("low") is not None:
            lows.append(float(r["low"]))
    return min(lows) if lows else None


def up_days_since(rows: list[dict[str, Any]], opened: date) -> int:
    n = 0
    prev = None
    for r in rows:
        d = date.fromisoformat(str(r["trade_date"])[:10])
        if d < opened:
            prev = float(r["close"]) if r.get("close") is not None else prev
            continue
        cur = float(r["close"]) if r.get("close") is not None else None
        if cur is not None and prev is not None and cur > prev:
            n += 1
        if cur is not None:
            prev = cur
    return n


def decide_rhythm_exit(
    pos: dict[str, Any],
    px: float,
    rows: list[dict[str, Any]],
    as_of: date,
    p: dict[str, Any],
) -> tuple[str, int, str] | None:
    """reason, sell_qty, kind。何もしないなら None。"""
    avg = float(pos["avg_price"])
    qty = int(pos["qty"])
    if qty <= 0:
        return None
    pnl_pct = (px - avg) / avg
    opened = date.fromisoformat(str(pos["opened_at"])[:10])
    held = (as_of - opened).days
    sl = float(p["stop_loss_pct"])
    tp = float(p["take_profit_pct"])
    max_hold = int(p["max_hold_days"])
    band = float(p["mean_target_band"])
    fail = float(p["rhythm_fail_pct"])
    partial_frac = float(p["partial_exit_frac"])
    pl = pos_payload(pos)
    already_partial = bool(pl.get("partial_done"))

    if pos.get("symbol") == INVERSE_SYMBOL:
        if pnl_pct <= -sl:
            return f"インバース損切り {pnl_pct*100:.1f}%", qty, "full"
        if pnl_pct >= tp:
            return f"インバース利確 {pnl_pct*100:.1f}%", qty, "full"
        if held >= max_hold:
            return f"インバース保有{held}日で見直し", qty, "full"
        return None

    st = stretch_stats(rows, p)
    sw = swing_low_since(rows, opened) or float(pl.get("swing_low") or avg)
    n_signs, _ = rebound_signs(rows, p)

    if pnl_pct <= -sl or px < sw * (1 - fail):
        return f"硬損切/スイング割れ {pnl_pct*100:.1f}%（安値{sw:.1f}）", qty, "full"
    if held >= max_hold:
        return f"保有{held}日で見直し決済（上限{max_hold}日）", qty, "full"
    if pnl_pct >= tp:
        return f"伸び切り利確 {pnl_pct*100:.1f}%", qty, "full"
    if st and abs(px - st["mean"]) / st["mean"] <= band and px >= avg:
        sell_qty = max(1, int(qty * partial_frac)) if qty >= 2 else qty
        kind = "partial_mean" if sell_qty < qty else "full"
        return f"平均回帰到達（平均{st['mean']:.1f}）→ 半分利確", sell_qty, kind
    if already_partial and (px < avg * (1 - fail) or n_signs == 0):
        return f"一部撤退後もリズム回復せず → 残り撤退 {pnl_pct*100:.1f}%", qty, "full"
    if (not already_partial) and (px < avg * (1 - fail) or px < sw):
        sell_qty = max(1, int(qty * partial_frac)) if qty >= 2 else qty
        kind = "partial_break" if sell_qty < qty else "full"
        return f"リズム崩れ → 一部撤退 {pnl_pct*100:.1f}%", sell_qty, kind
    return None


def decide_scale_in(
    pos: dict[str, Any],
    px: float,
    rows: list[dict[str, Any]],
    as_of: date,
    p: dict[str, Any],
) -> tuple[int, str, list[str]] | None:
    """next_level, tag, signs。追加しないなら None。下落中は必ず None。"""
    if pos.get("symbol") == INVERSE_SYMBOL:
        return None
    pl = pos_payload(pos)
    fracs = list(p.get("scale_fracs") or [0.25, 0.35, 0.40])
    level = int(pl.get("scale_level") or 1)
    if level >= len(fracs):
        return None
    avg = float(pos["avg_price"])
    if px <= avg:
        return None
    n_signs, signs = rebound_signs(rows, p)
    if n_signs < int(p["rebound_min_signs"]):
        return None
    st = stretch_stats(rows, p)
    c = closes_of(rows)
    fast = sma(c, int(p["sma_fast"]))
    opened = date.fromisoformat(str(pos["opened_at"])[:10])
    ups = up_days_since(rows, opened)
    gain = (px - avg) / avg
    confirm_gain = float(p["confirm_gain_pct"])
    next_level = level + 1
    if next_level == 2:
        if gain >= confirm_gain and ups >= 2:
            return next_level, "確認買い増し", signs
    elif next_level == 3:
        if (
            gain >= confirm_gain * 1.5
            and st is not None
            and st["rsi"] >= float(p["convince_rsi"])
            and fast is not None
            and px >= fast
        ):
            return next_level, "確信買い増し", signs
    return None
