#!/usr/bin/env python3
"""
夜間トリアージ — パートナー以外（admin Gmail）の未返信候補・返信送信。

メール振り分け:

1. **パートナー**（`連絡先一覧.yaml`）
   → Jarvis「パートナー」レーン（管理・運用軸）。
   → 物件紹介シグナルがあっても partner レーンは維持。あわせて **KURASHIFT 評価にも載せうる**（二重経路・排他ではない）。
2. **不動産購入・物件紹介**（差出がパートナーでも可）
   → KURASHIFT（選定〜比較）。非パートナー分は Jarvis general には出さない。
3. **その他（非パートナー）**
   → Jarvis general。取込時に `kind=mail`（要確認）／`kind=skim`（要約用）へ振り分け。
"""
from __future__ import annotations

import base64
import hashlib
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from email.utils import parseaddr
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
MANUAL_DIR = REPO / "215_kamiooya" / "C1_cursor" / "1b_Cursorマニュアル"

DEFAULT_CONTACT_YAML = (
    Path.home()
    / "Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部"
    / "C2_ルーティン作業/26_パートナー社への相談/000_共通/連絡先一覧.yaml"
)

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

# 購入・紹介シグナル（KURASHIFT 評価側でも使う。Jarvis general からは非パートナー分を除外）
RE_PURCHASE_MAIL_RE = re.compile(
    r"(物件紹介|収益物件|戸建(て|)|土地値|不動産投資|"
    r"投資用(不動産|物件)|利回り\s*[：:]?\s*\d|"
    r"物件情報|空き家再生|中古戸建|"
    r"買付|販売図面|健美家|楽待|レインズ|"
    r"表面利回り|想定利回り|満室経営|一棟(アパート|マンション|物件)?|"
    r"物件選定|指値|融資付(き|)|区分(投資|マンション)|"
    r"新着物件|フルローン|稼働中)",
    re.I,
)

# 要確認に上げるシグナル（返信・期限・依頼）
NEEDS_ACTION_RE = re.compile(
    r"(ご確認|ご返信|ご返答|ご回答|お願い|ご対応|至急|期限|"
    r"までに|お返事|お返事ください|要返信|ご連絡ください|"
    r"アンケート|署名|同意|承認|決裁|見積|請求|振込|"
    r"please\s+(reply|confirm|respond)|action\s+required|"
    r"response\s+needed|deadline)",
    re.I,
)

# 要約用（skim）寄り
SKIM_HINT_RE = re.compile(
    r"(ニュース|メルマガ|newsletter|週刊|日刊|ダイジェスト|"
    r"キャンペーン|セール|ポイント付与|お知らせのみ|"
    r"配信停止|unsubscribe|広告|プロモーション|"
    r"リリースノート|changelog|新機能のご案内)",
    re.I,
)


def is_kurashift_property_mail(subject: str, body: str = "") -> bool:
    """物件紹介・購入メールか（KURASHIFT 評価対象のシグナル）。

    Jarvis general からは非パートナー分を除外する用途。
    パートナー差出でもシグナル自体は真になりうる（KURASHIFT 側で別途取込）。
    """
    blob = f"{subject or ''}\n{(body or '')[:1200]}"
    return bool(RE_PURCHASE_MAIL_RE.search(blob))


def classify_general_kind(subject: str, body: str = "", from_email: str = "") -> str:
    """general 取込の kind: mail（要確認）| skim（要約用）。"""
    blob = f"{subject or ''}\n{(body or '')[:2000]}\n{from_email or ''}"
    if SKIM_HINT_RE.search(blob) and not NEEDS_ACTION_RE.search(blob):
        return "skim"
    if NOISE_FROM_RE.search(from_email or "") and not NEEDS_ACTION_RE.search(blob):
        return "skim"
    if NEEDS_ACTION_RE.search(blob):
        return "mail"
    # 未返信スレッドでも依頼語が無ければ要約側（ホームで確認したよ）
    return "skim"


def resolve_contact_yaml(explicit: Path | None = None) -> Path:
    if explicit and explicit.is_file():
        return explicit
    ci = (
        REPO
        / "215_kamiooya/C1_cursor/1b_Cursorマニュアル/連絡先一覧.snapshot.yaml"
    )
    if DEFAULT_CONTACT_YAML.is_file():
        return DEFAULT_CONTACT_YAML
    if ci.is_file():
        return ci
    return DEFAULT_CONTACT_YAML


def mail_routing_bucket(
    from_email: str,
    subject: str,
    body: str = "",
    *,
    partner_emails: set[str] | None = None,
    partner_domains: set[str] | None = None,
    contact_yaml: Path | None = None,
) -> str:
    """振り分けバケット（Jarvis 用）: partner | kurashift_purchase | general。

    - partner: 連絡先一覧 → Jarvis パートナー（KURASHIFT 併載は別スクリプト）
    - kurashift_purchase: 非パートナーの物件紹介 → general に載せない
    - general: その他 → mail/skim 振り分け
    """
    emails = partner_emails
    domains = partner_domains
    if emails is None or domains is None:
        emails, domains = load_partner_filters(resolve_contact_yaml(contact_yaml))
    if is_partner_address(from_email, emails, domains):
        return "partner"
    if is_kurashift_property_mail(subject, body):
        return "kurashift_purchase"
    return "general"


def skip_pending_kurashift_property_triage(
    sb: Any,
    *,
    mark_gmail_read: bool = True,
    dry_run: bool = False,
    limit: int = 200,
    contact_yaml: Path | None = None,
) -> dict[str, Any]:
    """general pending のうち「非パートナーの物件紹介」だけ skipped。

    - lane=partner は一切触らない
    - from_email が連絡先一覧のパートナーなら触らない（誤って general に居ても保護）
    """
    emails, domains = load_partner_filters(resolve_contact_yaml(contact_yaml))
    resp = (
        sb.table("triage_items")
        .select(
            "id,subject,original_body,summary,gmail_message_id,account,"
            "payload,status,lane,from_email,partner"
        )
        .eq("status", "pending")
        .eq("lane", "general")
        .limit(limit)
        .execute()
    )
    rows = resp.data or []
    skipped_ids: list[str] = []
    protected_partner: list[str] = []
    read_ok = 0
    read_fail = 0
    now = datetime.now(JST).isoformat()

    for row in rows:
        subject = row.get("subject") or ""
        body = row.get("original_body") or row.get("summary") or ""
        from_email = (row.get("from_email") or "").strip()
        bucket = mail_routing_bucket(
            from_email,
            subject,
            str(body),
            partner_emails=emails,
            partner_domains=domains,
        )
        if bucket == "partner":
            protected_partner.append(str(row.get("id") or ""))
            continue
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        if payload.get("re_vendor_reply") or payload.get("vendor_id"):
            continue
        if bucket != "kurashift_purchase":
            continue
        rid = str(row.get("id") or "")
        if not rid:
            continue
        skipped_ids.append(rid)
        if dry_run:
            continue

        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        payload = {
            **payload,
            "kurashift_excluded_at": now,
            "kurashift_exclude_reason": "re_purchase_mail",
        }
        gid = (row.get("gmail_message_id") or "").strip()
        account = (row.get("account") or "admin").strip() or "admin"

        if mark_gmail_read and gid:
            try:
                service, _ = build_admin_gmail_service()
                if account not in ("", "admin", "mail_admin"):
                    print(
                        f"# skip mark-read non-admin account={account} id={rid}",
                        file=sys.stderr,
                    )
                else:
                    service.users().messages().modify(
                        userId="me",
                        id=gid,
                        body={"removeLabelIds": ["UNREAD"]},
                    ).execute()
                    payload["gmail_read_at"] = datetime.now(timezone.utc).isoformat()
                    read_ok += 1
            except Exception as e:
                read_fail += 1
                payload["gmail_read_error"] = str(e)[:200]
                print(f"# mark-read fail id={rid}: {e}", file=sys.stderr)

        sb.table("triage_items").update(
            {
                "status": "skipped",
                "payload": payload,
                "updated_at": now,
            }
        ).eq("id", rid).execute()

    return {
        "matched": len(skipped_ids),
        "skipped_ids": skipped_ids,
        "protected_partner_ids": protected_partner,
        "gmail_read_ok": read_ok,
        "gmail_read_fail": read_fail,
        "dry_run": dry_run,
    }


def rescue_partner_misfiled_in_general(
    sb: Any,
    *,
    dry_run: bool = False,
    limit: int = 300,
    contact_yaml: Path | None = None,
) -> dict[str, Any]:
    """general に紛れたパートナー差出を lane=partner へ戻す（status は pending 優先）。"""
    emails, domains = load_partner_filters(resolve_contact_yaml(contact_yaml))
    resp = (
        sb.table("triage_items")
        .select("id,status,from_email,subject,payload,lane")
        .eq("lane", "general")
        .limit(limit)
        .execute()
    )
    moved: list[str] = []
    now = datetime.now(JST).isoformat()
    for row in resp.data or []:
        fe = (row.get("from_email") or "").strip()
        if not is_partner_address(fe, emails, domains):
            continue
        rid = str(row.get("id") or "")
        if not rid:
            continue
        moved.append(rid)
        if dry_run:
            continue
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        payload = {
            **payload,
            "rescued_to_partner_at": now,
            "rescued_from_lane": "general",
        }
        # kurashift 除外で skipped にした誤判定は pending に戻す
        next_status = row.get("status") or "pending"
        if payload.get("kurashift_exclude_reason") and next_status == "skipped":
            next_status = "pending"
            payload.pop("kurashift_exclude_reason", None)
            payload.pop("kurashift_excluded_at", None)
        sb.table("triage_items").update(
            {
                "lane": "partner",
                "status": next_status,
                "payload": payload,
                "updated_at": now,
            }
        ).eq("id", rid).execute()
    return {"moved": len(moved), "ids": moved, "dry_run": dry_run}


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
    """Returns (service, my_email).

    GHA / 明示パス:
      GMAIL_ADMIN_TOKEN_PATH … admin token JSON
      GMAIL_CREDENTIALS_PATH … credentials.json（gmail_to_yoritoori 側で参照）
    """
    _ensure_manual_path()
    from gmail_to_yoritoori import build_service_for_token  # type: ignore

    token_env = (os.environ.get("GMAIL_ADMIN_TOKEN_PATH") or "").strip()
    token = Path(token_env) if token_env else (MANUAL_DIR / "token_livingsupport.json")
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
            # 最優先: 連絡先一覧のパートナーは partner レーン担当（ここでは general に載せない）
            continue
        if NOISE_FROM_RE.search(from_email) or NOISE_FROM_RE.search(from_raw):
            continue
        if NOISE_SUBJECT_RE.search(subject):
            continue

        body = _extract_body(payload)
        # 非パートナーの物件紹介・購入 → KURASHIFT（Jarvis 要確認から除外）
        if is_kurashift_property_mail(subject, body):
            continue

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
        kind = classify_general_kind(subject, body, from_email)
        candidates.append(
            {
                "id": eid,
                "lane": "general",
                "kind": kind,
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
                "priority": "high" if kind == "mail" else "low",
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
