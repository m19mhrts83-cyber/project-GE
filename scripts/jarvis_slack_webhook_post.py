#!/usr/bin/env python3
"""Post a simple message to Slack Incoming Webhook (AIエージェントチーム).

Secrets (`.env.jarvis_private`):
  SLACK_WEBHOOK_AI_TEAM_REPORT / CONSULT / OPS
未設定チャンネルは REPORT にフォールバック（本文先頭に 【#consult】等を付ける）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request


def _webhook_for(channel: str) -> tuple[str, str, bool]:
    """Return (url, resolved_channel, used_fallback)."""
    ch = (channel or "report").strip().lstrip("#").lower()
    if ch not in ("report", "consult", "ops"):
        ch = "report"
    env_map = {
        "report": "SLACK_WEBHOOK_AI_TEAM_REPORT",
        "consult": "SLACK_WEBHOOK_AI_TEAM_CONSULT",
        "ops": "SLACK_WEBHOOK_AI_TEAM_OPS",
    }
    url = (os.environ.get(env_map[ch]) or "").strip()
    if url:
        return url, ch, False
    # fallback: REPORT（consult/ops 専用 Webhook が無いとき）
    report = (os.environ.get("SLACK_WEBHOOK_AI_TEAM_REPORT") or "").strip()
    if report and ch != "report":
        return report, "report", True
    if report:
        return report, "report", False
    return "", ch, False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--channel",
        default="report",
        help="論理名: report | consult | ops（Webhook URL の選択。投稿先はWebhook作成時に固定）",
    )
    ap.add_argument("--text", required=True, help="投稿本文")
    ap.add_argument(
        "--username",
        default="Jarvis AI Team",
        help="表示名（Incoming Webhook が許可する場合）",
    )
    args = ap.parse_args()

    requested = (args.channel or "report").strip().lstrip("#").lower()
    url, resolved, fallback = _webhook_for(args.channel)
    if not url:
        print(
            "❌ Webhook URL がありません。"
            " .env.jarvis_private に SLACK_WEBHOOK_AI_TEAM_REPORT"
            "（任意: CONSULT / OPS）を設定してください。",
            file=sys.stderr,
        )
        return 2

    text = args.text
    if fallback and requested != resolved:
        text = f"【#{requested}】\n{text}"

    payload = {"text": text, "username": args.username}
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
            fb = " fallback→#report" if fallback else ""
            print(
                f"✅ Slack webhook OK status={resp.status} "
                f"requested=#{requested} resolved=#{resolved}{fb} body={body!r}"
            )
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
