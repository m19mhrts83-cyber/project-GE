"""第一問合せの経路仕分け（TS: apps/trade-desk/lib/reInquiryChannel.ts と同期）"""

from __future__ import annotations

import os
from email.utils import parseaddr
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[1]
VENDOR_LIST = REPO / "config" / "kurashift_re_vendor_list.yaml"

KNOWN_SELF = {
    "matsuno.estate@gmail.com",
    "admin@livingsupport-matsu.co.jp",
    "m19m.hrts83@gmail.com",
}

PORTAL_DOMAIN_HINTS = (
    "kenbiya.com",
    "athome.co.jp",
    "homes.co.jp",
    "suumo.jp",
    "rakumachi.jp",
    "reins.jp",
    "reins.or.jp",
    "c21.co.jp",
    "apamanshop.com",
    "minimo.jp",
)

NOT_APPLICABLE_TITLE_SUBSTR = (
    "業者開拓",
    "E2E-GROK-KURASHIFT",
    "approved A'",
    "approved A’",
)

GROK_HANDOFF_SUBJECT_PREFIX = "[KURASHIFT問合せ依頼]"

_vendor_cache: dict[str, str] | None = None


def parse_email_addr(raw: str | None) -> str:
    if not raw:
        return ""
    _, addr = parseaddr(str(raw))
    return (addr or str(raw)).strip().lower()


def self_emails_extra() -> list[str]:
    out: list[str] = []
    for k in ("PERSONAL_EMAIL", "INQUIRY_GROK_HANDOFF_TO"):
        v = (os.environ.get(k) or "").strip().lower()
        if v:
            out.append(v)
    return out


def is_self_email(email: str, extra: list[str] | None = None) -> bool:
    addr = parse_email_addr(email) or (email or "").strip().lower()
    if not addr or "@" not in addr:
        return False
    if addr.endswith("@livingsupport-matsu.co.jp"):
        return True
    if addr in KNOWN_SELF:
        return True
    for e in extra or self_emails_extra():
        if e and addr == e.strip().lower():
            return True
    return False


def is_portal_or_noreply(email: str) -> bool:
    addr = parse_email_addr(email) or (email or "").strip().lower()
    if "@" not in addr:
        return False
    local, _, domain = addr.partition("@")
    if (
        local.startswith("noreply")
        or local.startswith("no-reply")
        or local == "mailer-daemon"
        or local.startswith("info+")
    ):
        return True
    return any(domain == d or domain.endswith(f".{d}") for d in PORTAL_DOMAIN_HINTS)


def handoff_to() -> str:
    return (
        (os.environ.get("INQUIRY_GROK_HANDOFF_TO") or "").strip()
        or (os.environ.get("PERSONAL_EMAIL") or "").strip()
        or "m19m.hrts83@gmail.com"
    )


def _vendor_emails() -> dict[str, str]:
    global _vendor_cache
    if _vendor_cache is not None:
        return _vendor_cache
    out: dict[str, str] = {}
    if VENDOR_LIST.is_file():
        try:
            doc = yaml.safe_load(VENDOR_LIST.read_text(encoding="utf-8")) or {}
            for v in doc.get("vendors") or []:
                vid = str(v.get("id") or "").strip()
                em = str(v.get("contact_email") or "").strip()
                if vid and "@" in em:
                    out[vid] = em
        except Exception:
            pass
    _vendor_cache = out
    return out


def vendor_contact_email(vendor_id: str | None) -> str:
    if not vendor_id:
        return ""
    return _vendor_emails().get(str(vendor_id).strip(), "")


def sj_of(deal: dict[str, Any]) -> dict[str, Any]:
    sj = deal.get("summary_json")
    return dict(sj) if isinstance(sj, dict) else {}


def resolve_agent_to(
    deal: dict[str, Any], *, explicit_to: str | None = None
) -> tuple[str, str]:
    extra = self_emails_extra()
    sj = sj_of(deal)

    explicit = (explicit_to or "").strip()
    if "@" in explicit and not is_self_email(explicit, extra) and not is_portal_or_noreply(
        explicit
    ):
        return parse_email_addr(explicit) or explicit, "explicit"

    reply_to = parse_email_addr(str(sj.get("reply_to") or ""))
    if reply_to and not is_self_email(reply_to, extra) and not is_portal_or_noreply(
        reply_to
    ):
        return reply_to, "reply_to"

    from_addr = parse_email_addr(str(sj.get("from") or ""))
    if from_addr and not is_self_email(from_addr, extra) and not is_portal_or_noreply(
        from_addr
    ):
        return from_addr, "from"

    v_em = vendor_contact_email(str(sj.get("vendor_id") or "") or None)
    if v_em and not is_self_email(v_em, extra) and not is_portal_or_noreply(v_em):
        return parse_email_addr(v_em) or v_em, "vendor_list"

    return "", "none"


def is_not_applicable(deal: dict[str, Any]) -> bool:
    title = str(deal.get("title") or "")
    for s in NOT_APPLICABLE_TITLE_SUBSTR:
        if s in title:
            return True
    # Grok調査でも掲載URLがあれば listing_web（classify 側）。URL無しのみ対象外。
    if is_grok_research(deal) and not resolve_listing_url(deal):
        return True
    return False


def is_grok_research(deal: dict[str, Any]) -> bool:
    title = str(deal.get("title") or "")
    for s in NOT_APPLICABLE_TITLE_SUBSTR:
        if s in title:
            return False
    source = str(deal.get("source") or "").strip()
    if source == "mail_grok":
        return True
    if "[Grok調査]" in title or "Grok調査" in title:
        return True
    sj = sj_of(deal)
    account = str(sj.get("account") or "")
    return account == "mail_grok" and source not in ("mail_admin", "mail_estate")


def resolve_listing_url(deal: dict[str, Any]) -> str:
    sj = sj_of(deal)
    grok = sj.get("grok") if isinstance(sj.get("grok"), dict) else {}
    for v in (sj.get("listing_url"), sj.get("url"), grok.get("url") if isinstance(grok, dict) else None):
        s = str(v or "").strip()
        if s.startswith("http://") or s.startswith("https://"):
            return s
    return ""


def is_kamiooya_intro_form(deal: dict[str, Any]) -> bool:
    sj = sj_of(deal)
    if sj.get("kamiooya_intro") is True:
        return True
    url = str(sj.get("interest_form_url") or "").strip()
    if url:
        return True
    title = str(deal.get("title") or "")
    return "【神大家】" in title and "物件紹介" in title


def classify_inquiry_channel(
    deal: dict[str, Any], *, explicit_to: str | None = None
) -> dict[str, str]:
    title = str(deal.get("title") or "")
    for s in NOT_APPLICABLE_TITLE_SUBSTR:
        if s in title:
            return {
                "channel": "not_applicable",
                "to": "",
                "reason": "vendor_outreach_or_fixture_memo",
            }
    if is_kamiooya_intro_form(deal):
        sj = sj_of(deal)
        form_url = str(sj.get("interest_form_url") or "").strip()
        return {
            "channel": "kamiooya_form",
            "to": form_url,
            "reason": "interest_form_url" if form_url else "kamiooya_intro_subject",
        }
    listing = resolve_listing_url(deal)
    if is_grok_research(deal) and listing:
        return {
            "channel": "listing_web",
            "to": listing,
            "reason": "grok_research_with_listing_url",
        }
    if is_not_applicable(deal):
        return {
            "channel": "not_applicable",
            "to": "",
            "reason": "grok_report_without_listing_url",
        }
    to, src = resolve_agent_to(deal, explicit_to=explicit_to)
    if to:
        return {"channel": "agent_email", "to": to, "reason": f"to_from_{src}"}
    return {
        "channel": "grok_handoff",
        "to": handoff_to(),
        "reason": "no_agent_email",
    }


def build_grok_handoff_subject(title: str, max_len: int = 40) -> str:
    t = title or "物件"
    short = t if len(t) <= max_len else t[: max_len - 1] + "…"
    return f"{GROK_HANDOFF_SUBJECT_PREFIX} {short}"


def build_grok_handoff_body(
    deal: dict[str, Any],
    *,
    inquiry_subject: str,
    inquiry_body: str,
) -> str:
    sj = sj_of(deal)
    grok = sj.get("grok") if isinstance(sj.get("grok"), dict) else {}
    location = str(grok.get("location") or deal.get("area") or deal.get("title") or "")
    price = ""
    if grok.get("price_man_raw"):
        price = str(grok["price_man_raw"])
    elif deal.get("price_man") is not None:
        price = str(deal["price_man"])
    elif grok.get("price_man") is not None:
        price = str(grok["price_man"])
    url = (
        str(sj.get("url") or "")
        or str(sj.get("listing_url") or "")
        or str(grok.get("url") or "")
    )
    lines = [
        "KURASHIFT からの物件第一問合せ依頼です。",
        "仲介メールが取れないため、Webフォーム問合せまたは調査フローで対応してください。",
        "",
        f"deal_id: {deal.get('id')}",
        f"案件: {deal.get('title')}",
        f"住所: {location}",
        f"価格: {price}万" if price else "価格: （不明）",
        f"URL: {url}" if url else "URL: （なし）",
        "",
        "--- 希望する第一問合せ文面（参考） ---",
        f"件名: {inquiry_subject}",
        "",
        inquiry_body,
        "",
        "---",
        "完了後は従来どおり [Grok調査] または業者からの紹介メールが estate に届く想定です。",
        "※ 業者開拓 A'（地場リストの顧客登録）とは別レーンです。",
    ]
    return "\n".join(lines)
