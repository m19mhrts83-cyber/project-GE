#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""58_ 段階2: todoist_webhook_events の status（new→claimed→done/failed/skipped）を 317 L1 で回す。

正本: docs/AIエージェントチーム/58_自律化_4合図共通仕様とTodoistイベント検知_草案_20261112.md
列: 段階1 migration 20261114_todoist_webhook_events_common_cols.sql（event_id・status・claimed_by・attempts・last_error）

- 境界時刻（sync_meta `todoist_event_lifecycle_since`）より後に届いた行だけを対象にする。
  境界より前の行はこれまでどおり processed_at だけで処理する（古い new を一気に流さない）
- 取る前に new→claimed（条件付き PATCH。Mac と GHA が同時に取っても片方だけ）
- 同じ event_id が done なら skipped（processed_at も付けて既存の読み手から消す）
- 成功 → done＋processed_at
- 失敗 → attempts+1・last_error。3回目で failed（processed_at は付けない＝#report の未処理に残す）
  再試行は 5分・30分あける（last_error の先頭に失敗時刻を書く。列は増やさない）
- 取ったまま落ちた claimed は 15分で失敗1回として数え直す

止める: JARVIS_TODOIST_EVENT_LIFECYCLE_DISABLE=1（これまでの processed_at だけの動きに戻る）
境界を手で決める: JARVIS_TODOIST_EVENT_LIFECYCLE_SINCE=2026-11-25T00:00:00Z
"""
from __future__ import annotations

import os
import re
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

SINCE_META_KEY = "todoist_event_lifecycle_since"
MAX_ATTEMPTS = 3
# n 回目の失敗のあと次に取るまでの間（58_: 5分・30分・2時間。3回目で failed なので2時間は使わない）
RETRY_BACKOFF = (timedelta(minutes=5), timedelta(minutes=30), timedelta(hours=2))
CLAIM_STALE = timedelta(minutes=15)
# item:completed は同じタスクを再完了しうるので、done と同じ event_id を重複とみなすのは近い時刻だけ
DEDUPE_WINDOW = {"item:completed": timedelta(hours=1)}
LAST_ERROR_MAX = 300

SbReq = Callable[..., Any]


def lifecycle_disabled() -> bool:
    return (os.environ.get("JARVIS_TODOIST_EVENT_LIFECYCLE_DISABLE") or "").strip() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_ts(raw: Any) -> datetime | None:
    s = str(raw or "").strip()
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    # PostgREST は "2026-11-24 15:50:16.91508+00" の形も返す
    if len(s) >= 3 and s[-3] in "+-" and s[-2:].isdigit():
        s = s + ":00"
    s = s.replace(" ", "T", 1)
    # 3.10 以前の fromisoformat は小数秒 3/6 桁しか読まない → 6 桁にそろえる
    m = re.match(r"^(.*T\d\d:\d\d:\d\d)\.(\d+)(.*)$", s)
    if m:
        s = f"{m.group(1)}.{(m.group(2) + '000000')[:6]}{m.group(3)}"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def runner_name() -> str:
    """claimed_by の係名（社員番号＋どこで動いたか）。"""
    where = "gha" if (os.environ.get("GITHUB_ACTIONS") or "").strip() == "true" else "mac"
    return f"317:{where}"


def claim_label(now: datetime | None = None) -> str:
    return f"{runner_name()}@{_iso(now or _utcnow())}"


def claimed_at(claimed_by: Any) -> datetime | None:
    s = str(claimed_by or "")
    if "@" not in s:
        return None
    return parse_ts(s.rsplit("@", 1)[1])


def format_last_error(err: str, now: datetime | None = None) -> str:
    msg = " ".join(str(err or "").split())
    return f"{_iso(now or _utcnow())} {msg}"[:LAST_ERROR_MAX]


def last_error_at(last_error: Any) -> datetime | None:
    s = str(last_error or "").strip()
    if not s:
        return None
    return parse_ts(s.split(" ", 1)[0])


def ready_for_retry(row: dict[str, Any], now: datetime | None = None) -> bool:
    """失敗後のあけ時間が過ぎたか（失敗していなければ True）。"""
    attempts = int(row.get("attempts") or 0)
    if attempts <= 0:
        return True
    at = last_error_at(row.get("last_error"))
    if at is None:
        return True
    wait = RETRY_BACKOFF[min(attempts, len(RETRY_BACKOFF)) - 1]
    return (now or _utcnow()) >= at + wait


class Lifecycle:
    """境界時刻より後の行の status を進める。境界より前の行は legacy（processed_at だけ）。"""

    def __init__(
        self,
        sb_req: SbReq,
        *,
        since: datetime | None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._sb = sb_req
        self.since = since
        self._now = now or (lambda: _utcnow())
        self.failed: list[dict[str, Any]] = []
        self.counts = {"claimed": 0, "done": 0, "skipped": 0, "retry": 0, "failed": 0}

    # --- 境界 ---------------------------------------------------------------
    @classmethod
    def load(cls, sb_req: SbReq, *, init_if_missing: bool, log: Callable[[str], None] = print) -> "Lifecycle":
        """境界時刻を読む。無ければ（書く実行のときだけ）いまを境界にする。

        読取失敗は「境界なし」と扱わない: この回は段階2を使わず legacy だけで動く。
        """
        if lifecycle_disabled():
            log("lifecycle: disabled（processed_at だけ）")
            return cls(sb_req, since=None)
        env = (os.environ.get("JARVIS_TODOIST_EVENT_LIFECYCLE_SINCE") or "").strip()
        if env:
            dt = parse_ts(env)
            if dt is None:
                log("lifecycle: SINCE の形が読めない → この回は legacy だけ")
            return cls(sb_req, since=dt)
        try:
            rows = sb_req(
                "GET",
                f"sync_meta?key=eq.{urllib.parse.quote(SINCE_META_KEY)}&select=value",
            )
        except (Exception, SystemExit) as exc:  # noqa: BLE001  （接続設定なしは SystemExit）
            log(f"lifecycle: 境界の読取失敗 → この回は legacy だけ: {exc}")
            return cls(sb_req, since=None)
        row = (rows[0] if isinstance(rows, list) and rows else None) or {}
        dt = parse_ts(row.get("value")) if isinstance(row, dict) else None
        if dt is not None:
            return cls(sb_req, since=dt)
        if row:
            log("lifecycle: 境界の値が読めない → この回は legacy だけ")
            return cls(sb_req, since=None)
        if not init_if_missing:
            return cls(sb_req, since=None)
        now = _utcnow()
        try:
            sb_req(
                "POST",
                "sync_meta?on_conflict=key",
                body=[{"key": SINCE_META_KEY, "value": _iso(now), "updated_at": _iso(now)}],
                prefer="resolution=merge-duplicates,return=minimal",
            )
        except Exception as exc:  # noqa: BLE001
            log(f"lifecycle: 境界の保存失敗 → この回は legacy だけ: {exc}")
            return cls(sb_req, since=None)
        log(f"lifecycle: 境界を {_iso(now)} に設定（これより後に届いた行から status を回す）")
        return cls(sb_req, since=now)

    @property
    def active(self) -> bool:
        return self.since is not None

    def is_tracked(self, row: dict[str, Any]) -> bool:
        if not self.active:
            return False
        created = parse_ts(row.get("created_at"))
        return created is not None and created >= self.since  # type: ignore[operator]

    # --- 取得 ---------------------------------------------------------------
    def legacy_filter(self) -> str:
        """境界より前の行だけ（既存の processed_at 判定）。"""
        if not self.active:
            return ""
        return f"&created_at=lt.{urllib.parse.quote(_iso(self.since))}"  # type: ignore[arg-type]

    def fetch(self, *, event_name: str, limit: int, select: str) -> list[dict[str, Any]]:
        """境界より後で、まだ終わっていない行（new／claimed）。あけ時間中・他が取っている行は除く。"""
        if not self.active:
            return []
        cols = select + ",event_id,status,claimed_by,attempts,last_error"
        qs = (
            "todoist_webhook_events"
            f"?select={cols}"
            f"&event_name=eq.{urllib.parse.quote(event_name)}"
            "&processed_at=is.null"
            "&status=in.(new,claimed)"
            f"&created_at=gte.{urllib.parse.quote(_iso(self.since))}"  # type: ignore[arg-type]
            "&order=created_at.asc"
            f"&limit={limit}"
        )
        rows = self._sb("GET", qs) or []
        now = self._now()
        out: list[dict[str, Any]] = []
        for r in rows if isinstance(rows, list) else []:
            if r.get("status") == "claimed":
                at = claimed_at(r.get("claimed_by"))
                if at is not None and now - at < CLAIM_STALE:
                    continue  # 他の実行が処理中
                # 取ったまま落ちた → 失敗1回として数え直し、あけ時間後に取り直す
                self._record_failure(r, "claim timeout（取ったまま終わらなかった）", expect="claimed")
                continue
            if not ready_for_retry(r, now):
                continue
            out.append(r)
        return out

    # --- 状態遷移 -------------------------------------------------------------
    def claim(self, row: dict[str, Any]) -> bool:
        """new→claimed。返りが空なら他が先に取った。"""
        rid = int(row["id"])
        res = self._sb(
            "PATCH",
            f"todoist_webhook_events?id=eq.{rid}&status=eq.new",
            body={"status": "claimed", "claimed_by": claim_label(self._now())},
            prefer="return=representation",
        )
        ok = bool(res) if isinstance(res, list) else bool(res)
        if ok:
            self.counts["claimed"] += 1
            row["status"] = "claimed"
        return ok

    def already_done(self, row: dict[str, Any]) -> bool:
        """同じ event_id がもう done か（Todoist の再送）。"""
        eid = str(row.get("event_id") or "")
        if not eid:
            return False
        qs = (
            "todoist_webhook_events?select=id,created_at"
            f"&event_id=eq.{urllib.parse.quote(eid, safe='')}"
            "&status=eq.done"
            f"&id=neq.{int(row['id'])}"
            "&order=created_at.desc&limit=1"
        )
        rows = self._sb("GET", qs) or []
        if not rows:
            return False
        window = DEDUPE_WINDOW.get(str(row.get("event_name") or ""))
        if window is None:
            return True
        mine = parse_ts(row.get("created_at"))
        theirs = parse_ts(rows[0].get("created_at"))
        if mine is None or theirs is None:
            return False
        return abs(mine - theirs) <= window

    def done(self, row: dict[str, Any]) -> None:
        self._finish(row, "done")

    def skipped(self, row: dict[str, Any]) -> None:
        self._finish(row, "skipped")

    def _finish(self, row: dict[str, Any], status: str) -> None:
        rid = int(row["id"])
        self._sb(
            "PATCH",
            f"todoist_webhook_events?id=eq.{rid}",
            body={"status": status, "processed_at": _iso(self._now())},
            prefer="return=minimal",
        )
        row["status"] = status
        self.counts[status] += 1

    def fail(self, row: dict[str, Any], err: str) -> str:
        """失敗を記録。返り値は 'retry' か 'failed'。"""
        return self._record_failure(row, err, expect="claimed")

    def _record_failure(self, row: dict[str, Any], err: str, *, expect: str) -> str:
        rid = int(row["id"])
        attempts = int(row.get("attempts") or 0) + 1
        status = "failed" if attempts >= MAX_ATTEMPTS else "new"
        body = {
            "status": status,
            "attempts": attempts,
            "last_error": format_last_error(err, self._now()),
            "claimed_by": None,
        }
        res = self._sb(
            "PATCH",
            f"todoist_webhook_events?id=eq.{rid}&status=eq.{expect}",
            body=body,
            prefer="return=representation",
        )
        if not res:
            return "lost"  # 他の実行が先に動かした
        row.update(body)
        if status == "failed":
            self.counts["failed"] += 1
            self.failed.append(
                {
                    "id": rid,
                    "event_name": str(row.get("event_name") or ""),
                    "error": " ".join(str(err or "").split())[:80],
                }
            )
            return "failed"
        self.counts["retry"] += 1
        return "retry"


def build_ops_text(failed: list[dict[str, Any]]) -> str:
    """#ops 1通（41_: 先頭1行で分かる・1項目2行以内）。本文・人名は載せない。"""
    lines = [f"【ops】317 Todoistイベント 失敗 {len(failed)}件（{MAX_ATTEMPTS}回試した）"]
    for f in failed[:5]:
        lines += ["", f"・id {f['id']} {f['event_name']}", f"　{f['error']}"]
    if len(failed) > 5:
        lines += ["", f"他{len(failed) - 5}件は todoist_webhook_events の status=failed"]
    lines += ["", "次: 原因を直してから status=new・attempts=0 に戻すと取り直す"]
    return "\n".join(lines)
