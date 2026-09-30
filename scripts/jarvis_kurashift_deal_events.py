#!/usr/bin/env python3
"""kurashift_re_deal_events — 物件候補の判断履歴（best-effort insert）。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

EVENT_TYPES = frozenset(
    {
        "created",
        "status_change",
        "inquiry_sent",
        "inquiry_reply",
        "grok_applied",
        "grok_handoff_sent",
        "grok_handoff_ready",
        "review_confirm",
        "review_pass",
        "note",
    }
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def insert_deal_event(
    sb: Any,
    *,
    deal_id: str,
    event_type: str,
    summary: str = "",
    actor: str = "jarvis",
    from_status: str | None = None,
    to_status: str | None = None,
    payload: dict[str, Any] | None = None,
    occurred_at: str | None = None,
) -> bool:
    """Insert event. Returns True on success. Failures are silent (table may not exist yet)."""
    if event_type not in EVENT_TYPES:
        return False
    row = {
        "deal_id": deal_id,
        "event_type": event_type,
        "actor": actor,
        "summary": (summary or "")[:500],
        "payload": payload or {},
        "occurred_at": occurred_at or now_iso(),
    }
    if from_status:
        row["from_status"] = from_status
    if to_status:
        row["to_status"] = to_status
    try:
        sb.table("kurashift_re_deal_events").insert(row).execute()
        return True
    except Exception:
        return False
