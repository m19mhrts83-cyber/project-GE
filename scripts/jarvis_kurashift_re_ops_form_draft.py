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
import re
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


def _s3(deal: dict[str, Any]) -> dict[str, Any]:
    s = _sj(deal).get("s3_investigation")
    return s if isinstance(s, dict) else {}


def _build_instructor_questions(
    deal: dict[str, Any], form_field: dict[str, Any]
) -> str | None:
    """デフォルト3点 + S3ヒアリング + 戸建固有を統合。"""
    default = str(form_field.get("default_template") or "").strip()
    s3 = _s3(deal)
    grok = _grok(deal)
    hearing = s3.get("hearing_questions") or []
    if not isinstance(hearing, list):
        hearing = []

    lines: list[str] = []
    if default:
        lines.append(default.rstrip())
    if hearing:
        lines.append("")
        lines.append("【詳細調査（S3）ヒアリング】")
        for i, q in enumerate(hearing, 1):
            q = str(q).strip()
            if q:
                lines.append(f"{i}. {q}")

    kodate_extras: list[str] = []
    building = str(grok.get("building") or s3.get("structure") or "")
    if "戸建" in str(deal.get("structure") or "") or "戸建" in building or "2棟" in str(
        deal.get("title") or ""
    ):
        if "間取り" in " ".join(str(x) for x in hearing) or "間取" in building:
            pass
        else:
            kodate_extras.append("間取り・専有・水回りが未確認の場合の修繕・家賃見立ての見方")
        if any("旧耐震" in str(x) or "1975" in str(x) or "軽量鉄骨" in str(x) for x in hearing) or (
            "旧耐震" in building or "1975" in building
        ):
            kodate_extras.append("旧耐震／軽量鉄骨戸建としての修繕目安と購入可否の数字感")
        if any("土砂" in str(x) or "ハザード" in str(x) for x in hearing) or "注意" in str(
            grok.get("hazard_eval") or ""
        ):
            kodate_extras.append("ハザード（土砂・洪水等）が内見判断にどう効くか")
        land = str(grok.get("land100_ratio") or "")
        if land:
            kodate_extras.append(f"土地値{land}の見方と、買付前に確認すべき接道・境界の有無")

    if kodate_extras:
        lines.append("")
        lines.append("【戸建固有・追加確認】")
        for x in kodate_extras:
            lines.append(f"・{x}")

    out = "\n".join(lines).strip()
    return out or (default or None)


def _reply_value(field: dict[str, Any], deal: dict[str, Any], grok: dict[str, Any]) -> str | None:
    """reply tier: Grok / S3 から埋められるものを埋める。"""
    fid = str(field.get("id") or "")
    s3 = _s3(deal)
    building = str(grok.get("building") or s3.get("structure") or "")
    if fid == "nearest_station":
        pop = str(grok.get("population_table") or "").strip()
        if pop:
            return pop.split("·")[0].strip() if "·" in pop else pop
        return None
    if fid == "building_age":
        m = re.search(r"築(\d{4})", building)
        if m:
            year = int(m.group(1))
            age = max(0, datetime.now().year - year)
            return f"築{age}年（{year}年）"
        m2 = re.search(r"(19\d{2}|20\d{2})", building)
        if m2:
            year = int(m2.group(1))
            return f"築{max(0, datetime.now().year - year)}年（{year}年）"
        return None
    if fid == "occupancy":
        if "空室" in building:
            return "空室"
        if "入居" in building or "満室" in building:
            return "入居中"
        return None
    if fid == "land_sqm":
        la = grok.get("land_area")
        return str(la).strip() if la else None
    if fid == "building_sqm":
        m = re.search(r"([\d.]+)\s*㎡", building)
        return f"{m.group(1)}㎡" if m else None
    if fid == "gas":
        # S3 / grok 本文にプロパン等があれば
        blob = f"{building} {s3.get('structure') or ''} {s3.get('verdict_reason') or ''}"
        if "プロパン" in blob or "LP" in blob:
            return "プロパンガス"
        if "都市ガス" in blob:
            return "都市ガス"
        return None
    if fid == "transaction_type":
        note = str(grok.get("inquiry_note") or _sj(deal).get("inquiry_note") or "")
        if "売主" in note or "AlbaLink" in note or "アルバ" in note:
            return "売主"
        return None
    if fid == "annual_rent" or fid == "gross_yield":
        rent = str(s3.get("expected_rent") or "").strip()
        return rent or None
    if fid == "structure_rooms":
        struct = str(deal.get("structure") or "").strip()
        persona = s3.get("persona") if isinstance(s3.get("persona"), dict) else {}
        layout = str((persona or {}).get("layout") or "")
        parts = [p for p in [struct, building[:80] if building else "", layout] if p]
        return " / ".join(parts) if parts else None
    return None


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
        yi = _sj(deal).get("yield_info")
        if isinstance(yi, dict) and yi.get("label"):
            return str(yi["label"])
        return f"表面利回り{y}%" if y is not None else None
    if src == "deal.structure":
        # structure_rooms は reply_value も試す
        rv = _reply_value({**field, "id": "structure_rooms"}, deal, grok)
        if rv:
            return rv
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
        ratio = grok.get("land100_ratio") or _sj(deal).get("land100_ratio")
        if ratio:
            parts.append(str(ratio))
        if grok.get("route_price_tsubo"):
            parts.append(f"路線価:{grok['route_price_tsubo']}")
        if grok.get("land_method"):
            parts.append(str(grok["land_method"]))
        if grok.get("land_appraisal_man"):
            parts.append(f"評価概算:{grok['land_appraisal_man']}万円")
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
    if fid == "gross_yield":
        return _reply_value({"id": "gross_yield"}, deal, grok)
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
        elif tier == "reply":
            val = _reply_value(f, deal, grok)
        elif tier == "research" and f.get("id") in ("annual_rent", "gross_yield"):
            val = _reply_value(f, deal, grok)
        elif tier == "manual" and f.get("id") == "questions_for_instructor":
            val = _build_instructor_questions(deal, f)

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
