#!/usr/bin/env python3
"""
夜間トリアージ — パートナー以外（admin Gmail）の未返信候補・返信送信。
"""
from __future__ import annotations

import base64
import hashlib
import re
import sys
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.utils import parseaddr
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
MANUAL_DIR = REPO / "215_kamiooya" / "C1_cursor" / "1b_Cursorマニュアル"

NOISE_FROM_RE = re.compile(
    r"(noreply|no-reply|no_reply|donotreply|do-not-reply|mailer-daemon|"
    r"notifications?@|newsletter|news@|info@google|facebookmail|"
    r"linkedin\.com|appleid\.apple|github\.com|amazon\.|paypal\.|"
    r"stripe\.com|notion\.so|slack\.com|zoom\.us)",
    re.I,
)
NOISE_SUBJECT_RE = re.compile(
    r"(unsubscribe|配信停止|メルマガ|newsletter|ご注文|領収書の控え|"
    r"security alert|ログインの新しい|verify your|確認コード|"
    r"ワンタイム|OTP|password reset|パスワードリセット)",
    re.I,
)


def _ensure_manual_path() -> None:
    s = str(MANUAL_DIR)
    if s not in sys.path:
        sys.path.insert(0, s)


def load_partner_filters(contact_yaml: Path) -> tuple[set[str], set[str]]:
    """(emails_lower, domains_lower)"""
    emails: set[str] = set()
    domains: set[str] = set()
    if not contact_yaml.is_file():
        return emails, domains
    data = yaml.safe_load(contact_yaml.read_text(encoding="utf-8")) or {}
    for p in data.get("partners") or []:
        if not isinstance(p, dict):
            continue
        for e in p.get("emails") or []:
            if isinstance(e, str) and "@" in e:
                emails.add(e.strip().lower())
        for d in p.get("email_domains") or []:
            if isinstance(d, str) and d.strip():
                domains.add(d.strip().lower().lstrip("@"))
    return emails, domains


def is_partner_address(addr: str, emails: set[str], domains: set[str]) -> bool:
    a = (addr or "").strip().lower()
    if not a or "@" not in a:
        return False
    if a in emails:
        return True
    dom = a.split("@", 1)[1]
    return dom in domains


def build_admin_gmail_service():
    """Returns (service, my_email)."""
    _ensure_manual_path()
    from gmail_to_yoritoori import build_service_for_token  # type: ignore

    token = MANUAL_DIR / "token_livingsupport.json"
    if not token.is_file():
        raise RuntimeError(f"admin token missing: {token}")
    service, email = build_service_for_token(token)
    if not service:
        raise RuntimeError("failed to build Gmail service for admin")
    return service, (email or "admin@livingsupport-matsu.co.jp").lower()


def _header_map(payload: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for h in payload.get("headers") or []:
        name = (h.get("name") or "").lower()
        if name:
            out[name] = h.get("value") or ""
    return out


def _extract_body(payload: dict, limit: int = 3500) -> str:
    def walk(part: dict) -> str:
        mime = (part.get("mimeType") or "").lower()
        body = part.get("body") or {}
        data = body.get("data")
        if data and mime.startswith("text/plain"):
            try:
                return base64.urlsafe_b64decode(data.encode("utf-8")).decode("utf-8", errors="replace")
            except Exception:
                return ""
        texts = []
        for p in part.get("parts") or []:
            t = walk(p)
            if t:
                texts.append(t)
        if texts:
            return "\n".join(texts)
        if data and mime.startswith("text/html"):
            try:
                raw = base64.urlsafe_b64decode(data.encode("utf-8")).decode("utf-8", errors="replace")
                return re.sub(r"<[^>]+>", " ", raw)
            except Exception:
                return ""
        return ""

    return (walk(payload) or "")[:limit]


def _parse_internal_dt(ms: str) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(ms) / 1000.0, tz=JST)
    except Exception:
        return None


def find_general_unreplied(
    *,
    contact_yaml: Path,
    lookback_days: int = 14,
    max_threads: int = 40,
) -> list[dict[str, Any]]:
    """admin INBOX の未返信スレッド（パートナー除外）。"""
    service, my_email = build_admin_gmail_service()
    emails, domains = load_partner_filters(contact_yaml)
    q = f"in:inbox newer_than:{max(1, lookback_days)}d -category:promotions -category:social"
    threads: list[dict] = []
    page_token = None
    while len(threads) < max_threads:
        kwargs: dict[str, Any] = {"userId": "me", "q": q, "maxResults": min(50, max_threads - len(threads))}
        if page_token:
            kwargs["pageToken"] = page_token
        resp = service.users().threads().list(**kwargs).execute()
        threads.extend(resp.get("threads") or [])
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    candidates: list[dict[str, Any]] = []
    for th in threads[:max_threads]:
        tid = th.get("id")
        if not tid:
            continue
        full = service.users().threads().get(userId="me", id=tid, format="full").execute()
        msgs = full.get("messages") or []
        if not msgs:
            continue
        # chronological
        msgs_sorted = sorted(msgs, key=lambda m: int(m.get("internalDate") or 0))
        last = msgs_sorted[-1]
        payload = last.get("payload") or {}
        headers = _header_map(payload)
        from_raw = headers.get("from", "")
        _, from_email = parseaddr(from_raw)
        from_email = (from_email or "").lower()
        subject = headers.get("subject") or "(件名なし)"
        message_id_hdr = headers.get("message-id") or ""
        dt = _parse_internal_dt(str(last.get("internalDate") or "0"))
        received_at = dt.strftime("%Y/%m/%d %H:%M") if dt else ""

        # 自分が最後に送っている → 未返信ではない
        if from_email == my_email or from_email.endswith("@livingsupport-matsu.co.jp"):
            # 自分の送信（admin）で終わっている
            label_ids = set(last.get("labelIds") or [])
            if "SENT" in label_ids or from_email == my_email:
                continue

        if is_partner_address(from_email, emails, domains):
            continue
        if NOISE_FROM_RE.search(from_email) or NOISE_FROM_RE.search(from_raw):
            continue
        if NOISE_SUBJECT_RE.search(subject):
            continue

        body = _extract_body(payload)
        # context: last up to 3 messages
        ctx = []
        for m in msgs_sorted[-3:]:
            p = m.get("payload") or {}
            h = _header_map(p)
            fr = parseaddr(h.get("from", ""))[1].lower()
            inbound = fr != my_email and not fr.endswith("@livingsupport-matsu.co.jp")
            ctx.append(
                {
                    "received_at": (
                        _parse_internal_dt(str(m.get("internalDate") or "0")) or datetime.now(JST)
                    ).strftime("%Y/%m/%d %H:%M"),
                    "inbound": inbound,
                    "subject": h.get("subject") or subject,
                    "body": _extract_body(p, 1500),
                }
            )

        eid = hashlib.sha1(f"general|{tid}|{last.get('id')}".encode()).hexdigest()[:12]
        display_name = from_raw.split("<")[0].strip().strip('"') or from_email
        candidates.append(
            {
                "id": eid,
                "lane": "general",
                "folder": "",
                "partner_name": display_name[:80],
                "partner": display_name[:80],
                "received_at": received_at,
                "channel": "相手から返信",
                "summary": (body or subject)[:200].replace("\n", " "),
                "subject": subject,
                "subject_norm": subject,
                "body": body,
                "inbound": True,
                "gmail": True,
                "context": ctx,
                "account": "admin",
                "gmail_thread_id": tid,
                "gmail_message_id": last.get("id") or "",
                "from_email": from_email,
                "message_id_header": message_id_hdr,
            }
        )

    candidates.sort(key=lambda x: x.get("received_at") or "", reverse=True)
    return candidates


def send_general_reply(item: dict[str, Any], body_text: str) -> dict[str, Any]:
    """Gmail API でスレッドに Reply。自動送信禁止の最終段（呼び出し元で承認済み前提）。"""
    service, my_email = build_admin_gmail_service()
    thread_id = item.get("gmail_thread_id") or ""
    to_addr = item.get("from_email") or ""
    subject = item.get("subject") or ""
    if not thread_id or not to_addr:
        raise RuntimeError("gmail_thread_id / from_email missing")
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"

    msg = MIMEText(body_text, "plain", "utf-8")
    msg["To"] = to_addr
    msg["From"] = my_email
    msg["Subject"] = subject
    mid = (item.get("message_id_header") or "").strip()
    if mid:
        msg["In-Reply-To"] = mid
        msg["References"] = mid

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
    sent = (
        service.users()
        .messages()
        .send(userId="me", body={"raw": raw, "threadId": thread_id})
        .execute()
    )
    return {"id": sent.get("id"), "threadId": sent.get("threadId"), "to": to_addr, "subject": subject}
