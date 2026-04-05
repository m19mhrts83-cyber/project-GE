#!/usr/bin/env python3
"""
chrline_sync_to_yoritoori.py が出力する decode_stats JSONL を集計して、
本文取得率の比較（特に defer_sync_placeholders ON/OFF）を見える化する。
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from chrline_client_utils import save_root_from_env

DECODE_STATS_FILENAME = ".chrline_sync_decode_stats.jsonl"


@dataclass
class Agg:
    runs: int = 0
    seen: int = 0
    textual: int = 0
    placeholder: int = 0
    media_or_stamp: int = 0
    written: int = 0
    source_sync: int = 0
    source_direct_backfill: int = 0

    def add_bucket(self, b: dict) -> None:
        self.seen += int(b.get("seen", 0))
        self.textual += int(b.get("textual", 0))
        self.placeholder += int(b.get("placeholder", 0))
        self.media_or_stamp += int(b.get("media_or_stamp", 0))
        self.written += int(b.get("written", 0))
        self.source_sync += int(b.get("source_sync", 0))
        self.source_direct_backfill += int(b.get("source_direct_backfill", 0))

    @property
    def textual_rate(self) -> float:
        return (self.textual / self.seen * 100.0) if self.seen else 0.0


def _default_stats_path() -> Path:
    return save_root_from_env() / DECODE_STATS_FILENAME


def _parse_ts(v: str) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(v)
    except ValueError:
        return None


def _render_table(headers: list[str], rows: list[list[str]]) -> str:
    widths = [len(h) for h in headers]
    for row in rows:
        for i, col in enumerate(row):
            widths[i] = max(widths[i], len(col))
    head = " | ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    sep = "-+-".join("-" * widths[i] for i in range(len(headers)))
    body = [" | ".join(col.ljust(widths[i]) for i, col in enumerate(row)) for row in rows]
    return "\n".join([head, sep, *body])


def main() -> int:
    parser = argparse.ArgumentParser(description="CHRLINE decode_stats JSONL の集計レポート")
    parser.add_argument(
        "--stats-file",
        type=Path,
        default=None,
        help=f"decode stats JSONL（未指定時は LINE_UNOFFICIAL_AUTH_DIR/{DECODE_STATS_FILENAME}）",
    )
    parser.add_argument(
        "--since-days",
        type=int,
        default=14,
        help="直近何日分を集計するか（0 以下で全期間）",
    )
    parser.add_argument(
        "--preset",
        default="",
        help="特定 preset のみ（例: line-default, tcell-yuki）",
    )
    args = parser.parse_args()

    stats_path = (args.stats_file.expanduser().resolve() if args.stats_file else _default_stats_path())
    if not stats_path.is_file():
        print(f"decode stats が見つかりません: {stats_path}")
        return 1

    cutoff: datetime | None = None
    if args.since_days and args.since_days > 0:
        cutoff = datetime.now() - timedelta(days=args.since_days)

    total = Agg()
    by_target: dict[str, Agg] = defaultdict(Agg)
    by_defer: dict[str, Agg] = defaultdict(Agg)
    total_runs = 0

    with stats_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = _parse_ts(str(rec.get("ts", "")))
            if cutoff and ts and ts < cutoff:
                continue
            preset = str(rec.get("preset", ""))
            if args.preset and preset != args.preset:
                continue
            buckets = rec.get("stats")
            if not isinstance(buckets, list):
                continue

            total_runs += 1
            defer_key = "unknown"
            if "defer_sync_placeholders" in rec:
                defer_key = "on" if bool(rec.get("defer_sync_placeholders")) else "off"
            by_defer[defer_key].runs += 1

            for b in buckets:
                if not isinstance(b, dict):
                    continue
                total.add_bucket(b)
                by_defer[defer_key].add_bucket(b)
                target_kind = "1:1" if bool(b.get("is_personal_u_mid")) else "G"
                target_key = f"{target_kind} {b.get('org_label', '?')} {str(b.get('target_mid', '?'))[:12]}..."
                by_target[target_key].add_bucket(b)

    if total_runs == 0:
        print("集計対象のレコードがありません。")
        return 0

    print(f"# decode stats report: {stats_path}")
    print(f"# runs={total_runs}  seen={total.seen}  textual={total.textual}  rate={total.textual_rate:.1f}%")
    print(
        f"# placeholder={total.placeholder} media_or_stamp={total.media_or_stamp} "
        f"source_sync={total.source_sync} source_backfill={total.source_direct_backfill}"
    )
    print()

    defer_rows: list[list[str]] = []
    for k in ("on", "off", "unknown"):
        agg = by_defer.get(k)
        if not agg or agg.runs == 0:
            continue
        defer_rows.append(
            [
                k,
                str(agg.runs),
                str(agg.seen),
                str(agg.textual),
                f"{agg.textual_rate:.1f}%",
                str(agg.placeholder),
                str(agg.media_or_stamp),
            ]
        )
    if defer_rows:
        print("## defer_sync_placeholders 比較")
        print(
            _render_table(
                ["mode", "runs", "seen", "textual", "rate", "placeholder", "media/stamp"],
                defer_rows,
            )
        )
        print()

    target_rows: list[list[str]] = []
    for k, agg in sorted(by_target.items(), key=lambda kv: kv[1].seen, reverse=True):
        target_rows.append(
            [
                k,
                str(agg.seen),
                str(agg.textual),
                f"{agg.textual_rate:.1f}%",
                str(agg.placeholder),
                str(agg.media_or_stamp),
            ]
        )
    print("## ターゲット別")
    print(_render_table(["target", "seen", "textual", "rate", "placeholder", "media/stamp"], target_rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
