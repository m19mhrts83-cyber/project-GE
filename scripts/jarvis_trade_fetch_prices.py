#!/usr/bin/env python3
"""ウォッチリストの日足を Yahoo から取得して trade_prices に upsert。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_trade_fetch_prices.py
  ~/selenium_env/venv/bin/python scripts/jarvis_trade_fetch_prices.py --range 6mo
"""
from __future__ import annotations

import argparse
import sys

from jarvis_trade_common import fetch_yahoo_daily, load_watchlist, sb_client, sleep_polite


def upsert_instruments(sb, instruments: list[dict]) -> None:
    rows = []
    for it in instruments:
        rows.append(
            {
                "symbol": it["symbol"],
                "ticker_jp": it.get("ticker_jp"),
                "name": it["name"],
                "theme": it.get("theme") or "other",
                "asset_class": it.get("asset_class") or "equity",
                "enabled": bool(it.get("enabled", True)),
            }
        )
    if rows:
        sb.table("trade_instruments").upsert(rows, on_conflict="symbol").execute()


def main() -> int:
    ap = argparse.ArgumentParser(description="Trade Desk 日足取得")
    ap.add_argument("--range", default="1y", help="Yahoo range (3mo/6mo/1y)")
    ap.add_argument("--symbol", default="", help="1銘柄だけ")
    args = ap.parse_args()

    instruments = load_watchlist()
    if args.symbol:
        instruments = [i for i in instruments if i["symbol"] == args.symbol]
        if not instruments:
            print(f"# unknown symbol {args.symbol}", file=sys.stderr)
            return 2

    sb = sb_client()
    upsert_instruments(sb, load_watchlist())

    ok = 0
    fail = 0
    bars = 0
    for it in instruments:
        sym = it["symbol"]
        try:
            rows = fetch_yahoo_daily(sym, range_=args.range)
            if rows:
                # upsert は unique (symbol, trade_date)。id は自動
                chunk = 200
                for i in range(0, len(rows), chunk):
                    sb.table("trade_prices").upsert(
                        rows[i : i + chunk],
                        on_conflict="symbol,trade_date",
                    ).execute()
                bars += len(rows)
            print(f"# {sym} {it['name']} bars={len(rows)}")
            ok += 1
        except Exception as e:
            print(f"# FAIL {sym}: {e}", file=sys.stderr)
            fail += 1
        sleep_polite()

    print(f"📎 Trade Desk 日足: ok={ok} fail={fail} bars={bars}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
