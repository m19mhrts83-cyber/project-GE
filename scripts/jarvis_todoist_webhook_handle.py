#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Todoist Webhook 未処理イベントを拾って報告／返信／要フォロー連動する。

入口: Supabase jarvis-dashboard `todoist_webhook_events`
  - note:added … コメント（表示:ヒント／チャット）
  - item:completed … 要フォロー完了 → ホームから外す（表示:抑制不要）
確認: Jarvis 分身トークンでコメント返信（対外メールではない）
履歴: Todoist コメント + `processed_at` + watch payload.user_ack
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


def _fetch_unprocessed(*, limit: int, event_name: str = "note:added") -> list[dict[str, Any]]:
    qs = (
        "todoist_webhook_events"
        "?select=id,delivery_id,event_name,user_id,event_data,initiator,created_at,processed_at"
        f"&event_name=eq.{urllib.parse.quote(event_name)}"
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
    # item:completed は event_data がタスク本体そのもの、のことがある
    if not item and ed.get("content"):
        item = ed
    initiator = row.get("initiator") if isinstance(row.get("initiator"), dict) else {}
    posted_uid = str(ed.get("posted_uid") or initiator.get("id") or "")
    return {
        "row_id": row.get("id"),
        "event_name": str(row.get("event_name") or ""),
        "created_at": row.get("created_at"),
        "task_id": str(ed.get("item_id") or item.get("id") or ed.get("id") or ""),
        "task_title": str(item.get("content") or ed.get("content") or ""),
        "task_url": str(ed.get("url") or item.get("url") or ""),
        "comment_id": str(ed.get("id") or ""),
        "comment": str(ed.get("content") or "").strip()
        if str(row.get("event_name") or "") == "note:added"
        else "",
        "posted_uid": posted_uid,
        "from_name": str(initiator.get("full_name") or ""),
        "from_email": str(initiator.get("email") or ""),
    }


def _process_item_completed(*, limit: int) -> int:
    """要フォロータスクの完了 → ホームから外す（表示:抑制不要）。"""
    try:
        from jarvis_watch_todoist_sync import (
            ack_watch_on_todoist_complete,
            watch_id_from_task_title,
            _load_yaml,
            _sync_cfg,
            _load_state,
        )
    except Exception as exc:
        print(f"{LOG}: complete import skip: {exc}", file=sys.stderr)
        return 0

    quiet = int((_sync_cfg(_load_yaml()).get("quiet_days") or 7))
    state = _load_state()
    by_watch = dict(state.get("todoist_by_watch_id") or {})
    tid_to_wid = {
        str(v.get("task_id") or ""): wid
        for wid, v in by_watch.items()
        if isinstance(v, dict) and v.get("task_id")
    }

    n = 0
    for row in _fetch_unprocessed(limit=max(1, limit), event_name="item:completed"):
        s = _summarize(row)
        rid = int(s["row_id"])
        tid = s["task_id"]
        title = s["task_title"]
        if not title and tid:
            try:
                req = urllib.request.Request(
                    f"{DEFAULT_API}/tasks/{urllib.parse.quote(tid)}",
                    headers={
                        "Authorization": f"Bearer {_todoist_token()}",
                        "Accept": "application/json",
                    },
                    method="GET",
                )
                with urllib.request.urlopen(req, timeout=30) as r:
                    tdata = json.loads(r.read().decode("utf-8"))
                title = str(tdata.get("content") or "")
            except Exception:
                # 完了済みは 404 になりうる → mapping / タイトル無しならスキップ処理済み
                pass
        wid = watch_id_from_task_title(title) if title else None
        if not wid and tid:
            wid = tid_to_wid.get(tid)
        if not wid:
            # 要フォロー以外の完了 → そのまま消化
            _mark_processed(rid)
            continue
        try:
            res = ack_watch_on_todoist_complete(
                wid, task_id=tid or None, quiet_days=quiet
            )
            _mark_processed(rid)
            n += 1
            print(
                f"{LOG}: item:completed → home外し watch={wid} "
                f"task={tid} ok={res.get('ok')}"
            )
        except Exception as exc:
            print(f"{LOG}: complete FAIL {wid}: {exc}", file=sys.stderr)
    return n


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

    # 要フォロー完了 → ホームから外す（何もしなくてよい本線）
    completed_n = _process_item_completed(limit=max(1, args.limit))
    if completed_n:
        print(f"{LOG}: 完了連動 {completed_n}件")

    # 要フォロー表示学習（Phase2）— reply 待ちなしで定型コメントを処理
    try:
        from jarvis_watch_todoist_sync import (
            apply_display_hint,
            parse_display_hint_comment,
            watch_id_from_task_title,
            _load_yaml,
            _sync_cfg,
        )

        hint_quiet = int(
            (_sync_cfg(_load_yaml()).get("display_hint_quiet_days") or 30)
        )
    except Exception as exc:
        apply_display_hint = None  # type: ignore
        parse_display_hint_comment = None  # type: ignore
        watch_id_from_task_title = None  # type: ignore
        hint_quiet = 30
        print(f"{LOG}: display_hint import skip: {exc}", file=sys.stderr)

    skip_uids = set() if args.include_self else _jarvis_uids()
    rows = _fetch_unprocessed(limit=max(1, args.limit), event_name="note:added")
    items: list[dict[str, Any]] = []
    for row in rows:
        s = _summarize(row)
        if s["posted_uid"] in skip_uids:
            # 自分の配信は既定で処理済み扱いにして溜めない（--reply / --mark-only を待たない）
            _mark_processed(int(s["row_id"]))
            continue
        if not s["comment"]:
            if args.mark_only or args.reply:
                _mark_processed(int(s["row_id"]))
            continue

        # 定型「表示: …」→ display_hints（要フォロータスクのみ）
        if (
            apply_display_hint
            and parse_display_hint_comment
            and watch_id_from_task_title
        ):
            action = parse_display_hint_comment(s["comment"])
            title = s["task_title"]
            if action and not title and s["task_id"]:
                try:
                    req = urllib.request.Request(
                        f"{DEFAULT_API}/tasks/{urllib.parse.quote(s['task_id'])}",
                        headers={
                            "Authorization": f"Bearer {_todoist_token()}",
                            "Accept": "application/json",
                        },
                        method="GET",
                    )
                    with urllib.request.urlopen(req, timeout=30) as r:
                        tdata = json.loads(r.read().decode("utf-8"))
                    title = str(tdata.get("content") or "")
                    s["task_title"] = title
                except Exception:
                    pass
            wid = watch_id_from_task_title(title) if action else None
            if action and wid:
                try:
                    apply_display_hint(wid, action=action, quiet_days=hint_quiet)
                    if args.reply and s["task_id"]:
                        _todoist_comment(
                            s["task_id"],
                            f"サマリ: 表示ヒントを反映しました（{action} / {wid}）",
                        )
                    _mark_processed(int(s["row_id"]))
                    print(
                        f"{LOG}: display_hint {action} watch={wid} "
                        f"task={s['task_id']}"
                    )
                    continue
                except Exception as exc:
                    print(
                        f"{LOG}: display_hint FAIL {wid}: {exc}",
                        file=sys.stderr,
                    )

        items.append(s)

    if not items:
        if not completed_n:
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
