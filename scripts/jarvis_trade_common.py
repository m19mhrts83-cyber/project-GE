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


def _yahoo_chart_url(symbol: str, *, range_: str | None = None, period1: int | None = None, period2: int | None = None) -> str:
    base = YAHOO_CHART.format(symbol=symbol)
    if period1 is not None and period2 is not None:
        return f"{base}?interval=1d&period1={period1}&period2={period2}"
    return f"{base}?interval=1d&range={range_ or '1y'}"


def _parse_yahoo_chart(payload: dict[str, Any], symbol: str) -> list[dict[str, Any]]:
    result = ((payload.get("chart") or {}).get("result") or [None])[0]
    if not result:
        return []
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


def _fetch_yahoo_url(url: str, symbol: str) -> list[dict[str, Any]]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"yahoo HTTP {e.code} {symbol}") from e
    return _parse_yahoo_chart(payload, symbol)


def fetch_yahoo_daily(symbol: str, range_: str = "1y") -> list[dict[str, Any]]:
    """日足取得。range=max は Yahoo が月足に間引くため、期間指定で分割する。"""
    long = range_ in {"max", "20y", "15y", "10y"}
    if long:
        years = {"10y": 10, "15y": 15, "20y": 20}.get(range_, 20)
        now = int(time.time())
        start = now - years * 365 * 24 * 3600
        chunk = 4 * 365 * 24 * 3600  # 4年ずつなら interval=1d が保たれやすい
        merged: dict[str, dict[str, Any]] = {}
        t = start
        while t < now:
            t2 = min(t + chunk, now)
            url = _yahoo_chart_url(symbol, period1=t, period2=t2)
            try:
                chunk_rows = _fetch_yahoo_url(url, symbol)
            except RuntimeError:
                chunk_rows = []
            for row in chunk_rows:
                merged[row["trade_date"]] = row
            t = t2
            time.sleep(0.2)
        if merged:
            return [merged[k] for k in sorted(merged)]
        return _fetch_yahoo_url(_yahoo_chart_url(symbol, range_="5y"), symbol)
    return _fetch_yahoo_url(_yahoo_chart_url(symbol, range_=range_), symbol)


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
