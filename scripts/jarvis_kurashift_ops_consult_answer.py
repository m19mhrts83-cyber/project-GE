#!/usr/bin/env python3
"""運営回答を KURASHIFT deal ＋ Notion 購入手前 DB（コメント）へ両反映。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  # ドライラン
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_ops_consult_answer.py \\
    --deal-id <uuid> --summary '内見推奨。修繕は屋根優先' --dry-run
  # 反映
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_ops_consult_answer.py \\
    --deal-id <uuid> --summary '…' --verdict '内見推奨' --apply

Notion 正本: config/notion_task_dbs.yaml → purchase_pre
（DB_物件購入検討(購入手前)。一覧はコメントで概観）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
NOTION_VERSION = "2022-06-28"
API = "https://api.notion.com/v1"
PURCHASE_PRE_DB = "25ef6bbe-5a76-80c7-be60-dd114cb0e231"


def _sb() -> Any:
    url = os.environ.get("JARVIS_SUPABASE_URL")
    key = os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY が必要です")
    from supabase import create_client

    return create_client(url, key)


def _notion_token() -> str:
    tok = (os.environ.get("NOTION_API_TOKEN") or "").strip()
    if not tok:
        raise SystemExit("NOTION_API_TOKEN が必要です")
    return tok


def _notion(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{API}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {_notion_token()}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Notion API {e.code} {path}: {err[:400]}") from e


def _sj(deal: dict[str, Any]) -> dict[str, Any]:
    raw = deal.get("summary_json")
    return raw if isinstance(raw, dict) else {}


def _strip_grok(title: str) -> str:
    return re.sub(r"^\[Grok調査\]\s*", "", title or "").strip()


def _prop_title(name: str) -> dict[str, Any]:
    return {"title": [{"type": "text", "text": {"content": name[:2000]}}]}


def _prop_rich(text: str) -> dict[str, Any]:
    return {"rich_text": [{"type": "text", "text": {"content": (text or "")[:1900]}}]}


def _prop_num(v: Any) -> dict[str, Any] | None:
    try:
        if v is None or v == "":
            return None
        return {"number": float(v)}
    except (TypeError, ValueError):
        return None


def _prop_url(u: str) -> dict[str, Any] | None:
    u = (u or "").strip()
    if not u.startswith("http"):
        return None
    return {"url": u}


def _prop_date_today() -> dict[str, Any]:
    return {"date": {"start": datetime.now().astimezone().date().isoformat()}}


def find_notion_page(property_name: str) -> dict[str, Any] | None:
    q = _notion(
        "POST",
        f"/databases/{PURCHASE_PRE_DB}/query",
        {
            "filter": {"property": "物件名", "title": {"equals": property_name}},
            "page_size": 5,
        },
    )
    rows = q.get("results") or []
    if rows:
        return rows[0]
    # soft contains
    short = property_name[:20]
    q2 = _notion(
        "POST",
        f"/databases/{PURCHASE_PRE_DB}/query",
        {
            "filter": {"property": "物件名", "title": {"contains": short}},
            "page_size": 5,
        },
    )
    rows2 = q2.get("results") or []
    return rows2[0] if rows2 else None


def build_notion_props(deal: dict[str, Any], verdict: str | None) -> dict[str, Any]:
    sj = _sj(deal)
    ov = sj.get("ops_form_overrides") if isinstance(sj.get("ops_form_overrides"), dict) else {}
    draft = sj.get("ops_form_draft") if isinstance(sj.get("ops_form_draft"), dict) else {}
    filled = {
        str(x.get("id")): str(x.get("value") or "")
        for x in (draft.get("filled") or [])
        if isinstance(x, dict) and x.get("id")
    }

    def g(*keys: str) -> str:
        for k in keys:
            if ov.get(k):
                return str(ov[k])
            if filled.get(k):
                return str(filled[k])
        return ""

    name = g("property_name") or _strip_grok(str(deal.get("title") or "")) or "（無題）"
    props: dict[str, Any] = {
        "物件名": _prop_title(name),
        "日付": _prop_date_today(),
    }
    if verdict:
        props["評価結果"] = _prop_rich(verdict)
    addr = g("nearest_station")  # fallback only
    # prefer s3 address
    s3 = sj.get("s3_investigation") if isinstance(sj.get("s3_investigation"), dict) else {}
    if s3.get("address"):
        props["物件住所"] = _prop_rich(str(s3["address"]))
    elif addr:
        props["最寄駅と駅からの徒歩分数"] = _prop_rich(addr)

    price = deal.get("price_man")
    pn = _prop_num(price)
    if pn:
        props["販売価格【万円】"] = pn

    drive = g("drive_folder")
    pu = _prop_url(drive)
    if pu:
        props["資料格納場所"] = pu

    for notion_key, src in (
        ("至急度", "urgency"),
        ("不動産に使える現在の自己資金", "self_funds"),
        ("融資依頼先・融資条件", "loan_terms"),
        ("講師に確認したいこと", "questions_for_instructor"),
        ("入居状況", "occupancy"),
        ("構造、間取り✖️部屋数", "structure_rooms"),
        ("現在の駐車場台数", "parking"),
        ("他の状況", "features_hazard"),
    ):
        val = g(src)
        if val:
            props[notion_key] = _prop_rich(val)

    purpose = g("purchase_purpose")
    if purpose.startswith("a"):
        props["購入目的"] = {"select": {"name": "a）長期所有目的（ＣＦ獲得目的）"}}
    elif purpose:
        # leave as rich in 評価 if select mismatch
        pass

    return props


def create_or_update_notion(
    deal: dict[str, Any],
    *,
    verdict: str | None,
    page_id: str | None,
) -> dict[str, Any]:
    props = build_notion_props(deal, verdict)
    name = props["物件名"]["title"][0]["text"]["content"]
    if page_id:
        page = _notion("PATCH", f"/pages/{page_id}", {"properties": props})
        return page
    existing = find_notion_page(name)
    if existing:
        page = _notion(
            "PATCH", f"/pages/{existing['id']}", {"properties": props}
        )
        return page
    page = _notion(
        "POST",
        "/pages",
        {"parent": {"database_id": PURCHASE_PRE_DB}, "properties": props},
    )
    return page


def post_comment(page_id: str, text: str) -> dict[str, Any]:
    return _notion(
        "POST",
        "/comments",
        {
            "parent": {"page_id": page_id},
            "rich_text": [{"type": "text", "text": {"content": text[:1900]}}],
        },
    )


def update_deal(
    sb: Any,
    deal_id: str,
    sj: dict[str, Any],
    *,
    summary: str,
    verdict: str | None,
    notion_page_id: str,
    notion_url: str,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    sj = dict(sj)
    sj["ops_consult_status"] = "answered"
    sj["ops_consult_answered_at"] = now
    sj["ops_consult_reply_summary"] = summary[:4000]
    if verdict:
        sj["ops_consult_verdict"] = verdict
    sj["ops_consult_notion_page_id"] = notion_page_id
    sj["ops_consult_notion_url"] = notion_url
    sb.table("kurashift_re_deals").update(
        {"summary_json": sj, "updated_at": now}
    ).eq("id", deal_id).execute()
    try:
        sb.table("kurashift_re_deal_events").insert(
            {
                "deal_id": deal_id,
                "event_type": "note",
                "from_status": "viewing",
                "to_status": "viewing",
                "actor": "jarvis",
                "summary": f"運営回答反映: {(verdict or summary)[:80]}",
                "payload": {
                    "action": "ops_consult_answered",
                    "notion_page_id": notion_page_id,
                },
            }
        ).execute()
    except Exception as e:
        print(f"# event insert skipped: {e}", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(description="運営回答 → KURASHIFT + Notion 両反映")
    ap.add_argument("--deal-id", required=True)
    ap.add_argument("--summary", default="", help="運営回答の要約（案件詳細＋コメント）")
    ap.add_argument("--verdict", default="", help="評価結果欄（例: 内見推奨 / 見送り）")
    ap.add_argument(
        "--comment",
        default="",
        help="Notion コメント本文（省略時は summary を一覧向けに整形）",
    )
    ap.add_argument("--notion-page-id", default="", help="既存行があれば指定")
    ap.add_argument(
        "--seed-awaiting",
        action="store_true",
        help="回答前に Notion 行だけ作り、deal に page_id を紐づける（status は answered にしない）",
    )
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not args.dry_run and not args.apply:
        raise SystemExit("--dry-run または --apply を指定してください")
    if args.seed_awaiting and not (args.summary or "").strip():
        args.summary = "運営相談フォーム送信済・回答待ち"
    if not (args.summary or "").strip():
        raise SystemExit("--summary が必要です（または --seed-awaiting）")

    sb = _sb()
    r = (
        sb.table("kurashift_re_deals")
        .select("id,title,status,price_man,summary_json")
        .eq("id", args.deal_id)
        .single()
        .execute()
    )
    deal = r.data
    sj = _sj(deal)
    title = _strip_grok(str(deal.get("title") or ""))
    verdict = (args.verdict or "").strip() or None
    summary = args.summary.strip()
    comment = (args.comment or "").strip() or (
        f"【運営回答】{verdict + ' — ' if verdict else ''}{summary}"
    )

    print(f"📎 運営回答両反映 — {title[:60]}")
    print(f"deal_id: {args.deal_id}")
    print(f"verdict: {verdict or '—'}")
    print(f"summary: {summary[:200]}")
    print(f"notion_db: {PURCHASE_PRE_DB}")

    if args.dry_run:
        props = build_notion_props(deal, verdict)
        print("# dry-run notion props keys:", list(props.keys()))
        print("# comment preview:", comment[:180])
        return 0

    page = create_or_update_notion(
        deal, verdict=verdict, page_id=(args.notion_page_id or None)
    )
    page_id = page["id"]
    page_url = page.get("url") or (
        f"https://app.notion.com/p/{page_id.replace('-', '')}"
    )
    cmt = post_comment(page_id, comment)
    if args.seed_awaiting:
        now = datetime.now(timezone.utc).isoformat()
        sj2 = dict(sj)
        sj2["ops_consult_notion_page_id"] = page_id
        sj2["ops_consult_notion_url"] = page_url
        sb.table("kurashift_re_deals").update(
            {"summary_json": sj2, "updated_at": now}
        ).eq("id", args.deal_id).execute()
        print("✅ KURASHIFT: Notion 行を紐づけ（回答待ちのまま）")
    else:
        update_deal(
            sb,
            args.deal_id,
            sj,
            summary=summary,
            verdict=verdict,
            notion_page_id=page_id,
            notion_url=page_url,
        )
        print("✅ KURASHIFT: ops_consult_status=answered")
    print(f"✅ Notion page: {page_url}")
    print(f"✅ Notion comment: {cmt.get('id', '')[:12]}…")
    return 0


if __name__ == "__main__":
    sys.exit(main())
