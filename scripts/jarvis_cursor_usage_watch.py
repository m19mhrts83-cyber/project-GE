#!/usr/bin/env python3
"""Cursor 枠使い切りウォッチ（手動入力本線）。

個人 Pro / Pro+ の Spending に公開 API が無いため、目視％を state に載せて
/billing と状況ウォッチへ投影する。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_cursor_usage_watch.py --status
  ~/selenium_env/venv/bin/python scripts/jarvis_cursor_usage_watch.py \\
    --set --plan pro --other-pct 45 --cursor-pct 10 --cycle-end 2026-09-25
  ~/selenium_env/venv/bin/python scripts/jarvis_cursor_usage_watch.py --push

閾値（固定）:
  Other ≥70% → suggest（warn）
  Other ≥90% または 残り日数≤7 かつ Other≥50% → ask（attention）
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
STATE_PATH = REPO / ".jarvis_state" / "cursor_usage_watch.json"
SPENDING_URL = "https://cursor.com/dashboard/spending"

PLAN_INCLUDED = {
    "pro": 20,
    "pro_plus": 70,
    "ultra": 400,
}


def now_iso() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S%z")


def today_jst() -> date:
    return datetime.now(JST).date()


def load_state() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        return {
            "updated_at": None,
            "disabled": False,
            "plan": "pro",
            "billing_cycle_end": None,
            "other_models_pct_used": None,
            "cursor_models_pct_used": None,
            "other_included_usd": 20,
            "on_demand_enabled": None,
            "note": None,
            "level": "info",
            "verdict": "未記録",
            "spending_url": SPENDING_URL,
        }
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_state(data: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _pct(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(100.0, n))


def _ymd(s: Any) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def evaluate(state: dict[str, Any]) -> dict[str, Any]:
    """level / verdict / days_left を付与したコピーを返す。"""
    out = dict(state)
    other = _pct(out.get("other_models_pct_used"))
    cursor_m = _pct(out.get("cursor_models_pct_used"))
    cycle_end = _ymd(out.get("billing_cycle_end"))
    plan = str(out.get("plan") or "pro").strip().lower().replace("+", "_plus")
    if plan == "proplus":
        plan = "pro_plus"
    out["plan"] = plan
    included = PLAN_INCLUDED.get(plan)
    if included is not None:
        out["other_included_usd"] = included

    days_left: int | None = None
    if cycle_end:
        days_left = (cycle_end - today_jst()).days
    out["days_left"] = days_left
    out["spending_url"] = SPENDING_URL

    if out.get("disabled"):
        out["level"] = "ok"
        out["verdict"] = "無効化中"
        return out

    if other is None and cursor_m is None:
        out["level"] = "info"
        out["verdict"] = "未記録 — Spending を見て --set してください"
        return out

    other_n = other if other is not None else 0.0
    # ask / attention
    if other_n >= 90 or (
        days_left is not None and days_left <= 7 and other_n >= 50
    ):
        out["level"] = "attention"
        bits = [f"Other {other_n:.0f}%"]
        if days_left is not None:
            bits.append(f"残{days_left}日")
        out["verdict"] = "要検討（Pro+ 再上げを検討）— " + " · ".join(bits)
        return out

    if other_n >= 70:
        out["level"] = "warn"
        out["verdict"] = f"注意 — Other {other_n:.0f}%（Composer / Cursor Grok へ寄せ可）"
        return out

    out["level"] = "ok"
    bits = []
    if other is not None:
        bits.append(f"Other {other:.0f}%")
    if cursor_m is not None:
        bits.append(f"Cursor Models {cursor_m:.0f}%")
    if days_left is not None:
        bits.append(f"残{days_left}日")
    out["verdict"] = "余裕 — " + (" · ".join(bits) if bits else "記録あり")
    return out


def format_status(state: dict[str, Any]) -> str:
    e = evaluate(state)
    plan = e.get("plan") or "—"
    lines = [
        "📎 Cursor枠ウォッチ",
        f"- プラン: {plan}（Other込み ${e.get('other_included_usd') or '—'}）",
        f"- 判定: {e.get('level')} / {e.get('verdict')}",
    ]
    other = e.get("other_models_pct_used")
    cur = e.get("cursor_models_pct_used")
    lines.append(
        f"- Other Models: {other if other is not None else '—'}%"
        f" · Cursor Models: {cur if cur is not None else '—'}%"
    )
    if e.get("billing_cycle_end"):
        dl = e.get("days_left")
        lines.append(
            f"- サイクル末日: {e.get('billing_cycle_end')}"
            + (f"（残{dl}日）" if dl is not None else "")
        )
    if e.get("on_demand_enabled") is not None:
        lines.append(
            f"- on-demand: {'ON' if e.get('on_demand_enabled') else 'OFF'}"
        )
    if e.get("note"):
        lines.append(f"- メモ: {e.get('note')}")
    if e.get("updated_at"):
        lines.append(f"- 更新: {e.get('updated_at')}")
    lines.append(f"- Spending: {SPENDING_URL}")
    lines.append(
        "  （Grok Bot: Pro可・週次枠はPro+より小。Bot多用で枠不足ならPro+再上げ。SuperGrok連携≈$100はPro+より高い→採用せず）"
    )
    return "\n".join(lines)


def _sb():
    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        return None
    from supabase import create_client

    return create_client(url, key)


def push_sync_meta(payload: dict[str, Any]) -> bool:
    sb = _sb()
    if not sb:
        print("# sync_meta skip: JARVIS_SUPABASE_* 未設定", file=sys.stderr)
        return False
    try:
        sb.table("sync_meta").upsert(
            {
                "key": "cursor_usage_watch",
                "value": json.dumps(payload, ensure_ascii=False),
                "updated_at": now_iso(),
            },
            on_conflict="key",
        ).execute()
        return True
    except Exception as e:
        print(f"# sync_meta skip: {e}", file=sys.stderr)
        return False


def apply_set(args: argparse.Namespace, state: dict[str, Any]) -> dict[str, Any]:
    out = dict(state)
    if args.plan:
        plan = args.plan.strip().lower().replace("+", "_plus")
        if plan == "proplus":
            plan = "pro_plus"
        if plan not in PLAN_INCLUDED and plan not in ("pro", "pro_plus", "ultra"):
            raise SystemExit(f"不明な --plan: {args.plan}（pro / pro_plus / ultra）")
        out["plan"] = plan
        out["other_included_usd"] = PLAN_INCLUDED.get(plan, out.get("other_included_usd"))
    if args.other_pct is not None:
        out["other_models_pct_used"] = _pct(args.other_pct)
    if args.cursor_pct is not None:
        out["cursor_models_pct_used"] = _pct(args.cursor_pct)
    if args.cycle_end:
        d = _ymd(args.cycle_end)
        if not d:
            raise SystemExit(f"不正な --cycle-end: {args.cycle_end}")
        out["billing_cycle_end"] = d.isoformat()
    if args.on_demand is not None:
        out["on_demand_enabled"] = bool(args.on_demand)
    if args.note is not None:
        out["note"] = args.note
    out["updated_at"] = now_iso()
    out["spending_url"] = SPENDING_URL
    return evaluate(out)


def main() -> int:
    ap = argparse.ArgumentParser(description="Cursor 枠使い切りウォッチ")
    ap.add_argument("--status", action="store_true", help="判定を表示")
    ap.add_argument("--set", action="store_true", help="値を書き込む")
    ap.add_argument("--plan", choices=["pro", "pro_plus", "ultra", "pro+"], default=None)
    ap.add_argument("--other-pct", type=float, default=None, dest="other_pct")
    ap.add_argument("--cursor-pct", type=float, default=None, dest="cursor_pct")
    ap.add_argument("--cycle-end", default=None, dest="cycle_end")
    ap.add_argument(
        "--on-demand",
        type=int,
        choices=[0, 1],
        default=None,
        dest="on_demand",
        help="1=ON / 0=OFF",
    )
    ap.add_argument("--note", default=None)
    ap.add_argument("--push", action="store_true", help="sync_meta へ投影")
    ap.add_argument("--json", action="store_true", help="評価後JSONをstdout")
    args = ap.parse_args()

    state = load_state()

    if args.set:
        if (
            args.plan is None
            and args.other_pct is None
            and args.cursor_pct is None
            and args.cycle_end is None
            and args.on_demand is None
            and args.note is None
        ):
            print("--set には少なくとも1つの値を指定してください", file=sys.stderr)
            return 2
        state = apply_set(args, state)
        save_state(state)
        print(f"# saved {STATE_PATH}", file=sys.stderr)
    else:
        state = evaluate(state)

    if args.push:
        ok = push_sync_meta(state)
        print(f"# push {'ok' if ok else 'failed'}", file=sys.stderr)

    if args.json:
        print(json.dumps(state, ensure_ascii=False, indent=2))
    else:
        print(format_status(state))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
