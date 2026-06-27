#!/usr/bin/env python3
"""
LINE sync 定常ルーティン用: プレースホルダー・retry キュー・decode_stats の要約と前回比較。

パートナー取り込み（chrline_yoritoori_inbox_fetch.py）の sync 直後に呼ぶ想定。
"""
from __future__ import annotations

import json
from pathlib import Path

from chrline_client_utils import save_root_from_env
from chrline_placeholder_inventory import _line_default_md_paths, build_inventory

HEALTH_STATE_FILENAME = ".chrline_line_health_last.json"
ROUTINE_MARKER = "LINE本文ヘルス（定常）"


def _health_state_path(save_root: Path | None = None) -> Path:
    root = save_root or save_root_from_env()
    return root / HEALTH_STATE_FILENAME


def load_previous_health(save_root: Path | None = None) -> dict | None:
    path = _health_state_path(save_root)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def save_current_health(snapshot: dict, save_root: Path | None = None) -> Path:
    path = _health_state_path(save_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _folder_placeholder_map(inv: dict) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in inv.get("md_reports") or []:
        if not r.get("exists"):
            continue
        name = Path(str(r["path"])).parent.name
        out[name] = int(r.get("placeholder_blocks", 0))
    return out


def build_health_snapshot(inv: dict) -> dict:
    by_folder = _folder_placeholder_map(inv)
    dq = inv.get("decode_stats") or {}
    rq = inv.get("retry_queue") or {}
    return {
        "generated_at": inv.get("generated_at"),
        "total_placeholder_blocks": int(inv.get("total_placeholder_blocks", 0)),
        "by_folder": by_folder,
        "queue_total": int(rq.get("queue_total", 0)),
        "queue_exhausted": int(rq.get("queue_exhausted", 0)),
        "decode_seen": int(dq.get("seen", 0)),
        "decode_textual": int(dq.get("textual", 0)),
        "textual_rate_pct": float(dq.get("textual_rate_pct", 0.0)),
    }


def evaluate_alerts(current: dict, previous: dict | None) -> list[str]:
    alerts: list[str] = []
    if previous:
        prev_ph = int(previous.get("total_placeholder_blocks", 0))
        cur_ph = int(current.get("total_placeholder_blocks", 0))
        delta = cur_ph - prev_ph
        if delta > 0:
            alerts.append(f"MDプレースホルダーが前回比 +{delta} 件増加（新規確定の疑い）")
        prev_q = int(previous.get("queue_total", 0))
        cur_q = int(current.get("queue_total", 0))
        if cur_q > prev_q + 20:
            alerts.append(f"retryキューが急増（{prev_q} → {cur_q}）")

    rate = float(current.get("textual_rate_pct", 0.0))
    seen = int(current.get("decode_seen", 0))
    if seen >= 20 and rate < 5.0:
        alerts.append(f"直近の本文取得率が低い（textual {rate}%）— E2EE 未復号の可能性")

    exhausted = int(current.get("queue_exhausted", 0))
    if exhausted > 0:
        alerts.append(f"retryキュー exhausted {exhausted} 件（MD未確定のまま枯渇）")

    return alerts


def _delta_str(cur: int, prev: int | None) -> str:
    if prev is None:
        return str(cur)
    d = cur - prev
    if d == 0:
        return f"{cur}（±0）"
    sign = "+" if d > 0 else ""
    return f"{cur}（{sign}{d}）"


def render_routine_block(
    inv: dict,
    *,
    previous: dict | None = None,
    since_days: int = 7,
) -> str:
    """パートナー確認 後半報告用の短いブロック（Markdown）。"""
    cur = build_health_snapshot(inv)
    alerts = evaluate_alerts(cur, previous)
    by_folder = cur.get("by_folder") or {}
    folder_parts = [f"{k} {v}" for k, v in sorted(by_folder.items())]
    folder_line = " / ".join(folder_parts) if folder_parts else "—"

    prev_ph = int(previous["total_placeholder_blocks"]) if previous else None
    prev_q = int(previous["queue_total"]) if previous else None
    prev_rate = float(previous["textual_rate_pct"]) if previous else None

    ok_flags: list[str] = []
    warn_flags: list[str] = []
    if previous is not None:
        if int(cur["total_placeholder_blocks"]) <= int(previous.get("total_placeholder_blocks", 0)):
            ok_flags.append("MD新規増加なし")
        else:
            warn_flags.append("MDプレースホルダー増加")
    if float(cur["textual_rate_pct"]) >= 5.0:
        ok_flags.append("復号率OK")
    elif int(cur.get("decode_seen", 0)) < 10:
        ok_flags.append("復号率サンプル少")
    else:
        warn_flags.append("復号率要フォロー")

    judgment_parts = []
    if ok_flags:
        judgment_parts.append("✅ " + "・".join(ok_flags))
    if warn_flags or alerts:
        judgment_parts.append("⚠️ " + "・".join(warn_flags + alerts[:2]))

    lines = [
        "---",
        f"📎 {ROUTINE_MARKER}（直近{since_days}日 decode）",
        f"- MDプレースホルダー: {_delta_str(int(cur['total_placeholder_blocks']), prev_ph)} — {folder_line}",
        f"- retryキュー: {_delta_str(int(cur['queue_total']), prev_q)}（exhausted {cur['queue_exhausted']}）",
        f"- textual率: {cur['textual_rate_pct']}%"
        + (f"（前回 {prev_rate}%）" if prev_rate is not None else ""),
        f"- 判定: {' / '.join(judgment_parts) if judgment_parts else '—'}",
        "---",
    ]
    return "\n".join(lines)


def run_line_health_routine(
    *,
    since_days: int = 7,
    save_baseline: bool = True,
    save_root: Path | None = None,
) -> tuple[dict, str]:
    """
    棚卸し → 前回比較 → 報告ブロック生成。save_baseline 時は今回値を次回比較用に保存。
    戻り値: (inventory, routine_block_markdown)
    """
    root = save_root or save_root_from_env()
    previous = load_previous_health(root)
    inv = build_inventory(md_paths=_line_default_md_paths(), since_days=since_days, save_root=root)
    block = render_routine_block(inv, previous=previous, since_days=since_days)
    if save_baseline:
        save_current_health(build_health_snapshot(inv), root)
    return inv, block


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="LINE 定常ヘルス要約（パートナー確認用）")
    parser.add_argument("--since-days", type=int, default=7)
    parser.add_argument("--no-save-baseline", action="store_true", help="次回比較用スナップショットを保存しない")
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args()

    inv, block = run_line_health_routine(
        since_days=args.since_days,
        save_baseline=not args.no_save_baseline,
    )
    print(block)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        payload = {"inventory": inv, "routine_block": block}
        args.json_out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
