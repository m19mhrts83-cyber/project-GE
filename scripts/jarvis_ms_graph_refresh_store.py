#!/usr/bin/env python3
"""
MS Graph refresh_token の耐久ストア（jarvis-dashboard sync_meta）。

Vercel `lib/onedrive/graphRead.ts` と同じキー:
  sync_meta.key = ms_graph_refresh_token

GHA / Mac の Graph スクリプトは Secrets が古くてもここを優先する。
回転時はここに書き戻し、次回ジョブの invalid_grant を防ぐ。
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from typing import Any

REFRESH_META_KEY = "ms_graph_refresh_token"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _supabase_client() -> Any | None:
    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (
        os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("JARVIS_SUPABASE_SECRET_KEY")
        or ""
    ).strip()
    if not url or not key:
        return None
    try:
        from supabase import create_client
    except ImportError:
        return None
    return create_client(url, key)


def load_persisted_refresh() -> str:
    """sync_meta から refresh。無ければ空文字。"""
    sb = _supabase_client()
    if sb is None:
        return ""
    try:
        r = (
            sb.table("sync_meta")
            .select("value")
            .eq("key", REFRESH_META_KEY)
            .maybe_single()
            .execute()
        )
        data = r.data
        if isinstance(data, dict):
            v = data.get("value")
            return v.strip() if isinstance(v, str) else ""
    except Exception as e:  # noqa: BLE001
        print(
            f"# ms_graph refresh_store load skip: {type(e).__name__}",
            file=sys.stderr,
        )
    return ""


def persist_refresh(token: str) -> bool:
    """回転／シードした refresh を sync_meta へ。値はログに出さない。"""
    token = (token or "").strip()
    if not token:
        return False
    sb = _supabase_client()
    if sb is None:
        print(
            "# ms_graph refresh_store persist skip: JARVIS_SUPABASE_* 未設定",
            file=sys.stderr,
        )
        return False
    try:
        sb.table("sync_meta").upsert(
            {
                "key": REFRESH_META_KEY,
                "value": token,
                "updated_at": _now_iso(),
            },
            on_conflict="key",
        ).execute()
        print(
            f"# ms_graph: sync_meta.{REFRESH_META_KEY} updated (len={len(token)})",
            file=sys.stderr,
        )
        return True
    except Exception as e:  # noqa: BLE001
        print(
            f"# ms_graph refresh_store persist fail: {type(e).__name__}: {e}",
            file=sys.stderr,
        )
        return False


def fingerprint(token: str) -> str:
    """ログ用・値を晒さない短い指紋。"""
    import hashlib

    t = (token or "").strip()
    if not t:
        return "-"
    return hashlib.sha256(t.encode("utf-8")).hexdigest()[:8]
