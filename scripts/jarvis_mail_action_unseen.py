#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""メール要対応（Slack）で、出したのに触られなかったカードを「未判断（unseen）」として残す。

- 触っていない ≠ 良い／不要。NG（skipped）には混ぜず action=unseen（outcome=none）で残す。
- 1回 Slack に出したら1回だけ数える（出し直したら、その回の分をもう1回）。
- 理由は聞かない。週次レビューで「未判断がN件、理由を1つだけ」聞く材料にする。

平日夜（GHA jarvis-mail-action-unseen.yml）に走る。失敗しても何も止めない。
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from jarvis_owner_decision_log import log_owner_decision  # noqa: E402

JST = timezone(timedelta(hours=9))
MIN_HOURS_DEFAULT = 6.0


def parse_ts(raw: Any) -> datetime | None:
    s = str(raw or "").strip()
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    # "+0900" → "+09:00"（fromisoformat は 3.11 で両方読めるが念のため）
    if len(s) >= 5 and s[-5] in "+-" and s[-3] != ":":
        s = f"{s[:-2]}:{s[-2:]}"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def is_unseen_due(row: dict[str, Any], *, now: datetime, min_hours: float = MIN_HOURS_DEFAULT) -> bool:
    """Slack に出してから min_hours たっても何も押されていない pending か。"""
    if str(row.get("status") or "") != "pending":
        return False
    pl = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    if pl.get("slack_ma_action") or pl.get("slack_ma_dedupe_sibling_of") or pl.get("loopware_hesitated_at"):
        return False
    posted = parse_ts(pl.get("slack_ma_posted_at"))
    if not posted or now - posted < timedelta(hours=min_hours):
        return False
    seen = parse_ts(pl.get("slack_ma_unseen_at"))
    # 前回 unseen を記録した後に出し直していなければ、もう数えない
    return not (seen and seen >= posted)


def unseen_record(row: dict[str, Any], *, now: datetime) -> dict[str, Any]:
    """owner_decisions に渡す引数（ネットワーク不要・テスト用に分ける）。"""
    pl = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    posted = parse_ts(pl.get("slack_ma_posted_at"))
    hours = round((now - posted).total_seconds() / 3600, 1) if posted else None
    digest = pl.get("slack_ma_digest") if isinstance(pl.get("slack_ma_digest"), dict) else {}
    tid = str(row.get("id") or "")
    payload: dict[str, Any] = {
        "posted_at": pl.get("slack_ma_posted_at"),
        "hours_since_post": hours,
        "from_email": row.get("from_email") or None,
        "lane": row.get("lane") or None,
        "ai_rank": digest.get("score"),
    }
    if pl.get("applied_rules"):
        payload["applied_rules"] = pl.get("applied_rules")
    if pl.get("loopware_miss"):
        payload["from_miss"] = True
    return {
        "surface": "triage",
        "action": "unseen",
        "source": "script:mail_action_unseen",
        "employee": "116",
        "target_type": "triage_item",
        "target_id": tid,
        "subject": str(row.get("subject") or "") or None,
        "payload": {k: v for k, v in payload.items() if v is not None},
        # 同じ「出した回」は1回だけ
        "idem_key": f"script:triage:{tid}:unseen:{pl.get('slack_ma_posted_at')}",
    }


def stamp_unseen(pl: dict[str, Any], *, now: datetime) -> dict[str, Any]:
    out = dict(pl)
    out["slack_ma_unseen_at"] = now.astimezone(JST).isoformat()
    out["slack_ma_unseen_count"] = int(out.get("slack_ma_unseen_count") or 0) + 1
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--min-hours", type=float, default=MIN_HOURS_DEFAULT)
    ap.add_argument("--limit", type=int, default=200)
    args = ap.parse_args()

    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        print("supabase env missing — skip")
        return 0
    from supabase import create_client

    sb = create_client(url, key)
    now = datetime.now(timezone.utc)
    since = (now - timedelta(days=14)).isoformat()
    res = (
        sb.table("triage_items")
        .select("id,status,subject,from_email,lane,payload")
        .eq("status", "pending")
        .not_.is_("payload->>slack_ma_posted_at", "null")
        .gte("updated_at", since)
        .limit(args.limit)
        .execute()
    )
    rows = [r for r in (res.data or []) if is_unseen_due(r, now=now, min_hours=args.min_hours)]
    logged = 0
    for r in rows:
        rec = unseen_record(r, now=now)
        print(f"# unseen id={rec['target_id']} hours={rec['payload'].get('hours_since_post')} {(rec['subject'] or '')[:40]}")
        if args.dry_run:
            continue
        if log_owner_decision(**rec):
            logged += 1
            pl = r.get("payload") if isinstance(r.get("payload"), dict) else {}
            try:
                sb.table("triage_items").update({"payload": stamp_unseen(pl, now=now)}).eq("id", rec["target_id"]).execute()
            except Exception as e:  # noqa: BLE001 — soft-fail
                print(f"# stamp soft-fail {rec['target_id']}: {e}", file=sys.stderr)
    print(f"📎 mail action unseen — candidates={len(rows)} logged={logged} dry_run={args.dry_run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
