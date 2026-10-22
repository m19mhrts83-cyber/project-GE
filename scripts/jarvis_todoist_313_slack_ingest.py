#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""313 Slack返信 → 完了 close ／ 期日リスケ（クラウド常駐・GitHub Actions 用）

#consult の 313 投稿（完了候補＝✅／期日超過＝📅）とスレ返信を読み、
「✅1,3」「閉じて ✅2」「📅2,5」「リスケ 📅1」を解釈して Todoist を更新する。

設計の要点:
- 完了候補と期日超過は **別投稿**＋**記号付き番号**で区別（スレ混在でも安全）
- 状態ファイルを持たない（公開リポジトリのため）。冪等は Bot 返信の処理済み印
- 秘密は環境変数のみ（SLACK_BOT_TOKEN / TODOIST_API_TOKEN）

  python3 scripts/jarvis_todoist_313_slack_ingest.py --dry-run
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
CLOSE_MARKER = "閉じてよければ ✅番号で返信"
OVERDUE_MARKER = "リスケしてよければ 📅番号で返信"
DEFAULT_CHANNEL = "C0C7R0UF3MM"
LOOKBACK_HOURS = 48
AGENT = "313"
CLOSE_MARK = "✅"
OVERDUE_MARK = "📅"


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


def parse_close_digest(text: str) -> dict[int, dict[str, str]]:
    """*✅1.* <url|title> _(lane)_"""
    items: dict[int, dict[str, str]] = {}
    for line in (text or "").splitlines():
        m = re.match(
            rf"^\*{re.escape(CLOSE_MARK)}(\d+)\.\*\s+"
            r"<(https://app\.todoist\.com/app/task/[^|>]+)\|([^>]+)>"
            r"(?:\s+_?\(([^)]*)\)_?)?\s*$",
            line,
        )
        if not m:
            continue
        items[int(m.group(1))] = {
            "task_id": m.group(2).rstrip("/").rsplit("/", 1)[-1],
            "title": m.group(3).strip(),
            "lane": (m.group(4) or "").strip(),
        }
    return items


def parse_overdue_digest(text: str) -> dict[int, dict[str, str]]:
    """*📅1.* <url|title> … の次行 → *YYYY-MM-DD* へ"""
    items: dict[int, dict[str, str]] = {}
    lines = (text or "").splitlines()
    for i, line in enumerate(lines):
        m = re.match(
            rf"^\*{re.escape(OVERDUE_MARK)}(\d+)\.\*\s+"
            r"<(https://app\.todoist\.com/app/task/[^|>]+)\|([^>]+)>",
            line,
        )
        if not m:
            continue
        n = int(m.group(1))
        new_due = ""
        if i + 1 < len(lines):
            dm = re.search(r"\*?(\d{4}-\d{2}-\d{2})\*?", lines[i + 1])
            if dm:
                new_due = dm.group(1)
        items[n] = {
            "task_id": m.group(2).rstrip("/").rsplit("/", 1)[-1],
            "title": m.group(3).strip(),
            "new_due": new_due,
        }
    return items


def parse_reply(text: str, *, kind: str) -> dict[str, Any] | None:
    """kind=close → ✅番号／kind=overdue → 📅番号。記号なし数字は当該スレ種別として解釈。"""
    t = (text or "").strip()
    if not t:
        return None
    if kind == "close" and re.search(r"全部残す|残すで", t):
        return {"skip": True}
    if kind == "overdue" and re.search(r"全部そのまま|そのまま", t):
        return {"skip": True}

    mark = CLOSE_MARK if kind == "close" else OVERDUE_MARK
    other = OVERDUE_MARK if kind == "close" else CLOSE_MARK
    # 他方の記号だけなら無視（誤スレ）
    if other in t and mark not in t:
        return None

    # 「✅1,3」「✅1,✅3」「閉じて ✅2,5」— 当該記号がある返信は数字を全部拾う
    # （他記号の番号は先に除去。L1上限5のため 1〜20 のみ）
    if mark in t:
        cleaned = re.sub(rf"{re.escape(other)}\s*\d+", "", t)
        nums = [int(x) for x in re.findall(r"\d+", cleaned) if 1 <= int(x) <= 20]
        return {"nums": nums} if nums else None

    # 「閉じて 1,3」「リスケ 2」／裸の「1,3」（当該スレ種別として解釈）
    prefix = r"(?:閉じて|close)\s*" if kind == "close" else r"(?:リスケ|reschedule)\s*"
    m = re.match(rf"^(?:{prefix})?([0-9]+(?:\s*[,、]\s*[0-9]+)*)$", t, re.I)
    if not m:
        return None
    return {"nums": [int(x) for x in re.split(r"[,、]", m.group(1))]}


def _replies(channel: str, ts: str, token: str) -> list[dict[str, Any]]:
    res = _slack("conversations.replies", {"channel": channel, "ts": ts, "limit": 200}, token)
    if not res.get("ok"):
        raise RuntimeError(res.get("error") or "conversations.replies failed")
    return res.get("messages", [])


def _handled_nums(bot_texts: list[str], mark: str) -> set[int]:
    done: set[int] = set()
    for text in bot_texts:
        for n in re.findall(rf"{re.escape(mark)}(\d+)\s*(?:✅|済|リスケ済)", text or ""):
            done.add(int(n))
        for n in re.findall(rf"#(\d+)\s*(?:✅|済)", text or ""):
            done.add(int(n))
    return done


def _close_task(item: dict[str, str], token: str, *, dry_run: bool, n: int) -> dict[str, Any]:
    tid = item["task_id"]
    title = item.get("title") or tid
    if dry_run:
        return {"ok": True, "dry_run": True, "title": title, "task_id": tid}
    comment = (
        "【FRIDAY】タスク完了したよ（松野確認OK）\n"
        f"サマリ: {AGENT} Slack返信トリガー — 閉じて {CLOSE_MARK}{n}\n"
        "アウトプット:\n"
        f"- [該当タスク](https://app.todoist.com/app/task/{tid})\n"
    )
    try:
        _todoist("comments", token, method="POST", body={"task_id": tid, "content": comment})
    except urllib.error.HTTPError as e:
        print(f"comment failed: {e}", file=sys.stderr)
    try:
        _todoist(f"tasks/{tid}/close", token, method="POST", body={})
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"close HTTP {e.code}", "title": title, "task_id": tid}
    return {"ok": True, "title": title, "task_id": tid}


def _reschedule(item: dict[str, str], token: str, *, dry_run: bool, n: int) -> dict[str, Any]:
    tid = item["task_id"]
    title = item.get("title") or tid
    new_due = item.get("new_due") or ""
    if not new_due:
        return {"ok": False, "error": "new_due missing", "title": title, "task_id": tid}
    if dry_run:
        return {"ok": True, "dry_run": True, "title": title, "task_id": tid, "new_due": new_due}
    comment = (
        "【FRIDAY】\n"
        f"サマリ: 期日を {new_due} へリスケ（{AGENT} Slack・「リスケ {OVERDUE_MARK}{n}」）\n"
        "アウトプット:\n"
        f"- [該当タスク](https://app.todoist.com/app/task/{tid})\n"
    )
    try:
        _todoist("comments", token, method="POST", body={"task_id": tid, "content": comment})
        _todoist(f"tasks/{tid}", token, method="POST", body={"due_date": new_due})
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.code}", "title": title, "task_id": tid}
    return {"ok": True, "title": title, "task_id": tid, "new_due": new_due}


def _process_thread(
    *,
    kind: str,
    digest: dict[str, Any],
    items: dict[int, dict[str, str]],
    channel: str,
    slack_token: str,
    todoist_token: str,
    dry_run: bool,
) -> int:
    mark = CLOSE_MARK if kind == "close" else OVERDUE_MARK
    thread = _replies(channel, digest["ts"], slack_token)
    print(f"{kind} ts={digest['ts']} items={len(items)} thread={len(thread)}")
    bot_texts = [m.get("text") or "" for m in thread if m.get("bot_id")]
    handled = _handled_nums(bot_texts, mark)
    humans = [
        m
        for m in thread
        if float(m["ts"]) > float(digest["ts"]) and not m.get("bot_id") and not m.get("subtype")
    ]
    acted = 0
    for m in humans:
        cmd = parse_reply(m.get("text") or "", kind=kind)
        if not cmd:
            continue
        if cmd.get("skip"):
            ack = "残すで了解（完了しません）" if kind == "close" else "そのまま了解（期日は変えません）"
            if any(ack[:4] in x for x in bot_texts):
                continue
            print(f"skip reply ts={m['ts']}")
            if not dry_run:
                _slack_post(
                    {"channel": channel, "thread_ts": digest["ts"], "text": ack},
                    slack_token,
                )
            continue

        lines: list[str] = []
        for n in cmd["nums"]:
            if n in handled:
                lines.append(f"{mark}{n} は処理済み")
                continue
            item = items.get(n)
            if not item:
                lines.append(f"{mark}{n} は番号が見つかりません")
                continue
            if kind == "close":
                res = _close_task(item, todoist_token, dry_run=dry_run, n=n)
                if res.get("ok"):
                    lines.append(f"{mark}{n} ✅ {res.get('title', '')[:60]}")
                    handled.add(n)
                    acted += 1
                else:
                    lines.append(f"{mark}{n} ❌ {res.get('error', '')[:80]}")
            else:
                res = _reschedule(item, todoist_token, dry_run=dry_run, n=n)
                if res.get("ok"):
                    lines.append(
                        f"{mark}{n} リスケ済 → {res.get('new_due')} {res.get('title', '')[:40]}"
                    )
                    handled.add(n)
                    acted += 1
                else:
                    lines.append(f"{mark}{n} ❌ {res.get('error', '')[:80]}")
        if not dry_run and lines:
            try:
                _slack_post(
                    {
                        "channel": channel,
                        "thread_ts": digest["ts"],
                        "text": "\n".join(lines) + f"\n`{AGENT} cloud chain`",
                    },
                    slack_token,
                )
            except Exception as e:  # noqa: BLE001
                print(f"slack reply failed: {e}", file=sys.stderr)
        for line in lines:
            print("  " + line)
    return acted


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

    close_digest = next(
        (m for m in reversed(msgs) if CLOSE_MARKER in (m.get("text") or "")), None
    )
    overdue_digest = next(
        (m for m in reversed(msgs) if OVERDUE_MARKER in (m.get("text") or "")), None
    )

    total = 0
    if close_digest:
        items = parse_close_digest(close_digest.get("text") or "")
        total += _process_thread(
            kind="close",
            digest=close_digest,
            items=items,
            channel=channel,
            slack_token=slack_token,
            todoist_token=todoist_token,
            dry_run=dry_run,
        )
    else:
        print("no close digest in window")

    if overdue_digest:
        items = parse_overdue_digest(overdue_digest.get("text") or "")
        total += _process_thread(
            kind="overdue",
            digest=overdue_digest,
            items=items,
            channel=channel,
            slack_token=slack_token,
            todoist_token=todoist_token,
            dry_run=dry_run,
        )
    else:
        print("no overdue digest in window")

    print(f"done: acted={total}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="313 Slack返信 → close／リスケ")
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
