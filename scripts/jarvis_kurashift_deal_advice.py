#!/usr/bin/env python3
"""案件／購入条件向けに神大家ナレッジを検索し advice_json を付与。

正本候補: kamiooya-qa-web/data/knowledge.csv（ローカル）
なければ Supabase kamiooya-qa の comments（読み取り専用）

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_deal_advice.py --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_deal_advice.py --apply
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
KNOWLEDGE_CSV = REPO / "apps" / "kamiooya-qa-web" / "data" / "knowledge.csv"
WESTUDY_TEXT = Path(
    "/Users/matsunomasaharu2/Library/CloudStorage/"
    "GoogleDrive-admin@livingsupport-matsu.co.jp/マイドライブ/"
    "215_神大家_WeStudyスクレイプ/text"
)
# 融資・購入を優先して読む（容量制限）
WESTUDY_PRIORITY = (
    "最新融資情報",
    "購入・売却",
    "資金調達",
    "オススメ_苦戦エリア",
    "修繕",
)
FINANCE_HINTS = ("融資", "金利", "銀行", "借入", "属性", "審査", "頭金", "戸建", "利回り")


def sb_client() -> Any:
    url = os.environ.get("JARVIS_SUPABASE_URL")
    key = os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY が必要です")
    from supabase import create_client

    return create_client(url, key)


def tokenize(q: str) -> list[str]:
    s = q.lower()
    parts = re.split(r"[^0-9a-zA-Zぁ-んァ-ン一-龥]+", s)
    return [p for p in parts if len(p) >= 2]


def load_westudy_rows(limit: int = 6000) -> list[dict[str, str]]:
    if not WESTUDY_TEXT.is_dir():
        return []
    csvs = sorted(WESTUDY_TEXT.rglob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    # 優先ファイルを先頭に
    def rank(p: Path) -> tuple[int, float]:
        name = p.name
        for i, key in enumerate(WESTUDY_PRIORITY):
            if key in name or key in str(p.parent):
                return (i, -p.stat().st_mtime)
        return (len(WESTUDY_PRIORITY), -p.stat().st_mtime)

    csvs = sorted(csvs, key=rank)
    rows: list[dict[str, str]] = []
    for path in csvs:
        try:
            with path.open(encoding="utf-8", errors="replace", newline="") as f:
                reader = csv.DictReader(f)
                for r in reader:
                    body = (r.get("body") or r.get("コメント内容") or "").strip()
                    if len(body) < 40:
                        continue
                    rows.append(
                        {
                            "id": r.get("comment_id") or "",
                            "author": r.get("author") or "",
                            "content": body,
                            "topic": r.get("topic_title") or path.stem,
                        }
                    )
                    if len(rows) >= limit:
                        return rows
        except Exception:
            continue
    return rows


def load_knowledge_rows() -> list[dict[str, str]]:
    westudy = load_westudy_rows()
    if westudy:
        return westudy
    if not KNOWLEDGE_CSV.is_file():
        return []
    text = KNOWLEDGE_CSV.read_text(encoding="utf-8", errors="replace")
    # skip comment lines starting with #
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    if not lines:
        return []
    reader = csv.DictReader(lines)
    rows: list[dict[str, str]] = []
    for r in reader:
        content = (
            r.get("コメント内容")
            or r.get("content")
            or r.get("本文")
            or ""
        )
        if not content.strip():
            continue
        rows.append(
            {
                "id": r.get("コメントID") or r.get("id") or "",
                "author": r.get("投稿者名") or r.get("author") or "",
                "content": content.strip(),
            }
        )
        if len(rows) >= 8000:
            break
    return rows


def search(rows: list[dict[str, str]], query: str, limit: int = 5) -> list[dict[str, Any]]:
    toks = tokenize(query)
    if not toks:
        return []
    scored: list[tuple[float, dict[str, str]]] = []
    for r in rows:
        c = r["content"]
        cl = c.lower()
        score = 0.0
        for t in toks:
            if t in cl:
                score += 1.0
                if t in FINANCE_HINTS:
                    score += 1.5
        if score <= 0:
            continue
        scored.append((score, r))
    scored.sort(key=lambda x: -x[0])
    hits: list[dict[str, Any]] = []
    for score, r in scored[:limit]:
        snippet = r["content"].replace("\n", " ")[:220]
        hits.append(
            {
                "score": round(score, 2),
                "id": r["id"],
                "author": r["author"],
                "snippet": snippet,
            }
        )
    return hits


def build_query_for_deal(deal: dict[str, Any], criteria_blob: str) -> str:
    parts = [
        deal.get("area") or "",
        deal.get("structure") or "",
        deal.get("title") or "",
        "融資 戸建 利回り",
    ]
    # criteria から短いキーワード
    for line in criteria_blob.splitlines():
        if any(k in line for k in ("利回り", "戸建", "土地値", "融資", "愛知", "岐阜")):
            parts.append(line[:40])
    return " ".join(p for p in parts if p)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--limit-deals", type=int, default=30)
    args = ap.parse_args()
    if not args.apply:
        args.dry_run = True

    rows = load_knowledge_rows()
    src = "westudy_scrape" if rows and WESTUDY_TEXT.is_dir() else "knowledge.csv"
    print(f"# knowledge rows={len(rows)} source={src}")
    if not rows:
        print("# WARN: ナレッジが空。WeStudyスクレイプ CSV または knowledge.csv を確認")

    sb = sb_client()
    ver = (
        sb.table("kurashift_buy_plan_versions")
        .select("id")
        .eq("is_canonical", True)
        .limit(1)
        .execute()
    )
    vid = (ver.data or [{}])[0].get("id")
    criteria_blob = ""
    if vid:
        cr = (
            sb.table("kurashift_buy_plan_criteria")
            .select("raw_text")
            .eq("version_id", vid)
            .execute()
        )
        criteria_blob = "\n".join(r.get("raw_text") or "" for r in (cr.data or []))

    # 条件だけのベース助言（deals が空でも残す）
    base_q = "戸建 融資 利回り 愛知 岐阜 " + criteria_blob[:200]
    base_hits = search(rows, base_q, limit=5)
    print(f"# base advice hits={len(base_hits)}")
    for h in base_hits[:3]:
        print(f"  - [{h['score']}] {h['snippet'][:80]}")

    deals = (
        sb.table("kurashift_re_deals")
        .select("id, title, area, structure, status, advice_json")
        .neq("status", "archived")
        .order("updated_at", desc=True)
        .limit(args.limit_deals)
        .execute()
    )

    updated = 0
    for d in deals.data or []:
        q = build_query_for_deal(d, criteria_blob)
        hits = search(rows, q, limit=5) or base_hits
        advice = {
            "summary": hits[0]["snippet"] if hits else "該当ナレッジなし（knowledge.csv 要更新）",
            "query": q[:200],
            "hits": hits,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "westudy_scrape_or_knowledge",
        }
        print(f"# deal {d['id'][:8]}… hits={len(hits)} {d.get('title','')[:40]}")
        if args.apply:
            sb.table("kurashift_re_deals").update(
                {"advice_json": advice, "updated_at": datetime.now(timezone.utc).isoformat()}
            ).eq("id", d["id"]).execute()
            updated += 1

    # メタとして ops メモにベース助言を残さない。deals が 0 なら基準カードを1件作る
    if args.apply and not (deals.data or []) and base_hits:
        sb.table("kurashift_re_deals").insert(
            {
                "title": "【助言プレースホルダ】現行購入条件向けナレッジ",
                "status": "info",
                "source": "manual",
                "match_score": 0,
                "summary_json": {"kind": "criteria_advice_seed"},
                "advice_json": {
                    "summary": base_hits[0]["snippet"],
                    "query": base_q[:200],
                    "hits": base_hits,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "source": "westudy_scrape_or_knowledge",
                },
            }
        ).execute()
        updated += 1
        print("# seeded criteria advice deal")

    mode = "apply" if args.apply else "dry-run"
    print(f"📎 deal_advice: mode={mode} updated={updated}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
