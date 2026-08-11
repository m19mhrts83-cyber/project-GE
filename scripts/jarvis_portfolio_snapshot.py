#!/usr/bin/env python3
"""資産全体ビュー: 口座の月次評価額・キャッシュフローを記録。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_portfolio_snapshot.py --list
  ~/selenium_env/venv/bin/python scripts/jarvis_portfolio_snapshot.py \\
    --account sony_life --value 1234567 --as-of 2026-08-01
  ~/selenium_env/venv/bin/python scripts/jarvis_portfolio_snapshot.py \\
    --account akatsuki_bond --flow living_draw --amount 50000 --note '生活費'
"""
from __future__ import annotations

import argparse
from datetime import date

from jarvis_trade_common import sb_client, today_jst


def main() -> int:
    ap = argparse.ArgumentParser(description="portfolio スナップショット／CF")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--account", default="")
    ap.add_argument("--value", type=float, default=None, help="評価額（円）")
    ap.add_argument("--cost", type=float, default=None, help="取得原価（円）")
    ap.add_argument("--as-of", default="", help="YYYY-MM-DD（省略時は今日）")
    ap.add_argument("--note", default="")
    ap.add_argument("--flow", default="", help="contribution/withdrawal/living_draw/dividend")
    ap.add_argument("--amount", type=float, default=None)
    ap.add_argument("--advisor", default="", help="石川さんメモ本文")
    args = ap.parse_args()

    sb = sb_client()
    if args.list:
        acc = sb.table("portfolio_accounts").select("*").eq("active", True).execute()
        print("📎 portfolio_accounts")
        for a in acc.data or []:
            print(f"- {a['id']}: {a['name']} ({a['ingest']})")
        snaps = (
            sb.table("portfolio_snapshots")
            .select("account_id,as_of,value_jpy")
            .order("as_of", desc=True)
            .limit(12)
            .execute()
        )
        if snaps.data:
            print("直近スナップ:")
            for s in snaps.data:
                print(f"  {s['as_of']} {s['account_id']} {float(s['value_jpy']):,.0f}円")
        return 0

    if args.advisor:
        sb.table("advisor_notes").insert(
            {
                "advisor": "ishikawa",
                "note_date": (args.as_of or today_jst().isoformat()),
                "body": args.advisor,
                "related_accounts": [args.account] if args.account else None,
            }
        ).execute()
        print("📎 advisor_notes 追記済み")
        return 0

    if args.flow:
        if not args.account or args.amount is None:
            raise SystemExit("--account と --amount が必要です")
        sb.table("portfolio_cashflows").insert(
            {
                "account_id": args.account,
                "flow_date": args.as_of or today_jst().isoformat(),
                "kind": args.flow,
                "amount_jpy": args.amount,
                "note": args.note or None,
            }
        ).execute()
        print(f"📎 cashflow {args.account} {args.flow} {args.amount:,.0f}円")
        return 0

    if args.value is None or not args.account:
        raise SystemExit("--list / --value+--account / --flow / --advisor のいずれかを指定")

    as_of = args.as_of or today_jst().isoformat()
    sb.table("portfolio_snapshots").upsert(
        {
            "account_id": args.account,
            "as_of": as_of,
            "value_jpy": args.value,
            "cost_jpy": args.cost,
            "source": "manual",
            "note": args.note or None,
        },
        on_conflict="account_id,as_of",
    ).execute()
    print(f"📎 snapshot {args.account} {as_of} {args.value:,.0f}円")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
