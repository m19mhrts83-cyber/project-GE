#!/usr/bin/env python3
"""Phase PDF-0 — 問合せ返信メールの PDF 添付を deal 配下に保存。

使用アカウント: estate / admin（deal の inquiry スレッド） / Gmail API
実体: ~/git-repos/.jarvis_state/kurashift_re_deal_attachments/{deal_id}/
メタ: kurashift_re_deal_attachments（jarvis-dashboard）

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_re_deal_pdf_fetch.py --deal-id <uuid>
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_re_deal_pdf_fetch.py --poll-all
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_re_deal_pdf_fetch.py --dry-run --deal-id <uuid>
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
ATTACH_ROOT = REPO / ".jarvis_state" / "kurashift_re_deal_attachments"

# re_inquiry から Gmail / deal 操作を再利用
sys.path.insert(0, str(REPO / "scripts"))
from jarvis_kurashift_re_inquiry import (  # noqa: E402
    account_for_deal_with_sb,
    gmail_for_account,
    get_deal,
    header_map,
    inquiry_fields,
    list_messages,
    sb_client,
)


def sanitize_filename(name: str) -> str:
    s = re.sub(r'[<>:"/\\|?*]', "_", name or "attachment")
    return re.sub(r"\s+", "_", s).strip() or "attachment"


def collect_attachment_parts(payload: dict) -> list[dict[str, str]]:
    parts: list[dict[str, str]] = []

    def walk(p: dict | None) -> None:
        if not p:
            return
        body = p.get("body") or {}
        if p.get("filename") and body.get("attachmentId"):
            parts.append(
                {
                    "filename": str(p["filename"]),
                    "attachmentId": str(body["attachmentId"]),
                    "mimeType": str(p.get("mimeType") or ""),
                }
            )
        for ch in p.get("parts") or []:
            walk(ch)

    walk(payload)
    return parts


def attachments_table_ok(sb: Any) -> bool:
    try:
        sb.table("kurashift_re_deal_attachments").select("id").limit(1).execute()
        return True
    except Exception:
        return False


def existing_keys(sb: Any, deal_id: str) -> set[tuple[str, str]]:
    if not attachments_table_ok(sb):
        return set()
    resp = (
        sb.table("kurashift_re_deal_attachments")
        .select("gmail_id, filename")
        .eq("deal_id", deal_id)
        .execute()
    )
    out: set[tuple[str, str]] = set()
    for row in resp.data or []:
        gid = row.get("gmail_id")
        fn = row.get("filename")
        if gid and fn:
            out.add((str(gid), str(fn)))
    return out


def fetch_pdfs_for_deal(
    sb: Any,
    deal: dict[str, Any],
    *,
    dry_run: bool = False,
    pdf_only: bool = True,
) -> dict[str, Any]:
    deal_id = str(deal["id"])
    acct = account_for_deal_with_sb(sb, deal)
    svc = gmail_for_account(acct)
    fields = inquiry_fields(deal)
    thread_id = fields.get("inquiry_thread_id")
    if not thread_id:
        for m in list_messages(sb, deal):
            if m.get("thread_id"):
                thread_id = m["thread_id"]
                break
    if not thread_id:
        return {"ok": True, "deal_id": deal_id, "skipped": "no_thread", "saved": 0}

    full = (
        svc.users()
        .threads()
        .get(userId="me", id=thread_id, format="full")
        .execute()
    )
    seen = existing_keys(sb, deal_id)
    dest_dir = ATTACH_ROOT / deal_id
    saved = 0
    scanned = 0

    for msg in full.get("messages") or []:
        mid = str(msg.get("id") or "")
        payload = msg.get("payload") or {}
        hm = header_map(payload.get("headers"))
        direction = "inbound"
        from_raw = hm.get("from", "")
        if "matsuno.estate" in from_raw.lower() or "livingsupport" in from_raw.lower():
            direction = "outbound"

        for part in collect_attachment_parts(payload):
            fn = part["filename"]
            mime = part.get("mimeType") or ""
            if pdf_only and not (
                fn.lower().endswith(".pdf") or "pdf" in mime.lower()
            ):
                continue
            scanned += 1
            key = (mid, fn)
            if key in seen:
                continue
            if dry_run:
                print(f"  dry-run would save {direction} {fn} ({mid[:12]}…)")
                saved += 1
                continue

            dest_dir.mkdir(parents=True, exist_ok=True)
            att = (
                svc.users()
                .messages()
                .attachments()
                .get(userId="me", messageId=mid, id=part["attachmentId"])
                .execute()
            )
            raw = att.get("data") or ""
            raw = raw.replace("-", "+").replace("_", "/")
            buf = base64.b64decode(raw)
            safe = sanitize_filename(fn)
            path = dest_dir / safe
            if path.exists():
                stem = path.stem
                path = dest_dir / f"{stem}_{mid[:8]}{path.suffix}"

            path.write_bytes(buf)
            rel = str(path.relative_to(REPO))
            row = {
                "deal_id": deal_id,
                "gmail_id": mid,
                "filename": fn,
                "mime_type": mime or "application/pdf",
                "size_bytes": len(buf),
                "storage_path": rel,
                "payload": {"direction": direction, "account": acct},
            }
            if attachments_table_ok(sb):
                sb.table("kurashift_re_deal_attachments").insert(row).execute()
            else:
                sj = deal.get("summary_json") or {}
                if not isinstance(sj, dict):
                    sj = {}
                att_list = list(sj.get("attachments") or [])
                att_list.append(row)
                sb.table("kurashift_re_deals").update(
                    {"summary_json": {**sj, "attachments": att_list}}
                ).eq("id", deal_id).execute()
            seen.add(key)
            saved += 1
            print(f"  saved {fn} → {rel}")

    return {
        "ok": True,
        "deal_id": deal_id,
        "thread_id": thread_id,
        "scanned_parts": scanned,
        "saved": saved,
        "dry_run": dry_run,
    }


def poll_all(sb: Any, *, dry_run: bool = False) -> dict[str, Any]:
    deals = (
        sb.table("kurashift_re_deals")
        .select("*")
        .in_("inquiry_status", ["sent", "awaiting_reply", "has_reply"])
        .limit(100)
        .execute()
        .data
        or []
    )
    total_saved = 0
    for deal in deals:
        r = fetch_pdfs_for_deal(sb, deal, dry_run=dry_run)
        total_saved += int(r.get("saved") or 0)
    out = {"ok": True, "deals": len(deals), "saved": total_saved, "dry_run": dry_run}
    print(f"📎 pdf_fetch poll-all: deals={len(deals)} saved={total_saved}")
    print(f"KURASHIFT_RESULT:{json.dumps(out, ensure_ascii=False)}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="KURASHIFT deal PDF attachments (PDF-0)")
    ap.add_argument("--deal-id", default="")
    ap.add_argument("--poll-all", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    print("使用アカウント: estate / admin（deal スレッド） / Gmail API")
    sb = sb_client()

    if args.poll_all:
        poll_all(sb, dry_run=args.dry_run)
        return 0
    if not args.deal_id:
        ap.error("--deal-id または --poll-all が必要です")
    deal = get_deal(sb, args.deal_id)
    r = fetch_pdfs_for_deal(sb, deal, dry_run=args.dry_run)
    print(f"📎 pdf_fetch: saved={r.get('saved')} thread={r.get('thread_id') or '—'}")
    print(f"KURASHIFT_RESULT:{json.dumps(r, ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
