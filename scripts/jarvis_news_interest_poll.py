#!/usr/bin/env python3
"""ニュース投稿の 👍/👎 とスレコメントを回収し興味ログ＋要約を更新。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_news_interest_poll.py --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_news_interest_poll.py --apply
  # 先に posts sync してから:
  ~/selenium_env/venv/bin/python scripts/jarvis_news_posts_sync.py --apply

要: SLACK_BOT_TOKEN / JARVIS_SUPABASE_*
停止: JARVIS_NEWS_DIGEST_DISABLE=1
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from jarvis_news_digest_lib import (  # noqa: E402
    SUMMARY_LOCAL,
    disabled,
    insert_interest,
    list_recent_posts,
    now_iso,
    supabase_client,
)

JST = timezone(timedelta(hours=9))
PLUS = {"+1", "thumbsup", "+1::skin-tone-2", "+1::skin-tone-3", "+1::skin-tone-4", "+1::skin-tone-5"}
MINUS = {"-1", "thumbsdown", "-1::skin-tone-2", "-1::skin-tone-3", "-1::skin-tone-4", "-1::skin-tone-5"}


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


def reaction_kind(name: str) -> str | None:
    base = (name or "").split("::", 1)[0]
    if base in PLUS or name in PLUS:
        return "plus1"
    if base in MINUS or name in MINUS:
        return "minus1"
    return None


def fetch_reactions(channel: str, ts: str, *, token: str) -> list[dict[str, Any]]:
    data = _api(
        "reactions.get",
        token,
        {"channel": channel, "timestamp": ts, "full": "true"},
    )
    msg = data.get("message") or {}
    return list(msg.get("reactions") or [])


def fetch_replies(channel: str, ts: str, *, token: str) -> list[dict[str, Any]]:
    data = _api(
        "conversations.replies",
        token,
        {"channel": channel, "ts": ts, "limit": "50"},
    )
    msgs = list(data.get("messages") or [])
    return msgs[1:] if len(msgs) > 1 else []


def write_summary(lines: list[str], *, dry: bool) -> Path | None:
    text = "\n".join(lines).rstrip() + "\n"
    print("--- summary ---")
    print(text)
    if dry:
        return None
    SUMMARY_LOCAL.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_LOCAL.write_text(text, encoding="utf-8")
    # Drive JarvisBox outbox（Banto／ホークが読める）
    try:
        from jarvis_bucho_bridge_lib import outbox_dir_for_target, sanitize_title
        from datetime import datetime as _dt
        from zoneinfo import ZoneInfo

        day = _dt.now(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d")
        hm = _dt.now(ZoneInfo("Asia/Tokyo")).strftime("%H%M")
        out_dir = outbox_dir_for_target("hawk")
        path = out_dir / f"{day}_{hm}_{sanitize_title('ニュース興味要約')}.md"
        path.write_text(
            "# Jarvis → Banto/Hawk\n"
            "target: hawk\n"
            "priority: normal\n"
            "action: news_interest_summary\n"
            "title: ニュース興味要約（Banto向け）\n"
            "---\n"
            f"{text}\n",
            encoding="utf-8",
        )
        print(f"📎 outbox: {path}")
        return path
    except Exception as e:  # noqa: BLE001
        print(f"⚠️ outbox skip: {e}", file=sys.stderr)
        print(f"📎 local summary: {SUMMARY_LOCAL}")
        return SUMMARY_LOCAL


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--days", type=int, default=14)
    args = ap.parse_args()
    dry = args.dry_run or not args.apply

    if disabled():
        print("news digest disabled")
        return 0

    token = slack_token()
    if not token:
        print("❌ SLACK_BOT_TOKEN がありません", file=sys.stderr)
        return 2

    sb = supabase_client()
    posts = list_recent_posts(sb, days=args.days)
    print(f"# posts={len(posts)} dry_run={dry}")

    tallies: dict[str, dict[str, int]] = defaultdict(lambda: {"plus1": 0, "minus1": 0, "comment": 0})
    events = 0

    for p in posts:
        post_id = int(p["id"])
        channel = p.get("slack_channel") or ""
        ts = p.get("slack_ts") or ""
        feed = p.get("feed_id") or "?"
        item = p.get("item_key") or "?"
        label = f"{feed}/{item}"
        if not channel or not ts:
            continue
        try:
            reactions = fetch_reactions(channel, ts, token=token)
        except Exception as e:  # noqa: BLE001
            print(f"⚠️ reactions.get fail {label}: {e}", file=sys.stderr)
            reactions = []
        for r in reactions:
            kind = reaction_kind(str(r.get("name") or ""))
            if not kind:
                continue
            users = list(r.get("users") or []) or ["anon"]
            for u in users:
                tallies[label][kind] += 1
                print(f"- {label} {kind} user={u}")
                if not dry:
                    if insert_interest(
                        sb, post_id=post_id, kind=kind, actor=str(u), payload={"name": r.get("name")}
                    ):
                        events += 1
        try:
            replies = fetch_replies(channel, ts, token=token)
        except Exception as e:  # noqa: BLE001
            print(f"⚠️ replies fail {label}: {e}", file=sys.stderr)
            replies = []
        for rep in replies:
            uid = str(rep.get("user") or rep.get("bot_id") or "anon")
            body = (rep.get("text") or "").strip()
            if not body:
                continue
            tallies[label]["comment"] += 1
            print(f"- {label} comment user={uid}: {body[:80]}")
            if not dry:
                if insert_interest(
                    sb,
                    post_id=post_id,
                    kind="comment",
                    actor=uid,
                    text=body,
                ):
                    events += 1

    lines = [
        f"# ニュース興味要約 {now_iso()}",
        "",
        "番頭さん向け。次回選定の参考（👍=plus1／👎=minus1）。",
        "",
    ]
    if not tallies:
        lines.append("（直近の登録投稿なし、または反応なし）")
    else:
        for label, t in sorted(tallies.items()):
            lines.append(
                f"- {label}: 👍{t['plus1']} 👎{t['minus1']} コメント{t['comment']}"
            )
        lines.append("")
        liked = [k for k, t in tallies.items() if t["plus1"] > t["minus1"]]
        disliked = [k for k, t in tallies.items() if t["minus1"] > t["plus1"]]
        if liked:
            lines.append("優先寄り: " + ", ".join(liked))
        if disliked:
            lines.append("抑え寄り: " + ", ".join(disliked))

    write_summary(lines, dry=dry)
    if not dry:
        print(f"✅ interest events touched≈{events}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
