#!/usr/bin/env python3
"""KURASHIFT 第一問合せ — 閾値評価（YAML 正本と TS reInquiryCandidate 同期）。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_re_inquiry_rules.py --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_re_inquiry_rules.py --deal-id <uuid>
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO / "config" / "kurashift_re_inquiry_auto.yaml"

LEGACY_AP_RE = re.compile(
    r"(築古|ボロ|空き家).*(アパート|AP|マンション一棟)", re.I
)
LEGACY_AP_ALT = re.compile(
    r"(アパート|AP|マンション一棟).*(築古|ボロ|空き家)", re.I
)
DEFAULT_E2E_MARKER = "E2E-GROK-KURASHIFT"


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.is_file():
        return {}
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}


def is_legacy_ap_text(text: str) -> bool:
    return bool(LEGACY_AP_RE.search(text) or LEGACY_AP_ALT.search(text))


def should_skip_low_score_auto_pass(
    text: str, score: float, *, city_hints: list[str], min_score: float = 2.0
) -> bool:
    """築古一棟AP + 東海エリア + score 下限なら low_score auto_pass をスキップ。"""
    cfg = load_config()
    ingest = cfg.get("ingest") or {}
    if not ingest.get("legacy_ap_skip_low_score_auto_pass", True):
        return False
    if score >= min_score:
        return False
    if not is_legacy_ap_text(text):
        return False
    return any(c in text for c in city_hints)


def sj_of(deal: dict[str, Any]) -> dict[str, Any]:
    sj = deal.get("summary_json")
    return sj if isinstance(sj, dict) else {}


def grok_of(deal: dict[str, Any]) -> dict[str, Any]:
    g = sj_of(deal).get("grok")
    return g if isinstance(g, dict) else {}


def parse_email_from_deal(deal: dict[str, Any]) -> str:
    try:
        from jarvis_kurashift_re_inquiry_channel import classify_inquiry_channel

        ch = classify_inquiry_channel(deal)
        if ch.get("channel") in ("agent_email", "grok_handoff") and ch.get("to"):
            return str(ch["to"])
    except Exception:
        pass
    sj = deal.get("summary_json") if isinstance(deal.get("summary_json"), dict) else {}
    from_raw = str(sj.get("from") or "")
    if not from_raw.strip():
        return ""
    m = re.search(r"<([^>]+)>", from_raw)
    return (m.group(1) if m else from_raw).strip()


def is_production_inquiry_deal(
    deal: dict[str, Any], cfg: dict[str, Any] | None = None
) -> bool:
    """Tier2 等 — E2E fixture を除外（本番候補のみ）。"""
    cfg = cfg or load_config()
    pf = cfg.get("production_filter") or {}
    title_subs = pf.get("exclude_title_substrings") or [DEFAULT_E2E_MARKER]
    e2e_markers = pf.get("exclude_e2e_markers") or [DEFAULT_E2E_MARKER]

    title = str(deal.get("title") or "")
    for sub in title_subs:
        if sub and sub in title:
            return False

    sj = sj_of(deal)
    grok = grok_of(deal) or {}
    blob = "\n".join(
        [
            title,
            str(sj.get("e2e") or ""),
            str(sj.get("report_id") or ""),
            str(grok.get("e2e") or ""),
            str(grok.get("report_id") or ""),
        ]
    )
    for marker in e2e_markers:
        if marker and marker in blob:
            return False
    return True


def inquiry_status(deal: dict[str, Any]) -> str:
    if deal.get("inquiry_status"):
        return str(deal["inquiry_status"])
    return str(sj_of(deal).get("inquiry_status") or "none")


def score_of(deal: dict[str, Any]) -> float:
    try:
        return float(deal.get("match_score") or 0)
    except (TypeError, ValueError):
        return 0.0


def _channel_of(deal: dict[str, Any]) -> dict[str, str]:
    from jarvis_kurashift_re_inquiry_channel import classify_inquiry_channel

    return classify_inquiry_channel(deal)


def evaluate_inquiry_candidate(
    deal: dict[str, Any], cfg: dict[str, Any] | None = None
) -> dict[str, Any]:
    cfg = cfg or load_config()
    tiers = cfg.get("tiers") or {}
    overrides = cfg.get("inquiry_candidate_overrides") or {}
    t0 = tiers.get("tier0_exclude_inquiry_status") or [
        "sending",
        "awaiting_reply",
        "awaiting_grok",
        "has_reply",
    ]
    t1 = tiers.get("tier1_candidate") or {}
    t2 = tiers.get("tier2_daily_queue") or {}
    t3 = tiers.get("tier3_auto_send") or {}

    inq = inquiry_status(deal)
    reasons: list[str] = []
    badges: list[str] = []
    ch = _channel_of(deal)
    channel = str(ch.get("channel") or "")
    has_to = bool(ch.get("to") and "@" in str(ch.get("to")))

    def _base() -> dict[str, Any]:
        return {
            "has_to": has_to,
            "inquiry_channel": channel or None,
        }

    if inq in t0:
        return {
            "tier": 0,
            "tier1": False,
            "tier2": False,
            "tier3": False,
            "can_quick_send": False,
            "revive": False,
            "badges": badges,
            "reasons": [f"inquiry_status={inq}"],
            **_base(),
        }

    allowed_inq = t1.get("require_inquiry_status") or ["none", "draft", ""]
    if inq not in allowed_inq:
        return {
            "tier": None,
            "tier1": False,
            "tier2": False,
            "tier3": False,
            "can_quick_send": False,
            "revive": False,
            "badges": badges,
            "reasons": [f"inquiry_not_ready={inq}"],
            **_base(),
        }

    if channel == "not_applicable":
        badges.append("問合せ対象外")
        return {
            "tier": None,
            "tier1": False,
            "tier2": False,
            "tier3": False,
            "can_quick_send": False,
            "revive": False,
            "badges": badges,
            "reasons": [f"channel={ch.get('reason') or 'not_applicable'}"],
            **_base(),
        }

    title = str(deal.get("title") or "")
    if any(m in title for m in ("※受付終了※", "＊受付終了＊", "*受付終了*")):
        badges.append("受付終了")
        return {
            "tier": None,
            "tier1": False,
            "tier2": False,
            "tier3": False,
            "can_quick_send": False,
            "revive": False,
            "badges": badges,
            "reasons": ["uketsuke_shuryo"],
            **_base(),
        }

    grok = grok_of(deal)
    listen = str(grok.get("listen_value") or "")
    listen_vals = overrides.get("grok_listen_values") or ["聞く", "保留"]
    grok_override = bool(listen and listen in listen_vals)

    revive = (
        deal.get("status") == "passed"
        and overrides.get("revive_passed_status")
        and grok_override
    )
    if revive:
        badges.append("再検討")

    reason = str(sj_of(deal).get("auto_pass_reason") or "")
    excluded = overrides.get("exclude_auto_pass_reasons") or []
    if reason in excluded and not grok_override:
        return {
            "tier": None,
            "tier1": False,
            "tier2": False,
            "tier3": False,
            "can_quick_send": False,
            "revive": False,
            "badges": badges,
            "reasons": [f"auto_pass={reason}"],
            **_base(),
        }

    st = str(deal.get("status") or "")
    status_ok = st in ("info", "viewing") or (
        revive and overrides.get("revive_passed_status")
    )
    if not status_ok:
        return {
            "tier": None,
            "tier1": False,
            "tier2": False,
            "tier3": False,
            "can_quick_send": False,
            "revive": revive,
            "badges": badges,
            "reasons": [f"status={st}"],
            **_base(),
        }

    min1 = float(t1.get("min_score") or 2.0)
    listen_t1 = t1.get("grok_listen_values") or ["聞く", "保留"]
    score_ok = score_of(deal) >= min1
    listen_ok = bool(listen and listen in listen_t1)
    if not score_ok and not listen_ok:
        return {
            "tier": None,
            "tier1": False,
            "tier2": False,
            "tier3": False,
            "can_quick_send": False,
            "revive": revive,
            "badges": badges,
            "reasons": ["score/listen below tier1"],
            **_base(),
        }

    if score_ok:
        reasons.append(f"score>={min1}")
    if listen_ok:
        reasons.append(f"listen={listen}")

    hazard = str(grok.get("hazard_eval") or "")
    land100 = str(grok.get("land100") or "")

    tier2 = (
        listen == str(t2.get("grok_listen") or "聞く")
        and score_of(deal) >= float(t2.get("min_score") or 5.0)
        and hazard != str(t2.get("hazard_eval_not") or "除外")
    )
    tier3_enabled = bool((cfg.get("tier3_auto_send") or {}).get("enabled"))
    tier3 = (
        tier3_enabled
        and listen == str(t3.get("grok_listen") or "聞く")
        and score_of(deal) >= float(t3.get("min_score") or 7.0)
        and hazard == str(t3.get("hazard_eval") or "OK")
        and land100 != str(t3.get("land100_not") or "見送り")
    )
    if channel == "grok_handoff":
        badges.append("Grok依頼")
    elif channel == "agent_email":
        badges.append("メール問合せ")
    if tier2:
        badges.append("送信待ち")
    if tier3:
        badges.append("自動可")

    tier_num: int | None = 3 if tier3 else 2 if tier2 else 1

    return {
        "tier": tier_num,
        "tier1": True,
        "tier2": tier2,
        "tier3": tier3,
        "can_quick_send": True,
        "revive": revive,
        "badges": badges,
        "reasons": reasons,
        **_base(),
    }


def inquiry_tier_hint(deal: dict[str, Any]) -> int | None:
    ev = evaluate_inquiry_candidate(deal)
    t = ev.get("tier")
    if t in (1, 2, 3):
        return int(t)
    return None


def jst_day_start_iso() -> str:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    now = datetime.now(ZoneInfo("Asia/Tokyo"))
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start.isoformat()


def count_today_inquiry_sends(sb: Any) -> int:
    since = jst_day_start_iso()
    r = (
        sb.table("kurashift_jobs")
        .select("id", count="exact")
        .eq("job_type", "re_deal_inquiry_send")
        .in_("status", ["queued", "running", "succeeded"])
        .gte("created_at", since)
        .execute()
    )
    return int(getattr(r, "count", None) or 0)


def tier2_queue_summary(sb: Any, cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Tier2 日次キュー（digest / CLI 用。TS reInquiryTier2Queue と同等ロジック）。"""
    cfg = cfg or load_config()
    t2 = (cfg.get("tiers") or {}).get("tier2_daily_queue") or {}
    enabled = bool(t2.get("enabled"))
    daily_cap = int(cfg.get("daily_send_cap") or 5)
    sent_today = count_today_inquiry_sends(sb)
    remaining = max(0, daily_cap - sent_today)

    base = {
        "enabled": enabled,
        "daily_cap": daily_cap,
        "sent_today": sent_today,
        "remaining": remaining,
        "queue_count": 0,
        "queue_titles": [],
    }
    if not enabled:
        return base

    rows = (
        sb.table("kurashift_re_deals")
        .select("id, title, status, match_score, area, inquiry_status, summary_json")
        .in_("status", ["info", "viewing"])
        .order("match_score", desc=True)
        .limit(120)
        .execute()
    ).data or []

    queue: list[dict[str, Any]] = []
    for d in rows:
        if not is_production_inquiry_deal(d, cfg):
            continue
        ev = evaluate_inquiry_candidate(d, cfg)
        if not ev.get("tier2") or not ev.get("can_quick_send"):
            continue
        if "@" not in parse_email_from_deal(d):
            continue
        queue.append(d)

    queue.sort(key=lambda x: float(x.get("match_score") or 0), reverse=True)
    capped = queue[:remaining]
    base["queue_count"] = len(capped)
    base["queue_titles"] = [str(d.get("title") or "")[:50] for d in capped[:5]]
    return base


def format_tier2_digest_block(summary: dict[str, Any]) -> list[str]:
    if not summary.get("enabled"):
        return []
    lines = [
        f"- Tier2 送信待ち: {summary.get('queue_count', 0)}件 "
        f"（本日 {summary.get('sent_today', 0)}/{summary.get('daily_cap', 5)} · "
        f"残り {summary.get('remaining', 0)}）",
    ]
    for t in summary.get("queue_titles") or []:
        if t:
            lines.append(f"  · {t}")
    if summary.get("queue_count", 0) > 0:
        lines.append("- 次: KURASHIFT /realestate/deals/tier2 で一括確認")
    return lines


def sb_client() -> Any:
    url = os.environ.get("JARVIS_SUPABASE_URL")
    key = os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY が必要です")
    from supabase import create_client

    return create_client(url, key)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="全 deals を Tier 分類")
    ap.add_argument("--deal-id", help="1件評価")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    cfg = load_config()

    if args.deal_id:
        sb = sb_client()
        row = (
            sb.table("kurashift_re_deals")
            .select("*")
            .eq("id", args.deal_id)
            .maybe_single()
            .execute()
        )
        deal = row.data
        if not deal:
            print(f"not found: {args.deal_id}", file=sys.stderr)
            return 1
        ev = evaluate_inquiry_candidate(deal, cfg)
        if args.json:
            print(json.dumps(ev, ensure_ascii=False, indent=2))
        else:
            print(f"tier={ev.get('tier')} tier1={ev.get('tier1')} badges={ev.get('badges')}")
            print(f"  reasons: {ev.get('reasons')}")
        return 0

    if args.dry_run:
        sb = sb_client()
        rows = (
            sb.table("kurashift_re_deals")
            .select("id, title, status, match_score, inquiry_status, summary_json")
            .order("match_score", desc=True)
            .limit(80)
            .execute()
        ).data or []
        counts: dict[Any, int] = {1: 0, 2: 0, 3: 0, None: 0, 0: 0}
        print("# inquiry tier dry-run")
        for d in rows:
            ev = evaluate_inquiry_candidate(d, cfg)
            t = ev.get("tier")
            key = t if t in counts else None
            counts[key] = counts.get(key, 0) + 1
            if ev.get("tier1"):
                title = str(d.get("title") or "")[:50]
                print(
                    f"  T{t} [{d.get('status')}] score={d.get('match_score')} "
                    f"{title} badges={ev.get('badges')}"
                )
        t1 = counts.get(1, 0) + counts.get(2, 0) + counts.get(3, 0)
        print(
            f"# summary tier1={t1} t2={counts.get(2, 0)} t3={counts.get(3, 0)} "
            f"excluded={counts.get(None, 0) + counts.get(0, 0)}"
        )
        return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
