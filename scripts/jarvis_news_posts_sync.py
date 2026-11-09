#!/usr/bin/env python3
"""#report 上のニュース投稿（meta: feed=… item=…）を news_posts へ登録。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_news_posts_sync.py --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_news_posts_sync.py --apply

要: SLACK_BOT_TOKEN / JARVIS_SUPABASE_*
停止: JARVIS_NEWS_DIGEST_DISABLE=1
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from jarvis_news_digest_lib import (  # noqa: E402
    REPORT_CHANNEL_ID,
    disabled,
    first_title_line,
    parse_meta,
    supabase_client,
    upsert_post,
)

JST = timezone(timedelta(hours=9))


def slack_token() -> str:
    return (
        (os.environ.get("SLACK_BOT_TOKEN") or "").strip()
        or (os.environ.get("SLACK_USER_TOKEN") or "").strip()
    )


def _api(method: str, token: str, params: dict[str, str]) -> dict[str, Any]:
    url = f"https://slack.com/api/{method}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {token}"}, method="GET"
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if not data.get("ok"):
        raise RuntimeError(data.get("error") or f"{method}_failed")
    return data


def history(channel: str, *, token: str, oldest: float, limit: int = 100) -> list[dict]:
    data = _api(
        "conversations.history",
        token,
        {"channel": channel, "oldest": str(oldest), "limit": str(limit)},
    )
    return list(data.get("messages") or [])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--channel", default=REPORT_CHANNEL_ID)
    args = ap.parse_args()
    dry = args.dry_run or not args.apply

    if disabled():
        print("news digest disabled")
        return 0

    token = slack_token()
    if not token:
        print("❌ SLACK_BOT_TOKEN がありません", file=sys.stderr)
        return 2

    oldest = time.time() - args.days * 86400
    msgs = history(args.channel, token=token, oldest=oldest)
    candidates: list[tuple[dict, str, str]] = []
    for m in msgs:
        text = m.get("text") or ""
        meta = parse_meta(text)
        if not meta:
            continue
        feed_id, item_key = meta
        candidates.append((m, feed_id, item_key))

    print(f"# scanned={len(msgs)} news_meta={len(candidates)} dry_run={dry}")
    if not candidates:
        return 0

    sb = None if dry else supabase_client()
    for m, feed_id, item_key in candidates:
        ts = str(m.get("ts") or "")
        title = first_title_line(m.get("text") or "")
        posted_at = None
        try:
            posted_at = datetime.fromtimestamp(float(ts), tz=JST).isoformat(
                timespec="seconds"
            )
        except (TypeError, ValueError):
            pass
        print(f"- {feed_id}/{item_key} ts={ts} {title[:60]}")
        if dry or sb is None:
            continue
        upsert_post(
            sb,
            feed_id=feed_id,
            item_key=item_key,
            slack_ts=ts,
            title=title,
            channel=args.channel,
            payload={
                "username": m.get("username"),
                "bot_id": m.get("bot_id"),
                "user": m.get("user"),
            },
            posted_at=posted_at,
        )
    if not dry:
        print(f"✅ upserted {len(candidates)} news_posts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
