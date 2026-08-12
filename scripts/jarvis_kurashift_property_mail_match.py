#!/usr/bin/env python3
"""物件紹介メール → kurashift_re_deals 候補（送信なし・dry-run 既定）。

使用アカウント: admin（主） + estate（補完） / Gmail API

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_property_mail_match.py --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_property_mail_match.py --apply
"""
from __future__ import annotations

import argparse
import base64
import os
import re
import sys
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

REPO = Path(__file__).resolve().parents[1]
MANUAL = REPO / "215_kamiooya" / "C1_cursor" / "1b_Cursorマニュアル"
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
]

# 広めに拾い、criteria でスコア
GMAIL_QUERY = (
    "(物件 OR 戸建 OR 戸建て OR 収益物件 OR 利回り OR 土地値 OR 不動産投資 OR 紹介)"
    " newer_than:{days}d -unsubscribe"
)

SUBJECT_NOISE = (
    "号外",
    "ダイジェスト",
    "税理士",
    "平均年収",
    "夕方メール",
    "ワンルーム投資やめとけ",
    "成果報告",
)

CITY_HINTS = [
    "岡崎",
    "碧南",
    "知多",
    "安城",
    "豊田",
    "瀬戸",
    "春日井",
    "犬山",
    "一宮",
    "各務原",
    "岐阜",
    "大垣",
    "桑名",
    "四日市",
    "津市",
    "鈴鹿",
    "愛知",
    "岐阜県",
    "三重",
    "名古屋",
]


def sb_client() -> Any:
    url = os.environ.get("JARVIS_SUPABASE_URL")
    key = os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY が必要です")
    from supabase import create_client

    return create_client(url, key)


def gmail_service(token_name: str):
    path = MANUAL / token_name
    if not path.is_file():
        raise FileNotFoundError(path)
    creds = Credentials.from_authorized_user_file(str(path), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def decode_body(payload: dict) -> str:
    parts = [payload]
    texts: list[str] = []
    while parts:
        p = parts.pop()
        body = p.get("body") or {}
        data = body.get("data")
        mime = (p.get("mimeType") or "").lower()
        if data and ("text/plain" in mime or not p.get("parts")):
            try:
                texts.append(base64.urlsafe_b64decode(data).decode("utf-8", "replace"))
            except Exception:
                pass
        for ch in p.get("parts") or []:
            parts.append(ch)
    return "\n".join(texts)[:8000]


def header_map(headers: list[dict]) -> dict[str, str]:
    out: dict[str, str] = {}
    for h in headers or []:
        out[(h.get("name") or "").lower()] = h.get("value") or ""
    return out


def score_text(text: str, criteria_blob: str) -> tuple[float, list[str]]:
    blob = text + "\n" + criteria_blob
    hits: list[str] = []
    score = 0.0
    for city in CITY_HINTS:
        if city in text:
            hits.append(city)
            score += 2.0 if city in criteria_blob or city in ("愛知", "岐阜", "三重") else 1.0
    if re.search(r"戸建|戸建て", text):
        hits.append("戸建")
        score += 3.0
    if re.search(r"利回り\s*[１２3-9０-９\d]", text) or "利回り" in text:
        hits.append("利回り")
        score += 1.5
    if "万円" in text or re.search(r"\d+\s*万", text):
        score += 0.5
    if "海沿" in text and "除外" not in criteria_blob:
        score -= 0.5
    return score, hits


def load_criteria_blob(sb: Any) -> str:
    ver = (
        sb.table("kurashift_buy_plan_versions")
        .select("id")
        .eq("is_canonical", True)
        .limit(1)
        .execute()
    )
    vid = (ver.data or [{}])[0].get("id")
    if not vid:
        return ""
    rows = (
        sb.table("kurashift_buy_plan_criteria")
        .select("raw_text")
        .eq("version_id", vid)
        .execute()
    )
    return "\n".join((r.get("raw_text") or "") for r in (rows.data or []))


def fetch_account(
    token_name: str,
    source: str,
    *,
    days: int,
    limit: int,
    criteria_blob: str,
) -> list[dict[str, Any]]:
    svc = gmail_service(token_name)
    q = GMAIL_QUERY.format(days=days)
    resp = (
        svc.users()
        .messages()
        .list(userId="me", q=q, maxResults=min(limit, 50))
        .execute()
    )
    out: list[dict[str, Any]] = []
    for m in resp.get("messages") or []:
        full = (
            svc.users()
            .messages()
            .get(userId="me", id=m["id"], format="full")
            .execute()
        )
        hm = header_map(full.get("payload", {}).get("headers") or [])
        subject = hm.get("subject") or "(無題)"
        if any(n in subject for n in SUBJECT_NOISE):
            continue
        body = decode_body(full.get("payload") or {})
        text = f"{subject}\n{body}"
        sc, hits = score_text(text, criteria_blob)
        if sc < 2.0:
            continue
        date_hdr = hm.get("date")
        try:
            occurred = parsedate_to_datetime(date_hdr) if date_hdr else datetime.now(timezone.utc)
            if occurred.tzinfo is None:
                occurred = occurred.replace(tzinfo=timezone.utc)
        except Exception:
            occurred = datetime.now(timezone.utc)
        area = next((c for c in CITY_HINTS if c in text and c not in ("愛知", "岐阜県", "三重")), None)
        price = None
        pm = re.search(r"(\d{2,5})\s*万", text)
        if pm:
            try:
                price = float(pm.group(1))
            except Exception:
                pass
        yld = None
        ym = re.search(r"利回り\s*[：:]?\s*(\d+(?:\.\d+)?)\s*%", text)
        if ym:
            yld = float(ym.group(1)) / 100.0
        out.append(
            {
                "title": subject[:180],
                "status": "info",
                "source": source,
                "area": area,
                "structure": "戸建" if re.search(r"戸建|戸建て", text) else None,
                "price_man": price,
                "yield_pct": yld,
                "match_score": round(sc, 2),
                "summary_json": {
                    "gmail_id": m["id"],
                    "from": hm.get("from", "")[:200],
                    "hits": hits,
                    "snippet": text[:500],
                    "account": source,
                },
                "advice_json": {},
                "first_seen_at": occurred.isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    out.sort(key=lambda x: (-(x["match_score"] or 0), x["title"]))
    return out


def existing_gmail_ids(sb: Any) -> set[str]:
    rows = (
        sb.table("kurashift_re_deals")
        .select("summary_json")
        .in_("source", ["mail_admin", "mail_estate"])
        .limit(500)
        .execute()
    )
    ids: set[str] = set()
    for r in rows.data or []:
        sj = r.get("summary_json") or {}
        gid = sj.get("gmail_id")
        if gid:
            ids.add(gid)
    return ids


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=120)
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true", help="kurashift_re_deals へ upsert")
    args = ap.parse_args()
    if not args.apply:
        args.dry_run = True

    print("使用アカウント: admin（主）+ estate（補完） / Gmail API")
    sb = sb_client()
    criteria_blob = load_criteria_blob(sb)
    candidates: list[dict[str, Any]] = []
    for token, source in (
        ("token_livingsupport.json", "mail_admin"),
        ("token_estate.json", "mail_estate"),
    ):
        try:
            part = fetch_account(
                token, source, days=args.days, limit=args.limit, criteria_blob=criteria_blob
            )
            print(f"# {source}: candidates={len(part)}")
            candidates.extend(part)
        except Exception as e:
            print(f"# {source}: FAIL {type(e).__name__}: {e}")

    # dedupe by gmail_id preferring higher score
    by_id: dict[str, dict[str, Any]] = {}
    for c in candidates:
        gid = (c.get("summary_json") or {}).get("gmail_id")
        if not gid:
            continue
        prev = by_id.get(gid)
        if not prev or (c.get("match_score") or 0) > (prev.get("match_score") or 0):
            by_id[gid] = c
    uniq = sorted(by_id.values(), key=lambda x: (-(x["match_score"] or 0), x["title"]))
    print(f"# unique={len(uniq)}")
    for c in uniq[:12]:
        print(
            f"  - [{c['match_score']}] {c['source']} {c.get('area') or '-'} {c['title'][:70]}"
        )

    if args.dry_run and not args.apply:
        print("📎 property_mail_match: dry-run（--apply で deals 反映）")
        return 0

    seen = existing_gmail_ids(sb)
    inserted = 0
    for c in uniq:
        gid = (c.get("summary_json") or {}).get("gmail_id")
        if gid in seen:
            continue
        sb.table("kurashift_re_deals").insert(c).execute()
        inserted += 1
        if gid:
            seen.add(gid)
    print(f"📎 property_mail_match: inserted={inserted} skipped_existing={len(uniq) - inserted}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
