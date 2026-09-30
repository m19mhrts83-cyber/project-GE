#!/usr/bin/env python3
"""同一 summary_json.gmail_id の deals 重複を掃除（DELETE 禁止）。

診断: existing_gmail_ids の .limit(500) 窓落ちで同一 gmail_id が再 insert された。
本スクリプトは gmail_id グループごとに勝者1件を残し、敗者を status=archived
＋ summary_json.duplicate_of / gmail_id_dedupe_* で印付けする。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_gmail_id_dedupe.py
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_gmail_id_dedupe.py --apply
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_gmail_id_dedupe.py --json

※ DELETE は実装しない。破壊的削除が必要なら別チケット＋松野了承。
※ fingerprint 系マージは jarvis_kurashift_re_deal_dedupe_merge.py（別軸）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any

PAGE_SIZE = 1000
MAX_PAGES = 200
MAIL_SOURCES = ("mail_admin", "mail_estate", "mail_grok")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sb_client() -> Any:
    url = os.environ.get("JARVIS_SUPABASE_URL")
    key = os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY が必要です")
    from supabase import create_client

    return create_client(url, key)


def sj_of(deal: dict[str, Any]) -> dict[str, Any]:
    sj = deal.get("summary_json")
    return dict(sj) if isinstance(sj, dict) else {}


def gmail_id_of(deal: dict[str, Any]) -> str:
    gid = sj_of(deal).get("gmail_id")
    return str(gid).strip() if gid else ""


def parse_ts(raw: Any) -> float:
    if not raw:
        return 0.0
    s = str(raw).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s).timestamp()
    except Exception:
        return 0.0


def keep_score(deal: dict[str, Any]) -> float:
    """高いほど残す。非 archived・スコア・更新時刻を優先。"""
    score = 0.0
    status = str(deal.get("status") or "").lower()
    if status == "archived":
        score -= 50_000
    elif status in ("passed", "rejected", "見送り"):
        score -= 10_000
    else:
        score += 20_000
    try:
        score += float(deal.get("match_score") or 0) * 10
    except (TypeError, ValueError):
        pass
    score += min(parse_ts(deal.get("updated_at") or deal.get("created_at")), 1e12) / 1e9
    # 既に duplicate_of 印がある行は敗者扱い寄り
    if sj_of(deal).get("duplicate_of") or sj_of(deal).get("gmail_id_duplicate_of"):
        score -= 5_000
    return score


def fetch_mail_deals(sb: Any) -> list[dict[str, Any]]:
    cols = (
        "id, title, status, source, match_score, created_at, updated_at, summary_json"
    )
    out: list[dict[str, Any]] = []
    start = 0
    for _ in range(MAX_PAGES):
        resp = (
            sb.table("kurashift_re_deals")
            .select(cols)
            .in_("source", list(MAIL_SOURCES))
            .order("id")
            .range(start, start + PAGE_SIZE - 1)
            .execute()
        )
        rows = resp.data or []
        out.extend(rows)
        if len(rows) < PAGE_SIZE:
            break
        start += PAGE_SIZE
    return out


def plan_gmail_dedupe(deals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for d in deals:
        gid = gmail_id_of(d)
        if not gid:
            continue
        # 既に gmail_id 重複印で archived なら計画から除外（再処理しない）
        sj = sj_of(d)
        if str(d.get("status") or "") == "archived" and (
            sj.get("gmail_id_duplicate_of") or sj.get("duplicate_of")
        ):
            continue
        groups.setdefault(gid, []).append(d)

    plans: list[dict[str, Any]] = []
    for gid, members in groups.items():
        if len(members) < 2:
            continue
        ranked = sorted(members, key=keep_score, reverse=True)
        winner = ranked[0]
        losers = ranked[1:]
        plans.append(
            {
                "gmail_id": gid,
                "winner": winner,
                "losers": losers,
                "winner_score": keep_score(winner),
            }
        )
    plans.sort(key=lambda p: len(p["losers"]), reverse=True)
    return plans


def apply_plan(sb: Any, plan: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
    winner = plan["winner"]
    losers = plan["losers"]
    winner_id = str(winner["id"])
    loser_ids = [str(x["id"]) for x in losers]
    gid = plan["gmail_id"]
    result = {
        "gmail_id": gid,
        "winner_id": winner_id,
        "loser_ids": loser_ids,
        "winner_title": str(winner.get("title") or "")[:80],
        "loser_count": len(loser_ids),
    }
    if dry_run:
        return result

    stamp = now_iso()
    for loser in losers:
        lid = str(loser["id"])
        sj = sj_of(loser)
        sj["gmail_id_duplicate_of"] = winner_id
        sj["duplicate_of"] = winner_id
        sj["gmail_id_dedupe_at"] = stamp
        sj["gmail_id_dedupe_reason"] = "same_gmail_id"
        payload = {
            "status": "archived",
            "summary_json": sj,
            "updated_at": stamp,
        }
        sb.table("kurashift_re_deals").update(payload).eq("id", lid).execute()

    win_sj = sj_of(winner)
    prev = win_sj.get("gmail_id_dedupe_merged_ids")
    prev_ids = [str(x) for x in prev] if isinstance(prev, list) else []
    win_sj["gmail_id_dedupe_merged_ids"] = list(
        dict.fromkeys([*prev_ids, *loser_ids])
    )
    win_sj["gmail_id_dedupe_at"] = stamp
    win_sj.pop("gmail_id_duplicate_of", None)
    # fingerprint 側 duplicate_of は触らない（別軸）
    sb.table("kurashift_re_deals").update(
        {"summary_json": win_sj, "updated_at": stamp}
    ).eq("id", winner_id).execute()
    return result


def main() -> int:
    ap = argparse.ArgumentParser(
        description="KURASHIFT deals: same gmail_id archive-dedupe (no DELETE)"
    )
    ap.add_argument(
        "--apply",
        action="store_true",
        help="DB に書き込む（既定は dry-run。DELETE は無い）",
    )
    ap.add_argument("--json", action="store_true", help="機械可読出力")
    ap.add_argument(
        "--limit-groups",
        type=int,
        default=0,
        help="適用するグループ上限（0=無制限。dry-run 確認後の段階適用用）",
    )
    args = ap.parse_args()
    dry_run = not args.apply

    sb = sb_client()
    deals = fetch_mail_deals(sb)
    plans = plan_gmail_dedupe(deals)
    if args.limit_groups and args.limit_groups > 0:
        plans = plans[: args.limit_groups]

    applied: list[dict[str, Any]] = []
    for p in plans:
        applied.append(apply_plan(sb, p, dry_run=dry_run))

    summary = {
        "dry_run": dry_run,
        "delete_used": False,
        "deals_loaded": len(deals),
        "duplicate_groups": len(applied),
        "losers_to_archive": sum(a["loser_count"] for a in applied),
        "groups": [
            {
                "gmail_id": a["gmail_id"][:24],
                "winner_id": a["winner_id"],
                "loser_ids": a["loser_ids"],
                "winner_title": a.get("winner_title"),
            }
            for a in applied[:40]
        ],
    }

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        mode = "DRY-RUN" if dry_run else "APPLY"
        print(f"📎 Gmail-id deal dedupe ({mode}) — DELETE禁止 / archiveのみ")
        print(f"- deals_loaded: {summary['deals_loaded']}")
        print(f"- duplicate_groups: {summary['duplicate_groups']}")
        print(f"- losers_to_archive: {summary['losers_to_archive']}")
        for g in summary["groups"][:20]:
            print(
                f"  · gmail={g['gmail_id']}… winner={g['winner_id'][:8]} "
                f"losers={len(g['loser_ids'])} | {g.get('winner_title')}"
            )
        if dry_run:
            print("→ 問題なければ --apply（段階なら --limit-groups N）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
