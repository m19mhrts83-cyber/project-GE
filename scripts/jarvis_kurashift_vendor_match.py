#!/usr/bin/env python3
"""地場業者リスト — メールアドレス・ドメイン照合（返信 triage 用）。"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

REPO = Path(__file__).resolve().parents[1]
LIST_PATH = REPO / "config" / "kurashift_re_vendor_list.yaml"
EXAMPLE_PATH = REPO / "config" / "kurashift_re_vendor_list.example.yaml"

ACTIVE_STATUSES = frozenset({"contacted", "replied"})


def load_list(path: Path | None = None) -> dict[str, Any]:
    p = path or LIST_PATH
    if not p.is_file():
        if EXAMPLE_PATH.is_file():
            return yaml.safe_load(EXAMPLE_PATH.read_text(encoding="utf-8")) or {}
        return {"vendors": []}
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {"vendors": []}


def _domain(email_or_url: str) -> str:
    s = (email_or_url or "").strip().lower()
    if "@" in s:
        return s.split("@", 1)[1]
    if s.startswith("http"):
        try:
            host = urlparse(s).netloc.lower()
            return host[4:] if host.startswith("www.") else host
        except Exception:
            return ""
    return ""


def _norm_email(s: str) -> str:
    return (s or "").strip().lower()


def vendor_is_outreach_active(v: dict[str, Any]) -> bool:
    st = str(v.get("status") or "").strip()
    if st in ACTIVE_STATUSES:
        return True
    if (v.get("contacted_at") or "").strip():
        return True
    return False


def build_match_index(data: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    data = data or load_list()
    out: list[dict[str, Any]] = []
    for v in data.get("vendors") or []:
        if not isinstance(v, dict) or not v.get("id"):
            continue
        if not vendor_is_outreach_active(v):
            continue
        emails: set[str] = set()
        ce = _norm_email(str(v.get("contact_email") or ""))
        if ce:
            emails.add(ce)
        domains: set[str] = set()
        for d in (_domain(ce), _domain(str(v.get("url") or "")), _domain(str(v.get("contact_url") or ""))):
            if d and "." in d:
                domains.add(d)
        name = str(v.get("name") or "").strip()
        out.append(
            {
                "id": str(v["id"]),
                "name": name,
                "emails": emails,
                "domains": domains,
                "status": str(v.get("status") or ""),
            }
        )
    return out


def match_vendor(
    from_email: str,
    *,
    from_display: str = "",
    subject: str = "",
    index: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """返信元が outreach 済み業者なら vendor dict を返す。"""
    idx = index if index is not None else build_match_index()
    em = _norm_email(from_email)
    if not em:
        return None
    dom = _domain(em)
    disp = (from_display or "").strip()
    subj = subject or ""

    for v in idx:
        if em in v["emails"]:
            return v
        if dom and dom in v["domains"]:
            return v

    # 社名が From 表示または件名に含まれる（弱い一致・1件のみ）
    name_hits = []
    for v in idx:
        name = v.get("name") or ""
        if len(name) >= 4 and (name in disp or name in subj):
            name_hits.append(v)
    if len(name_hits) == 1:
        return name_hits[0]
    return None
