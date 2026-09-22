#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Todoist Webhook 未処理コメントを拾って報告／返信する。

入口: Supabase jarvis-dashboard `todoist_webhook_events`（note:added）
確認: Jarvis 分身トークンでコメント返信（対外メールではない）
履歴: Todoist コメント + `processed_at`
停止: JARVIS_TODOIST_WEBHOOK_HANDLE_DISABLE=1 / 自分投稿はスキップ

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_webhook_handle.py
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_webhook_handle.py --reply
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_webhook_handle.py --mark-only

Cursor チャット即時: 会話中に本スクリプトを実行（または「書いた」で Jarvis が実行）。
常時自動は launchd／/loop が別途必要（Webhook だけでは Cursor は起きない）。
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
from typing import Any

JST = timezone(timedelta(hours=9))
DEFAULT_API = "https://api.todoist.com/api/v1"
# Jarvis 分身（Webhook initiator / posted_uid）
JARVIS_UID_DEFAULT = "60814751"
LOG = "📎 Todoist Webhookコメント"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _sb() -> tuple[str, str]:
    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").rstrip("/")
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        raise SystemExit("ERROR: JARVIS_SUPABASE_URL / SERVICE_ROLE_KEY 未設定")
    return url, key


def _sb_req(
    method: str,
    path_qs: str,
    *,
    body: dict[str, Any] | list[Any] | None = None,
    prefer: str | None = None,
) -> Any:
    base, key = _sb()
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{base}/rest/v1/{path_qs}",
        data=data,
        headers=headers,
        method=method,
    )
    with urllib.request.urlopen(req, timeout=45) as r:
        raw = r.read()
        if not raw:
            return None
        return json.loads(raw.decode("utf-8"))


def _todoist_token() -> str:
    tok = (os.environ.get("TODOIST_API_TOKEN") or "").strip()
    if not tok:
        raise SystemExit("ERROR: TODOIST_API_TOKEN 未設定")
    return tok


def _todoist_comment(task_id: str, text: str) -> None:
    payload = json.dumps({"task_id": task_id, "content": text}).encode("utf-8")
    req = urllib.request.Request(
        f"{DEFAULT_API}/comments",
        data=payload,
        headers={
            "Authorization": f"Bearer {_todoist_token()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=45) as r:
        r.read()


def _jarvis_uids() -> set[str]:
    raw = (os.environ.get("TODOIST_JARVIS_USER_IDS") or JARVIS_UID_DEFAULT).strip()
    return {x.strip() for x in raw.split(",") if x.strip()}


def _fetch_unprocessed(*, limit: int) -> list[dict[str, Any]]:
    qs = (
        "todoist_webhook_events"
        "?select=id,delivery_id,event_name,user_id,event_data,initiator,created_at,processed_at"
        "&event_name=eq.note:added"
        "&processed_at=is.null"
        "&order=created_at.asc"
        f"&limit={limit}"
    )
    rows = _sb_req("GET", qs) or []
    return list(rows) if isinstance(rows, list) else []


def _mark_processed(row_id: int) -> None:
    _sb_req(
        "PATCH",
        f"todoist_webhook_events?id=eq.{row_id}",
        body={"processed_at": _now_iso()},
        prefer="return=minimal",
    )


def _summarize(row: dict[str, Any]) -> dict[str, Any]:
    ed = row.get("event_data") or {}
    if not isinstance(ed, dict):
        ed = {}
    item = ed.get("item") if isinstance(ed.get("item"), dict) else {}
    initiator = row.get("initiator") if isinstance(row.get("initiator"), dict) else {}
    posted_uid = str(ed.get("posted_uid") or initiator.get("id") or "")
    return {
        "row_id": row.get("id"),
        "created_at": row.get("created_at"),
        "task_id": str(ed.get("item_id") or item.get("id") or ""),
        "task_title": str(item.get("content") or ""),
        "task_url": str(ed.get("url") or ""),
        "comment_id": str(ed.get("id") or ""),
        "comment": str(ed.get("content") or "").strip(),
        "posted_uid": posted_uid,
        "from_name": str(initiator.get("full_name") or ""),
        "from_email": str(initiator.get("email") or ""),
    }


def main() -> int:
    if (os.environ.get("JARVIS_TODOIST_WEBHOOK_HANDLE_DISABLE") or "").strip() == "1":
        print(f"{LOG}: disabled")
        return 0

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument(
        "--reply",
        action="store_true",
        help="未処理の人コメントに Todoist 返信を付けて processed にする",
    )
    ap.add_argument(
        "--mark-only",
        action="store_true",
        help="返信せず processed_at だけ付ける（既にチャット対応済みのとき）",
    )
    ap.add_argument(
        "--include-self",
        action="store_true",
        help="Jarvis 自身のコメントも対象にする（通常は不要）",
    )
    args = ap.parse_args()

    skip_uids = set() if args.include_self else _jarvis_uids()
    rows = _fetch_unprocessed(limit=max(1, args.limit))
    items: list[dict[str, Any]] = []
    for row in rows:
        s = _summarize(row)
        if not s["comment"]:
            if args.mark_only or args.reply:
                _mark_processed(int(s["row_id"]))
            continue
        if s["posted_uid"] in skip_uids:
            # 自分の配信は既定で処理済み扱いにして溜めない
            if args.mark_only or args.reply:
                _mark_processed(int(s["row_id"]))
            continue
        items.append(s)

    if not items:
        print(f"{LOG}: 未処理の人コメントなし")
        return 0

    print(f"{LOG}")
    print(f"- 件数: {len(items)}")
    for s in items:
        print(f"- [{s['row_id']}] {s['task_title'][:60]}")
        print(f"  from: {s['from_name'] or s['from_email'] or s['posted_uid']}")
        print(f"  comment: {s['comment'][:200]}")
        print(f"  task: {s['task_url'] or s['task_id']}")

    if not args.reply and not args.mark_only:
        print("次: --reply で Todoist 返信＋processed／既対応なら --mark-only")
        return 0

    for s in items:
        rid = int(s["row_id"])
        tid = s["task_id"]
        if args.reply and tid:
            body = (
                "サマリ: コメントを受信しました（Webhook）。"
                f"「{s['comment'][:80]}」を確認しました。"
                "チャットでも対応します。"
            )
            try:
                _todoist_comment(tid, body)
            except urllib.error.HTTPError as e:
                print(f"{LOG}: FAIL reply task={tid} HTTP {e.code}", file=sys.stderr)
                return 1
        _mark_processed(rid)
        print(f"- processed id={rid}" + (" +reply" if args.reply else ""))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
