#!/usr/bin/env python3
"""KURASHIFT Tier3 — 高スコア自動問合せ（YAML enabled 時のみ実送信）。

正本: config/kurashift_re_inquiry_auto.yaml → tier3_auto_send.enabled
有効化手順: docs/KURASHIFT_Tier3_自動送信_有効化手順.md

既定は dry-run（候補一覧のみ）。実送信は:
  --i-confirm-send かつ YAML enabled: true

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_re_tier3_auto_send.py
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_re_tier3_auto_send.py --i-confirm-send
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from jarvis_kurashift_re_inquiry import (  # noqa: E402
    build_preview,
    sb_client,
    send_inquiry,
)
from jarvis_kurashift_re_inquiry_rules import (  # noqa: E402
    evaluate_inquiry_candidate,
    load_config,
)


def _today_sent_count(sb: Any) -> int:
    try:
        r = (
            sb.table("kurashift_re_deals")
            .select("id, inquiry_sent_at, summary_json")
            .in_(
                "inquiry_status",
                ["awaiting_reply", "awaiting_grok", "has_reply", "sending"],
            )
            .limit(500)
            .execute()
        )
    except Exception:
        return 0
    today = date.today().isoformat()
    n = 0
    for d in r.data or []:
        sent = d.get("inquiry_sent_at")
        if not sent:
            sj = d.get("summary_json") if isinstance(d.get("summary_json"), dict) else {}
            sent = sj.get("inquiry_sent_at")
        if sent and str(sent)[:10] == today:
            n += 1
    return n


def list_tier3_candidates(
    sb: Any, cfg: dict[str, Any]
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    r = (
        sb.table("kurashift_re_deals")
        .select("*")
        .in_("status", ["info", "viewing", "passed"])
        .limit(300)
        .execute()
    )
    out: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for deal in r.data or []:
        ev = evaluate_inquiry_candidate(deal, cfg)
        # enabled 前でも候補一覧できるよう eligible を見る
        if ev.get("tier3_eligible") or ev.get("tier3"):
            out.append((deal, ev))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Tier3 auto inquiry (gated by YAML)")
    ap.add_argument(
        "--i-confirm-send",
        action="store_true",
        help="YAML enabled のときだけ実送信",
    )
    ap.add_argument("--limit", type=int, default=0, help="送信上限（0=日次 cap 残り）")
    ap.add_argument(
        "--dry-run-send",
        action="store_true",
        help="enabled 時も send_inquiry(dry_run=True) で止める",
    )
    args = ap.parse_args()

    cfg = load_config()
    enabled = bool((cfg.get("tier3_auto_send") or {}).get("enabled"))
    daily_cap = int(cfg.get("daily_send_cap") or 5)
    sb = sb_client()
    candidates = list_tier3_candidates(sb, cfg)
    already = _today_sent_count(sb)
    remain = max(0, daily_cap - already)
    limit = args.limit if args.limit > 0 else remain

    print("📎 Tier3 auto-send")
    print(f"- YAML enabled: {enabled}")
    print(f"- daily_cap: {daily_cap} / today_approx_sent: {already} / remain: {remain}")
    print(f"- candidates: {len(candidates)} / will_try: {min(limit, len(candidates))}")

    for deal, ev in candidates[:20]:
        print(
            f"  · {(deal.get('title') or '')[:50]} score={deal.get('match_score')} "
            f"badges={ev.get('badges')}"
        )

    if not args.i_confirm_send:
        print("候補一覧のみ（送信するには --i-confirm-send）。YAML enabled=false なら拒否。")
        print(
            "KURASHIFT_RESULT:"
            + json.dumps(
                {
                    "enabled": enabled,
                    "candidates": len(candidates),
                    "dry_run": True,
                },
                ensure_ascii=False,
            )
        )
        return 0

    if not enabled:
        print(
            "❌ tier3_auto_send.enabled が false です。"
            "docs/KURASHIFT_Tier3_自動送信_有効化手順.md を参照。"
        )
        return 2

    sent = 0
    skipped = 0
    errors = 0
    for deal, ev in candidates:
        if sent >= limit:
            break
        deal_id = str(deal["id"])
        try:
            prev = build_preview(deal)
        except Exception as e:
            print(f"  preview fail {deal_id}: {e}")
            errors += 1
            continue
        to_email = (prev.get("to") or "").strip()
        channel = prev.get("inquiry_channel") or ev.get("inquiry_channel")
        if not to_email or "@" not in to_email:
            print(f"  skip no-to: {(deal.get('title') or deal_id)[:40]}")
            skipped += 1
            continue
        dry = bool(args.dry_run_send)
        r = send_inquiry(
            sb,
            deal_id,
            to_email=to_email,
            subject=None,
            body=None,
            confirm=True,
            dry_run=dry,
            inquiry_channel=str(channel) if channel else None,
        )
        if r.get("ok"):
            if r.get("skipped"):
                skipped += 1
                print(f"  skipped {r.get('skipped')}: {(deal.get('title') or '')[:40]}")
            else:
                sent += 1
                mode = "dry" if dry else "sent"
                print(f"  {mode} → …{to_email[-12:]} {(deal.get('title') or '')[:40]}")
        else:
            errors += 1
            print(f"  fail: {r.get('error')} {(deal.get('title') or '')[:40]}")

    print(
        "KURASHIFT_RESULT:"
        + json.dumps(
            {
                "enabled": enabled,
                "sent": sent,
                "skipped": skipped,
                "errors": errors,
            },
            ensure_ascii=False,
        )
    )
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
