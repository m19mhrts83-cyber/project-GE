#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""312 Slack返信 → Todoist起票（クラウド常駐・GitHub Actions 用）

#consult の最新ダイジェストと、それへの人の返信を読み、
「2」「起票して 1,3」「全部見送り」を解釈して Todoist に create する。

設計の要点:
- 状態ファイルを持たない（公開リポジトリのため）。冪等性は Todoist 側の
  「同じタイトルのタスクが既にあるか」で担保する。
- 秘密は環境変数のみ（SLACK_BOT_TOKEN / TODOIST_API_TOKEN）。
- 失敗は Slack に返信し、標準エラーにも出す。

  python3 scripts/jarvis_todoist_312_slack_ingest.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any

JST = timezone(timedelta(hours=9))
DIGEST_MARKER = "起票してよければ番号で返信"
DEFAULT_CHANNEL = "C0C7R0UF3MM"
LOOKBACK_HOURS = 48
LANE = "ai_raimo"
AGENT = "312"


def _now() -> datetime:
    return datetime.now(JST)


def _slack(method: str, params: dict[str, Any], token: str) -> dict[str, Any]:
    url = f"https://slack.com/api/{method}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def _slack_post(payload: dict[str, Any], token: str) -> dict[str, Any]:
    req = urllib.request.Request(
        "https://slack.com/api/chat.postMessage",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def _todoist(path: str, token: str, *, method: str = "GET", body: dict | None = None) -> Any:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        f"https://api.todoist.com/api/v1/{path}",
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method=method,
    )
    with urllib.request.urlopen(req, timeout=25) as r:
        raw = r.read().decode()
        return json.loads(raw) if raw.strip() else {}


def _clean(title: str) -> str:
    t = re.sub(r"\s+", " ", str(title or "")).strip()
    t = re.sub(r"\s*[—–-]\s*状況[:：].*$", "", t)
    t = re.sub(r"[（(]状況[:：][^）)]*[）)]", "", t)
    return t.strip().rstrip("。．.")


def parse_digest(text: str) -> dict[int, dict[str, str]]:
    items: dict[int, dict[str, str]] = {}
    for line in (text or "").splitlines():
        m = re.match(r"^\*(\d+)\.\*\s+(.+?)(?:\s+·\s+<([^|>]+)\|[^>]*>)?\s*$", line)
        if not m:
            continue
        items[int(m.group(1))] = {
            "title": _clean(m.group(2)),
            "url": m.group(3) or "",
        }
    return items


def parse_reply(text: str) -> dict[str, Any] | None:
    t = (text or "").strip()
    if not t:
        return None
    if re.search(r"全部見送り|見送りで", t):
        return {"skip": True}
    m = re.match(r"^(?:起票して\s*)?([0-9]+(?:\s*[,、]\s*[0-9]+)*)$", t)
    if not m:
        return None
    return {"nums": [int(x) for x in re.split(r"[,、]", m.group(1))]}


def _task_title(item: dict[str, str]) -> str:
    return f"[{AGENT}][{LANE}] {item['title']}"


def _exists(title: str, token: str) -> str | None:
    """同じタイトルの未完了タスクがあるか（補助的な二重起票よけ）。"""
    targets = {_clean(title)}
    rows: list[dict[str, Any]] = []
    for path in ("tasks/filter?query=%40quick", "tasks?limit=200"):
        try:
            data = _todoist(path, token)
        except urllib.error.HTTPError:
            continue
        part = data.get("results") if isinstance(data, dict) else data
        if isinstance(part, list):
            rows.extend(part)
    for row in rows:
        if _clean(row.get("content", "")) in targets:
            return str(row.get("id"))
    return None


def create_task(item: dict[str, str], token: str, *, dry_run: bool) -> dict[str, Any]:
    title = _task_title(item)
    already = _exists(title, token)
    if already:
        return {"ok": True, "skipped": True, "id": already, "title": title}
    if dry_run:
        return {"ok": True, "dry_run": True, "title": title}
    desc = "312 Slack返信トリガーの①create"
    if item.get("url"):
        desc += f"\n出典: {item['url']}"
    task = _todoist(
        "tasks",
        token,
        method="POST",
        body={"content": title, "labels": ["SecondBrain", "quick"], "description": desc},
    )
    tid = str(task.get("id") or "")
    if not tid:
        return {"ok": False, "error": json.dumps(task)[:200], "title": title}
    comment = (
        "【FRIDAY】\n"
        "サマリ: 312 Slack返信トリガーの①create\n"
        "アウトプット:\n"
        f"- [会議]({item.get('url') or 'https://app.todoist.com'})\n"
    )
    try:
        _todoist("comments", token, method="POST", body={"task_id": tid, "content": comment})
    except urllib.error.HTTPError as e:
        print(f"comment failed: {e}", file=sys.stderr)
    return {"ok": True, "id": tid, "title": title}


def _replies(channel: str, ts: str, token: str) -> list[dict[str, Any]]:
    """ダイジェストのスレッド（親＋返信）を取る。"""
    res = _slack("conversations.replies", {"channel": channel, "ts": ts, "limit": 200}, token)
    if not res.get("ok"):
        raise RuntimeError(res.get("error") or "conversations.replies failed")
    return res.get("messages", [])


def _handled_nums(bot_texts: list[str]) -> set[int]:
    done: set[int] = set()
    for text in bot_texts:
        for n in re.findall(r"#(\d+)\s*(?:✅|済)", text or ""):
            done.add(int(n))
    return done


def run(*, dry_run: bool, channel: str, slack_token: str, todoist_token: str) -> int:
    oldest = str(int((_now() - timedelta(hours=LOOKBACK_HOURS)).timestamp()))
    hist = _slack(
        "conversations.history",
        {"channel": channel, "oldest": oldest, "limit": 100},
        slack_token,
    )
    if not hist.get("ok"):
        print(f"slack error: {hist.get('error')}", file=sys.stderr)
        return 2
    msgs = sorted(hist.get("messages", []), key=lambda m: float(m["ts"]))

    digest = next((m for m in reversed(msgs) if DIGEST_MARKER in (m.get("text") or "")), None)
    if not digest:
        print("no digest in window")
        return 0
    items = parse_digest(digest.get("text") or "")
    thread = _replies(channel, digest["ts"], slack_token)
    print(f"digest ts={digest['ts']} items={len(items)} thread={len(thread)}")

    bot_texts = [m.get("text") or "" for m in thread if m.get("bot_id")]
    handled = _handled_nums(bot_texts)
    humans = [
        m for m in thread
        if float(m["ts"]) > float(digest["ts"]) and not m.get("bot_id") and not m.get("subtype")
    ]

    created: list[str] = []
    for m in humans:
        cmd = parse_reply(m.get("text") or "")
        if not cmd:
            continue
        if cmd.get("skip"):
            if any("見送りで了解" in x for x in bot_texts):
                continue
            print(f"skip reply ts={m['ts']}")
            if not dry_run:
                _slack_post(
                    {"channel": channel, "thread_ts": digest["ts"], "text": "見送りで了解（登録しません）"},
                    slack_token,
                )
            continue

        lines: list[str] = []
        for n in cmd["nums"]:
            if n in handled:
                lines.append(f"#{n} は処理済み")
                continue
            item = items.get(n)
            if not item:
                lines.append(f"#{n} は番号が見つかりません")
                continue
            res = create_task(item, todoist_token, dry_run=dry_run)
            if res.get("ok"):
                mark = "済" if res.get("skipped") else "✅"
                lines.append(f"#{n} {mark} {res['title']}")
                created.append(res["title"])
                handled.add(n)
            else:
                lines.append(f"#{n} ❌ {res.get('error', '')[:80]}")
        if not dry_run and lines:
            try:
                _slack_post(
                    {
                        "channel": channel,
                        "thread_ts": digest["ts"],
                        "text": "\n".join(lines) + "\n`312 cloud chain`",
                    },
                    slack_token,
                )
            except Exception as e:  # noqa: BLE001
                print(f"slack reply failed: {e}", file=sys.stderr)
        for line in lines:
            print("  " + line)
    print(f"done: created/skipped={len(created)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="312 Slack返信 → Todoist起票")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--channel", default=os.environ.get("SLACK_CHANNEL_ID", DEFAULT_CHANNEL))
    args = p.parse_args(argv)

    slack_token = (os.environ.get("SLACK_BOT_TOKEN") or "").strip()
    todoist_token = (os.environ.get("TODOIST_API_TOKEN") or "").strip()
    if not slack_token or not todoist_token:
        print("SLACK_BOT_TOKEN / TODOIST_API_TOKEN がありません", file=sys.stderr)
        return 2
    return run(
        dry_run=bool(args.dry_run),
        channel=args.channel,
        slack_token=slack_token,
        todoist_token=todoist_token,
    )


if __name__ == "__main__":
    raise SystemExit(main())
