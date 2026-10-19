#!/usr/bin/env python3
"""
MS Graph refresh_token の任意ストア（jarvis-dashboard sync_meta）。

方針（2026-10-19）:
  耐久本線は .env.jarvis_private ＋ GHA/Vercel Secrets。
  sync_meta.ms_graph_refresh_token は既定 OFF。
  互換が必要なときだけ JARVIS_MS_GRAPH_USE_SYNC_META=1。

値はログに出さない（fingerprint のみ）。
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from typing import Any

REFRESH_META_KEY = "ms_graph_refresh_token"


def use_sync_meta() -> bool:
    """sync_meta を読む／書くか。既定 False。"""
    v = (os.environ.get("JARVIS_MS_GRAPH_USE_SYNC_META") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


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
    """sync_meta から refresh。opt-in でない／無ければ空文字。"""
    if not use_sync_meta():
        return ""
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
    """回転／シードした refresh を sync_meta へ（opt-in 時のみ）。"""
    if not use_sync_meta():
        return False
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


def delete_persisted_refresh() -> bool:
    """sync_meta から ms_graph_refresh_token 行を削除（値は出さない）。

    USE_SYNC_META に依存しない（掃除用）。行が無くても True。
    """
    sb = _supabase_client()
    if sb is None:
        print(
            "# ms_graph refresh_store delete skip: JARVIS_SUPABASE_* 未設定",
            file=sys.stderr,
        )
        return False
    try:
        sb.table("sync_meta").delete().eq("key", REFRESH_META_KEY).execute()
        print(
            f"# ms_graph: sync_meta.{REFRESH_META_KEY} deleted",
            file=sys.stderr,
        )
        return True
    except Exception as e:  # noqa: BLE001
        print(
            f"# ms_graph refresh_store delete fail: {type(e).__name__}: {e}",
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


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="MS Graph refresh sync_meta ヘルパ")
    ap.add_argument(
        "--delete",
        action="store_true",
        help="sync_meta.ms_graph_refresh_token を削除",
    )
    ap.add_argument(
        "--probe",
        action="store_true",
        help="load 結果の有無と use_sync_meta を表示（値は出さない）",
    )
    args = ap.parse_args(argv)
    if args.delete:
        ok = delete_persisted_refresh()
        print({"delete": "ok" if ok else "fail"})
        return 0 if ok else 1
    if args.probe:
        loaded = load_persisted_refresh()
        print(
            {
                "use_sync_meta": use_sync_meta(),
                "has_value": bool(loaded),
                "fp": fingerprint(loaded) if loaded else "-",
            }
        )
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
