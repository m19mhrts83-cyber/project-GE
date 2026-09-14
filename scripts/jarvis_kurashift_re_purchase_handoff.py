#!/usr/bin/env python3
"""買い進めハンドオフ — deal パックを Grok（S7融資 / S6買付）へ outbox。

  # 融資打診文面の材料（運営相談と前後可）
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_re_purchase_handoff.py \\
    --deal-id <uuid> --mode loan --apply

  # 運営回答後 → 買付交渉案
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_re_purchase_handoff.py \\
    --deal-id <uuid> --mode offer --apply

送信はしない（jarvis-outbound-confirm）。outbox → ホーク／部長 → S6/S7。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[1]
PIPELINE_YAML = REPO / "config" / "kurashift_re_purchase_pipeline.yaml"
STATE_DRIVE = REPO / ".jarvis_state" / "kamiooya_ops_drive.json"
OUTBOX_WRITE = REPO / "scripts" / "jarvis_bucho_outbox_write.py"


def sb_client() -> Any:
    url = os.environ.get("JARVIS_SUPABASE_URL")
    key = os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY が必要です")
    from supabase import create_client

    return create_client(url, key)


def load_pipeline() -> dict[str, Any]:
    return yaml.safe_load(PIPELINE_YAML.read_text(encoding="utf-8")) or {}


def stage_for_mode(mode: str) -> dict[str, Any]:
    pipe = load_pipeline()
    for st in pipe.get("stages") or []:
        if not isinstance(st, dict):
            continue
        hand = st.get("handoff") or {}
        if hand.get("mode") == mode:
            return st
    raise SystemExit(f"pipeline に mode={mode} の handoff がありません")


def _sj(deal: dict[str, Any]) -> dict[str, Any]:
    sj = deal.get("summary_json")
    return sj if isinstance(sj, dict) else {}


def drive_url_for(deal_id: str, sj: dict[str, Any]) -> str:
    ov = sj.get("ops_form_overrides") if isinstance(sj.get("ops_form_overrides"), dict) else {}
    if ov.get("drive_folder"):
        return str(ov["drive_folder"])
    if STATE_DRIVE.is_file():
        try:
            raw = json.loads(STATE_DRIVE.read_text(encoding="utf-8"))
            d = (raw.get("deals") or {}).get(deal_id) or {}
            if d.get("url"):
                return str(d["url"])
        except Exception:
            pass
    return ""


def filled_map(sj: dict[str, Any]) -> dict[str, str]:
    draft = sj.get("ops_form_draft") if isinstance(sj.get("ops_form_draft"), dict) else {}
    out: dict[str, str] = {}
    for item in draft.get("filled") or []:
        if isinstance(item, dict) and item.get("id"):
            out[str(item["id"])] = str(item.get("value") or "")
    ov = sj.get("ops_form_overrides") if isinstance(sj.get("ops_form_overrides"), dict) else {}
    for k, v in ov.items():
        if v:
            out[str(k)] = str(v)
    return out


def build_body(*, mode: str, deal: dict[str, Any], stage: dict[str, Any]) -> str:
    deal_id = str(deal.get("id") or "")
    sj = _sj(deal)
    fm = filled_map(sj)
    grok = sj.get("grok") if isinstance(sj.get("grok"), dict) else {}
    s3 = sj.get("s3_investigation") if isinstance(sj.get("s3_investigation"), dict) else {}
    drive = drive_url_for(deal_id, sj)
    paste = (stage.get("handoff") or {}).get("grok_paste") or ""

    lines = [
        "[Jarvis] 買い進めハンドオフ",
        f"mode: {mode}",
        f"deal_id: {deal_id}",
        f"title: {deal.get('title')}",
        f"area: {deal.get('area')} / price: {deal.get('price_man')}万",
        f"inquiry_status: {deal.get('inquiry_status') or sj.get('inquiry_status')}",
        f"資料Drive: {drive or '（未設定）'}",
        f"Instructions正本: {paste}",
        "",
        "## 依頼",
    ]
    if mode == "loan":
        lines += [
            "融資相談 Bot（S7）向け:",
            "1. 下記物件で融資打診メール文面を作成（送信はしない・松野確認後）",
            "2. 第一打診先の候補と不足資料を列挙",
            "3. 共同担保・支店エリアの留意があれば1行",
            "",
        ]
    else:
        lines += [
            "買付交渉 Bot（S6）向け:",
            "1. 運営回答（809）を踏まえ、内見に値するか／買付方針を整理",
            "2. 価格交渉の論点（指値幅・条件）を箇条書き",
            "3. 現地で仲介に聞くチェックリスト",
            "",
        ]

    lines.append("## 運営フォーム要約（抜粋）")
    for key in (
        "property_name",
        "list_price",
        "self_funds",
        "loan_terms",
        "annual_rent",
        "gross_yield",
        "monthly_cf",
        "land_value",
        "features_hazard",
        "questions_for_instructor",
        "transaction_type",
        "viewing_done",
    ):
        if fm.get(key):
            lines.append(f"- {key}: {fm[key][:400]}")

    if grok.get("land100_ratio") or grok.get("reason_line"):
        lines.append("")
        lines.append("## Grok要点")
        if grok.get("land100_ratio"):
            lines.append(f"- land100: {grok.get('land100_ratio')}")
        if grok.get("reason_line"):
            lines.append(f"- reason: {str(grok.get('reason_line'))[:240]}")

    if s3:
        lines.append("")
        lines.append("## S3")
        for k in ("verdict", "expected_rent", "verdict_reason"):
            if s3.get(k):
                lines.append(f"- {k}: {str(s3[k])[:200]}")

    lines += [
        "",
        "## 注意",
        "- 秘密（口座番号・PW）は書かない",
        "- 対外送信は Jarvis / 松野の確認後のみ",
        f"- パイプライン: config/kurashift_re_purchase_pipeline.yaml（{stage.get('id')}）",
    ]
    return "\n".join(lines)


def write_outbox(
    *,
    title: str,
    body: str,
    target: str,
    action: str,
    dry_run: bool,
) -> int:
    cmd = [
        sys.executable,
        str(OUTBOX_WRITE),
        "--title",
        title,
        "--body",
        body,
        "--target",
        target,
        "--action",
        action if action in (
            "memo",
            "routine",
            "ask",
            "handoff",
            "s9_precheck",
            "weather_brief",
        ) else "handoff",
        "--priority",
        "high",
    ]
    # action may not be in ACTIONS — use memo + body prefix if needed
    # Check ACTIONS by running help - safer to use memo and put action in body
    cmd = [
        sys.executable,
        str(OUTBOX_WRITE),
        "--title",
        title,
        "--body",
        f"action_hint: {action}\n\n{body}",
        "--target",
        target,
        "--action",
        "memo",
        "--priority",
        "high",
    ]
    if dry_run:
        cmd.append("--dry-run")
    return subprocess.call(cmd, cwd=str(REPO))


def main() -> int:
    ap = argparse.ArgumentParser(description="買い進め Grok ハンドオフ")
    ap.add_argument("--deal-id", required=True)
    ap.add_argument("--mode", required=True, choices=("loan", "offer"))
    ap.add_argument("--apply", action="store_true", help="outbox に書く")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    stage = stage_for_mode(args.mode)
    hand = stage.get("handoff") or {}
    sb = sb_client()
    r = (
        sb.table("kurashift_re_deals")
        .select("*")
        .eq("id", args.deal_id)
        .single()
        .execute()
    )
    deal = r.data
    if not deal:
        raise SystemExit("deal なし")

    body = build_body(mode=args.mode, deal=deal, stage=stage)
    short = str(deal.get("title") or args.deal_id)[:40]
    title = f"{'S7融資打診' if args.mode == 'loan' else 'S6買付案'}_{short}"
    target = str(hand.get("outbox_target") or "re")
    action = str(hand.get("action") or "memo")

    print(f"📎 purchase handoff mode={args.mode} target={target}")
    print(f"- title: {title}")
    if not args.apply and not args.dry_run:
        print(body)
        print("\n# --apply で outbox 書込 / --dry-run でパス確認")
        return 0

    rc = write_outbox(
        title=title,
        body=body,
        target=target,
        action=action,
        dry_run=bool(args.dry_run) or not args.apply,
    )
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
