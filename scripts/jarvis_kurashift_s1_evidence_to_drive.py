#!/usr/bin/env python3
"""S1 / Grok調査 メール添付を証憑フォルダへ保存し、attachments メタを更新。

バイナリは Drive/OneDrive 同期フォルダ（Supabase Storage には上げない）。
正本: docs/KURASHIFT_S1問合せ証憑_Drive_20260825.md

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_s1_evidence_to_drive.py --deal-id <uuid>
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_s1_evidence_to_drive.py --poll-recent
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_s1_evidence_to_drive.py --dry-run --poll-recent
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_s1_evidence_to_drive.py --verify-drive-api
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_evidence_gdrive.py --verify
"""
from __future__ import annotations

import argparse
import base64
import os
import re
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
LOCAL_MIRROR = REPO / ".jarvis_state" / "kurashift_re_deal_attachments"
ONEDRIVE_DEFAULT = Path.home() / (
    "Library/CloudStorage/OneDrive-個人用/230_物件調査/KURASHIFT_問合せ証憑"
)
GDRIVE_DEFAULT = Path.home() / (
    "Library/CloudStorage/GoogleDrive-admin@livingsupport-matsu.co.jp"
    "/マイドライブ/230_物件調査/KURASHIFT_問合せ証憑"
)

sys.path.insert(0, str(REPO / "scripts"))
from jarvis_kurashift_re_deal_pdf_fetch import (  # noqa: E402
    attachments_table_ok,
    collect_attachment_parts,
    existing_keys,
    sanitize_filename,
)
from jarvis_kurashift_re_inquiry import (  # noqa: E402
    gmail_for_account,
    get_deal,
    header_map,
    sb_client,
)
from jarvis_kurashift_evidence_gdrive import (  # noqa: E402
    drive_api_disabled,
    upload_evidence_file,
    verify_drive_api,
)


def evidence_root() -> Path:
    env = (os.environ.get("KURASHIFT_INQUIRY_EVIDENCE_ROOT") or "").strip()
    if env:
        return Path(env).expanduser()
    if ONEDRIVE_DEFAULT.parent.is_dir():
        return ONEDRIVE_DEFAULT
    if GDRIVE_DEFAULT.parent.is_dir():
        return GDRIVE_DEFAULT
    return ONEDRIVE_DEFAULT


def open_url_for(path: Path) -> str:
    """Finder / browser 向け。file URL。"""
    return path.resolve().as_uri()


def is_evidence_filename(fn: str, mime: str) -> bool:
    low = (fn or "").lower()
    m = (mime or "").lower()
    if low.endswith((".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".heic")):
        return True
    if any(x in m for x in ("pdf", "image/", "jpeg", "png")):
        return True
    return False


def fetch_evidence_for_deal(
    sb: Any,
    deal: dict[str, Any],
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    deal_id = str(deal["id"])
    sj = deal.get("summary_json") if isinstance(deal.get("summary_json"), dict) else {}
    gmail_id = sj.get("gmail_id") or sj.get("s1_gmail_id")
    if not gmail_id:
        return {"ok": True, "deal_id": deal_id, "skipped": "no_gmail_id", "saved": 0}

    svc = gmail_for_account("estate")
    full = (
        svc.users()
        .messages()
        .get(userId="me", id=str(gmail_id), format="full")
        .execute()
    )
    payload = full.get("payload") or {}
    hm = header_map(payload.get("headers") or [])
    subject = hm.get("subject") or ""
    if "[Grok調査]" not in subject and "[Grok調査証憑]" not in subject:
        # still allow if deal source is mail_grok
        if deal.get("source") != "mail_grok":
            return {
                "ok": True,
                "deal_id": deal_id,
                "skipped": "not_grok_subject",
                "saved": 0,
            }

    seen = existing_keys(sb, deal_id)
    root = evidence_root() / deal_id
    mirror = LOCAL_MIRROR / deal_id
    saved = 0
    parts = collect_attachment_parts(payload)
    if not parts:
        return {"ok": True, "deal_id": deal_id, "skipped": "no_attachments", "saved": 0}

    for part in parts:
        fn = part["filename"]
        mime = part.get("mimeType") or ""
        if not is_evidence_filename(fn, mime):
            continue
        mid = str(gmail_id)
        key = (mid, fn)
        if key in seen:
            continue
        if dry_run:
            print(f"  dry-run would save {fn} → {root / sanitize_filename(fn)}")
            saved += 1
            continue

        att = (
            svc.users()
            .messages()
            .attachments()
            .get(userId="me", messageId=mid, id=part["attachmentId"])
            .execute()
        )
        raw = (att.get("data") or "").replace("-", "+").replace("_", "/")
        buf = base64.b64decode(raw)
        safe = sanitize_filename(fn)
        root.mkdir(parents=True, exist_ok=True)
        mirror.mkdir(parents=True, exist_ok=True)
        dest = root / safe
        if dest.exists():
            dest = root / f"{dest.stem}_{mid[:8]}{dest.suffix}"
        dest.write_bytes(buf)
        mirror_path = mirror / dest.name
        mirror_path.write_bytes(buf)

        rel_mirror = str(mirror_path.relative_to(REPO))
        payload: dict[str, Any] = {
            "kind": "s1_evidence",
            "evidence_dir": str(dest),
            "open_url": open_url_for(dest),
            "account": "estate",
            "subject": subject[:200],
        }
        if not drive_api_disabled():
            up = upload_evidence_file(dest, deal_id, dry_run=dry_run)
            if up.get("drive_web_view_link"):
                payload["drive_web_view_link"] = up["drive_web_view_link"]
                payload["drive_file_id"] = up.get("drive_file_id")
                payload["open_url"] = up["drive_web_view_link"]
            elif up.get("skipped"):
                payload["drive_api"] = up["skipped"]
            elif up.get("error"):
                payload["drive_api_error"] = str(up["error"])[:200]
                print(f"  drive-api warn: {up.get('error')}", file=sys.stderr)
        row = {
            "deal_id": deal_id,
            "gmail_id": mid,
            "filename": fn,
            "mime_type": mime or "application/octet-stream",
            "size_bytes": len(buf),
            "storage_path": rel_mirror,
            "payload": payload,
        }
        if attachments_table_ok(sb):
            try:
                sb.table("kurashift_re_deal_attachments").insert(row).execute()
            except Exception as e:
                if "duplicate" not in str(e).lower() and "23505" not in str(e):
                    raise
        seen.add(key)
        saved += 1
        print(f"  saved {fn} → {dest}")

    return {
        "ok": True,
        "deal_id": deal_id,
        "saved": saved,
        "evidence_root": str(root),
    }


def poll_recent(sb: Any, *, limit: int, dry_run: bool) -> dict[str, Any]:
    resp = (
        sb.table("kurashift_re_deals")
        .select("id, title, source, summary_json")
        .eq("source", "mail_grok")
        .order("updated_at", desc=True)
        .limit(limit)
        .execute()
    )
    total = 0
    for deal in resp.data or []:
        r = fetch_evidence_for_deal(sb, deal, dry_run=dry_run)
        total += int(r.get("saved") or 0)
        if r.get("skipped"):
            print(f"# {deal.get('id')}: skip {r.get('skipped')}")
    return {"ok": True, "saved": total, "scanned": len(resp.data or [])}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--deal-id", default="")
    ap.add_argument("--poll-recent", action="store_true")
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--verify-drive-api",
        action="store_true",
        help="admin Drive API の接続・アップロードをスモーク検証",
    )
    args = ap.parse_args()

    if args.verify_drive_api:
        r = verify_drive_api()
        print(r)
        return 0 if r.get("ok") else 1

    print(f"# evidence_root={evidence_root()}")
    sb = sb_client()
    if args.deal_id:
        deal = get_deal(sb, args.deal_id.strip())
        if not deal:
            print("deal not found", file=sys.stderr)
            return 1
        r = fetch_evidence_for_deal(sb, deal, dry_run=args.dry_run)
        print(r)
        return 0 if r.get("ok") else 1
    if args.poll_recent:
        r = poll_recent(sb, limit=args.limit, dry_run=args.dry_run)
        print(r)
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
