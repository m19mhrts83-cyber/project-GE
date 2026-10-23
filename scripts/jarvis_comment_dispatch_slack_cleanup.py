#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""#report の 317 コメント起動 重複投稿を掃除（最新1通だけ残す）.

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_comment_dispatch_slack_cleanup.py --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_comment_dispatch_slack_cleanup.py --apply

要: SLACK_BOT_TOKEN（chat:history + chat:write。Webhook 投稿の削除権限があること）
既定チャンネル: C0C866FNU3C（#report）／上書き: --channel
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

DEFAULT_CHANNEL = "C0C866FNU3C"
MARKER = "【報告】317 コメント起動"


def _token() -> str:
    return (
        (os.environ.get("SLACK_BOT_TOKEN") or "").strip()
        or (os.environ.get("SLACK_USER_TOKEN") or "").strip()
        or (os.environ.get("SLACK_TOKEN") or "").strip()
    )


def _api_get(method: str, token: str, params: dict[str, str]) -> dict[str, Any]:
    url = f"https://slack.com/api/{method}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=45) as r:
        data = json.loads(r.read().decode("utf-8"))
    if not data.get("ok"):
        raise RuntimeError(f"{method}: {data.get('error')}")
    return data


def _api_post(method: str, token: str, body: dict[str, Any]) -> dict[str, Any]:
    raw = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"https://slack.com/api/{method}",
        data=raw,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=45) as r:
        data = json.loads(r.read().decode("utf-8"))
    if not data.get("ok"):
        raise RuntimeError(f"{method}: {data.get('error')}")
    return data


def collect_targets(
    token: str,
    channel: str,
    *,
    oldest: str | None,
    keep_newest: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (keep, delete) message dicts with ts/text. Newest first."""
    matches: list[dict[str, Any]] = []
    cursor = ""
    while True:
        params: dict[str, str] = {"channel": channel, "limit": "200"}
        if oldest:
            params["oldest"] = oldest
        if cursor:
            params["cursor"] = cursor
        data = _api_get("conversations.history", token, params)
        for m in data.get("messages") or []:
            text = str(m.get("text") or "")
            if MARKER not in text:
                continue
            matches.append(
                {
                    "ts": m.get("ts"),
                    "text": text[:120],
                    "user": m.get("user") or m.get("bot_id"),
                }
            )
        cursor = (data.get("response_metadata") or {}).get("next_cursor") or ""
        if not cursor:
            break
        time.sleep(0.35)
    keep_n = max(1, keep_newest)
    return matches[:keep_n], matches[keep_n:]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", default=True)
    ap.add_argument("--apply", action="store_true", help="実際に chat.delete")
    ap.add_argument("--channel", default=DEFAULT_CHANNEL)
    ap.add_argument("--oldest", default="1792600000", help="Unix ts（これ以降だけ）")
    ap.add_argument("--keep", type=int, default=1, help="残す最新件数")
    args = ap.parse_args()
    dry = not args.apply

    token = _token()
    if not token:
        print(
            "❌ SLACK_BOT_TOKEN がありません（Mac の .env.jarvis_private）",
            file=sys.stderr,
        )
        return 2

    keep, delete = collect_targets(
        token, args.channel, oldest=args.oldest, keep_newest=args.keep
    )
    print("📎 317 Slack cleanup #report")
    print(f"- match: {len(keep) + len(delete)}／keep={len(keep)}／delete={len(delete)}")
    for m in keep:
        print(f"  keep ts={m['ts']} {m['text'][:60]}")
    for m in delete[:5]:
        print(f"  del  ts={m['ts']} {m['text'][:60]}")
    if len(delete) > 5:
        print(f"  … and {len(delete) - 5} more")

    if dry:
        print("# dry-run: --apply で削除")
        return 0

    ok_n = 0
    fail_n = 0
    for m in delete:
        ts = m.get("ts")
        if not ts:
            continue
        try:
            _api_post("chat.delete", token, {"channel": args.channel, "ts": ts})
            ok_n += 1
        except (urllib.error.HTTPError, RuntimeError) as e:
            fail_n += 1
            print(f"FAIL ts={ts} {e}", file=sys.stderr)
        time.sleep(0.4)
    print(f"- deleted={ok_n} fail={fail_n}")
    return 0 if fail_n == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
