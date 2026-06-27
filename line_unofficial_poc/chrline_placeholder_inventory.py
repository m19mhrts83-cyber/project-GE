#!/usr/bin/env python3
"""
5.やり取り.md のプレースホルダー棚卸しと retry キュー・decode_stats との突合。
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from chrline_client_utils import save_root_from_env
from chrline_md_block_utils import PLACEHOLDER_PREFIX, find_placeholder_blocks, iter_yoritoori_blocks
from chrline_sync_to_yoritoori import (
    DECODE_STATS_FILENAME,
    RETRY_QUEUE_FILENAME,
    _default_kamiooya_kanji_yoritoori_path,
    _default_leaf_yoritoori_path,
    _default_tcell_yoritoori_path,
    _load_retry_queue,
    _retry_queue_path,
)


def _line_default_md_paths() -> list[Path]:
    return [
        _default_tcell_yoritoori_path(),
        _default_leaf_yoritoori_path(),
        _default_kamiooya_kanji_yoritoori_path(),
    ]


def _scan_md(path: Path) -> dict:
    if not path.is_file():
        return {"path": str(path), "exists": False, "placeholder_blocks": 0, "total_blocks": 0}
    text = path.read_text(encoding="utf-8")
    all_blocks = iter_yoritoori_blocks(text)
    ph_blocks = find_placeholder_blocks(text)
    by_date: Counter[str] = Counter()
    by_tag: Counter[str] = Counter()
    for b in ph_blocks:
        by_date[b.date_part] += 1
        by_tag[b.tag] += 1
    group_n = sum(1 for b in ph_blocks if "グループ" in b.tag)
    direct_n = sum(1 for b in ph_blocks if "1:1" in b.tag)
    return {
        "path": str(path),
        "exists": True,
        "placeholder_blocks": len(ph_blocks),
        "placeholder_lines": text.count(PLACEHOLDER_PREFIX),
        "total_blocks": len(all_blocks),
        "by_date": dict(sorted(by_date.items())),
        "by_tag": dict(by_tag.most_common(10)),
        "group_placeholders": group_n,
        "direct_placeholders": direct_n,
    }


def _decode_stats_summary(stats_path: Path, since_days: int) -> dict:
    if not stats_path.is_file():
        return {"seen": 0, "textual": 0, "placeholder": 0, "textual_rate_pct": 0.0}
    cutoff = datetime.now() - timedelta(days=since_days) if since_days > 0 else None
    seen = textual = placeholder = 0
    with stats_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts_s = str(rec.get("ts", ""))
            try:
                ts = datetime.fromisoformat(ts_s)
            except ValueError:
                ts = None
            if cutoff and ts and ts < cutoff:
                continue
            for b in rec.get("stats") or []:
                if not isinstance(b, dict):
                    continue
                seen += int(b.get("seen", 0))
                textual += int(b.get("textual", 0))
                placeholder += int(b.get("placeholder", 0))
    rate = (textual / seen * 100.0) if seen else 0.0
    return {
        "seen": seen,
        "textual": textual,
        "placeholder": placeholder,
        "textual_rate_pct": round(rate, 1),
    }


def _queue_crossref(queue: dict[str, dict], md_paths: list[Path]) -> dict:
    md_strs = {str(p) for p in md_paths}
    in_queue_not_md: list[str] = []
    by_route: dict[str, int] = defaultdict(int)
    exhausted = 0
    for dk, item in queue.items():
        rp = str(item.get("route_path", ""))
        by_route[rp] += 1
        if item.get("status") == "exhausted":
            exhausted += 1
        if rp in md_strs:
            in_queue_not_md.append(dk)
    return {
        "queue_total": len(queue),
        "queue_exhausted": exhausted,
        "queue_by_route": dict(by_route),
        "queue_keys": len(in_queue_not_md),
    }


def build_inventory(
    *,
    md_paths: list[Path],
    since_days: int = 14,
    save_root: Path | None = None,
) -> dict:
    root = save_root or save_root_from_env()
    queue = _load_retry_queue(_retry_queue_path(root))
    stats_path = root / DECODE_STATS_FILENAME
    md_reports = [_scan_md(p) for p in md_paths]
    total_ph = sum(r.get("placeholder_blocks", 0) for r in md_reports)
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "md_paths": [str(p) for p in md_paths],
        "md_reports": md_reports,
        "total_placeholder_blocks": total_ph,
        "retry_queue": _queue_crossref(queue, md_paths),
        "decode_stats": _decode_stats_summary(stats_path, since_days),
    }


def _render_table(inv: dict) -> str:
    lines = [
        f"# プレースホルダー棚卸し ({inv['generated_at']})",
        "",
        f"合計プレースホルダーブロック: **{inv['total_placeholder_blocks']}**",
        "",
        "## MD 別",
        "",
        "| ファイル | ブロック | 行(文字列) | 全ブロック |",
        "|----------|---------|------------|------------|",
    ]
    for r in inv["md_reports"]:
        name = Path(r["path"]).parent.name if r.get("exists") else Path(r["path"]).name
        lines.append(
            f"| {name} | {r.get('placeholder_blocks', '-')} | {r.get('placeholder_lines', '-')} | {r.get('total_blocks', '-')} |"
        )
    dq = inv["decode_stats"]
    lines.extend(
        [
            "",
            "## decode_stats",
            "",
            f"- seen: {dq['seen']}, textual: {dq['textual']}, placeholder: {dq['placeholder']}, rate: {dq['textual_rate_pct']}%",
            "",
            "## retry キュー",
            "",
            f"- 件数: {inv['retry_queue']['queue_total']} (exhausted: {inv['retry_queue']['queue_exhausted']})",
        ]
    )
    for rp, cnt in inv["retry_queue"].get("queue_by_route", {}).items():
        lines.append(f"  - {Path(rp).parent.name}: {cnt}")
    exhausted = inv["retry_queue"].get("queue_exhausted", 0)
    if exhausted:
        lines.append(f"  - exhausted（MD未確定）: {exhausted}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="LINE プレースホルダー棚卸し")
    parser.add_argument("--preset", choices=("line-default",), default="line-default")
    parser.add_argument("--md", type=Path, action="append", default=[], help="追加 MD（複数可）")
    parser.add_argument("--since-days", type=int, default=14)
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--report-out", type=Path, default=None, help="Markdown レポート出力")
    args = parser.parse_args()

    paths = list(_line_default_md_paths())
    for p in args.md:
        paths.append(p.expanduser().resolve())
    paths = list(dict.fromkeys(paths))

    inv = build_inventory(md_paths=paths, since_days=args.since_days)
    text = _render_table(inv)
    print(text)

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(inv, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nJSON: {args.json_out}", file=sys.stderr)

    if args.report_out:
        args.report_out.parent.mkdir(parents=True, exist_ok=True)
        args.report_out.write_text(text, encoding="utf-8")
        print(f"Report: {args.report_out}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
