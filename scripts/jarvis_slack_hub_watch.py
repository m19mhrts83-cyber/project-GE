#!/usr/bin/env python3
"""Slack ハブ監視 — Cursor（Jarvis）が #consult/#ops/#report の変化に気づくための state／ヒント。

本線のメッセージ読取は **Cursor Slack MCP**（`slack_read_channel`）。
本スクリプトは channel ID・前回既読・報告ブロック整形・`--mark-prompted` を担う。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_slack_hub_watch.py
  ~/selenium_env/venv/bin/python scripts/jarvis_slack_hub_watch.py --hints
  ~/selenium_env/venv/bin/python scripts/jarvis_slack_hub_watch.py --mark-prompted \\
    --summary 'consult: 315未解決 / report: （なし）'

任意: SLACK_BOT_TOKEN または SLACK_USER_TOKEN があれば Web API で差分取得可
（未設定なら MCP ヒントだけ出して exit 0）。

無効化: JARVIS_SLACK_HUB_WATCH_DISABLE=1 または state disabled: true
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[1]
CONFIG = REPO / "config" / "slack_ai_team_hub.yaml"
STATE = REPO / ".jarvis_state" / "slack_hub_watch.json"
JST = timezone(timedelta(hours=9))


def now_iso() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def load_config() -> dict[str, Any]:
    if not CONFIG.is_file():
        return {}
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}


def load_state() -> dict[str, Any]:
    if not STATE.is_file():
        return {
            "disabled": False,
            "channels": {},
            "last_prompted_at": None,
            "last_summaries": [],
        }
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"disabled": False, "channels": {}}


def save_state(st: dict[str, Any]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def disabled(st: dict[str, Any]) -> bool:
    if (os.environ.get("JARVIS_SLACK_HUB_WATCH_DISABLE") or "").strip() in (
        "1",
        "true",
        "yes",
    ):
        return True
    return bool(st.get("disabled"))


def slack_token() -> str:
    return (
        (os.environ.get("SLACK_BOT_TOKEN") or "").strip()
        or (os.environ.get("SLACK_USER_TOKEN") or "").strip()
        or (os.environ.get("SLACK_TOKEN") or "").strip()
    )


def api_history(channel_id: str, *, oldest: str | None, limit: int, token: str) -> list[dict]:
    params: dict[str, str] = {"channel": channel_id, "limit": str(limit)}
    if oldest:
        params["oldest"] = oldest
    url = "https://slack.com/api/conversations.history?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if not data.get("ok"):
        raise RuntimeError(data.get("error") or "slack_api_error")
    return list(data.get("messages") or [])


def preview_text(msg: dict[str, Any], max_len: int = 120) -> str:
    text = (msg.get("text") or "").replace("\n", " ").strip()
    if len(text) > max_len:
        text = text[: max_len - 1] + "…"
    return text or "(no text)"


def should_skip_prompt(st: dict[str, Any], cfg: dict[str, Any]) -> bool:
    hours = float(cfg.get("min_hours_between_prompts") or 4)
    last = st.get("last_prompted_at")
    if not last:
        return False
    try:
        dt = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=JST)
    except ValueError:
        return False
    return datetime.now(JST) - dt.astimezone(JST) < timedelta(hours=hours)


def print_hints(cfg: dict[str, Any], st: dict[str, Any]) -> None:
    chans = cfg.get("channels") or {}
    order = cfg.get("read_priority") or list(chans.keys())
    limit = int(cfg.get("limit_per_channel") or 8)
    print("📎 Slackハブ監視 — MCP読取ヒント")
    print("- 本線: Cursor Slack MCP `slack_read_channel`")
    print(f"- limit目安: {limit}/ch")
    for name in order:
        meta = chans.get(name) or {}
        cid = meta.get("id") or ""
        seen = (st.get("channels") or {}).get(name) or {}
        print(f"- #{name}: channel_id={cid} last_ts={seen.get('last_ts') or '（初回）'}")
    print("- 読後: --mark-prompted --summary '…' で state 更新")
    print("- 正本: docs/AIエージェントチーム/37_Slackハブ_Jarvis読取_20261018.md")


def run_api_digest(cfg: dict[str, Any], st: dict[str, Any], token: str) -> list[str]:
    chans = cfg.get("channels") or {}
    order = cfg.get("read_priority") or list(chans.keys())
    limit = int(cfg.get("limit_per_channel") or 8)
    lines: list[str] = []
    ch_state = dict(st.get("channels") or {})
    for name in order:
        meta = chans.get(name) or {}
        cid = str(meta.get("id") or "").strip()
        if not cid:
            continue
        prev = ch_state.get(name) or {}
        oldest = prev.get("last_ts")
        try:
            msgs = api_history(cid, oldest=oldest, limit=limit, token=token)
        except (urllib.error.URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as e:
            lines.append(f"- #{name}: API失敗（{e}）→ MCP で読んでください")
            continue
        # Slack は新しい順。oldest 指定時は差分。初回は最新だけ要約
        if not oldest:
            msgs = msgs[:3]
        else:
            # oldest 含むことがあるので除外
            msgs = [m for m in msgs if str(m.get("ts") or "") != str(oldest)]
        if not msgs:
            continue
        newest_ts = msgs[0].get("ts")
        for m in msgs[:5]:
            lines.append(f"- #{name}: {preview_text(m)}")
        if newest_ts:
            ch_state[name] = {
                "last_ts": str(newest_ts),
                "last_seen_at": now_iso(),
            }
    st["channels"] = ch_state
    return lines


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--hints", action="store_true", help="MCP用 channel_id と last_ts を出す")
    ap.add_argument("--mark-prompted", action="store_true", help="促し済みを記録")
    ap.add_argument("--summary", default="", help="報告に出した要約（mark 時）")
    ap.add_argument("--set-ts", nargs=2, metavar=("CHANNEL", "TS"), help="既読 ts を手動セット")
    ap.add_argument("--force", action="store_true", help="間隔無視でヒント／API読取")
    args = ap.parse_args()

    cfg = load_config()
    st = load_state()
    if disabled(st):
        return 0

    if args.set_ts:
        name, ts = args.set_ts
        ch = dict(st.get("channels") or {})
        ch[name] = {"last_ts": ts, "last_seen_at": now_iso()}
        st["channels"] = ch
        save_state(st)
        print(f"updated #{name} last_ts={ts}")
        return 0

    if args.mark_prompted:
        st["last_prompted_at"] = now_iso()
        if args.summary.strip():
            hist = list(st.get("last_summaries") or [])
            hist.insert(0, {"at": now_iso(), "summary": args.summary.strip()})
            st["last_summaries"] = hist[:20]
        save_state(st)
        print("📎 Slackハブ監視: prompted 記録済み")
        return 0

    if args.hints or not slack_token():
        if should_skip_prompt(st, cfg) and not args.force and not args.hints:
            return 0
        print_hints(cfg, st)
        if args.hints:
            return 0
        # no token: hints only
        return 0

    if should_skip_prompt(st, cfg) and not args.force:
        return 0

    try:
        lines = run_api_digest(cfg, st, slack_token())
    except Exception as e:  # noqa: BLE001
        print(f"📎 Slackハブ監視: APIエラー — {e}", file=sys.stderr)
        print_hints(cfg, st)
        return 0

    if not lines:
        return 0

    print("📎 Slackハブ差分（API）")
    for ln in lines:
        print(ln)
    print("次: 必要なら本題に相乗り提案。--mark-prompted で記録")
    save_state(st)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
