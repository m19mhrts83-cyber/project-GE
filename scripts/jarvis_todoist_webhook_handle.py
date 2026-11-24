#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Todoist Webhook 未処理イベントを拾って報告／返信／要フォロー連動する。

入口: Supabase jarvis-dashboard `todoist_webhook_events`
  - note:added … コメント（表示:ヒント／チャット）
  - item:completed … 要フォロー完了 → ホームから外す（表示:抑制不要）
確認: Jarvis 分身トークンでコメント返信（対外メールではない）
履歴: Todoist コメント + `processed_at` + watch payload.user_ack
  58_ 段階2: 境界時刻より後の行は status（new→claimed→done/failed/skipped）も回す
  （jarvis_todoist_event_lifecycle.py。3回失敗で failed＋#ops 1通）
停止: JARVIS_TODOIST_WEBHOOK_HANDLE_DISABLE=1 / 自分投稿はスキップ
  段階2だけ止める: JARVIS_TODOIST_EVENT_LIFECYCLE_DISABLE=1

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
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from jarvis_todoist_event_lifecycle import Lifecycle, build_ops_text  # noqa: E402

JST = timezone(timedelta(hours=9))
DEFAULT_API = "https://api.todoist.com/api/v1"
# Jarvis 分身（Webhook initiator / posted_uid）
JARVIS_UID_DEFAULT = "60814751"
LOG = "📎 Todoist Webhookコメント"
# AI 社員が本人トークンで書く記録コメント（投稿者 uid では自分と見分けられない）。人のコメントとして
# 受領を返すと、その返しでまた相手が反応する循環になるので、本文の先頭で見分けて処理済みにする。
# 318 Todoist消化係の【318】（FlowForge 318 node_format_log「317 が【318】コメントを処理しない」）
AGENT_COMMENT_PREFIXES = ("【318】",)


def is_agent_comment(text: str) -> bool:
    """AI 社員の記録コメントか（先頭の空白は無視）。"""
    return str(text or "").lstrip().startswith(AGENT_COMMENT_PREFIXES)


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


_SELECT = "id,delivery_id,event_name,user_id,event_data,initiator,created_at,processed_at"


def _fetch_unprocessed(
    *, limit: int, event_name: str = "note:added", lc: Lifecycle | None = None
) -> list[dict[str, Any]]:
    """境界より前（legacy: processed_at だけ）＋境界より後（段階2: status つき）。"""
    qs = (
        "todoist_webhook_events"
        f"?select={_SELECT}"
        f"&event_name=eq.{urllib.parse.quote(event_name)}"
        "&processed_at=is.null"
        f"{lc.legacy_filter() if lc else ''}"
        "&order=created_at.asc"
        f"&limit={limit}"
    )
    rows = _sb_req("GET", qs) or []
    out = list(rows) if isinstance(rows, list) else []
    if lc and lc.active:
        try:
            out += lc.fetch(event_name=event_name, limit=limit, select=_SELECT)
        except Exception as exc:  # noqa: BLE001
            print(f"{LOG}: lifecycle fetch FAIL {event_name}: {exc}", file=sys.stderr)
    return out


def _begin(row: dict[str, Any], lc: Lifecycle | None) -> bool:
    """書く前に取る（段階2の行だけ）。取れない・同じ event_id が done なら False。"""
    if not (lc and lc.is_tracked(row)):
        return True
    if not lc.claim(row):
        return False
    if lc.already_done(row):
        lc.skipped(row)
        print(f"{LOG}: skipped id={row.get('id')}（同じ event_id が処理済み）")
        return False
    return True


def _ok(row: dict[str, Any], lc: Lifecycle | None) -> None:
    if lc and lc.is_tracked(row):
        lc.done(row)
    else:
        _mark_processed(int(row["id"]))


def _ng(row: dict[str, Any], lc: Lifecycle | None, err: str, *, legacy_mark: bool) -> None:
    """失敗。段階2の行は attempts+1（3回目で failed）。legacy はこれまでどおり。"""
    if lc and lc.is_tracked(row):
        res = lc.fail(row, err)
        print(f"{LOG}: {res} id={row.get('id')} attempts={row.get('attempts')}", file=sys.stderr)
    elif legacy_mark:
        _mark_processed(int(row["id"]))


def _post_ops(text: str) -> int:
    post = Path(__file__).resolve().parent / "jarvis_slack_webhook_post.py"
    r = subprocess.run(
        [
            sys.executable,
            str(post),
            "--channel",
            "ops",
            "--username",
            "317 コメント起動",
            "--signal",
            "red",
            "--text",
            text,
        ],
        timeout=60,
    )
    return int(r.returncode)


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


def _process_item_completed(*, limit: int, lc: Lifecycle | None = None) -> int:
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
    for row in _fetch_unprocessed(limit=max(1, limit), event_name="item:completed", lc=lc):
        if not _begin(row, lc):
            continue
        s = _summarize(row)
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
            _ok(row, lc)
            continue
        try:
            res = ack_watch_on_todoist_complete(
                wid, task_id=tid or None, quiet_days=quiet
            )
            _ok(row, lc)
            n += 1
            print(
                f"{LOG}: item:completed → home外し watch={wid} "
                f"task={tid} ok={res.get('ok')}"
            )
        except Exception as exc:
            print(f"{LOG}: complete FAIL {wid}: {exc}", file=sys.stderr)
            # legacy は processed にしない（次回また拾う）＝これまでどおり
            _ng(row, lc, f"item:completed: {exc}", legacy_mark=False)
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

    # 58_ 段階2: 境界時刻より後の行だけ status を回す（読めなければこの回は legacy だけ）
    lc = Lifecycle.load(_sb_req, init_if_missing=True, log=lambda m: print(f"{LOG}: {m}"))

    # 要フォロー完了 → ホームから外す（何もしなくてよい本線）
    completed_n = _process_item_completed(limit=max(1, args.limit), lc=lc)
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
    rows = _fetch_unprocessed(limit=max(1, args.limit), event_name="note:added", lc=lc)
    items: list[dict[str, Any]] = []
    for row in rows:
        s = _summarize(row)
        s["_row"] = row
        s["_claimed"] = False
        if s["posted_uid"] in skip_uids:
            # 自分の配信は既定で処理済み扱いにして溜めない（--reply / --mark-only を待たない）
            if _begin(row, lc):
                _ok(row, lc)
            continue
        if is_agent_comment(s["comment"]):
            # AI 社員の記録（【318】など）は受領も返さず処理済みにする（循環防止）
            if _begin(row, lc):
                _ok(row, lc)
            continue
        if not s["comment"]:
            if (args.mark_only or args.reply) and _begin(row, lc):
                _ok(row, lc)
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
                if not _begin(row, lc):
                    continue
                s["_claimed"] = True
                try:
                    apply_display_hint(wid, action=action, quiet_days=hint_quiet)
                    if args.reply and s["task_id"]:
                        _todoist_comment(
                            s["task_id"],
                            f"サマリ: 表示ヒントを反映しました（{action} / {wid}）",
                        )
                    _ok(row, lc)
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
                    if not (args.reply or args.mark_only) and lc.is_tracked(row):
                        # 一覧だけの回は取ったまま残さない（再試行に回す）
                        _ng(row, lc, f"display_hint: {exc}", legacy_mark=False)
                        continue

        items.append(s)

    if not items:
        if not completed_n:
            print(f"{LOG}: 未処理の人コメントなし")
        return _finish_lifecycle(lc, 0)

    print(f"{LOG}")
    print(f"- 件数: {len(items)}")
    for s in items:
        print(f"- [{s['row_id']}] {s['task_title'][:60]}")
        print(f"  from: {s['from_name'] or s['from_email'] or s['posted_uid']}")
        print(f"  comment: {s['comment'][:200]}")
        print(f"  task: {s['task_url'] or s['task_id']}")

    if not args.reply and not args.mark_only:
        print("次: --reply で Todoist 返信＋processed／既対応なら --mark-only")
        return _finish_lifecycle(lc, 0)

    # 1件の返信失敗でバッチ全体を止めない（未処理滞留→317 #report 連投の真因）
    reply_fail = 0
    for s in items:
        rid = int(s["row_id"])
        row = s["_row"]
        if not s["_claimed"] and not _begin(row, lc):
            continue
        tid = s["task_id"]
        replied = False
        err = ""
        if args.reply and tid:
            try:
                from jarvis_slack_report_fb_lib import build_todoist_seen_text
            except Exception:
                build_todoist_seen_text = None  # type: ignore
            if build_todoist_seen_text:
                body = build_todoist_seen_text(
                    comment_preview=s["comment"][:80],
                    source="317/Webhook",
                )
            else:
                body = (
                    "【AIチーム】見たよ（受けた）\n"
                    f"引用: {s['comment'][:80]}\n"
                    "チャット／次セッションでも続きを見るよ"
                )
            try:
                _todoist_comment(tid, body)
                replied = True
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    # Jarvis に共有されていない松野個人 PJ のタスク（owner トークンでは見える）。
                    # 松野名義で返信はしない方針なので失敗扱いにせず見送る。
                    print(
                        f"{LOG}: skip reply task={tid} HTTP 404（Jarvis 未共有 PJ）"
                        f"— processed にして滞留させない",
                        file=sys.stderr,
                    )
                else:
                    reply_fail += 1
                    err = f"reply HTTP {e.code}"
                    print(
                        f"{LOG}: FAIL reply task={tid} HTTP {e.code} "
                        f"— processed にして滞留させない",
                        file=sys.stderr,
                    )
            except Exception as exc:
                reply_fail += 1
                err = f"reply {type(exc).__name__}"
                print(
                    f"{LOG}: FAIL reply task={tid} {exc} "
                    f"— processed にして滞留させない",
                    file=sys.stderr,
                )
        if err:
            # legacy はこれまでどおり processed にして滞留させない／段階2は再試行（3回で failed）
            _ng(row, lc, err, legacy_mark=True)
        else:
            _ok(row, lc)
        tag = " +reply" if replied else (" +reply_fail" if args.reply and tid else "")
        st = row.get("status") if lc.is_tracked(row) else "processed"
        print(f"- {st} id={rid}{tag}")

    return _finish_lifecycle(lc, 1 if reply_fail else 0)


def _finish_lifecycle(lc: Lifecycle | None, rc: int) -> int:
    """段階2の集計と、3回失敗した行の #ops 1通。"""
    if not (lc and lc.active):
        return rc
    print(f"{LOG}: lifecycle {json.dumps(lc.counts, ensure_ascii=False)}")
    if lc.failed:
        try:
            _post_ops(build_ops_text(lc.failed))
        except Exception as exc:  # noqa: BLE001
            print(f"{LOG}: #ops 投稿 FAIL: {exc}", file=sys.stderr)
        return 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
