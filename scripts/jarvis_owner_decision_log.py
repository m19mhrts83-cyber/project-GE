#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""owner_decisions へ判断ログを書く（Python 経路・soft-fail）。

TS 側の apps/loopware/lib/decisionContract.ts（契約 v1）と同じ形に揃える:
入口は slack / loopware / dashboard / kurashift / script に寄せ（細かい名前は payload.source_detail）、
payload.v・idem_key・outcome を付け、同じ判断の二重記録を防ぐ。
失敗しても本線（Todoist 更新等）は止めない。
"""
from __future__ import annotations

import os
import sys
import time
from typing import Any

CONTRACT_VERSION = 1
SOURCES = ("slack", "loopware", "dashboard", "kurashift", "script")

# 採った／見送った／迷った／未判断…（decisionContract.ts の OUTCOME_OF と同じ）
_OUTCOME = {
    **dict.fromkeys(
        ["sent", "replied", "todo", "todoist", "adopt", "accept", "good", "rule_accept", "next_good",
         "create", "done", "close", "drop", "merge", "pick"], "take"),
    **dict.fromkeys(["skipped", "reject", "wrong", "rule_reject", "next_wrong", "dismiss", "skip"], "ng"),
    "hesitated": "hesitate",
    "revise": "note",
    "left": "note",
    "commit": "note",
    "unseen": "none",
    **dict.fromkeys(["snoozed", "reschedule", "rule_once", "defer"], "later"),
}


def outcome_of(action: str) -> str:
    return _OUTCOME.get(action, "note")


def coarse_source(raw: str | None) -> str:
    s = (raw or "").strip().lower()
    if s in SOURCES:
        return s
    for prefix, to in (("slack", "slack"), ("loopware", "loopware"), ("dashboard", "dashboard"),
                       ("kurashift", "kurashift"), ("trade", "kurashift")):
        if s.startswith(prefix):
            return to
    return "script"


def contract_row(
    *,
    surface: str,
    action: str,
    source: str,
    target_type: str,
    target_id: str,
    employee: str | None = None,
    subject: str | None = None,
    note: str | None = None,
    ai_proposal: str | None = None,
    payload: dict[str, Any] | None = None,
    idem_key: str | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """owner_decisions の1行（契約 v1）。ネットワーク不要。"""
    coarse = coarse_source(source)
    tid = (target_id or "-")[:200]
    minute = int((now if now is not None else time.time()) // 60)
    key = (idem_key or "").strip()[:200] or f"{coarse}:{surface}:{tid}:{action}:{minute}"
    pl: dict[str, Any] = dict(payload or {})
    pl["v"] = CONTRACT_VERSION
    pl["idem_key"] = key
    pl["outcome"] = outcome_of(action)
    if source and source != coarse:
        pl["source_detail"] = source[:60]
    return {
        "surface": surface,
        "action": action,
        "source": coarse,
        "employee": employee,
        "target_type": target_type,
        "target_id": tid,
        "subject": (subject or "")[:500] or None,
        "ai_proposal": (ai_proposal or "")[:4000] or None,
        "note": note,
        "payload": pl,
    }


def log_owner_decision(
    *,
    surface: str,
    action: str,
    source: str,
    target_type: str,
    target_id: str,
    employee: str | None = None,
    subject: str | None = None,
    note: str | None = None,
    ai_proposal: str | None = None,
    payload: dict[str, Any] | None = None,
    idem_key: str | None = None,
) -> bool:
    """Insert one row. Returns True if persisted (or already there), False on skip/soft-fail."""
    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        print("owner_decisions soft-fail: supabase env missing", file=sys.stderr)
        return False
    try:
        from supabase import create_client

        sb = create_client(url, key)
        row = contract_row(
            surface=surface, action=action, source=source, target_type=target_type,
            target_id=target_id, employee=employee, subject=subject, note=note,
            ai_proposal=ai_proposal, payload=payload, idem_key=idem_key,
        )
        dup = (
            sb.table("owner_decisions").select("id")
            .eq("payload->>idem_key", row["payload"]["idem_key"]).limit(1).execute()
        )
        if getattr(dup, "data", None):
            return True
        res = sb.table("owner_decisions").insert(row).execute()
        if getattr(res, "data", None) is None and getattr(res, "error", None):
            print(f"owner_decisions soft-fail: {res.error}", file=sys.stderr)
            return False
        return True
    except Exception as e:  # noqa: BLE001 — soft-fail
        print(f"owner_decisions soft-fail: {e}", file=sys.stderr)
        return False
