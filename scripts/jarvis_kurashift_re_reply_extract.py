#!/usr/bin/env python3
"""KURASHIFT — 問合せ返信から調査シート項目を抽出（suggested）。

正本フィールド: config/kurashift_re_research_fields.yaml
保存先: kurashift_re_deal_field_values（verified は上書きしない）

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_re_reply_extract.py --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_re_reply_extract.py --deal-id <uuid>
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_re_reply_extract.py --apply
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_re_reply_extract.py --apply --emit-grok-mail-draft
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[1]
FIELDS_YAML = REPO / "config" / "kurashift_re_research_fields.yaml"
DRAFT_DIR = REPO / ".jarvis_state" / "kurashift_viewing_judgment_drafts"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sb_client() -> Any:
    url = os.environ.get("JARVIS_SUPABASE_URL")
    key = os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY が必要です")
    from supabase import create_client

    return create_client(url, key)


def load_fields_cfg() -> dict[str, Any]:
    return yaml.safe_load(FIELDS_YAML.read_text(encoding="utf-8")) or {}


def sj_of(deal: dict[str, Any]) -> dict[str, Any]:
    sj = deal.get("summary_json")
    return sj if isinstance(sj, dict) else {}


def grok_of(deal: dict[str, Any]) -> dict[str, Any]:
    g = sj_of(deal).get("grok")
    return g if isinstance(g, dict) else {}


def list_inbound_bodies(sb: Any, deal_id: str) -> list[dict[str, Any]]:
    try:
        r = (
            sb.table("kurashift_re_deal_messages")
            .select("id, direction, kind, subject, body_text, gmail_id, occurred_at")
            .eq("deal_id", deal_id)
            .eq("direction", "inbound")
            .order("occurred_at", desc=True)
            .limit(20)
            .execute()
        )
        return list(r.data or [])
    except Exception as e:
        print(f"# messages {deal_id}: {type(e).__name__}: {e}", file=sys.stderr)
        return []


def building_year_to_age(year_s: str) -> str | None:
    try:
        y = int(year_s)
        age = datetime.now().year - y
        if 0 <= age <= 120:
            return str(age)
    except Exception:
        return None
    return None


def apply_extract(
    text: str, rules: list[dict[str, Any]]
) -> tuple[str | None, str | None, float]:
    """Return (value, excerpt, confidence 0-1)."""
    if not text:
        return None, None, 0.0
    for rule in rules or []:
        pat = rule.get("pattern") or ""
        if not pat:
            continue
        try:
            m = re.search(pat, text, flags=re.MULTILINE | re.IGNORECASE)
        except re.error as e:
            print(f"# bad pattern {pat!r}: {e}", file=sys.stderr)
            continue
        if not m:
            continue
        g = int(rule.get("group") or 1)
        try:
            raw = m.group(0) if g == 0 else m.group(g)
        except IndexError:
            raw = m.group(0)
        raw = (raw or "").strip()
        transform = rule.get("transform")
        if transform == "building_year_to_age":
            converted = building_year_to_age(raw)
            if not converted:
                continue
            raw = converted
        mapping = rule.get("map") or {}
        if mapping and raw in mapping:
            raw = str(mapping[raw])
        excerpt = m.group(0)[:200]
        return raw, excerpt, 0.8
    return None, None, 0.0


def resolve_auto_source(deal: dict[str, Any], source: str) -> Any:
    if source == "deal.title":
        return deal.get("title")
    if source == "deal.price_man":
        return deal.get("price_man") or sj_of(deal).get("price_man")
    if source == "deal.structure":
        return deal.get("structure") or sj_of(deal).get("structure")
    grok = grok_of(deal)
    if source == "grok.parking":
        return grok.get("parking")
    if source == "grok.route_price_tsubo":
        return grok.get("route_price_tsubo") or grok.get("route_price")
    if source == "grok.land100":
        return grok.get("land100")
    if source == "grok.hazard_flood":
        return grok.get("hazard_flood") or (grok.get("hazard") or {}).get("flood")
    if source == "grok.hazard_tsunami":
        return grok.get("hazard_tsunami") or (grok.get("hazard") or {}).get("tsunami")
    if source == "grok.hazard_landslide":
        return grok.get("hazard_landslide") or (grok.get("hazard") or {}).get("landslide")
    return None


def existing_field_status(sb: Any, deal_id: str, field_id: str) -> str | None:
    try:
        r = (
            sb.table("kurashift_re_deal_field_values")
            .select("status")
            .eq("deal_id", deal_id)
            .eq("field_id", field_id)
            .limit(1)
            .execute()
        )
        rows = r.data or []
        if rows:
            return str(rows[0].get("status") or "")
    except Exception as e:
        print(f"# field status: {type(e).__name__}: {e}", file=sys.stderr)
    return None


def upsert_field(
    sb: Any,
    *,
    deal_id: str,
    field_id: str,
    value: Any,
    source_type: str,
    source_ref: str | None,
    source_excerpt: str | None,
    value_type: str,
    dry_run: bool,
) -> str:
    status = existing_field_status(sb, deal_id, field_id)
    if status == "verified":
        return "skip_verified"
    value_text: str | None = None
    value_number: float | None = None
    if value is None or value == "":
        return "skip_empty"
    if value_type == "number":
        try:
            value_number = float(str(value).replace(",", "").replace("万円", "").strip())
            value_text = str(value)
        except Exception:
            value_text = str(value)
    else:
        value_text = str(value)

    row = {
        "deal_id": deal_id,
        "field_id": field_id,
        "value_text": value_text,
        "value_number": value_number,
        "source_type": source_type,
        "source_ref": source_ref,
        "source_excerpt": (source_excerpt or "")[:500] or None,
        "confidence": "medium",
        "status": "suggested",
        "updated_at": now_iso(),
    }
    if dry_run:
        print(f"  dry-run upsert {field_id}={value_text!r} src={source_type}")
        return "dry_run"
    try:
        sb.table("kurashift_re_deal_field_values").upsert(
            row, on_conflict="deal_id,field_id"
        ).execute()
        return "upserted"
    except Exception as e:
        print(f"# upsert {field_id}: {type(e).__name__}: {e}", file=sys.stderr)
        return "error"


def extract_deal(
    sb: Any,
    deal: dict[str, Any],
    cfg: dict[str, Any],
    *,
    dry_run: bool,
) -> dict[str, Any]:
    deal_id = str(deal["id"])
    fields = cfg.get("fields") or []
    msgs = list_inbound_bodies(sb, deal_id)
    combined = "\n\n".join(
        f"{m.get('subject') or ''}\n{m.get('body_text') or ''}" for m in msgs
    )
    latest_ref = None
    if msgs:
        latest_ref = str(msgs[0].get("gmail_id") or msgs[0].get("id") or "")

    stats = {"upserted": 0, "skip_verified": 0, "skip_empty": 0, "dry_run": 0, "error": 0}
    extracted: dict[str, Any] = {}

    for fdef in fields:
        fid = str(fdef.get("id") or "")
        if not fid:
            continue
        tier = str(fdef.get("tier") or "")
        vtype = str(fdef.get("value_type") or "text")
        value = None
        source_type = "manual"
        excerpt = None
        ref = None

        if tier == "auto" and fdef.get("source"):
            value = resolve_auto_source(deal, str(fdef["source"]))
            source_type = "deal" if str(fdef["source"]).startswith("deal.") else "grok"
            ref = str(fdef["source"])
        if (value is None or value == "") and fdef.get("extract") and combined:
            value, excerpt, _ = apply_extract(combined, list(fdef.get("extract") or []))
            if value is not None:
                source_type = "inbound_mail"
                ref = latest_ref

        if tier in ("manual", "research") and value is None:
            continue

        r = upsert_field(
            sb,
            deal_id=deal_id,
            field_id=fid,
            value=value,
            source_type=source_type,
            source_ref=ref,
            source_excerpt=excerpt,
            value_type=vtype,
            dry_run=dry_run,
        )
        stats[r] = stats.get(r, 0) + 1
        if r in ("upserted", "dry_run") and value is not None:
            extracted[fid] = value

    return {
        "deal_id": deal_id,
        "title": deal.get("title"),
        "inbound_msgs": len(msgs),
        "stats": stats,
        "extracted": extracted,
    }


def emit_grok_mail_draft(deal: dict[str, Any], result: dict[str, Any]) -> Path:
    """Write a draft for [Grok内見判断] — send is manual / separate path."""
    DRAFT_DIR.mkdir(parents=True, exist_ok=True)
    deal_id = str(deal["id"])
    path = DRAFT_DIR / f"{deal_id}.md"
    extr = result.get("extracted") or {}
    lines = [
        f"件名: [Grok内見判断] {deal.get('title') or deal_id}",
        "",
        "（estate → 自分宛。Grok が拾って内見: 行く|保留|見送り を返す）",
        "",
        f"deal_id: {deal_id}",
        f"title: {deal.get('title')}",
        f"area: {deal.get('area')}",
        f"match_score: {deal.get('match_score')}",
        f"inquiry_status: {deal.get('inquiry_status') or sj_of(deal).get('inquiry_status')}",
        "",
        "## 抽出（suggested）",
    ]
    for k, v in extr.items():
        lines.append(f"- {k}: {v}")
    if not extr:
        lines.append("- （抽出なし — 返信本文を確認）")
    grok = grok_of(deal)
    lines.extend(
        [
            "",
            "## 既存 Grok 調査メモ",
            f"- listen_value: {grok.get('listen_value')}",
            f"- hazard_eval: {grok.get('hazard_eval')}",
            f"- land100: {grok.get('land100')}",
            "",
            "## 依頼",
            "返信内容と上記を踏まえ、内見に行く価値を判定してください。",
            "出力ラベル: `内見: 行く|保留|見送り`（1行）＋理由3点以内。",
            "",
            f"generated_at: {now_iso()}",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description="KURASHIFT reply → research fields extract")
    ap.add_argument("--deal-id", help="単一 deal")
    ap.add_argument("--apply", action="store_true", help="DB に upsert（省略時は dry-run）")
    ap.add_argument("--dry-run", action="store_true", help="明示 dry-run")
    ap.add_argument(
        "--emit-grok-mail-draft",
        action="store_true",
        help="[Grok内見判断] 下書きを .jarvis_state に書く",
    )
    ap.add_argument(
        "--has-reply-only",
        action="store_true",
        default=True,
        help="inquiry_status=has_reply のみ（既定）",
    )
    ap.add_argument("--all-deals", action="store_true", help="has_reply 限定を外す")
    args = ap.parse_args()
    dry_run = not args.apply or args.dry_run

    cfg = load_fields_cfg()
    sb = sb_client()
    q = sb.table("kurashift_re_deals").select("*").limit(200)
    if args.deal_id:
        q = q.eq("id", args.deal_id)
    elif not args.all_deals:
        q = q.eq("inquiry_status", "has_reply")
    deals = q.execute().data or []
    if not deals:
        print("📎 reply_extract: 対象 deal 0件")
        return 0

    print(f"📎 reply_extract: {len(deals)} deals dry_run={dry_run}")
    summaries = []
    for deal in deals:
        r = extract_deal(sb, deal, cfg, dry_run=dry_run)
        summaries.append(r)
        print(
            f"- {r['title'][:40] if r.get('title') else r['deal_id']}: "
            f"in={r['inbound_msgs']} {r['stats']}"
        )
        if args.emit_grok_mail_draft:
            p = emit_grok_mail_draft(deal, r)
            print(f"  draft: {p}")

    print(f"KURASHIFT_RESULT:{json.dumps({'n': len(summaries), 'dry_run': dry_run}, ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
