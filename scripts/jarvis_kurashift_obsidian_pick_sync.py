#!/usr/bin/env python3
"""KURASHIFT — Obsidian ☆Real_Estate_Pick (S3需給三次・ペルソナ) 成果物を
Supabase kurashift_re_deals に同期・投影するスクリプト。

対象:
  ~/Documents/500_Obsidian_r1/01_Journaling/☆Real_Estate_Pick/*_S3.md

実行例:
  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  /Users/matsunomasaharu2/selenium_env/venv/bin/python scripts/jarvis_kurashift_obsidian_pick_sync.py
  /Users/matsunomasaharu2/selenium_env/venv/bin/python scripts/jarvis_kurashift_obsidian_pick_sync.py --apply
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[1]
OBSIDIAN_DIR = Path("/Users/matsunomasaharu2/Documents/500_Obsidian_r1/01_Journaling/☆Real_Estate_Pick")


def sb_client() -> Any:
    url = os.environ.get("JARVIS_SUPABASE_URL")
    key = os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY が必要です")
    from supabase import create_client

    return create_client(url, key)


def parse_s5_line(line: str) -> dict[str, str]:
    """年代=30代〜40代前半 / 間取り=4DK / 家賃帯=5.0-6.0万 / 駐車場=要 / 層=ファミリー を分解"""
    res: dict[str, str] = {}
    if not line:
        return res
    parts = [p.strip() for p in line.split("/") if p.strip()]
    for p in parts:
        if "=" in p:
            k, v = p.split("=", 1)
            k, v = k.strip(), v.strip()
            if "年代" in k:
                res["age"] = v
            elif "間取り" in k:
                res["layout"] = v
            elif "家賃" in k:
                res["rent_range"] = v
            elif "駐車" in k:
                res["parking"] = v
            elif "層" in k:
                res["target_class"] = v
    return res


def parse_s3_file(path: Path) -> dict[str, Any] | None:
    text = path.read_text(encoding="utf-8")
    fm_match = re.match(r"^---\n(.*?)\n---\n(.*)", text, re.DOTALL)
    if not fm_match:
        return None
    fm_text, body = fm_match.group(1), fm_match.group(2)
    try:
        fm = yaml.safe_load(fm_text) or {}
    except Exception:
        fm = {}

    if fm.get("type") != "s3_supply":
        return None

    verdict = str(fm.get("verdict") or "").strip().lower()
    address = str(fm.get("address") or "").strip()
    city = str(fm.get("city") or "").strip()
    deal_id = fm.get("deal_id")
    if deal_id:
        deal_id = str(deal_id).strip()
    s5_line = str(fm.get("s5_line") or "").strip()
    updated = str(fm.get("updated") or "").strip()

    # Verdict reason
    verdict_reason = ""
    v_m = re.search(r"判定:\s*\*\*?(\w+)\*\*?\n-\s*理由1行:\s*(.*?)(?=\n##|\Z)", body, re.DOTALL)
    if v_m:
        verdict_reason = v_m.group(2).strip()
    else:
        v_m2 = re.search(r"- 理由1行:\s*(.*?)(?=\n##|\Z)", body, re.DOTALL)
        if v_m2:
            verdict_reason = v_m2.group(1).strip()

    # Hearing questions
    questions: list[str] = []
    h_m = re.search(r"## ヒアリング確認リスト\n+(.*?)(?=\n##|\Z)", body, re.DOTALL)
    if h_m:
        for q in re.findall(r"^\d+\.\s*(.*?)$", h_m.group(1), re.MULTILINE):
            q_clean = q.strip()
            if q_clean:
                questions.append(q_clean)

    # Key attributes from bullets
    expected_rent = ""
    key_risk = ""
    portal_url = ""
    structure = ""

    rent_m = re.search(r"- 家賃:\s*([^\n]+)", body)
    if rent_m:
        expected_rent = rent_m.group(1).strip()

    risk_m = re.search(r"- 本線リスク:\s*([^\n]+)", body)
    if risk_m:
        key_risk = risk_m.group(1).strip()
    elif "メモ: がけ条例" in body:
        key_risk = "がけ条例（愛知県建築基準条例第8条・再建築制限要確認）"

    url_m = re.search(r"- (?:売|URL):\s*(https?://[^\s\n]+)", body)
    if url_m:
        portal_url = url_m.group(1).strip()

    prop_m = re.search(r"- 物件:\s*([^\n]+)", body)
    if prop_m:
        structure = prop_m.group(1).strip()
    else:
        struct_m = re.search(r"- 構造・間取り:\s*([^\n]+)", body)
        if struct_m:
            structure = struct_m.group(1).strip()

    persona = parse_s5_line(s5_line)

    verdict_labels = {
        "go": "推進（買付・内見候補）",
        "hold": "保留（内見・ヒアリング要確認）",
        "pass": "見送り",
    }

    return {
        "filename": path.name,
        "obsidian_path": f"01_Journaling/☆Real_Estate_Pick/{path.name}",
        "verdict": verdict,
        "verdict_label": verdict_labels.get(verdict, verdict.upper()),
        "verdict_reason": verdict_reason,
        "address": address,
        "city": city,
        "deal_id": deal_id,
        "s5_persona_line": s5_line,
        "persona": persona,
        "expected_rent": expected_rent,
        "key_risk": key_risk,
        "structure": structure,
        "hearing_questions": questions,
        "portal_url": portal_url,
        "updated_at": updated,
    }


def find_matching_deal(sb: Any, s3_data: dict[str, Any]) -> dict[str, Any] | None:
    deal_id = s3_data.get("deal_id")
    if deal_id:
        res = sb.table("kurashift_re_deals").select("*").eq("id", deal_id).maybe_single().execute()
        if res.data:
            return res.data

    # Match by keywords in address/filename
    addr = s3_data.get("address") or ""
    fn = s3_data.get("filename") or ""
    combined = f"{addr} {fn}"
    
    keywords: list[str] = []
    # ファイル名から日付やプレフィックスを除いた地名トークン
    parts = fn.replace(".md", "").split("_")
    for p in parts:
        if p and not re.match(r"^\d{4}-\d{2}-\d{2}$", p) and p not in ("S3", "S5", "Grok"):
            if len(p) >= 2:
                keywords.append(p)

    # 住所から町名・字名を抽出
    town_m = re.findall(r"([一-龥ぁ-んァ-ヶ]{2,}(?:町|字|丁目)?)", addr)
    for tm in town_m:
        if tm not in ("愛知県", "岐阜県", "三重県", "静岡県") and len(tm) >= 2:
            keywords.append(tm)

    # 重複除去
    keywords = list(dict.fromkeys(keywords))
    if not keywords:
        return None

    # Query deals across candidate/active statuses
    res = sb.table("kurashift_re_deals").select("*").in_("status", ["info", "viewing", "offer", "passed"]).execute()
    deals = res.data or []
    
    best_deal = None
    best_score = 0
    for d in deals:
        t = d.get("title") or ""
        score = sum(1 for kw in keywords if kw in t)
        # アクティブなものを少し優先
        if d.get("status") in ("info", "viewing"):
            score += 0.5
        if score > best_score:
            best_score = score
            best_deal = d

    if best_score >= 1.0:
        return best_deal
    return None


def sync_obsidian_picks(apply: bool = False) -> list[dict[str, Any]]:
    sb = sb_client()
    md_files = sorted(OBSIDIAN_DIR.glob("*_S3.md"))
    
    results = []
    for p in md_files:
        if "旧" in p.name:
            continue
        data = parse_s3_file(p)
        if not data:
            continue
        
        deal = find_matching_deal(sb, data)
        if not deal:
            print(f"[SKIP] No matching deal for {p.name} (addr={data['address']})")
            continue
        
        deal_id = deal["id"]
        title = deal.get("title") or ""
        print(f"[MATCH] {p.name} -> deal_id={deal_id} title={title[:40]}")
        
        sj = deal.get("summary_json") or {}
        if not isinstance(sj, dict):
            sj = {}
            
        # Update s3_investigation payload
        sj["s3_investigation"] = data
        
        # Also ensure status is 'viewing' if currently 'info'
        updates: dict[str, Any] = {
            "summary_json": sj,
        }
        if deal.get("status") == "info":
            updates["status"] = "viewing"
            
        results.append({
            "deal_id": deal_id,
            "title": title,
            "filename": p.name,
            "verdict": data["verdict"],
            "updates": updates,
        })
        
        if apply:
            sb.table("kurashift_re_deals").update(updates).eq("id", deal_id).execute()
            print(f"  -> Applied update to deal {deal_id}")
            
            # Optionally write back deal_id to obsidian file frontmatter if missing
            if not data.get("deal_id"):
                content = p.read_text(encoding="utf-8")
                new_content = re.sub(
                    r"^deal_id:.*$",
                    f"deal_id: {deal_id}",
                    content,
                    flags=re.MULTILINE,
                )
                if new_content != content:
                    p.write_text(new_content, encoding="utf-8")
                    print(f"  -> Updated frontmatter deal_id in {p.name}")

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync Obsidian ☆Real_Estate_Pick to kurashift_re_deals")
    parser.add_argument("--apply", action="store_true", help="Apply updates to Supabase")
    args = parser.parse_args()

    print(f"# Scanning Obsidian folder: {OBSIDIAN_DIR}")
    results = sync_obsidian_picks(apply=args.apply)
    print(f"# Matched & synced: {len(results)} deals (apply={args.apply})")
    for r in results:
        print(f"  - [{r['verdict'].upper()}] {r['title']} ({r['filename']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
