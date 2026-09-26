#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Todoist → admin Googleカレンダー同期（due + @cal）。

入口: Todoist で due がありラベル `cal` の未完了タスク
確認: 既定 dry-run。`--apply` で作成／更新／削除
履歴: `.jarvis_state/todoist_calendar_sync.json`（task_id→event_id）
停止: yaml `integrations.calendar_sync.enabled: false`
      または `JARVIS_TODOIST_CALENDAR_SYNC_DISABLE=1`
定期: launchd `bucho-inbox-poll`（15分・Mac起動中）が `--apply`。
      画面ロック解除でも `screen-unlock-catchup` が同じ runner を1回走らせる。
      完了・@cal外し・due削除は候補から外れた予定を削除する。

予定正本は admin Googleカレンダー。Todoist は「カレンダーに出したい」印（@cal）。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_calendar_sync.py
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_calendar_sync.py --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_calendar_sync.py --apply
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_calendar_sync.py --ensure-label
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
YAML_PATH = REPO / "config" / "todoist_projects.yaml"
STATE_PATH = REPO / ".jarvis_state" / "todoist_calendar_sync.json"
MANUAL = REPO / "215_kamiooya" / "C1_cursor" / "1b_Cursorマニュアル"
DEFAULT_API = "https://api.todoist.com/api/v1"
JST = ZoneInfo("Asia/Tokyo")
SOURCE_TAG = "todoist_cal_sync"

sys.path.insert(0, str(MANUAL))


def _load_yaml() -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ImportError:
        print("ERROR: PyYAML が必要です", file=sys.stderr)
        sys.exit(2)
    if not YAML_PATH.is_file():
        print(f"ERROR: 設定がありません: {YAML_PATH}", file=sys.stderr)
        sys.exit(2)
    return dict(yaml.safe_load(YAML_PATH.read_text(encoding="utf-8")) or {})


def _cal_cfg(cfg: dict[str, Any]) -> dict[str, Any]:
    integ = cfg.get("integrations") or {}
    cal = integ.get("calendar_sync") or {}
    return dict(cal) if isinstance(cal, dict) else {}


def _token() -> str:
    tok = (os.environ.get("TODOIST_API_TOKEN") or "").strip()
    if not tok:
        print("ERROR: TODOIST_API_TOKEN 未設定", file=sys.stderr)
        sys.exit(2)
    return tok


def _api_base(cfg: dict[str, Any]) -> str:
    return str(cfg.get("api_base") or DEFAULT_API).rstrip("/")


def _todoist_req(
    method: str,
    path: str,
    *,
    cfg: dict[str, Any],
    body: dict[str, Any] | None = None,
) -> Any:
    url = f"{_api_base(cfg)}{path}"
    data = None
    headers = {
        "Authorization": f"Bearer {_token()}",
        "Accept": "application/json",
    }
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            raw = r.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"Todoist {method} {path}: {e.code} {err}") from e


def _paginate(path: str, *, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    cursor: str | None = None
    while True:
        q = path
        if cursor:
            sep = "&" if "?" in path else "?"
            q = f"{path}{sep}cursor={urllib.parse.quote(cursor)}"
        data = _todoist_req("GET", q, cfg=cfg)
        if isinstance(data, list):
            out.extend(x for x in data if isinstance(x, dict))
            break
        if not isinstance(data, dict):
            break
        results = data.get("results")
        if isinstance(results, list):
            out.extend(x for x in results if isinstance(x, dict))
        elif data.get("id"):
            out.append(data)
            break
        cursor = data.get("next_cursor")
        if not cursor:
            break
    return out


def _load_state() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        return {"version": 1, "mappings": {}}
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"version": 1, "mappings": {}}
    if not isinstance(data, dict):
        return {"version": 1, "mappings": {}}
    data.setdefault("version", 1)
    data.setdefault("mappings", {})
    return data


def _save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = datetime.now(JST).isoformat(timespec="seconds")
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _ensure_label(cfg: dict[str, Any], name: str) -> None:
    existing = {str(x.get("name")) for x in _paginate("/labels", cfg=cfg)}
    if name in existing:
        print(f"label ok: @{name}")
        return
    _todoist_req("POST", "/labels", cfg=cfg, body={"name": name})
    print(f"label created: @{name}")


def _parse_due(due: dict[str, Any] | None) -> tuple[datetime | None, bool]:
    """Returns (start_dt_or_midnight, is_all_day)."""
    if not isinstance(due, dict):
        return None, True
    raw = str(due.get("date") or "").strip()
    if not raw:
        return None, True
    # datetime: 2026-09-23T18:00:00 or with Z
    if "T" in raw:
        cleaned = raw.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(cleaned)
        except ValueError:
            return None, True
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=JST)
        else:
            dt = dt.astimezone(JST)
        return dt, False
    try:
        d = date.fromisoformat(raw[:10])
    except ValueError:
        return None, True
    return datetime(d.year, d.month, d.day, tzinfo=JST), True


def _fingerprint(title: str, start: datetime, all_day: bool, duration_min: int) -> str:
    kind = "allday" if all_day else f"timed:{duration_min}"
    return f"{start.isoformat()}|{kind}|{title}"


def _event_body(
    *,
    title: str,
    start: datetime,
    all_day: bool,
    duration_min: int,
    task_id: str,
    task_url: str,
) -> dict[str, Any]:
    desc = (
        f"[Jarvis] Todoist @cal 同期\n"
        f"task: {task_url}\n"
        f"id: {task_id}\n"
        f"source: {SOURCE_TAG}"
    )
    body: dict[str, Any] = {
        "summary": title,
        "description": desc,
        "extendedProperties": {
            "private": {
                "jarvis_todoist_task_id": task_id,
                "jarvis_source": SOURCE_TAG,
            }
        },
    }
    if all_day:
        d0 = start.date()
        d1 = d0 + timedelta(days=1)
        body["start"] = {"date": d0.isoformat()}
        body["end"] = {"date": d1.isoformat()}
    else:
        end = start + timedelta(minutes=duration_min)
        body["start"] = {
            "dateTime": start.strftime("%Y-%m-%dT%H:%M:%S"),
            "timeZone": "Asia/Tokyo",
        }
        body["end"] = {
            "dateTime": end.strftime("%Y-%m-%dT%H:%M:%S"),
            "timeZone": "Asia/Tokyo",
        }
    return body


def _calendar_service():
    from google_calendar_create import _load_credentials  # type: ignore
    from googleapiclient.discovery import build

    creds = _load_credentials(
        login_hint="admin@livingsupport-matsu.co.jp",
        auth_console=False,
    )
    return build("calendar", "v3", credentials=creds)


def _candidates(cfg: dict[str, Any], label: str, duration_min: int) -> list[dict[str, Any]]:
    tasks = _paginate("/tasks", cfg=cfg)
    out: list[dict[str, Any]] = []
    for t in tasks:
        labs = [str(x) for x in (t.get("labels") or [])]
        if label not in labs:
            continue
        start, all_day = _parse_due(t.get("due") if isinstance(t.get("due"), dict) else None)
        if start is None:
            continue
        tid = str(t.get("id") or "")
        title = str(t.get("content") or "").strip() or "(無題)"
        url = f"https://app.todoist.com/app/task/{tid}"
        out.append(
            {
                "task_id": tid,
                "title": title,
                "url": url,
                "start": start,
                "all_day": all_day,
                "fingerprint": _fingerprint(title, start, all_day, duration_min),
                "body": _event_body(
                    title=title,
                    start=start,
                    all_day=all_day,
                    duration_min=duration_min,
                    task_id=tid,
                    task_url=url,
                ),
            }
        )
    out.sort(key=lambda x: (x["start"], x["title"]))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Todoist @cal → admin Googleカレンダー同期")
    ap.add_argument("--dry-run", action="store_true", help="変更せず候補だけ表示（既定）")
    ap.add_argument("--apply", action="store_true", help="作成／更新／削除を実行")
    ap.add_argument("--force", action="store_true", help="yaml enabled=false でも apply 可")
    ap.add_argument("--ensure-label", action="store_true", help="@cal ラベルが無ければ作成")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if (os.environ.get("JARVIS_TODOIST_CALENDAR_SYNC_DISABLE") or "").strip() == "1":
        print("📎 Todoist Calendar同期\n- 停止: JARVIS_TODOIST_CALENDAR_SYNC_DISABLE=1")
        return 0

    cfg = _load_yaml()
    cal = _cal_cfg(cfg)
    label = str(cal.get("due_label") or "cal").strip() or "cal"
    duration_min = int(cal.get("default_duration_minutes") or 60)
    calendar_id = str(cal.get("calendar_id") or "primary").strip() or "primary"
    enabled = bool(cal.get("enabled"))

    if args.ensure_label:
        _ensure_label(cfg, label)

    do_apply = bool(args.apply)
    if do_apply and not enabled and not args.force:
        print(
            "ERROR: calendar_sync.enabled が false。yaml を true にするか --force",
            file=sys.stderr,
        )
        return 2
    if not do_apply:
        args.dry_run = True

    cands = _candidates(cfg, label, duration_min)
    state = _load_state()
    mappings: dict[str, Any] = dict(state.get("mappings") or {})

    lines = [
        "📎 Todoist Calendar同期（due + @" + label + "）",
        f"- mode: {'APPLY' if do_apply else 'DRY-RUN'}",
        f"- enabled: {enabled}",
        f"- calendar: admin primary（{calendar_id}）",
        f"- 候補: {len(cands)}件",
    ]
    for c in cands:
        kind = "終日" if c["all_day"] else c["start"].strftime("%H:%M")
        day = c["start"].strftime("%Y-%m-%d")
        mapped = mappings.get(c["task_id"]) or {}
        status = "update" if mapped else "create"
        if mapped and mapped.get("fingerprint") == c["fingerprint"]:
            status = "ok"
        lines.append(f"  · [{status}] {day} {kind} — {c['title'][:60]}")
        lines.append(f"    {c['url']}")

    stale_ids = [tid for tid in mappings if tid not in {c["task_id"] for c in cands}]
    if stale_ids:
        lines.append(f"- 削除候補（@cal外/完了等）: {len(stale_ids)}件")
        for tid in stale_ids[:10]:
            lines.append(f"  · delete event for task {tid}")

    if args.json:
        print(
            json.dumps(
                {
                    "mode": "apply" if do_apply else "dry-run",
                    "candidates": [
                        {
                            "task_id": c["task_id"],
                            "title": c["title"],
                            "start": c["start"].isoformat(),
                            "all_day": c["all_day"],
                            "url": c["url"],
                        }
                        for c in cands
                    ],
                    "stale": stale_ids,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if not do_apply:
        lines.append("- 実行するとき: --apply（初回は yaml enabled:true または --force）")
        print("\n".join(lines))
        return 0

    try:
        service = _calendar_service()
    except Exception as exc:
        print(f"ERROR: Calendar 認証失敗: {exc}", file=sys.stderr)
        return 1

    created = updated = deleted = skipped = 0
    for c in cands:
        prev = mappings.get(c["task_id"]) or {}
        event_id = str(prev.get("event_id") or "")
        if event_id and prev.get("fingerprint") == c["fingerprint"]:
            skipped += 1
            continue
        try:
            if event_id:
                ev = (
                    service.events()
                    .patch(calendarId=calendar_id, eventId=event_id, body=c["body"])
                    .execute()
                )
                updated += 1
            else:
                ev = (
                    service.events()
                    .insert(calendarId=calendar_id, body=c["body"])
                    .execute()
                )
                created += 1
            mappings[c["task_id"]] = {
                "event_id": ev.get("id"),
                "fingerprint": c["fingerprint"],
                "html_link": ev.get("htmlLink") or "",
                "title": c["title"],
                "synced_at": datetime.now(JST).isoformat(timespec="seconds"),
            }
        except Exception as exc:
            lines.append(f"  ! fail {c['task_id']}: {exc}")

    for tid in list(stale_ids):
        prev = mappings.get(tid) or {}
        event_id = str(prev.get("event_id") or "")
        if not event_id:
            mappings.pop(tid, None)
            continue
        try:
            service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
            deleted += 1
        except Exception as exc:
            # 既に消えている等は mapping だけ落とす
            lines.append(f"  ! delete fail {tid}: {exc}")
        mappings.pop(tid, None)

    state["mappings"] = mappings
    state["last_run_at"] = datetime.now(JST).isoformat(timespec="seconds")
    state["last_counts"] = {
        "created": created,
        "updated": updated,
        "deleted": deleted,
        "skipped": skipped,
        "candidates": len(cands),
    }
    _save_state(state)

    lines.append(
        f"- 結果: create={created} update={updated} delete={deleted} skip={skipped}"
    )
    lines.append(f"- state: {STATE_PATH}")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
