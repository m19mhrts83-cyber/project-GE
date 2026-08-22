#!/usr/bin/env python3
"""
地場業者（Bot2 問合せ済）からの estate 返信 → Jarvis Dashboard general トリアージ。

- ブロックしない（milestone 成功系）
- kind=mail（要確認）で general レーンに載せ、DraftWorkbench で下書き・送信
- 物件紹介メールは property_mail_match と併走（KURASHIFT deals 側）

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_vendor_reply_triage.py --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_vendor_reply_triage.py --push
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_vendor_reply_triage.py --push --mark-inbound-replied

正本: config/kurashift_re_vendor_reply_template.yaml
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import os
import re
import sys
from datetime import datetime, timezone
from email.utils import parseaddr
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
MANUAL = REPO / "215_kamiooya" / "C1_cursor" / "1b_Cursorマニュアル"
TEMPLATE_PATH = REPO / "config" / "kurashift_re_vendor_reply_template.yaml"
ESTATE_MY = "matsuno.estate@gmail.com"

sys.path.insert(0, str(REPO / "scripts"))

from jarvis_kurashift_vendor_match import (  # noqa: E402
    build_match_index,
    match_vendor,
)
from jarvis_night_triage_general import (  # noqa: E402
    is_kurashift_property_mail,
    is_partner_address,
    load_partner_filters,
    resolve_contact_yaml,
)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]


def now_iso() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S%z")


def load_template() -> dict[str, Any]:
    if not TEMPLATE_PATH.is_file():
        return {"templates": {}, "settings": {}}
    return yaml.safe_load(TEMPLATE_PATH.read_text(encoding="utf-8")) or {}


def render_draft(vendor_name: str, body: str, subject: str) -> str:
    tpl_data = load_template()
    settings = tpl_data.get("settings") or {}
    templates = tpl_data.get("templates") or {}
    sig = str(settings.get("signature") or "松野真治\nmatsuno.estate@gmail.com").strip()
    blob = f"{subject}\n{body[:1200]}"
    if is_kurashift_property_mail(subject, body):
        key = "property_thanks"
    elif re.search(r"(ご質問|確認|教えて|いくら|予算|エリア|可能|でしょうか|\?)", blob):
        key = "question_ack"
    else:
        key = "generic"
    raw = str(templates.get(key) or templates.get("generic") or "")
    return (
        raw.replace("{vendor_name}", vendor_name or "ご担当者")
        .replace("{signature}", sig)
        .replace("{inquiry_summary}", body[:200].replace("\n", " "))
        .strip()
    )


def gmail_service():
    path = MANUAL / "token_estate.json"
    if not path.is_file():
        raise SystemExit(f"token_estate.json がありません: {path}")
    creds = Credentials.from_authorized_user_file(str(path), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    svc = build("gmail", "v1", credentials=creds, cache_discovery=False)
    prof = svc.users().getProfile(userId="me").execute()
    my_email = (prof.get("emailAddress") or ESTATE_MY).lower()
    return svc, my_email


def header_map(headers: list[dict]) -> dict[str, str]:
    out: dict[str, str] = {}
    for h in headers or []:
        out[(h.get("name") or "").lower()] = h.get("value") or ""
    return out


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


def parse_internal_dt(ms: str) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=JST)
    except (TypeError, ValueError):
        return None


def find_vendor_replies(
    *,
    lookback_days: int = 21,
    max_threads: int = 50,
) -> list[dict[str, Any]]:
    svc, my_email = gmail_service()
    partner_emails, partner_domains = load_partner_filters(resolve_contact_yaml())
    vindex = build_match_index()
    if not vindex:
        print("# vendor index empty (contacted/replied なし)", file=sys.stderr)
        return []

    q = f"in:inbox newer_than:{max(1, lookback_days)}d -category:promotions"
    threads: list[dict] = []
    page_token = None
    while len(threads) < max_threads:
        kwargs: dict[str, Any] = {
            "userId": "me",
            "q": q,
            "maxResults": min(50, max_threads - len(threads)),
        }
        if page_token:
            kwargs["pageToken"] = page_token
        resp = svc.users().threads().list(**kwargs).execute()
        threads.extend(resp.get("threads") or [])
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    out: list[dict[str, Any]] = []
    for th in threads[:max_threads]:
        tid = th.get("id")
        if not tid:
            continue
        full = svc.users().threads().get(userId="me", id=tid, format="full").execute()
        msgs = sorted(full.get("messages") or [], key=lambda m: int(m.get("internalDate") or 0))
        if not msgs:
            continue
        last = msgs[-1]
        payload = last.get("payload") or {}
        headers = header_map(payload.get("headers") or [])
        from_raw = headers.get("from", "")
        _, from_email = parseaddr(from_raw)
        from_email = (from_email or "").lower()
        if not from_email or from_email == my_email:
            continue
        if is_partner_address(from_email, partner_emails, partner_domains):
            continue

        subject = headers.get("subject") or "(件名なし)"
        body = decode_body(payload)
        display = from_raw.split("<")[0].strip().strip('"') or from_email
        vendor = match_vendor(
            from_email, from_display=display, subject=subject, index=vindex
        )
        if not vendor:
            continue

        dt = parse_internal_dt(str(last.get("internalDate") or "0"))
        received_at = dt.strftime("%Y/%m/%d %H:%M") if dt else ""
        mid = last.get("id") or ""
        eid = hashlib.sha1(f"re-vendor|{mid}".encode()).hexdigest()[:16]
        draft = render_draft(str(vendor.get("name") or ""), body, subject)
        has_property = is_kurashift_property_mail(subject, body)

        out.append(
            {
                "id": f"re-vendor-{eid}",
                "lane": "general",
                "kind": "mail",
                "status": "pending",
                "partner": vendor.get("name"),
                "folder": None,
                "subject": subject,
                "received_at": received_at,
                "summary": f"【業者返信】{vendor.get('name')} — {(body or subject)[:120].replace(chr(10), ' ')}",
                "draft_text": draft,
                "original_body": body or None,
                "priority": "high",
                "channel": "業者返信（estate）",
                "account": "estate",
                "gmail_thread_id": tid,
                "gmail_message_id": mid,
                "from_email": from_email,
                "payload": {
                    "source": "vendor_reply_triage",
                    "re_vendor_reply": True,
                    "vendor_id": vendor.get("id"),
                    "vendor_name": vendor.get("name"),
                    "vendor_status": vendor.get("status"),
                    "has_property_signal": has_property,
                    "message_id_header": headers.get("message-id") or "",
                    "ingest_kind": "mail",
                },
                "updated_at": now_iso(),
            }
        )
    out.sort(key=lambda x: x.get("received_at") or "", reverse=True)
    return out


def push_rows(rows: list[dict[str, Any]]) -> int:
    from supabase import create_client

    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_* 未設定")
    sb = create_client(url, key)
    protected = {"sent", "skipped", "snoozed", "done"}
    remote: dict[str, str] = {}
    ids = [r["id"] for r in rows]
    for i in range(0, len(ids), 80):
        chunk = ids[i : i + 80]
        r = sb.table("triage_items").select("id,status,draft_text,payload").in_("id", chunk).execute()
        for x in r.data or []:
            remote[str(x["id"])] = str(x.get("status") or "")
    n = 0
    for row in rows:
        rid = row["id"]
        if rid in remote and remote[rid] in protected:
            row["status"] = remote[rid]
            continue
        sb.table("triage_items").upsert(row, on_conflict="id").execute()
        n += 1
    return n


def mark_vendors_inbound_replied(rows: list[dict[str, Any]], *, dry_run: bool) -> int:
    """YAML: 返信受信を replied_at 記録（送信前の inbound milestone）。"""
    from jarvis_kurashift_vendor_list import load_list, save_list, vendor_index

    data = load_list()
    idx = vendor_index(data)
    touched = 0
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for row in rows:
        pl = row.get("payload") or {}
        vid = str(pl.get("vendor_id") or "").strip()
        if not vid or vid not in idx:
            continue
        v = idx[vid]
        if (v.get("replied_at") or "").strip():
            continue
        print(f"# mark inbound replied {vid} {v.get('name')}")
        if dry_run:
            touched += 1
            continue
        v["status"] = "replied"
        v["replied_at"] = today
        note = f"estate返信受信 {today}"
        prev = (v.get("notes") or "").strip()
        v["notes"] = f"{prev} | {note}".strip(" |") if prev else note
        touched += 1
    if touched and not dry_run:
        save_list(data)
    return touched


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Vendor reply → Jarvis Dashboard triage")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--push", action="store_true")
    ap.add_argument("--lookback-days", type=int, default=21)
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument(
        "--mark-inbound-replied",
        action="store_true",
        help="取込時に YAML status=replied（受信 milestone）",
    )
    args = ap.parse_args(argv)

    print("使用アカウント: estate / Gmail API（業者返信 triage）")
    rows = find_vendor_replies(
        lookback_days=args.lookback_days, max_threads=args.limit
    )
    print(f"# vendor_reply_candidates={len(rows)}")
    for r in rows:
        pl = r.get("payload") or {}
        prop = "物件シグナル" if pl.get("has_property_signal") else "質問/その他"
        print(
            f"  - {r['id']} {pl.get('vendor_id')} {r.get('partner')} "
            f"[{prop}] {r.get('subject', '')[:50]}"
        )

    if args.mark_inbound_replied and rows:
        n = mark_vendors_inbound_replied(rows, dry_run=args.dry_run or not args.push)
        print(f"# yaml inbound replied marked={n}")

    if not args.push:
        if not args.dry_run:
            print("# --push で Supabase upsert")
        return 0
    if args.dry_run:
        print("# dry-run: push skipped")
        return 0
    n = push_rows(rows)
    print(f"# pushed={n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
