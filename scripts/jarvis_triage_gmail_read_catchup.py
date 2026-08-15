#!/usr/bin/env python3
"""
Jarvis トリアージ閉じた件の Gmail 既読キャッチアップ（Mac）。

ダッシュボードでスキップ／送信済み／対応済みにしたあと、
Vercel に GMAIL_ADMIN_TOKEN_B64 が無い場合などの取りこぼしを埋める。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_triage_gmail_read_catchup.py
  ~/selenium_env/venv/bin/python scripts/jarvis_triage_gmail_read_catchup.py --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_triage_gmail_read_catchup.py --cleanup-re-pending
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
MANUAL = REPO / "215_kamiooya" / "C1_cursor" / "1b_Cursorマニュアル"

TOKEN_BY_ACCOUNT = {
    "admin": "token_livingsupport.json",
    "mail_admin": "token_livingsupport.json",
    "estate": "token_estate.json",
    "mail_estate": "token_estate.json",
    "m19m": "token_m19m.json",
    "mail_m19m": "token_m19m.json",
}


def sb_client() -> Any:
    from supabase import create_client
    import os

    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_* 未設定")
    return create_client(url, key)


def gmail_service(token_name: str) -> Any:
    sys.path.insert(0, str(MANUAL))
    from gmail_to_yoritoori import build_service_for_token  # type: ignore

    token = MANUAL / token_name
    if not token.is_file():
        raise FileNotFoundError(f"token missing: {token}")
    service, _ = build_service_for_token(token)
    if not service:
        raise RuntimeError(f"failed gmail service for {token_name}")
    return service


def mark_one(svc: Any, message_id: str) -> None:
    svc.users().messages().modify(
        userId="me",
        id=message_id,
        body={"removeLabelIds": ["UNREAD"]},
    ).execute()


def catchup_closed(*, dry_run: bool = False, limit: int = 80) -> dict[str, Any]:
    sb = sb_client()
    resp = (
        sb.table("triage_items")
        .select("id,status,gmail_message_id,account,payload,updated_at")
        .in_("status", ["skipped", "sent", "done"])
        .not_.is_("gmail_message_id", "null")
        .order("updated_at", desc=True)
        .limit(limit)
        .execute()
    )
    rows = resp.data or []
    ok = 0
    skip = 0
    fail = 0
    services: dict[str, Any] = {}

    for row in rows:
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        if payload.get("gmail_read_at"):
            skip += 1
            continue
        gid = (row.get("gmail_message_id") or "").strip()
        if not gid:
            skip += 1
            continue
        account = (row.get("account") or "admin").strip().lower() or "admin"
        token_name = TOKEN_BY_ACCOUNT.get(account, "token_livingsupport.json")
        if dry_run:
            print(f"# dry-run mark-read id={row.get('id')} gmail={gid} account={account}")
            ok += 1
            continue
        try:
            if token_name not in services:
                services[token_name] = gmail_service(token_name)
            mark_one(services[token_name], gid)
            payload = {
                **payload,
                "gmail_read_at": datetime.now(timezone.utc).isoformat(),
            }
            payload.pop("gmail_read_pending", None)
            payload.pop("gmail_read_error", None)
            sb.table("triage_items").update(
                {
                    "payload": payload,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            ).eq("id", row["id"]).execute()
            ok += 1
            print(f"📎 triage_gmail_read: id={row['id']} gmail={gid} account={account}")
        except Exception as e:
            fail += 1
            payload = {
                **payload,
                "gmail_read_pending": True,
                "gmail_read_error": str(e)[:200],
            }
            try:
                sb.table("triage_items").update({"payload": payload}).eq(
                    "id", row["id"]
                ).execute()
            except Exception:
                pass
            print(f"# fail id={row.get('id')}: {e}", file=sys.stderr)

    return {"ok": ok, "skipped_already": skip, "fail": fail, "dry_run": dry_run}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=80)
    ap.add_argument(
        "--cleanup-re-pending",
        action="store_true",
        help="pending の物件紹介メールを skipped＋既読（KURASHIFT 担当分）",
    )
    args = ap.parse_args(argv)

    out: dict[str, Any] = {}
    if args.cleanup_re_pending:
        sys.path.insert(0, str(REPO / "scripts"))
        from jarvis_night_triage_general import (  # type: ignore
            skip_pending_kurashift_property_triage,
        )

        sb = sb_client()
        out["cleanup_re"] = skip_pending_kurashift_property_triage(
            sb,
            mark_gmail_read=True,
            dry_run=args.dry_run,
        )
        print(
            "📎 cleanup_re_pending:",
            json.dumps(out["cleanup_re"], ensure_ascii=False),
        )

    out["catchup"] = catchup_closed(dry_run=args.dry_run, limit=args.limit)
    print("📎 triage_gmail_read_catchup:", json.dumps(out["catchup"], ensure_ascii=False))
    return 0 if out["catchup"].get("fail", 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
