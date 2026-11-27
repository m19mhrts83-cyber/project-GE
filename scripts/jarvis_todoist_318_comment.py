#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""318 Todoist消化係 — Phase 3 準備: 【318】コメントの整形と反映（FlowForge node_format_log・node_comment）.

既定はオフ。`jarvis_todoist_318_triage.py run --write-comments` を明示した本実行だけで動く。

決まり（設計の正本 flow_HMy15MUxWiSpw5QgAPYa_8e4 の説明文）:
- 内部ログの保存に成功した後、変化があって分類し直したタスクだけ。先頭は必ず【318】
- 中身: 処理状態（やり切った／途中／要判断／本人作業）・要約・成果物・残作業／必要な判断。末尾に「処理ID: <run_id>」
- 前回と同じ中身なら書かない（処理ID の行を除いた指紋で比べる）
- 投稿前に Todoist のコメントを読み、同じ処理ID・同じ中身の【318】コメントがあれば書かない。読めなければ書かない
- 応答が分からない（時間切れ・5xx・接続切れ）時は「照合待ち」にして再送しない。次の回にコメントを読んで、
  処理ID が見つかれば投稿済み、無ければ再送してよい（読めなければ照合待ちのまま）
- 送る前に「送信中」を判断履歴へ保存する（途中で落ちても次の回に照合できるように）。保存できなければ送らない
- はっきり失敗した時（4xx）は失敗状態と再試行条件を残し、次の回に重複確認のうえ再送（3回まで）
- 317 が【318】を処理しない（循環しない）ことを毎回確かめる。確かめられなければ書かない
- Todoist に対してやるのはコメントの追記だけ。完了・削除・期限変更の口は作らない
"""
from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any, Callable, Protocol

PREFIX = "【318】"
ID_LABEL = "処理ID: "
POST_CAP = 25  # 1 回に書くコメントの上限（処理 15 件＋古い物・済みらしい分）
MAX_ATTEMPTS = 3
API_BASE = "https://api.todoist.com/api/v1"
# 送ったかどうか分かる失敗（Todoist が受け付けていない）。ほかは「応答不明」として照合待ちにする
DEFINITE_FAIL_HTTP = {400, 401, 403, 404, 410, 413, 422, 429}

STATE_LABEL = {"1": "途中", "2": "要判断", "3": "本人作業"}  # ① は自律実行が未稼働なので「やり切った」にはならない


class Writer(Protocol):
    def post_comment(self, task_id: str, content: str) -> Any: ...


class TodoistCommentWriter:
    """コメントの追記（POST /comments）だけの口。完了・削除・更新のメソッドは作らない。"""

    def __init__(self, token: str, timeout: int = 40):
        self._token = token
        self._timeout = timeout
        self.calls = 0

    def post_comment(self, task_id: str, content: str) -> Any:
        if not str(content).lstrip().startswith(PREFIX):
            raise ValueError("【318】で始まらないコメントは書かない")
        self.calls += 1
        body = json.dumps({"task_id": str(task_id), "content": content}).encode("utf-8")
        req = urllib.request.Request(
            API_BASE + "/comments",
            data=body,
            headers={"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self._timeout) as r:
            raw = r.read().decode("utf-8")
        return json.loads(raw) if raw.strip() else {}


def _h(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def body_sig(body: str) -> str:
    """処理ID の行を除いた中身の指紋（同じ中身かどうか）。"""
    lines = [ln.rstrip() for ln in str(body or "").strip().splitlines() if not ln.strip().startswith(ID_LABEL)]
    return _h("\n".join(lines))


def has_run_id(body: str, run_id: str) -> bool:
    return any(ln.strip() == f"{ID_LABEL}{run_id}" for ln in str(body or "").splitlines())


def guard_317() -> str:
    """317 が【318】コメントを AI の記録として飛ばすか。飛ばさないなら書かない（循環防止が未検証）。"""
    try:
        from jarvis_todoist_webhook_handle import is_agent_comment  # noqa: PLC0415
    except Exception as e:  # noqa: BLE001
        return f"317 の除外を読み込めない（{type(e).__name__}）"
    sample = f"{PREFIX}要判断\n要約: 確認\n{ID_LABEL}r318-test"
    if not is_agent_comment(sample) or not is_agent_comment("  " + sample):
        return "317 が【318】コメントを除外していない"
    try:
        from jarvis_comment_dispatch import is_agent_comment as dispatch_check  # noqa: PLC0415
    except Exception as e:  # noqa: BLE001
        return f"317 の振り分け側の除外を読み込めない（{type(e).__name__}）"
    if not dispatch_check(sample):
        return "317 の振り分け側が【318】コメントを除外していない"
    return ""


def format_comment(entry: dict[str, Any], run_id: str, *, published: bool) -> str:
    """分類した 1 件から【318】コメントを作る（題は書かない。タスクの中に書くので）。"""
    cat = str(entry.get("category") or "2")
    reason = str(entry.get("reason") or "").strip() or "根拠なし"
    lines = [f"{PREFIX}{STATE_LABEL.get(cat, '要判断')}"]
    if cat == "1":
        plan = str((entry.get("planned_action") or {}).get("plan") or "").strip()
        lines += [
            f"要約: AI だけで進められる見込み（{reason[:120]}）。自律実行はまだ動かしていない",
            "成果物: なし",
            "残作業: " + (plan[:200] if plan else "やる内容を決めて実行する（未着手）"),
        ]
    elif cat == "3":
        lines += [
            f"要約: 松野さんの操作が要る（{reason[:120]}）",
            "成果物: なし",
            "残作業: " + ("今週の9件の候補に渡した" if published else "今週の9件にはまだ渡していない"),
        ]
    else:
        lines += [
            f"要約: 松野さんの一言判断が要る（{reason[:120]}）",
            "成果物: なし",
            "必要な判断: " + ("/313/bulk で選ぶ（完了・残す・日を変える・削除）" if published
                          else "判断の画面（/313/bulk）にはまだ載せていない"),
        ]
    if entry.get("large"):
        lines.append("大規模: 既存タスクのまま週次計画へ（ここでは進めない）")
    lines.append(f"{ID_LABEL}{run_id}")
    return "\n".join(lines)


def _classify_error(e: Exception) -> tuple[str, str]:
    """(state, 理由)。state は failed（受け付けられていない）か unknown（応答不明）。"""
    if isinstance(e, urllib.error.HTTPError):
        return ("failed" if e.code in DEFINITE_FAIL_HTTP else "unknown"), f"HTTP {e.code}"
    return "unknown", type(e).__name__


def _comments_of(reader_get: Callable[[str], list[dict]], tid: str) -> list[dict]:
    return reader_get(f"/comments?task_id={urllib.parse.quote(tid)}")


def write_comments(
    run: dict[str, Any],
    hist_tasks: dict[str, Any],
    active_ids: set[str],
    read_comments: Callable[[str], list[dict]],
    writer: Writer,
    save_hist: Callable[[], None],
    now: datetime,
    *,
    cap: int = POST_CAP,
) -> dict[str, Any]:
    """照合待ちの照合 → 再送 → 今回分の投稿。結果は run["comments"] と各 entry["comment"]、判断履歴の comment_318。"""
    at = now.isoformat(timespec="seconds")
    out: dict[str, Any] = {
        "enabled": True, "posted": 0, "same_as_last": 0, "already_there": 0, "unknown": 0,
        "failed": 0, "reconciled_posted": 0, "reconciled_missing": 0, "unverified": 0, "retried": 0,
        "precheck_failed": 0, "capped": 0, "gave_up": 0,
    }
    run["comments"] = out
    why = guard_317()
    out["guard_317"] = why or "ok"
    if why:
        out["enabled"] = False
        run["errors"].append({"where": "comment_guard_317", "error": why + "。自動コメントを止めた"})
        return out

    # 1) 照合: 送信中・応答不明だった件は、Todoist のコメントを読んで処理ID を探す
    for tid, row in hist_tasks.items():
        c = row.get("comment_318") or {}
        if c.get("state") not in ("sending", "unknown"):
            continue
        if tid not in active_ids:
            c.update(state="dropped", note="タスクが無くなった（完了・削除）", at=at)
            continue
        try:
            cs = _comments_of(read_comments, tid)
        except Exception as e:  # noqa: BLE001
            out["unverified"] += 1
            run["errors"].append({"task_id": tid, "where": "comment_reconcile", "error": f"照合できない（{type(e).__name__}）。再送しない"})
            continue
        if any(has_run_id(str(x.get("content") or ""), str(c.get("run_id") or "")) for x in cs):
            c.update(state="posted", posted_sig=c.get("sig"), at=at, note="照合で投稿済みと確認")
            c.pop("body", None)
            out["reconciled_posted"] += 1
        else:
            c.update(state="retry", at=at, note="照合で未投稿と確認（再送してよい）")
            out["reconciled_missing"] += 1

    # 2) 今回分（変化があって分類した件）と再送分を並べる。今回分を先に
    targets: list[tuple[str, str, str, dict[str, Any] | None]] = []  # (tid, body, run_id, entry)
    this_run = {str(e["task_id"]): e for e in run.get("tasks") or [] if e.get("category") and e.get("comment_draft")}
    for tid, e in this_run.items():
        targets.append((tid, e["comment_draft"], run["run_id"], e))
    for tid, row in hist_tasks.items():
        c = row.get("comment_318") or {}
        if tid in this_run or c.get("state") not in ("retry", "failed"):
            continue
        if tid not in active_ids:
            c.update(state="dropped", note="タスクが無くなった（完了・削除）", at=at)
            continue
        if int(c.get("attempts") or 0) >= MAX_ATTEMPTS:
            if c.get("state") != "gave_up":
                c.update(state="gave_up", at=at, note=f"{MAX_ATTEMPTS}回失敗。人が確かめるまで再送しない")
                out["gave_up"] += 1
                run["errors"].append({"task_id": tid, "where": "comment", "error": "再送の上限。人の確認待ち"})
            continue
        if c.get("body"):
            targets.append((tid, c["body"], str(c.get("run_id") or run["run_id"]), None))

    posts = 0
    for tid, body, rid, entry in targets:
        row = hist_tasks.setdefault(tid, {})
        c = row.get("comment_318") or {}
        sig = body_sig(body)
        is_retry = entry is None
        if not is_retry and c.get("posted_sig") == sig:
            entry["comment"] = "same_as_last"
            out["same_as_last"] += 1
            continue
        if not is_retry and c.get("state") in ("sending", "unknown"):
            entry["comment"] = "waiting_reconcile"  # 照合が済むまで、この件には書き足さない
            continue
        if posts >= cap:
            out["capped"] += 1
            if entry is not None:
                entry["comment"] = "capped"
            continue
        # 投稿前の重複確認（同じ処理ID・同じ中身の【318】）。読めなければ書かない
        try:
            cs = _comments_of(read_comments, tid)
        except Exception as e:  # noqa: BLE001
            out["precheck_failed"] += 1
            run["errors"].append({"task_id": tid, "where": "comment_precheck", "error": f"重複確認ができない（{type(e).__name__}）。書かない"})
            if entry is not None:
                entry["comment"] = "precheck_failed"
            continue
        dup = [x for x in cs if str(x.get("content") or "").lstrip().startswith(PREFIX)
               and (has_run_id(str(x.get("content")), rid) or body_sig(str(x.get("content"))) == sig)]
        if dup:
            row["comment_318"] = {**c, "state": "posted", "posted_sig": sig, "run_id": rid, "sig": sig, "at": at,
                                  "note": "同じ処理ID・同じ中身が既にある"}
            row["comment_318"].pop("body", None)
            out["already_there"] += 1
            if entry is not None:
                entry["comment"] = "already_there"
            continue
        attempts = int(c.get("attempts") or 0) + 1 if is_retry else 1
        row["comment_318"] = {"state": "sending", "run_id": rid, "sig": sig, "body": body, "at": at,
                              "attempts": attempts, "posted_sig": c.get("posted_sig")}
        try:
            save_hist()  # 送る前に「送信中」を残す。残せなければ送らない
        except Exception as e:  # noqa: BLE001
            row["comment_318"] = c
            run["errors"].append({"task_id": tid, "where": "comment_writeahead", "error": f"判断履歴に残せない（{type(e).__name__}）。書かない"})
            if entry is not None:
                entry["comment"] = "not_sent"
            break
        posts += 1
        try:
            res = writer.post_comment(tid, body)
            ok = isinstance(res, dict) and bool(res.get("id"))
            state, err = ("posted", "") if ok else ("unknown", "応答に id が無い")
        except Exception as e:  # noqa: BLE001
            state, err = _classify_error(e)
        cur = row["comment_318"]
        cur["state"] = state
        if state == "posted":
            cur["posted_sig"] = sig
            cur.pop("body", None)
            out["posted"] += 1
            out["retried"] += int(is_retry)
            run["writes"]["todoist"] += 1
        elif state == "unknown":
            cur["note"] = f"応答不明（{err}）。次の回に照合するまで再送しない"
            out["unknown"] += 1
            run["errors"].append({"task_id": tid, "where": "comment", "error": cur["note"]})
        else:
            cur["note"] = f"失敗（{err}）。次の回に重複確認のうえ再送（{MAX_ATTEMPTS}回まで）"
            out["failed"] += 1
            run["errors"].append({"task_id": tid, "where": "comment", "error": cur["note"]})
        if entry is not None:
            entry["comment"] = state
    try:
        save_hist()
    except Exception as e:  # noqa: BLE001
        run["errors"].append({"where": "comment_history", "error": f"コメントの結果を判断履歴に残せない（{type(e).__name__}）"})
    return out
