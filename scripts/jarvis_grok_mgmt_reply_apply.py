#!/usr/bin/env python3
"""管理会社・事前確認への返信を estate Gmail から拾い、台帳候補を出す。

本線: contacted の業者と From／本文を突合 → dry-run で提案。
確定は --apply-mark または CLI --mark（人／参謀判断後）。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_grok_mgmt_reply_apply.py --days 14 --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_grok_mgmt_reply_apply.py --days 14 --apply
  # 提案を確定:
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_mgmt_vendor_list.py \\
    --mark ID --status replied --vacancy-listing-ok true

使用アカウント: estate / Gmail API
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

REPO = Path(__file__).resolve().parents[1]
MANUAL = REPO / "215_kamiooya" / "C1_cursor" / "1b_Cursorマニュアル"
STATE_PATH = REPO / ".jarvis_state" / "mgmt_precheck_reply.json"
PY = Path("/Users/matsunomasaharu2/selenium_env/venv/bin/python")
LIST_SCRIPT = REPO / "scripts" / "jarvis_kurashift_mgmt_vendor_list.py"
SYNC_SCRIPT = REPO / "scripts" / "jarvis_kurashift_mgmt_vendor_sync.py"
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]

sys.path.insert(0, str(REPO / "scripts"))
from jarvis_kurashift_mgmt_vendor_list import (  # noqa: E402
    ensure_precheck_fields,
    load_list,
    mark_vendor,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_state() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        return {"processed_ids": [], "last_run_at": None}
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"processed_ids": [], "last_run_at": None}
        data.setdefault("processed_ids", [])
        return data
    except Exception:
        return {"processed_ids": [], "last_run_at": None}


def save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state["last_run_at"] = now_iso()
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def gmail_service():
    path = MANUAL / "token_estate.json"
    if not path.is_file():
        raise FileNotFoundError(f"token not found: {path}")
    creds = Credentials.from_authorized_user_file(str(path), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        path.write_text(creds.to_json(), encoding="utf-8")
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def body_text(payload: dict[str, Any]) -> str:
    def walk(p: dict[str, Any]) -> str:
        if (p.get("mimeType") or "").startswith("multipart/"):
            for c in p.get("parts") or []:
                t = walk(c)
                if t:
                    return t
        if p.get("mimeType") in ("text/plain", "text/html"):
            data = (p.get("body") or {}).get("data")
            if data:
                raw = base64.urlsafe_b64decode(data.encode()).decode("utf-8", "replace")
                raw = re.sub(r"<[^>]+>", " ", raw)
                return raw
        return ""

    return walk(payload or {})


def header_map(headers: list[dict[str, str]]) -> dict[str, str]:
    return {h.get("name", "").lower(): h.get("value", "") for h in headers}


def guess_intent(text: str) -> str:
    t = text or ""
    if any(x in t for x in ("ご協力できず", "お断り", "対応しておりません", "お受けでき", "仲介業を行ってい")):
        return "ng"
    if any(x in t for x in ("よろしくお願い", "ご連絡ありがとうございます", "お電話", "詳細", "可能です", "大丈夫です", "協力")):
        return "ok_or_unclear"
    return "unclear"


def match_vendors(from_hdr: str, subject: str, body: str, vendors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blob = f"{from_hdr} {subject} {body}".lower()
    hits: list[dict[str, Any]] = []
    for v in vendors:
        ensure_precheck_fields(v)
        if str(v.get("status") or "") not in ("contacted", "pending", "discovered"):
            # also allow contacted primarily
            if str(v.get("status") or "") != "contacted":
                continue
        name = str(v.get("name") or "").strip()
        email = str(v.get("contact_email") or "").strip().lower()
        score = 0
        if email and email in from_hdr.lower():
            score += 5
        if name and name.lower() in blob:
            score += 3
        # domain match
        if email and "@" in email:
            dom = email.split("@", 1)[1]
            if dom and dom in from_hdr.lower():
                score += 2
        if score >= 3:
            hits.append({**v, "_match_score": score})
    hits.sort(key=lambda x: -int(x.get("_match_score") or 0))
    return hits


def run(*, days: int, apply: bool, dry_run: bool) -> dict[str, Any]:
    print("使用アカウント: estate / Gmail API（管理会社・事前確認返信）")
    state = load_state()
    processed = set(str(x) for x in (state.get("processed_ids") or []))
    data = load_list()
    vendors = [v for v in (data.get("vendors") or []) if isinstance(v, dict)]
    contacted = [v for v in vendors if str(v.get("status") or "") == "contacted"]

    svc = gmail_service()
    q = f"newer_than:{max(1, days)}d -from:me -subject:[Grok"
    res = svc.users().messages().list(userId="me", q=q, maxResults=40).execute()
    msgs = res.get("messages") or []
    proposals: list[dict[str, Any]] = []
    applied = 0

    for m in msgs:
        mid = m["id"]
        if mid in processed:
            continue
        full = svc.users().messages().get(userId="me", id=mid, format="full").execute()
        hm = header_map(full.get("payload", {}).get("headers") or [])
        subject = hm.get("subject") or ""
        frm = hm.get("from") or ""
        body = body_text(full.get("payload") or {})[:4000]
        # skip newsletters
        if any(x in frm.lower() for x in ("kenbiya", "noreply", "newsletter", "westudy", "emailme")):
            continue
        hits = match_vendors(frm, subject, body, contacted or vendors)
        if not hits:
            continue
        intent = guess_intent(body + "\n" + subject)
        top = hits[0]
        prop = {
            "message_id": mid,
            "subject": subject[:120],
            "from": frm[:120],
            "vendor_id": top.get("id"),
            "vendor_name": top.get("name"),
            "match_score": top.get("_match_score"),
            "intent_guess": intent,
            "snippet": (body or "")[:240].replace("\n", " "),
        }
        proposals.append(prop)
        if apply and not dry_run and intent == "ng":
            mark_vendor(
                str(top["id"]),
                status="skip",
                note="precheck_reply:ng",
                vacancy_listing_ok="false",
                dry_run=False,
            )
            applied += 1
            processed.add(mid)
        elif apply and not dry_run and intent == "ok_or_unclear":
            # 自動で OK 確定はしない（曖昧含む）。state に残して人判断
            pass
        elif dry_run or not apply:
            pass
        if apply and not dry_run and intent == "ng":
            continue
        # mark seen lightly only for ng auto; others wait for human
        if apply and not dry_run and intent == "ng":
            processed.add(mid)

    if apply and not dry_run:
        state["processed_ids"] = sorted(processed)[-500:]
        save_state(state)
        if applied and SYNC_SCRIPT.is_file():
            subprocess.run(
                [str(PY), str(SYNC_SCRIPT), "--apply"],
                cwd=str(REPO),
                check=False,
            )

    out = {
        "ok": True,
        "days": days,
        "proposals": proposals,
        "contacted_vendors": len(contacted),
        "auto_applied_ng": applied,
        "dry_run": dry_run or not apply,
        "note": "OK確定は人手で --mark … --vacancy-listing-ok true",
    }
    print("📎 管理会社・事前確認返信")
    print(f"- 提案: {len(proposals)} 件 · contacted台帳 {len(contacted)}")
    print(f"- 自動NG適用: {applied}")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"MGMT_REPLY_APPLY:{json.dumps({k: out[k] for k in out if k != 'proposals'}, ensure_ascii=False)}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    dry = args.dry_run or not args.apply
    run(days=args.days, apply=bool(args.apply), dry_run=dry)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
