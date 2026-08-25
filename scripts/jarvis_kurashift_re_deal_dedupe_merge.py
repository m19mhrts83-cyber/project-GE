#!/usr/bin/env python3
"""千三つ RE 案件の DB 側重複マージ（property_fingerprint）。

同一 fingerprint（正規化 URL、または タイトル+価格+エリア）の複数 deal を
勝者1件に畳み、敗者は status=archived + summary_json.duplicate_of。

正本ロジックは apps/trade-desk/lib/reDealDedupe.ts（dealFingerprint / dealKeepScore）。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_re_deal_dedupe_merge.py
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_re_deal_dedupe_merge.py --apply
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs, urlparse, urlunparse, parse_qsl, urlencode

REPO = __file__
try:
    from pathlib import Path

    REPO_ROOT = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
except Exception:
    REPO_ROOT = None  # type: ignore


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


def grok_of(deal: dict[str, Any]) -> dict[str, Any] | None:
    g = sj_of(deal).get("grok")
    return dict(g) if isinstance(g, dict) else None


def deal_listing_url(deal: dict[str, Any]) -> str:
    sj = sj_of(deal)
    grok = grok_of(deal) or {}
    for v in (sj.get("listing_url"), sj.get("url"), grok.get("url")):
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def normalize_listing_url(raw: str) -> str:
    s = str(raw or "").strip()
    if not s:
        return ""
    try:
        u = urlparse(s)
        if u.hostname in ("www.google.com", "google.com") and u.path == "/url":
            qs = parse_qs(u.query)
            q = (qs.get("q") or qs.get("url") or [None])[0]
            if q:
                s = q
    except Exception:
        pass
    try:
        u = urlparse(s)
        drop = {
            "utm_source",
            "utm_medium",
            "utm_campaign",
            "utm_content",
            "utm_term",
            "fbclid",
            "gclid",
        }
        kept = [
            (k, v)
            for k, v in parse_qsl(u.query, keep_blank_values=True)
            if k not in drop and not k.startswith("utm_")
        ]
        path = (u.path or "/").rstrip("/") or "/"
        qs = urlencode(kept)
        host = (u.hostname or "").lower()
        return f"{host}{path}{('?' + qs) if qs else ''}"
    except Exception:
        return s.lower().rstrip("/")


def normalize_title(title: str) -> str:
    t = unicodedata.normalize("NFKC", str(title or ""))
    t = re.sub(r"^\s*(re|fw|fwd)\s*:\s*", "", t, flags=re.I)
    t = re.sub(r"\[Grok調査\]\s*", "", t, flags=re.I)
    t = re.sub(r"\[Grok部長\]\s*", "", t, flags=re.I)
    t = re.sub(r"\[KURASHIFT問合せ依頼\]\s*", "", t, flags=re.I)
    t = re.sub(r"[\s　]+", "", t).lower()
    return t


def normalize_area(area: str) -> str:
    a = unicodedata.normalize("NFKC", str(area or ""))
    return re.sub(r"[\s　]+", "", a).lower()


def price_key(price: Any) -> str:
    try:
        if price is None:
            return ""
        return str(int(round(float(price))))
    except (TypeError, ValueError):
        return ""


def deal_fingerprint(deal: dict[str, Any]) -> str:
    stored = str(deal.get("property_fingerprint") or "").strip()
    if stored:
        return stored
    url_key = normalize_listing_url(deal_listing_url(deal))
    if url_key:
        return f"url:{url_key}"
    grok = grok_of(deal) or {}
    loc = ""
    if isinstance(grok.get("location"), str) and grok["location"]:
        loc = grok["location"]
    else:
        loc = str(deal.get("area") or "")
    t = normalize_title(str(deal.get("title") or ""))
    p = price_key(deal.get("price_man"))
    a = normalize_area(loc)
    if t:
        return f"tp:{t}|{p}|{a}"
    return f"id:{deal.get('id')}"


def classify_channel(deal: dict[str, Any]) -> str:
    try:
        from jarvis_kurashift_re_inquiry_channel import classify_inquiry_channel

        r = classify_inquiry_channel(deal)
        return str(r.get("channel") or "not_applicable")
    except Exception:
        return "not_applicable"


def channel_sort_rank(channel: str) -> int:
    if channel == "agent_email":
        return 0
    if channel == "grok_handoff":
        return 1
    return 2


def inquiry_progress_rank(deal: dict[str, Any]) -> int:
    sj = sj_of(deal)
    raw = deal.get("inquiry_status") or sj.get("inquiry_status") or "none"
    return {
        "has_reply": 50,
        "awaiting_reply": 40,
        "awaiting_grok": 35,
        "grok_pending": 35,
        "sent": 30,
        "sending": 20,
        "draft": 10,
    }.get(str(raw), 0)


def score_of(deal: dict[str, Any]) -> float:
    try:
        s = deal.get("match_score")
        return float(s) if s is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def updated_ms(deal: dict[str, Any]) -> float:
    t = deal.get("updated_at")
    if not t:
        return 0.0
    try:
        # supabase returns ISO
        return datetime.fromisoformat(str(t).replace("Z", "+00:00")).timestamp() * 1000
    except Exception:
        return 0.0


def deal_keep_score(deal: dict[str, Any]) -> float:
    score = 0.0
    ch = classify_channel(deal)
    score += (2 - channel_sort_rank(ch)) * 10_000
    score += inquiry_progress_rank(deal) * 100
    score += score_of(deal)
    score += min(updated_ms(deal) / 1e12, 1.0)
    return score


def merge_loser_summary(
    sj: dict[str, Any], winner_id: str, fingerprint: str
) -> dict[str, Any]:
    out = dict(sj)
    out["duplicate_of"] = winner_id
    out["property_fingerprint"] = fingerprint
    out["dedupe_merged_at"] = now_iso()
    return out


def merge_winner_summary(
    sj: dict[str, Any], loser_ids: list[str], fingerprint: str
) -> dict[str, Any]:
    out = dict(sj)
    prev = out.get("dedupe_merged_ids")
    prev_ids = [str(x) for x in prev] if isinstance(prev, list) else []
    merged = list(dict.fromkeys([*prev_ids, *[str(x) for x in loser_ids]]))
    out["property_fingerprint"] = fingerprint
    out["dedupe_merged_ids"] = merged
    out["dedupe_merged_at"] = now_iso()
    out.pop("duplicate_of", None)
    return out


def fetch_all_deals(sb: Any) -> list[dict[str, Any]]:
    cols = (
        "id, title, area, price_man, match_score, updated_at, status, source, "
        "inquiry_status, summary_json, property_fingerprint"
    )
    out: list[dict[str, Any]] = []
    page = 0
    page_size = 500
    while True:
        start = page * page_size
        end = start + page_size - 1
        try:
            resp = (
                sb.table("kurashift_re_deals")
                .select(cols)
                .order("updated_at", desc=True)
                .range(start, end)
                .execute()
            )
        except Exception as e:
            if "property_fingerprint" in str(e):
                cols2 = (
                    "id, title, area, price_man, match_score, updated_at, status, source, "
                    "inquiry_status, summary_json"
                )
                resp = (
                    sb.table("kurashift_re_deals")
                    .select(cols2)
                    .order("updated_at", desc=True)
                    .range(start, end)
                    .execute()
                )
            else:
                raise
        rows = resp.data or []
        out.extend(rows)
        if len(rows) < page_size:
            break
        page += 1
        if page > 40:
            break
    return out


def plan_merges(deals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """fingerprint → {winner, losers, fingerprint}（losers が1件以上のもののみ）"""
    groups: dict[str, list[dict[str, Any]]] = {}
    for d in deals:
        if str(d.get("status") or "") == "archived":
            # 既に archived でも fingerprint 未設定なら後で埋める対象にしてもよいが
            # マージ計画からは除外（再マージしない）
            sj = sj_of(d)
            if sj.get("duplicate_of"):
                continue
        fp = deal_fingerprint(d)
        # id: のみは一意なのでグループに入れない
        if fp.startswith("id:"):
            continue
        groups.setdefault(fp, []).append(d)

    plans: list[dict[str, Any]] = []
    for fp, members in groups.items():
        if len(members) < 2:
            continue
        ranked = sorted(members, key=deal_keep_score, reverse=True)
        winner = ranked[0]
        losers = ranked[1:]
        plans.append(
            {
                "fingerprint": fp,
                "winner": winner,
                "losers": losers,
                "winner_score": deal_keep_score(winner),
            }
        )
    plans.sort(key=lambda p: len(p["losers"]), reverse=True)
    return plans


def apply_plan(sb: Any, plan: dict[str, Any], dry_run: bool) -> dict[str, Any]:
    fp = plan["fingerprint"]
    winner = plan["winner"]
    losers = plan["losers"]
    winner_id = str(winner["id"])
    loser_ids = [str(x["id"]) for x in losers]

    winner_sj = merge_winner_summary(sj_of(winner), loser_ids, fp)
    result = {
        "fingerprint": fp,
        "winner_id": winner_id,
        "loser_ids": loser_ids,
        "winner_title": str(winner.get("title") or "")[:80],
    }
    if dry_run:
        return result

    # losers first
    for loser in losers:
        lid = str(loser["id"])
        loser_sj = merge_loser_summary(sj_of(loser), winner_id, fp)
        payload = {
            "status": "archived",
            "summary_json": loser_sj,
            "property_fingerprint": fp,
            "updated_at": now_iso(),
        }
        sb.table("kurashift_re_deals").update(payload).eq("id", lid).execute()

    win_payload = {
        "summary_json": winner_sj,
        "property_fingerprint": fp,
        "updated_at": now_iso(),
    }
    sb.table("kurashift_re_deals").update(win_payload).eq("id", winner_id).execute()
    return result


def backfill_singletons(
    sb: Any, deals: list[dict[str, Any]], plans: list[dict[str, Any]], dry_run: bool
) -> int:
    """マージ対象外でも fingerprint 列が空なら埋める。"""
    planned_ids = set()
    for p in plans:
        planned_ids.add(str(p["winner"]["id"]))
        for L in p["losers"]:
            planned_ids.add(str(L["id"]))

    n = 0
    for d in deals:
        did = str(d.get("id"))
        if did in planned_ids:
            continue
        if str(d.get("property_fingerprint") or "").strip():
            continue
        fp = deal_fingerprint(d)
        if fp.startswith("id:"):
            continue
        n += 1
        if dry_run:
            continue
        sj = sj_of(d)
        sj["property_fingerprint"] = fp
        sb.table("kurashift_re_deals").update(
            {
                "property_fingerprint": fp,
                "summary_json": sj,
                "updated_at": now_iso(),
            }
        ).eq("id", did).execute()
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description="KURASHIFT RE deal fingerprint merge")
    ap.add_argument(
        "--apply",
        action="store_true",
        help="DB に書き込む（既定は dry-run）",
    )
    ap.add_argument(
        "--no-backfill-singletons",
        action="store_true",
        help="単独案件への fingerprint 埋めをスキップ",
    )
    ap.add_argument("--json", action="store_true", help="機械可読出力")
    args = ap.parse_args()
    dry_run = not args.apply

    sb = sb_client()
    deals = fetch_all_deals(sb)
    plans = plan_merges(deals)

    applied: list[dict[str, Any]] = []
    for p in plans:
        applied.append(apply_plan(sb, p, dry_run=dry_run))

    singleton_n = 0
    if not args.no_backfill_singletons:
        singleton_n = backfill_singletons(sb, deals, plans, dry_run=dry_run)

    summary = {
        "dry_run": dry_run,
        "deals_loaded": len(deals),
        "duplicate_groups": len(plans),
        "losers_to_archive": sum(len(p["losers"]) for p in plans),
        "singleton_fingerprint_backfill": singleton_n,
        "groups": [
            {
                "fingerprint": a["fingerprint"][:120],
                "winner_id": a["winner_id"],
                "loser_ids": a["loser_ids"],
                "winner_title": a.get("winner_title"),
            }
            for a in applied[:30]
        ],
    }

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        mode = "DRY-RUN" if dry_run else "APPLY"
        print(f"📎 RE deal dedupe merge ({mode})")
        print(f"- deals_loaded: {summary['deals_loaded']}")
        print(f"- duplicate_groups: {summary['duplicate_groups']}")
        print(f"- losers_to_archive: {summary['losers_to_archive']}")
        print(f"- singleton_fingerprint_backfill: {summary['singleton_fingerprint_backfill']}")
        for g in summary["groups"][:15]:
            print(
                f"  · {g['fingerprint'][:60]}… winner={g['winner_id'][:8]} "
                f"losers={len(g['loser_ids'])} | {g.get('winner_title')}"
            )
        if dry_run:
            print("→ 問題なければ --apply で実行")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
