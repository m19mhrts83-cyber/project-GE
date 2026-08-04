#!/usr/bin/env python3
"""
課金／サブスクの月次確認サマリー。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  python scripts/jarvis_billing_monthly_check.py
  python scripts/jarvis_billing_monthly_check.py --mark-done
  python scripts/jarvis_billing_monthly_check.py --refresh   # YAML から差分再計算

ウィンドウ（Jarvis 月次）: 毎月 1〜8 日。state: .jarvis_state/billing_monthly.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
STATE = REPO / ".jarvis_state" / "billing_monthly.json"
sys.path.insert(0, str(REPO / "scripts"))


def now_iso() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S%z")


def ym_now() -> str:
    return datetime.now(JST).strftime("%Y-%m")


def in_window(day: int | None = None) -> bool:
    d = day if day is not None else datetime.now(JST).day
    return 1 <= d <= 8


def fmt_yen(n: float | None) -> str:
    if n is None:
        return "—"
    return f"{round(n):,}円"


def load_state() -> dict:
    if not STATE.is_file():
        return {}
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def push_meta(summary: dict) -> None:
    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        return
    from supabase import create_client

    sb = create_client(url, key)
    sb.table("sync_meta").upsert(
        {
            "key": "subscriptions_monthly_summary",
            "value": json.dumps(summary, ensure_ascii=False),
            "updated_at": now_iso(),
        },
        on_conflict="key",
    ).execute()


def print_block(s: dict) -> None:
    ym = s.get("as_of_ym") or ym_now()
    prev = s.get("prev_ym")
    delta = s.get("delta_monthly")
    confirmed = s.get("confirmed_at")
    lines = [f"📎 課金月次サマリー — {ym}" + (f" / 対比 {prev}" if prev else " / ベースライン")]

    if delta is not None:
        sign = "+" if delta >= 0 else ""
        lines.append(
            f"- 月額換算: {fmt_yen(s.get('active_monthly_total'))}"
            f"（前月比 {sign}{fmt_yen(delta)}）"
        )
    else:
        lines.append(
            f"- 月額換算: {fmt_yen(s.get('active_monthly_total'))}（前月比なし）"
        )

    added = s.get("added") or []
    removed = s.get("removed") or []
    amount = s.get("amount_changed") or []
    status = s.get("status_changed") or []
    alerts = s.get("watch_alerts") or []
    watch = s.get("watch_active") or []

    if not prev:
        lines.append("- 変更: 初回スナップショット（前月比なし）")
    elif not (added or removed or amount or status or alerts):
        lines.append("- 変更: なし（前月比なし・変化なし）")
    else:
        if added:
            names = ", ".join(str(x.get("name") or x.get("id")) for x in added[:8])
            lines.append(f"- 新規: {names}")
        if removed:
            names = ", ".join(str(x.get("name") or x.get("id")) for x in removed[:8])
            lines.append(f"- 削除・一覧から除外: {names}")
        if amount:
            bits = []
            for x in amount[:6]:
                bits.append(
                    f"{x.get('name')}: {fmt_yen(x.get('from_monthly'))}→{fmt_yen(x.get('to_monthly'))}"
                )
            lines.append(f"- 金額変更: {'; '.join(bits)}")
        if status:
            bits = [f"{x.get('name')}: {x.get('from')}→{x.get('to')}" for x in status[:6]]
            lines.append(f"- ステータス変更: {'; '.join(bits)}")
        if alerts:
            bits = [f"{x.get('name')}（{x.get('reason')}）" for x in alerts[:8]]
            lines.append(f"- 注視・新規: {'; '.join(bits)}")

    if watch:
        lines.append(
            f"- 注視中: {', '.join(str(w.get('name')) for w in watch[:10])}"
            + ("…" if len(watch) > 10 else "")
        )
    lines.append(f"- 最終確認: {confirmed or '未確認（要確認）'}")
    lines.append(
        "- 判定: "
        + ("✅ 確認済" if confirmed else "⚠️ 要フォロー: 月次で金額・新規を確認")
    )
    print("\n".join(lines))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Billing monthly summary check")
    ap.add_argument("--mark-done", action="store_true")
    ap.add_argument("--refresh", action="store_true", help="YAML から差分を再計算")
    ap.add_argument("--force-window", action="store_true", help="ウィンドウ外でも出力")
    args = ap.parse_args(argv)

    if os.environ.get("JARVIS_BILLING_MONTHLY_DISABLE", "").strip() == "1":
        return 0
    st = load_state()
    if st.get("disabled") is True:
        return 0

    if args.refresh or not st.get("as_of_ym"):
        from jarvis_subscriptions_push import build_and_store_monthly_summary, load_rows

        rows, summary = load_rows()
        st = build_and_store_monthly_summary(rows, summary)

    ym = st.get("as_of_ym") or ym_now()
    if args.mark_done:
        st["confirmed_at"] = now_iso()
        st["last_check"] = ym
        STATE.write_text(json.dumps(st, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        push_meta(st)
        print(f"# marked confirmed_at={st['confirmed_at']}", file=sys.stderr)

    # 促し: ウィンドウ内かつ未確認、または force
    need = args.force_window or args.mark_done or args.refresh
    if not need:
        if in_window() and (st.get("confirmed_at") is None or not str(st.get("confirmed_at") or "").startswith(ym)):
            # confirmed_at is full iso; treat as confirmed for month if last_check == ym
            if st.get("last_check") != ym:
                need = True
        if st.get("has_changes") and st.get("last_check") != ym:
            need = True

    if not need and not args.mark_done:
        # 変更があり未確認なら常に出す
        if st.get("has_changes") and st.get("last_check") != ym:
            need = True

    if need or args.mark_done:
        print_block(st)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
