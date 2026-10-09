#!/usr/bin/env python3
"""Post a simple message to Slack Incoming Webhook (AIエージェントチーム).

Secrets: SLACK_WEBHOOK_AI_TEAM_REPORT / SLACK_WEBHOOK_AI_TEAM_OPS in .env.jarvis_private
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request


def _webhook_for(channel: str) -> str:
    ch = (channel or "report").strip().lstrip("#").lower()
    if ch == "ops":
        url = (os.environ.get("SLACK_WEBHOOK_AI_TEAM_OPS") or "").strip()
        if url:
            return url
    url = (os.environ.get("SLACK_WEBHOOK_AI_TEAM_REPORT") or "").strip()
    if not url and ch == "ops":
        url = (os.environ.get("SLACK_WEBHOOK_AI_TEAM_OPS") or "").strip()
    return url


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--channel",
        default="report",
        help="論理名: report | ops（Webhook URL の選択。投稿先チャンネルはWebhook作成時に固定）",
    )
    ap.add_argument("--text", required=True, help="投稿本文")
    ap.add_argument(
        "--username",
        default="Jarvis AI Team",
        help="表示名（Incoming Webhook が許可する場合）",
    )
    args = ap.parse_args()

    url = _webhook_for(args.channel)
    if not url:
        print(
            "❌ Webhook URL がありません。"
            " .env.jarvis_private に SLACK_WEBHOOK_AI_TEAM_REPORT"
            "（ops なら SLACK_WEBHOOK_AI_TEAM_OPS）を設定してください。",
            file=sys.stderr,
        )
        return 2

    payload = {"text": args.text, "username": args.username}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            print(f"✅ Slack webhook OK status={resp.status} body={body!r}")
            return 0
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        print(f"❌ Slack webhook HTTP {e.code}: {err}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"❌ Slack webhook failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
