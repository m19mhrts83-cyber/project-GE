#!/usr/bin/env python3
"""物件進行ゲート — 保留リマインド＆問合せ履歴。

  保留リマインド（#consult・1日1回。既に問合せ済み/重複/判断済みは自動で外す）:
    cd ~/git-repos && set -a && source .env.jarvis_private && set +a
    ~/selenium_env/venv/bin/python scripts/jarvis_property_gate_remind.py
    ~/selenium_env/venv/bin/python scripts/jarvis_property_gate_remind.py --dry-run
    ~/selenium_env/venv/bin/python scripts/jarvis_property_gate_remind.py --force --limit 20 --min-age-hours 0

  問合せ履歴（こういうふうに問い合わせた、を見る）:
    ~/selenium_env/venv/bin/python scripts/jarvis_property_gate_remind.py --history --deal-id UUID
    ~/selenium_env/venv/bin/python scripts/jarvis_property_gate_remind.py --history --recent 15

正本: docs/AIエージェントチーム/23_物件進行ゲート_Grok調査_20261012.md
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from jarvis_property_gate_lib import (  # noqa: E402
    fetch_deal_events,
    format_event_line,
    format_reminder,
    load_state,
    now_jst_date,
    pending_b_items,
    post_slack,
    reconcile_pending,
    save_state,
    sb_client,
)


def do_history(sb, args) -> int:
    if args.deal_id:
        evs = fetch_deal_events(sb, args.deal_id, limit=args.events)
        print(f"# 問合せ履歴 deal={args.deal_id}（{len(evs)}件）")
        for e in evs:
            print(format_event_line(e))
        if not evs:
            print("（履歴イベントは見つかりませんでした。deals.summary_json の inquiry_* を確認）")
        return 0
    n = args.recent or 15
    try:
        r = (
            sb.table("kurashift_re_deal_events")
            .select("deal_id,event_type,actor,summary,occurred_at")
            .in_("event_type", ["inquiry_sent", "grok_handoff_sent", "inquiry_reply"])
            .order("occurred_at", desc=True)
            .limit(n)
            .execute()
        )
    except Exception as e:  # pragma: no cover
        print(f"履歴取得に失敗: {e}", file=sys.stderr)
        return 1
    print(f"# 最近の問合せ/返信（{len(r.data or [])}件）")
    for e in r.data or []:
        print(f"{format_event_line(e)}  deal={str(e.get('deal_id'))[:8]}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="当日投稿済みでも再投稿")
    ap.add_argument("--limit", type=int, default=10, help="リマインドに載せる件数")
    ap.add_argument("--min-age-hours", type=float, default=12.0, help="これ未満の新着は除く")
    ap.add_argument("--no-post", action="store_true", help="Slack 投稿しない（整理のみ）")
    ap.add_argument("--history", action="store_true", help="問合せ履歴を表示")
    ap.add_argument("--deal-id", default="", help="履歴表示: 1件指定")
    ap.add_argument("--recent", type=int, default=0, help="履歴表示: 直近N件（横断）")
    ap.add_argument("--events", type=int, default=20, help="履歴表示: 1件あたりの件数")
    args = ap.parse_args()

    if (os.environ.get("JARVIS_PROPERTY_GATE_DISABLE") or "").strip() == "1":
        print("property_gate disabled")
        return 0

    sb = sb_client()
    st = load_state()

    if args.history:
        return do_history(sb, args)

    cleaned, deal_map = reconcile_pending(sb, st)
    items = pending_b_items(
        sb, st, min_age_hours=args.min_age_hours, deal_map=deal_map
    )
    if not args.dry_run:
        save_state(st)

    dropped = f"外した: 問合せ済み{cleaned['already_inquired']}／重複{cleaned['duplicate']}"
    if not items:
        print(f"保留なし（{dropped}）")
        return 0

    today = now_jst_date()
    if st.get("last_reminder_date") == today and not args.force and not args.dry_run:
        print(f"本日分は投稿済み（{today}）。保留 {len(items)}件。--force で再投稿。")
        return 0

    text = format_reminder(items, cleaned=cleaned, limit=args.limit)
    if args.no_post:
        print(text)
        print(f"# no-post（保留 {len(items)}件・{dropped}）")
        return 0
    pr = post_slack("consult", text, dry_run=args.dry_run)
    print(pr)
    print(f"# 保留 {len(items)}件・{dropped}")
    if pr.get("ok") and not args.dry_run:
        st["last_reminder_date"] = today
        save_state(st)
    return 0 if pr.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
