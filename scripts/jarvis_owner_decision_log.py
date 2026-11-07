#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""owner_decisions へ判断ログを書く（Python 経路・soft-fail）。

TS 側の apps/jarvis-dashboard/lib/ownerDecisionLog.ts と同契約。
失敗しても本線（Todoist 更新等）は止めない。
"""
from __future__ import annotations

import os
import sys
from typing import Any


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
) -> bool:
    """Insert one row. Returns True if persisted, False on skip/soft-fail."""
    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        print("owner_decisions soft-fail: supabase env missing", file=sys.stderr)
        return False
    try:
        from supabase import create_client

        sb = create_client(url, key)
        row: dict[str, Any] = {
            "surface": surface,
            "action": action,
            "source": source,
            "employee": employee,
            "target_type": target_type,
            "target_id": target_id or "-",
            "subject": (subject or "")[:500] or None,
            "ai_proposal": (ai_proposal or "")[:4000] or None,
            "note": note,
            "payload": payload or {},
        }
        res = sb.table("owner_decisions").insert(row).execute()
        if getattr(res, "data", None) is None and getattr(res, "error", None):
            print(f"owner_decisions soft-fail: {res.error}", file=sys.stderr)
            return False
        return True
    except Exception as e:  # noqa: BLE001 — soft-fail
        print(f"owner_decisions soft-fail: {e}", file=sys.stderr)
        return False
