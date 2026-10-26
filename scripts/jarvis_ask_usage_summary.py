#!/usr/bin/env python3
"""Jarvis Dashboard の ask_usage JSONL を本文なしで集計する。

例:
    python3 scripts/jarvis_ask_usage_summary.py server.log
    cat server.log | python3 scripts/jarvis_ask_usage_summary.py

ログ行の前後にプラットフォームの文字があっても、最初の JSON オブジェクトを探す。
質問・回答・エラー本文は入力にも出力にも保存しない。
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable


def parse_events(lines: Iterable[str]) -> list[dict]:
    events: list[dict] = []
    decoder = json.JSONDecoder()
    for line in lines:
        start = line.find("{")
        if start < 0:
            continue
        try:
            value, _ = decoder.raw_decode(line[start:])
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(value, dict) and value.get("event") == "ask_usage":
            events.append(value)
    return events


def summarize(events: list[dict]) -> dict:
    elapsed = [v for e in events if isinstance((v := e.get("elapsed_ms")), (int, float))]
    chars = [v for e in events if isinstance((v := e.get("input_chars")), (int, float))]
    known_tokens = [v for e in events if isinstance((v := e.get("tokens")), (int, float))]
    known_cost = [v for e in events if isinstance((v := e.get("cost")), (int, float))]
    return {
        "events": len(events),
        "by_engine": dict(Counter(str(e.get("engine") or "unknown") for e in events)),
        "by_via": dict(Counter(str(e.get("via") or "unknown") for e in events)),
        "by_outcome": dict(Counter(str(e.get("outcome") or "unknown") for e in events)),
        "cache_hits": sum(e.get("cache_hit") is True for e in events),
        "avg_input_chars": round(sum(chars) / len(chars), 1) if chars else None,
        "avg_elapsed_ms": round(sum(elapsed) / len(elapsed), 1) if elapsed else None,
        "tokens": sum(known_tokens) if len(known_tokens) == len(events) and events else None,
        "cost": round(sum(known_cost), 6) if len(known_cost) == len(events) and events else None,
        "measurement": (
            "complete" if events and len(known_tokens) == len(events) and len(known_cost) == len(events)
            else "tokens_and_cost_unavailable"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", nargs="?", help="JSONL/log file. Omit for stdin")
    args = parser.parse_args()
    if args.log:
        with Path(args.log).open(encoding="utf-8", errors="replace") as handle:
            events = parse_events(handle)
    else:
        events = parse_events(sys.stdin)
    print(json.dumps(summarize(events), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
