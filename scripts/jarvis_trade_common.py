"""Trade Desk 共通: Supabase 接続・指標計算・Yahoo 日足取得。"""
from __future__ import annotations

import json
import os
import ssl
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
WATCHLIST = REPO / "config" / "trade_watchlist.yaml"
YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
UA = "Mozilla/5.0 (compatible; JarvisTradeDesk/0.1; +https://github.com/local)"


def today_jst() -> date:
    return datetime.now(JST).date()


def sb_client():
    from supabase import create_client

    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        raise SystemExit(
            "JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY が未設定です。"
        )
    return create_client(url, key)


def load_watchlist() -> list[dict[str, Any]]:
    data = yaml.safe_load(WATCHLIST.read_text(encoding="utf-8")) or {}
    return list(data.get("instruments") or [])


def fetch_yahoo_daily(symbol: str, range_: str = "1y") -> list[dict[str, Any]]:
    url = f"{YAHOO_CHART.format(symbol=symbol)}?interval=1d&range={range_}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"yahoo HTTP {e.code} {symbol}") from e
    result = ((payload.get("chart") or {}).get("result") or [None])[0]
    if not result:
        raise RuntimeError(f"yahoo empty {symbol}")
    ts = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    vols = quote.get("volume") or []
    rows: list[dict[str, Any]] = []
    for i, t in enumerate(ts):
        c = closes[i] if i < len(closes) else None
        if c is None:
            continue
        d = datetime.fromtimestamp(int(t), tz=JST).date()
        rows.append(
            {
                "symbol": symbol,
                "trade_date": d.isoformat(),
                "open": _num(opens, i),
                "high": _num(highs, i),
                "low": _num(lows, i),
                "close": float(c),
                "volume": int(vols[i] or 0) if i < len(vols) else 0,
                "source": "yahoo",
            }
        )
    return rows


def _num(arr: list[Any], i: int) -> float | None:
    if i >= len(arr) or arr[i] is None:
        return None
    return float(arr[i])


def sma(values: list[float], n: int) -> float | None:
    if len(values) < n or n <= 0:
        return None
    return sum(values[-n:]) / n


def rsi(values: list[float], n: int = 14) -> float | None:
    if len(values) < n + 1:
        return None
    gains = 0.0
    losses = 0.0
    window = values[-(n + 1) :]
    for a, b in zip(window, window[1:]):
        d = b - a
        if d >= 0:
            gains += d
        else:
            losses -= d
    if losses == 0:
        return 100.0
    rs = (gains / n) / (losses / n)
    return 100.0 - (100.0 / (1.0 + rs))


def sleep_polite(sec: float = 0.35) -> None:
    time.sleep(sec)


def last_n_weekdays(end: date, n: int) -> list[date]:
    out: list[date] = []
    d = end
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return list(reversed(out))
