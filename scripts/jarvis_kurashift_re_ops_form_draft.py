#!/usr/bin/env python3
"""神大家運営相談フォーム（1906a1a5）下書き・不足チェック。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_re_ops_form_draft.py --deal-id <uuid>
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_re_ops_form_draft.py --deal-id <uuid> --apply

送信はしない（jarvis-outbound-confirm）。フォーム URL のみ案内。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[1]
FORM_YAML = REPO / "config" / "kurashift_re_ops_form_1906a1a5.yaml"
ATTACH_ROOT = REPO / ".jarvis_state" / "kurashift_re_deal_attachments"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sb_client() -> Any:
    url = os.environ.get("JARVIS_SUPABASE_URL")
    key = os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY が必要です")
    from supabase import create_client

    return create_client(url, key)


def load_form_config() -> dict[str, Any]:
    return yaml.safe_load(FORM_YAML.read_text(encoding="utf-8")) or {}


def _sj(deal: dict[str, Any]) -> dict[str, Any]:
    sj = deal.get("summary_json")
    return sj if isinstance(sj, dict) else {}


def _grok(deal: dict[str, Any]) -> dict[str, Any]:
    g = _sj(deal).get("grok")
    return g if isinstance(g, dict) else {}


def _inquiry_status(deal: dict[str, Any]) -> str:
    if deal.get("inquiry_status"):
        return str(deal["inquiry_status"])
    return str(_sj(deal).get("inquiry_status") or "none")


def _suggest_folder_name(deal: dict[str, Any]) -> str:
    title = str(deal.get("title") or "").strip()
    if title:
        return title[:80]
    area = str(deal.get("area") or "").strip()
    price = deal.get("price_man")
    if area and price is not None:
        return f"{area}{price}万円"
    return "（物件名を決めてDriveフォルダ名と一致させる）"


def _auto_value(field: dict[str, Any], deal: dict[str, Any], grok: dict[str, Any]) -> str | None:
    fid = field.get("id")
    src = field.get("source")
    if field.get("env"):
        for key in field["env"]:
            val = (os.environ.get(str(key)) or "").strip()
            if val:
                return val
        return None
    if src == "deal.title":
        return str(deal.get("title") or "").strip() or None
    if src == "deal.price_man":
        pm = deal.get("price_man")
        return f"{pm}万円" if pm is not None else None
    if src == "deal.yield_pct":
        y = deal.get("yield_pct")
        return f"表面利回り{y}%" if y is not None else None
    if src == "deal.structure":
        s = str(deal.get("structure") or "").strip()
        return s or None
    if src == "deal.source":
        src_val = str(deal.get("source") or "")
        if src_val in ("mail_grok", "kenbiya", "rakumachi"):
            return f"いいえ（source={src_val}。該当時のみはい）"
        return "いいえ"
    if src == "grok.land100":
        parts = []
        if grok.get("land100"):
            parts.append(str(grok["land100"]))
        if grok.get("land100_ratio"):
            parts.append(str(grok["land100_ratio"]))
        if grok.get("route_price_tsubo"):
            parts.append(f"路線価:{grok['route_price_tsubo']}")
        if grok.get("land_method"):
            parts.append(str(grok["land_method"]))
        return " / ".join(parts) if parts else None
    if src == "grok.hazard_eval":
        parts = []
        if grok.get("hazard_eval"):
            parts.append(f"HZ:{grok['hazard_eval']}")
        if grok.get("hazard_flood"):
            parts.append(f"洪水:{grok['hazard_flood']}")
        if grok.get("hazard_landslide"):
            parts.append(f"土砂:{grok['hazard_landslide']}")
        if grok.get("reason_line"):
            parts.append(str(grok["reason_line"])[:120])
        return " · ".join(parts) if parts else None
    if src == "grok.parking":
        return str(grok.get("parking") or "").strip() or None
    if fid == "property_name":
        return _suggest_folder_name(deal)
    return None


def count_attachments(deal_id: str, sb: Any) -> int:
    n = 0
    try:
        r = (
            sb.table("kurashift_re_deal_attachments")
            .select("id", count="exact")
            .eq("deal_id", deal_id)
            .execute()
        )
        n = int(getattr(r, "count", None) or 0)
    except Exception:
        pass
    local = ATTACH_ROOT / deal_id
    if local.is_dir():
        n = max(n, len(list(local.glob("*.pdf"))))
    return n


def build_form_draft(
    deal: dict[str, Any],
    *,
    attach_count: int = 0,
    form_cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = form_cfg or load_form_config()
    form_url = str(cfg.get("form_url") or "https://form.os7.biz/f/1906a1a5/")
    grok = _grok(deal)
    fields_cfg = cfg.get("fields") or []

    filled: list[dict[str, str]] = []
    missing: list[str] = []
    lines: list[str] = [
        f"📎 運営相談フォーム下書き — {deal.get('title', '')[:60]}",
        f"deal_id: {deal.get('id')}",
        f"問合せ: {_inquiry_status(deal)}",
        f"フォーム: {form_url}",
        "",
        "【自動・下書き済】",
    ]

    for f in fields_cfg:
        if not isinstance(f, dict):
            continue
        label = str(f.get("label") or f.get("id") or "")
        tier = str(f.get("tier") or "manual")
        val = None
        if tier == "auto":
            val = _auto_value(f, deal, grok)
        elif tier == "manual" and f.get("id") == "questions_for_instructor":
            val = str(f.get("default_template") or "").strip() or None

        if val:
            filled.append({"id": str(f.get("id")), "label": label, "value": val})
            lines.append(f"  · {label}: {val[:200]}")
        elif tier in ("research", "reply", "manual"):
            missing.append(label)

    if attach_count <= 0:
        missing.append("神大家個人Driveへの写真・図面格納（PDF添付0件）")
    else:
        lines.append(f"  · 添付PDF: {attach_count}件（Driveへも展開要）")

    lines.extend(["", "【要調査・要入力】"])
    for m in missing[:20]:
        lines.append(f"  ⚠ {m}")
    if len(missing) > 20:
        lines.append(f"  …他 {len(missing) - 20} 項目")

    lines.extend(
        [
            "",
            "【次の一手】",
            "1. 上記⚠を調べて記入（家賃相場・修繕試算・CF）",
            "2. 神大家個人Driveに物件フォルダ＋写真",
            f"3. フォーム入力 → 確認後送信 → {form_url}",
            "4. 809 運営回答後、内見判断",
        ]
    )

    markdown = "\n".join(lines)
    return {
        "ok": True,
        "deal_id": deal.get("id"),
        "form_url": form_url,
        "filled_count": len(filled),
        "missing_count": len(missing),
        "missing": missing,
        "filled": filled,
        "attach_count": attach_count,
        "markdown": markdown,
        "generated_at": now_iso(),
    }


def persist_draft(sb: Any, deal_id: str, draft: dict[str, Any]) -> None:
    deal = (
        sb.table("kurashift_re_deals")
        .select("summary_json")
        .eq("id", deal_id)
        .maybe_single()
        .execute()
    ).data
    if not deal:
        raise SystemExit(f"deal not found: {deal_id}")
    sj = deal.get("summary_json") if isinstance(deal.get("summary_json"), dict) else {}
    sj["ops_form_draft"] = {
        "at": draft.get("generated_at"),
        "form_url": draft.get("form_url"),
        "missing_count": draft.get("missing_count"),
        "markdown": draft.get("markdown"),
    }
    sb.table("kurashift_re_deals").update(
        {"summary_json": sj, "updated_at": now_iso()}
    ).eq("id", deal_id).execute()


def main() -> int:
    ap = argparse.ArgumentParser(description="神大家運営相談フォーム下書き")
    ap.add_argument("--deal-id", required=True)
    ap.add_argument("--apply", action="store_true", help="summary_json.ops_form_draft へ保存")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    sys.path.insert(0, str(REPO / "scripts"))
    from jarvis_kurashift_re_inquiry import get_deal  # noqa: E402

    sb = sb_client()
    deal = get_deal(sb, args.deal_id)
    attach_count = count_attachments(args.deal_id, sb)
    draft = build_form_draft(deal, attach_count=attach_count)

    print(draft["markdown"])
    if args.apply:
        persist_draft(sb, args.deal_id, draft)
        print(f"# ops_form_draft saved to deal {args.deal_id[:8]}…")

    print("KURASHIFT_RESULT:" + json.dumps(draft, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
