#!/usr/bin/env python3
"""Jarvis 月次 Vポイント確認 — state / 直近監査結果を読み、報告用テキストを出す。

使い方:
  python scripts/jarvis_vpoint_monthly_check.py
  python scripts/jarvis_vpoint_monthly_check.py --mark-done
  python scripts/jarvis_vpoint_monthly_check.py --status
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
STATE_PATH = REPO / ".jarvis_state" / "vpoint_monthly.json"
EXAMPLE_PATH = REPO / ".jarvis_state" / "vpoint_monthly.example.json"
RESULT_PATH = REPO / ".jarvis_state" / "vpoint_audit_result.json"
EXPECT_PATH = REPO / ".jarvis_state" / "vpoint_audit_expectations.json"
PRIVATE_ENV = REPO / ".env.jarvis_private"


def load_dotenv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+?)\s*$", line)
        if m and not line.lstrip().startswith("#"):
            out[m.group(1)] = m.group(2).strip().strip("\"'")
    return out


def load_json(path: Path, default: dict | None = None) -> dict:
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return default if default is not None else {}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def in_window_c(now: datetime) -> bool:
    return now.day >= 25


def month_key(now: datetime) -> str:
    return now.strftime("%Y-%m")


def build_report(state: dict, result: dict, env: dict[str, str], now: datetime) -> dict:
    mk = month_key(now)
    last = state.get("last_check_c")
    done = last == mk
    align = result.get("alignment_2026_07_30") or {}
    # 番号＋メールOTPで足りる。PASSWORD は任意
    tsite_env = bool(env.get("VPOINT_TSITE_ID"))
    tsite_status = "ready_id" if tsite_env else "pending_user"
    bal = (
        result.get("credit_tsumitate", {}).get("point_history", {}) or {}
    ).get("balance_pt")
    if bal is None:
        bal = result.get("credit_tsumitate", {}).get("vpoint_balance_2026_07_29")
    tsumi = result.get("credit_tsumitate", {}).get("monthly_yen_confirmed")
    rate = result.get("credit_tsumitate", {}).get("effective_rate", {})
    merchant = result.get("merchant_high_rate", {})
    id_note = (merchant.get("meisai_202608_sample") or {}).get("note") or merchant.get("verdict") or ""
    warnings: list[str] = []
    if not tsite_env:
        warnings.append("Tサイト認証待ち（VPOINT_TSITE_ID）")
    if rate.get("status") in (
        "not_yet_verifiable_as_6pct",
        "confirmed_1pct_not_6pct",
    ):
        warnings.append("クレカ積立は1%実績／6%未達")
    if "ｉＤ" in id_note or "iD" in id_note:
        warnings.append("明細に／ｉＤが多い（高還元対象外レール）")

    ok = len(warnings) == 0
    summary = {
        "window": "C",
        "month": mk,
        "in_window": in_window_c(now),
        "already_done": done,
        "ok": ok,
        "tsumitate_yen": tsumi,
        "vpoint_balance": bal,
        "id_rail_note": id_note[:160],
        "tsite_status": tsite_status,
        "rate_status": rate.get("status"),
        "warnings": warnings,
        "alignment_ops": (align.get("ops") or {}),
    }
    return summary


def format_block(s: dict) -> str:
    judge = "✅ 問題なし" if s["ok"] else "⚠️ 要フォロー: " + " / ".join(s["warnings"])
    lines = [
        "---",
        f"📎 月次確認（Vポイント）— ウィンドウC / {s['month']}",
        f"- クレカ積立: {s['tsumitate_yen'] or '—'}円/月想定（直近監査）",
        f"- Vポイント残高（直近監査）: {s['vpoint_balance'] if s['vpoint_balance'] is not None else '—'}",
        f"- 決済レール: {s['id_rail_note'] or '—'}",
        f"- Tサイト: {s['tsite_status']}",
        f"- 積立還元率: {s['rate_status'] or '—'}",
        f"- 判定: {judge}",
        "- 注: 月次は深い突合。日常は cadence（パートナー前半ついで）／Wallet強制変更なし",
        "---",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Jarvis Vポイント月次確認")
    ap.add_argument("--mark-done", action="store_true", help="当月ウィンドウCを実施済みにする")
    ap.add_argument("--status", action="store_true", help="ウィンドウ該当・実施済のみ表示")
    args = ap.parse_args()

    env = load_dotenv(PRIVATE_ENV)
    if env.get("JARVIS_VPOINT_MONTHLY_DISABLE") == "1":
        print("📎 Vポイント月次: 無効化（JARVIS_VPOINT_MONTHLY_DISABLE=1）")
        return 0

    state = load_json(STATE_PATH)
    if not state:
        state = load_json(EXAMPLE_PATH, {"disabled": False})
    if state.get("disabled"):
        print("📎 Vポイント月次: 無効化（vpoint_monthly.json disabled）")
        return 0

    now = datetime.now(JST)
    result = load_json(RESULT_PATH)
    summary = build_report(state, result, env, now)

    if args.status:
        print(
            json.dumps(
                {
                    "in_window_c": summary["in_window"],
                    "month": summary["month"],
                    "last_check_c": state.get("last_check_c"),
                    "already_done": summary["already_done"],
                    "should_run": summary["in_window"] and not summary["already_done"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    print(format_block(summary))
    print()
    print(
        json.dumps(
            {
                "in_window_c": summary["in_window"],
                "already_done": summary["already_done"],
                "should_run": summary["in_window"] and not summary["already_done"],
                "summary": summary,
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    if args.mark_done:
        state["last_check_c"] = summary["month"]
        state["last_result_c"] = {
            "at": now.isoformat(timespec="seconds"),
            "ok": summary["ok"],
            "tsumitate_yen": summary["tsumitate_yen"],
            "vpoint_balance": summary["vpoint_balance"],
            "id_rail_note": summary["id_rail_note"],
            "tsite_status": summary["tsite_status"],
            "note": "; ".join(summary["warnings"]) if summary["warnings"] else "ok",
        }
        save_state(state)
        print(f"\n✅ marked last_check_c={summary['month']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
