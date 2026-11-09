#!/usr/bin/env python3
"""ニュース配信（Banto Webhook）共通ヘルパ。"""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
STATE_PATH = REPO / ".jarvis_state" / "news_digest.json"
STATE_EXAMPLE = REPO / ".jarvis_state" / "news_digest.example.json"
SUMMARY_LOCAL = REPO / ".jarvis_state" / "news_interest_summary.md"
REPORT_CHANNEL_ID = "C0C866FNU3C"
JST = timezone(timedelta(hours=9))

META_RE = re.compile(
    r"meta:\s*feed=(?P<feed>[A-Za-z0-9_\-]+)\s+item=(?P<item>[A-Za-z0-9_\-\.]+)",
    re.I,
)

DEFAULT_FEEDS = {
    "cursor_friday": "Friday Cursor Automation Brief",
    "ai_weekly": "AI源流・未来動向ウィークリー",
    "space_defense_daily": "宇宙・防衛・AIデイリー",
    "defense_mgr": "防衛宇宙・製造管理職ブリーフ",
}


def disabled() -> bool:
    if (os.environ.get("JARVIS_NEWS_DIGEST_DISABLE") or "").strip() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return True
    st = load_state()
    return bool(st.get("disabled"))


def load_state() -> dict[str, Any]:
    for path in (STATE_PATH, STATE_EXAMPLE):
        if not path.is_file():
            continue
        try:
            import json

            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return {"disabled": False, "feeds": {}}


def save_state(st: dict[str, Any]) -> None:
    import json

    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(st, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def now_iso() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def parse_meta(text: str) -> tuple[str, str] | None:
    m = META_RE.search(text or "")
    if not m:
        return None
    return m.group("feed").strip(), m.group("item").strip()


def first_title_line(text: str) -> str:
    for line in (text or "").splitlines():
        s = line.strip()
        if not s or s.startswith("meta:"):
            continue
        return s[:200]
    return "(無題)"


def supabase_client():
    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        raise RuntimeError("JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY 未設定")
    from supabase import create_client

    return create_client(url, key)


def ensure_feed(sb: Any, feed_id: str) -> None:
    title = DEFAULT_FEEDS.get(feed_id, feed_id)
    sb.table("news_feeds").upsert(
        {"feed_id": feed_id, "title": title, "updated_at": now_iso()},
        on_conflict="feed_id",
    ).execute()


def upsert_post(
    sb: Any,
    *,
    feed_id: str,
    item_key: str,
    slack_ts: str,
    title: str,
    channel: str = REPORT_CHANNEL_ID,
    payload: dict[str, Any] | None = None,
    posted_at: str | None = None,
) -> dict[str, Any]:
    ensure_feed(sb, feed_id)
    row = {
        "feed_id": feed_id,
        "item_key": item_key,
        "slack_channel": channel,
        "slack_ts": slack_ts,
        "title": title,
        "payload": payload or {},
        "posted_at": posted_at or now_iso(),
    }
    res = (
        sb.table("news_posts")
        .upsert(row, on_conflict="feed_id,item_key")
        .execute()
    )
    data = getattr(res, "data", None) or []
    return data[0] if data else row


def list_recent_posts(sb: Any, *, days: int = 14) -> list[dict[str, Any]]:
    cutoff = (datetime.now(JST) - timedelta(days=days)).isoformat()
    res = (
        sb.table("news_posts")
        .select("*")
        .gte("posted_at", cutoff)
        .order("posted_at", desc=True)
        .limit(200)
        .execute()
    )
    return list(getattr(res, "data", None) or [])


def insert_interest(
    sb: Any,
    *,
    post_id: int,
    kind: str,
    actor: str,
    text: str | None = None,
    payload: dict[str, Any] | None = None,
) -> bool:
    row = {
        "post_id": post_id,
        "kind": kind,
        "actor": actor or "unknown",
        "text": (text or "")[:2000] or None,
        "payload": payload or {},
        "captured_at": now_iso(),
    }
    try:
        sb.table("news_interest_events").upsert(
            row, on_conflict="post_id,kind,actor"
        ).execute()
        return True
    except Exception:  # noqa: BLE001
        # unique 衝突などは無視
        return False
