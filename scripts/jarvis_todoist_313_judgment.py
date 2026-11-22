#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""313 共通部品 — 本人判断「残す」の記録・連続日数・状態ファイルの実行時刻.

置き場は未追跡の `.jarvis_state/`（private_paths.txt の範囲）。タスク名は書かない
（task_id と指紋のハッシュだけ）。Todoist の更新・close はここではしない。

- 判断記録  : `.jarvis_state/todoist_313_judgments.json`
    keep[task_id] = {fp, at, run}  … 本人が「残す」と答えた時点の内容の指紋。
    内容（題・期日・説明・ラベル・優先度・更新時刻）が変わって指紋が違えば再提示する。
- 連続日数  : 同じ `.json` の streak[task_id] = {first, last, days}
- 実行時刻  : 旧 `todoist_313_digest.json` に last_run_at / last_digest_at を書く
    （片付け 1 通へ切り替えた後、旧 digest だけが 11/07 で止まって見えた件の修正）
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
JST = ZoneInfo("Asia/Tokyo")
JUDGMENTS_PATH = REPO / ".jarvis_state" / "todoist_313_judgments.json"
LEGACY_DIGEST_PATH = REPO / ".jarvis_state" / "todoist_313_digest.json"
STREAK_KEEP_DAYS = 45


def _now() -> datetime:
    return datetime.now(JST)


def fingerprint(task: dict[str, Any]) -> str:
    """内容が変わったら変わる指紋。期限・更新時刻・題・説明・ラベル・優先度。"""
    due = task.get("due") or {}
    parts = [
        str(task.get("content") or ""),
        str(due.get("date") or "") if isinstance(due, dict) else str(due),
        str(task.get("description") or ""),
        ",".join(sorted(str(x) for x in (task.get("labels") or []))),
        str(task.get("priority") or ""),
        str(task.get("updated_at") or task.get("updatedAt") or ""),
    ]
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:16]


def _read(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.is_file():
        return default
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else default
    except Exception:  # noqa: BLE001
        return default


def _write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_judgments(path: Path | None = None) -> dict[str, Any]:
    d = _read(path or JUDGMENTS_PATH, {})
    d.setdefault("keep", {})
    d.setdefault("streak", {})
    return d


def save_judgments(data: dict[str, Any], path: Path | None = None) -> None:
    _write(path or JUDGMENTS_PATH, data)


def record_keep(
    judgments: dict[str, Any], task_id: str, fp: str, *, run: str = ""
) -> None:
    """本人が「残す」と答えた。今の内容の指紋で記録する。"""
    judgments.setdefault("keep", {})[str(task_id)] = {
        "fp": fp,
        "at": _now().isoformat(timespec="seconds"),
        "run": run,
    }


def is_kept(judgments: dict[str, Any], task_id: str, fp: str) -> bool:
    """残すと答えた時から内容が変わっていなければ True（再提示しない）。"""
    row = (judgments.get("keep") or {}).get(str(task_id))
    return bool(row) and row.get("fp") == fp


def filter_kept(
    tasks: list[dict[str, Any]], judgments: dict[str, Any]
) -> tuple[list[dict[str, Any]], int]:
    """task(dict) の列から「残す」済みを除く。除いた件数も返す。"""
    out, skipped = [], 0
    for t in tasks:
        if is_kept(judgments, str(t.get("id") or ""), fingerprint(t)):
            skipped += 1
            continue
        out.append(t)
    return out, skipped


def update_streak(
    judgments: dict[str, Any], task_ids: list[str], today: date | None = None
) -> dict[str, int]:
    """今回出した task_id ごとの連続日数を更新して {task_id: 日数} を返す。

    前回が昨日なら +1、今日（同日の再実行）なら据え置き、2 日以上空いたら 1 に戻す。
    今回出さなかった id は、古いものだけ捨てる。
    """
    today = today or _now().date()
    streak: dict[str, Any] = judgments.setdefault("streak", {})
    result: dict[str, int] = {}
    for tid in task_ids:
        tid = str(tid)
        row = streak.get(tid) or {}
        try:
            last = date.fromisoformat(str(row.get("last") or ""))
        except ValueError:
            last = None
        if last == today:
            days = int(row.get("days") or 1)
        elif last == today - timedelta(days=1):
            days = int(row.get("days") or 0) + 1
        else:
            days = 1
        streak[tid] = {
            "first": row.get("first") if (last and days > 1) else today.isoformat(),
            "last": today.isoformat(),
            "days": days,
        }
        result[tid] = days
    cutoff = today - timedelta(days=STREAK_KEEP_DAYS)
    for tid in list(streak):
        try:
            if date.fromisoformat(str(streak[tid].get("last"))) < cutoff:
                del streak[tid]
        except ValueError:
            del streak[tid]
    return result


def streak_line(days_by_id: dict[str, int], min_days: int = 2) -> str:
    """digest に出す 1 行。最大日数が min_days 未満なら空文字。"""
    if not days_by_id:
        return ""
    mx = max(days_by_id.values())
    if mx < min_days:
        return ""
    n = sum(1 for v in days_by_id.values() if v >= min_days)
    return f"🔁 同じ候補を{mx}日連続（{n}件）。残すなら「残す」と答えると再提示しません"


def stamp_run(
    *, digest_at: bool, path: Path | None = None, extra: dict[str, Any] | None = None
) -> None:
    """旧 digest 状態ファイルへ最終実行時刻を書く（他のキーは保つ）。

    実行が成功した時だけ呼ぶ。digest_at=True は「まとめを出した」回（Slack 送信成功・
    または超過 0 件で出すものが無かった回）。
    """
    p = path or LEGACY_DIGEST_PATH
    d = _read(p, {"proposals": [], "last_digest_at": None, "closed_ids": []})
    now = _now().isoformat(timespec="seconds")
    d["last_run_at"] = now
    if digest_at:
        d["last_digest_at"] = now
    if extra:
        d.update(extra)
    _write(p, d)
