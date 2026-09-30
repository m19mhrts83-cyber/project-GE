#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ホーム要フォロー（watch_status）→ Todoist『受信箱』正本同期。

入口: Supabase watch_status（active・HomeWatchBand と同条件）
確認: dry-run 既定。`--apply` で起票／更新／完了連動
履歴: `.jarvis_state/watch_todoist_sync.json`（watch_id→task_id）
      + watch payload.todoist_* / display_hints / user_ack
停止: yaml `integrations.watch_todoist_sync.enabled: false`
      または `JARVIS_WATCH_TODOIST_SYNC_DISABLE=1`

タイトル: [要フォロー][{watch_id}] {summary短縮}
重複キー: watch_id（state）。同一タイトルでも新規しない。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_watch_todoist_sync.py
  ~/selenium_env/venv/bin/python scripts/jarvis_watch_todoist_sync.py --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_watch_todoist_sync.py --apply
  ~/selenium_env/venv/bin/python scripts/jarvis_watch_todoist_sync.py --ensure-label
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
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
YAML_PATH = REPO / "config" / "todoist_projects.yaml"
STATE_PATH = REPO / ".jarvis_state" / "watch_todoist_sync.json"
HINTS_PATH = REPO / ".jarvis_state" / "watch_display_hints.json"
DEFAULT_API = "https://api.todoist.com/api/v1"
JST = ZoneInfo("Asia/Tokyo")
LABEL_FOLLOW = "要フォロー"
LABEL_JARVIS = "要Jarvis連携"

sys.path.insert(0, str(REPO / "scripts"))

OPS_EPHEMERAL = {"vercel_deploy", "gha_workflow_fail", "ops_fix_notice"}
BANNER_IDS = {
    "etc_mileage",
    "vpoint",
    "rent_step",
    "cursor_pro_plus_downgrade",
    "mobile_plan",
    "card_debit_watch",
}
DUE_BANNER_IDS = {"glucon_report_due", "quiet_edge_due"}


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


def _sync_cfg(cfg: dict[str, Any]) -> dict[str, Any]:
    integ = cfg.get("integrations") or {}
    cal = integ.get("watch_todoist_sync") or {}
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
    allow_404: bool = False,
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
            if not raw:
                return {}
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        if allow_404 and e.code == 404:
            return None
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


def _load_state() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        return {"version": 1, "todoist_by_watch_id": {}}
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"version": 1, "todoist_by_watch_id": {}}
    if not isinstance(data, dict):
        return {"version": 1, "todoist_by_watch_id": {}}
    data.setdefault("version", 1)
    data.setdefault("todoist_by_watch_id", {})
    return data


def _save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = datetime.now(JST).isoformat(timespec="seconds")
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _load_hints() -> dict[str, Any]:
    if not HINTS_PATH.is_file():
        return {"version": 1, "by_watch_id": {}}
    try:
        data = json.loads(HINTS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"version": 1, "by_watch_id": {}}
    if not isinstance(data, dict):
        return {"version": 1, "by_watch_id": {}}
    data.setdefault("by_watch_id", {})
    return data


def _save_hints(hints: dict[str, Any]) -> None:
    HINTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    hints["updated_at"] = datetime.now(JST).isoformat(timespec="seconds")
    HINTS_PATH.write_text(
        json.dumps(hints, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _as_dict(v: Any) -> dict[str, Any]:
    return v if isinstance(v, dict) else {}


def _zaim_pending_confirm_count(pl: dict[str, Any]) -> int:
    if pl.get("show_banner") is False:
        return 0
    n = pl.get("pending_confirm_count")
    try:
        if n is not None and float(n) == float(n):
            return max(0, int(float(n)))
    except (TypeError, ValueError):
        pass
    ack = str(pl.get("dashboard_ack_batch_id") or "")
    review_batch = str(pl.get("review_batch_id") or "")
    fixes = pl.get("recent_fixes") if isinstance(pl.get("recent_fixes"), list) else []
    n_pending = 0
    for f in fixes:
        if not isinstance(f, dict):
            continue
        st = str(f.get("status") or "pending_confirm")
        if st in ("confirmed", "failed", "disputed"):
            continue
        if st != "pending_confirm":
            continue
        bid = str(f.get("batch_id") or review_batch or "")
        if ack and bid and ack == bid:
            continue
        n_pending += 1
    return n_pending


def _zaim_visible(pl: dict[str, Any]) -> bool:
    if pl.get("show_banner") is False:
        return False
    if pl.get("show_banner") is True:
        return True
    return _zaim_pending_confirm_count(pl) > 0


def _ops_visible(watch_id: str, level: str, pl: dict[str, Any]) -> bool:
    if watch_id not in OPS_EPHEMERAL:
        return False
    if watch_id == "ops_fix_notice":
        return pl.get("show_banner") is True and level != "ok"
    if pl.get("show_banner") is True:
        return True
    return level in ("attention", "warn")


def _display_hints_suppress_home(pl: dict[str, Any]) -> bool:
    """表示: 抑制 — quiet_until 前ならホームから外す。"""
    dh = _as_dict(pl.get("display_hints"))
    if not dh.get("suppress_home"):
        return False
    until = str(dh.get("quiet_until") or "")
    if not until:
        return True
    try:
        dt = datetime.fromisoformat(until.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) < dt.astimezone(timezone.utc)
    except Exception:
        return True


def visible_on_home(row: dict[str, Any]) -> bool:
    """HomeWatchBand.tsx の filter と揃える（+ display_hints.suppress_home）。"""
    from jarvis_watch_user_ack import build_fingerprint, is_ack_active

    wid = str(row.get("id") or "").strip()
    if not wid or str(row.get("status") or "") != "active":
        return False
    level = str(row.get("level") or "")
    pl = _as_dict(row.get("payload"))
    if _display_hints_suppress_home(pl):
        return False
    if wid in OPS_EPHEMERAL:
        return _ops_visible(wid, level, pl)
    fp = build_fingerprint(
        wid, level=level, summary=str(row.get("summary") or ""), payload=pl
    )
    ua = pl.get("user_ack") if isinstance(pl.get("user_ack"), dict) else None
    if is_ack_active(ua, fp):
        return False
    if wid == "zaim_quality":
        if _zaim_visible(pl):
            return True
        return level != "ok"
    if wid in BANNER_IDS:
        if pl.get("show_banner") is True:
            return True
        # show_banner でなければ下の level 判定へ（HomeWatchBand と同じ）
    if wid in DUE_BANNER_IDS:
        return pl.get("show_banner") is True
    return level != "ok"


def _fingerprint_row(row: dict[str, Any]) -> str:
    from jarvis_watch_user_ack import build_fingerprint

    return build_fingerprint(
        str(row.get("id") or ""),
        level=str(row.get("level") or ""),
        summary=str(row.get("summary") or ""),
        payload=_as_dict(row.get("payload")),
    )


def _title_for(row: dict[str, Any]) -> str:
    wid = str(row.get("id") or "")
    summary = str(row.get("summary") or row.get("title") or wid).strip()
    summary = re.sub(r"\s+", " ", summary)[:80]
    return f"[要フォロー][{wid}] {summary}"


def _due_string(row: dict[str, Any]) -> str | None:
    pl = _as_dict(row.get("payload"))
    for key in ("due_date", "due", "next_due"):
        raw = pl.get(key)
        if raw:
            s = str(raw)[:10]
            if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
                return s
    olive = _as_dict(pl.get("olive_infinite"))
    od = str(olive.get("due_date") or "")[:10]
    if re.match(r"^\d{4}-\d{2}-\d{2}$", od):
        return od
    return None


def _needs_jarvis_label(row: dict[str, Any]) -> bool:
    level = str(row.get("level") or "")
    return level in ("attention", "warn")


def _ensure_label(cfg: dict[str, Any], name: str) -> None:
    existing = {str(x.get("name")) for x in _paginate("/labels", cfg=cfg)}
    if name in existing:
        print(f"label ok: @{name}")
        return
    _todoist_req("POST", "/labels", cfg=cfg, body={"name": name})
    print(f"label created: @{name}")


def _fetch_watches() -> list[dict[str, Any]]:
    rows = _sb_req(
        "GET",
        "watch_status?select=*&status=eq.active",
    )
    return list(rows) if isinstance(rows, list) else []


def _patch_watch_payload(watch_id: str, mutator) -> dict[str, Any] | None:
    rows = _sb_req(
        "GET",
        f"watch_status?id=eq.{urllib.parse.quote(watch_id)}&select=id,level,summary,status,payload",
    )
    if not isinstance(rows, list) or not rows:
        return None
    row = rows[0]
    pl = dict(_as_dict(row.get("payload")))
    mutator(pl, row)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _sb_req(
        "PATCH",
        f"watch_status?id=eq.{urllib.parse.quote(watch_id)}",
        body={"payload": pl, "updated_at": now},
        prefer="return=minimal",
    )
    return pl


def _task_url(task_id: str) -> str:
    return f"https://app.todoist.com/app/task/{task_id}"


def _get_task(cfg: dict[str, Any], task_id: str) -> dict[str, Any] | None:
    return _todoist_req(
        "GET", f"/tasks/{urllib.parse.quote(task_id)}", cfg=cfg, allow_404=True
    )


def _is_task_open(task: dict[str, Any] | None) -> bool:
    if not task:
        return False
    if task.get("checked") is True:
        return False
    if task.get("is_completed") is True:
        return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="ホーム要フォロー → Todoist 同期")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--ensure-label", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if (os.environ.get("JARVIS_WATCH_TODOIST_SYNC_DISABLE") or "").strip() == "1":
        print("📎 要フォロー→Todoist\n- 停止: JARVIS_WATCH_TODOIST_SYNC_DISABLE=1")
        return 0

    cfg = _load_yaml()
    sc = _sync_cfg(cfg)
    enabled = bool(sc.get("enabled"))
    quiet_days = int(sc.get("quiet_days") or 7)
    inbox = cfg.get("inbox") if isinstance(cfg.get("inbox"), dict) else {}
    inbox_pid = str(inbox.get("project_id") or "").strip()
    if not inbox_pid:
        print("ERROR: inbox.project_id 未設定", file=sys.stderr)
        return 2

    if args.ensure_label:
        _ensure_label(cfg, LABEL_FOLLOW)
        _ensure_label(cfg, LABEL_JARVIS)

    do_apply = bool(args.apply)
    if do_apply and not enabled and not args.force:
        print(
            "ERROR: watch_todoist_sync.enabled が false。yaml を true にするか --force",
            file=sys.stderr,
        )
        return 2
    if not do_apply:
        args.dry_run = True

    watches = _fetch_watches()
    home_rows = [w for w in watches if visible_on_home(w)]
    state = _load_state()
    mappings: dict[str, Any] = dict(state.get("todoist_by_watch_id") or {})
    hints_state = _load_hints()

    lines = [
        "📎 要フォロー→Todoist",
        f"- mode: {'APPLY' if do_apply else 'DRY-RUN'}",
        f"- enabled: {enabled}",
        f"- home候補: {len(home_rows)} / active={len(watches)}",
        f"- inbox: {inbox_pid}",
    ]

    created = updated = completed = skipped = acked = 0

    # 1) ホーム対象 → create / update
    for row in sorted(home_rows, key=lambda x: str(x.get("id") or "")):
        wid = str(row.get("id") or "")
        title = _title_for(row)
        fp = _fingerprint_row(row)
        due = _due_string(row)
        prev = dict(mappings.get(wid) or {})
        task_id = str(prev.get("task_id") or "").strip()
        pl = _as_dict(row.get("payload"))

        # ダッシュボード側で確認済 → Todoist 完了（1b）
        if pl.get("todoist_complete_requested") or (
            isinstance(pl.get("user_ack"), dict)
            and pl.get("ack_source") == "dashboard"
            and task_id
        ):
            if do_apply and task_id:
                task = _get_task(cfg, task_id)
                if _is_task_open(task):
                    try:
                        _todoist_req(
                            "POST",
                            f"/tasks/{urllib.parse.quote(task_id)}/close",
                            cfg=cfg,
                        )
                        completed += 1
                        lines.append(f"  · complete(dashboard) {wid} → {task_id}")
                    except Exception as exc:
                        lines.append(f"  ! complete fail {wid}: {exc}")
                # clear request flag
                def _clear(p: dict[str, Any], _r: dict[str, Any]) -> None:
                    p.pop("todoist_complete_requested", None)

                try:
                    _patch_watch_payload(wid, _clear)
                except Exception:
                    pass
            else:
                lines.append(f"  · would complete(dashboard) {wid}")
            skipped += 1
            continue

        if task_id:
            task = _get_task(cfg, task_id) if do_apply else {"id": task_id, "content": title}
            if do_apply and not _is_task_open(task):
                # 完了済み: 初回完了は必ず ack（表示:抑制不要）。
                # 以前完了済みなのに指紋が変わって再表示されたときだけ reopen。
                already_done = bool(prev.get("completed_at"))
                if already_done and prev.get("fingerprint") != fp:
                    try:
                        _todoist_req(
                            "POST",
                            f"/tasks/{urllib.parse.quote(task_id)}/reopen",
                            cfg=cfg,
                        )
                        body_re: dict[str, Any] = {"content": title}
                        if due:
                            body_re["due_string"] = due
                        _todoist_req(
                            "POST",
                            f"/tasks/{urllib.parse.quote(task_id)}",
                            cfg=cfg,
                            body=body_re,
                        )
                        _todoist_req(
                            "POST",
                            "/comments",
                            cfg=cfg,
                            body={
                                "task_id": task_id,
                                "content": (
                                    f"[Jarvis要フォロー同期] 再発のため reopen\n"
                                    f"level={row.get('level')} fingerprint変化"
                                )[:1900],
                            },
                        )
                        updated += 1
                        lines.append(f"  · [reopen] {wid}")
                        prev["fingerprint"] = fp
                        prev["title"] = title
                        prev.pop("completed_at", None)
                        mappings[wid] = prev
                    except Exception as exc:
                        lines.append(f"  ! reopen fail {wid}: {exc} → 新規へ")
                        mappings.pop(wid, None)
                        task_id = ""
                        prev = {}
                    if task_id:
                        continue
                else:
                    from jarvis_watch_user_ack import make_user_ack

                    def _ack(p: dict[str, Any], r: dict[str, Any]) -> None:
                        p["user_ack"] = make_user_ack(fp, days=quiet_days)
                        p["user_ack"]["acked_level"] = str(r.get("level") or "")
                        p["user_ack"]["ack_source"] = "todoist"
                        p["show_banner"] = False
                        p["badge_suppressed"] = True
                        p["todoist_task_id"] = task_id
                        p["todoist_url"] = _task_url(task_id)

                    try:
                        _patch_watch_payload(wid, _ack)
                        acked += 1
                        lines.append(f"  · ack from completed task {wid}")
                    except Exception as exc:
                        lines.append(f"  ! ack fail {wid}: {exc}")
                    prev["fingerprint"] = fp
                    prev["completed_at"] = datetime.now(JST).isoformat(
                        timespec="seconds"
                    )
                    mappings[wid] = prev
                    continue

            if task_id:
                # fingerprint 変化 → コメント＋タイトル更新
                if prev.get("fingerprint") == fp and prev.get("title") == title:
                    # まだ URL が payload に無いなら埋める
                    if do_apply and not pl.get("todoist_url"):

                        def _set_url(p: dict[str, Any], _r: dict[str, Any]) -> None:
                            p["todoist_task_id"] = task_id
                            p["todoist_url"] = _task_url(task_id)

                        try:
                            _patch_watch_payload(wid, _set_url)
                        except Exception:
                            pass
                    skipped += 1
                    lines.append(f"  · [ok] {wid}")
                    continue

                if do_apply:
                    try:
                        body: dict[str, Any] = {"content": title}
                        if due:
                            body["due_string"] = due
                        _todoist_req(
                            "POST",
                            f"/tasks/{urllib.parse.quote(task_id)}",
                            cfg=cfg,
                            body=body,
                        )
                        note = (
                            f"[Jarvis要フォロー同期] 状況更新\n"
                            f"level={row.get('level')} fingerprint変化\n"
                            f"summary: {str(row.get('summary') or '')[:200]}"
                        )
                        _todoist_req(
                            "POST",
                            "/comments",
                            cfg=cfg,
                            body={"task_id": task_id, "content": note[:1900]},
                        )

                        def _set_meta(p: dict[str, Any], _r: dict[str, Any]) -> None:
                            p["todoist_task_id"] = task_id
                            p["todoist_url"] = _task_url(task_id)
                            p["todoist_synced_at"] = datetime.now(JST).isoformat(
                                timespec="seconds"
                            )

                        _patch_watch_payload(wid, _set_meta)
                        updated += 1
                        lines.append(f"  · [update] {wid}")
                    except Exception as exc:
                        lines.append(f"  ! update fail {wid}: {exc}")
                    prev["fingerprint"] = fp
                    prev["title"] = title
                    mappings[wid] = prev
                else:
                    lines.append(f"  · would update {wid} — {title[:50]}")
                continue

        # create
        labels = [LABEL_FOLLOW]
        if _needs_jarvis_label(row):
            labels.append(LABEL_JARVIS)
        if do_apply:
            try:
                body = {
                    "content": title,
                    "project_id": inbox_pid,
                    "labels": labels,
                    "description": (
                        f"watch_id: {wid}\n"
                        f"level: {row.get('level')}\n"
                        f"source: {row.get('source') or '-'}\n"
                        f"dashboard: https://jarvis-dashboard-amber.vercel.app"
                        f"/situation?watch={urllib.parse.quote(wid)}"
                    ),
                }
                if due:
                    body["due_string"] = due
                created_t = _todoist_req("POST", "/tasks", cfg=cfg, body=body)
                tid = str(created_t.get("id") or "")
                url = str(created_t.get("url") or _task_url(tid))
                comment = (
                    "サマリ: ホーム要フォローから起票（Jarvis同期）\n"
                    f"アウトプット:\n"
                    f"- [状況ウォッチ](https://jarvis-dashboard-amber.vercel.app"
                    f"/situation?watch={urllib.parse.quote(wid)})\n"
                    "コメント先頭 `表示: 抑制` / `表示: ピン` / `表示: 通常` / `表示: 降格` で出し方を変えられます。"
                )
                if tid:
                    _todoist_req(
                        "POST",
                        "/comments",
                        cfg=cfg,
                        body={"task_id": tid, "content": comment[:1900]},
                    )

                def _set_new(p: dict[str, Any], _r: dict[str, Any]) -> None:
                    p["todoist_task_id"] = tid
                    p["todoist_url"] = url or _task_url(tid)
                    p["todoist_synced_at"] = datetime.now(JST).isoformat(
                        timespec="seconds"
                    )

                _patch_watch_payload(wid, _set_new)
                mappings[wid] = {
                    "task_id": tid,
                    "fingerprint": fp,
                    "title": title,
                    "url": url or _task_url(tid),
                    "created_at": datetime.now(JST).isoformat(timespec="seconds"),
                }
                created += 1
                lines.append(f"  · [create] {wid} → {tid}")
            except Exception as exc:
                lines.append(f"  ! create fail {wid}: {exc}")
        else:
            lines.append(f"  · would create {wid} — {title[:50]}")

    # 2) mapping あり・ホーム非表示・タスク未完了 → 完了連動はしない（ack済みで外れただけ）
    #    ただし Todoist 完了済みで mapping だけ残っている分は fingerprint 記録維持

    # 3) ホーム外だが Todoist が開いたまま＆user_ack 無し → 触らない（人が残したタスク）

    state["todoist_by_watch_id"] = mappings
    state["last_run_at"] = datetime.now(JST).isoformat(timespec="seconds")
    state["last_counts"] = {
        "created": created,
        "updated": updated,
        "completed": completed,
        "acked": acked,
        "skipped": skipped,
        "home": len(home_rows),
    }
    if do_apply:
        _save_state(state)
        _save_hints(hints_state)

    lines.append(
        f"- 結果: create={created} update={updated} complete={completed} "
        f"ack={acked} skip={skipped}"
    )
    lines.append(f"- state: {STATE_PATH}")
    if args.json:
        print(
            json.dumps(
                {
                    "mode": "apply" if do_apply else "dry-run",
                    "home": [
                        {"id": str(w.get("id")), "title": _title_for(w)}
                        for w in home_rows
                    ],
                    "counts": state["last_counts"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        if not do_apply:
            lines.append("- 実行するとき: --apply（yaml enabled:true または --force）")
        print("\n".join(lines))
    return 0


def apply_display_hint(
    watch_id: str,
    *,
    action: str,
    quiet_days: int = 30,
) -> dict[str, Any]:
    """Webhook 等から呼ぶ。action: suppress|pin|normal|demote"""
    hints = _load_hints()
    now = datetime.now(timezone.utc)
    until = (now + timedelta(days=max(1, quiet_days))).isoformat(timespec="seconds")

    def mut(p: dict[str, Any], _r: dict[str, Any]) -> None:
        dh = dict(_as_dict(p.get("display_hints")))
        if action == "suppress":
            dh = {
                "suppress_home": True,
                "pin_home_top": False,
                "demote": False,
                "quiet_until": until,
                "updated_at": now.isoformat(timespec="seconds"),
                "source": "todoist_comment",
            }
            from jarvis_watch_user_ack import build_fingerprint, make_user_ack

            fp = build_fingerprint(
                watch_id,
                level=str(_r.get("level") or ""),
                summary=str(_r.get("summary") or ""),
                payload=p,
            )
            p["user_ack"] = make_user_ack(fp, days=quiet_days)
            p["user_ack"]["ack_source"] = "display_hint"
            p["show_banner"] = False
            p["badge_suppressed"] = True
        elif action == "pin":
            dh["suppress_home"] = False
            dh["pin_home_top"] = True
            dh["demote"] = False
            dh["updated_at"] = now.isoformat(timespec="seconds")
            dh["source"] = "todoist_comment"
            p.pop("badge_suppressed", None)
        elif action == "demote":
            dh["suppress_home"] = False
            dh["demote"] = True
            dh["pin_home_top"] = False
            dh["updated_at"] = now.isoformat(timespec="seconds")
            dh["source"] = "todoist_comment"
        elif action == "normal":
            dh = {
                "suppress_home": False,
                "pin_home_top": False,
                "demote": False,
                "updated_at": now.isoformat(timespec="seconds"),
                "source": "todoist_comment",
            }
            p.pop("badge_suppressed", None)
        p["display_hints"] = dh
        hints.setdefault("by_watch_id", {})[watch_id] = dict(dh)

    pl = _patch_watch_payload(watch_id, mut)
    _save_hints(hints)
    return {"ok": True, "watch_id": watch_id, "action": action, "payload_hints": _as_dict(pl).get("display_hints") if pl else None}


def parse_display_hint_comment(text: str) -> str | None:
    t = str(text or "").strip()
    if t.startswith("表示: 抑制") or t.startswith("表示：抑制"):
        return "suppress"
    if t.startswith("表示: ピン") or t.startswith("表示：ピン"):
        return "pin"
    if t.startswith("表示: 通常") or t.startswith("表示：通常"):
        return "normal"
    if t.startswith("表示: 降格") or t.startswith("表示：降格"):
        return "demote"
    return None


def watch_id_from_task_title(title: str) -> str | None:
    m = re.search(r"\[要フォロー\]\[([^\]]+)\]", str(title or ""))
    return m.group(1).strip() if m else None


def ack_watch_on_todoist_complete(
    watch_id: str,
    *,
    task_id: str | None = None,
    quiet_days: int | None = None,
) -> dict[str, Any]:
    """Todoist 完了 → ホーム要フォローから外す（user_ack）。表示:抑制は不要。"""
    from jarvis_watch_user_ack import build_fingerprint, make_user_ack

    days = int(quiet_days) if quiet_days is not None else 7
    wid = str(watch_id or "").strip()
    if not wid:
        return {"ok": False, "error": "watch_id empty"}

    def mut(p: dict[str, Any], r: dict[str, Any]) -> None:
        fp = build_fingerprint(
            wid,
            level=str(r.get("level") or ""),
            summary=str(r.get("summary") or ""),
            payload=p,
        )
        p["user_ack"] = make_user_ack(fp, days=days)
        p["user_ack"]["acked_level"] = str(r.get("level") or "")
        p["user_ack"]["ack_source"] = "todoist"
        p["show_banner"] = False
        p["badge_suppressed"] = True
        if task_id:
            p["todoist_task_id"] = str(task_id)
            p["todoist_url"] = _task_url(str(task_id))

    pl = _patch_watch_payload(wid, mut)
    if pl is None:
        return {"ok": False, "error": "watch not found", "watch_id": wid}

    # state の fingerprint を揃えて再起票を防ぐ
    state = _load_state()
    mappings = dict(state.get("todoist_by_watch_id") or {})
    prev = dict(mappings.get(wid) or {})
    if task_id:
        prev["task_id"] = str(task_id)
    from jarvis_watch_user_ack import build_fingerprint

    # fingerprint は patch 後 payload で再計算
    rows = _sb_req(
        "GET",
        f"watch_status?id=eq.{urllib.parse.quote(wid)}&select=id,level,summary,payload",
    )
    if isinstance(rows, list) and rows:
        r0 = rows[0]
        prev["fingerprint"] = build_fingerprint(
            wid,
            level=str(r0.get("level") or ""),
            summary=str(r0.get("summary") or ""),
            payload=_as_dict(r0.get("payload")),
        )
    prev["completed_at"] = datetime.now(JST).isoformat(timespec="seconds")
    mappings[wid] = prev
    state["todoist_by_watch_id"] = mappings
    _save_state(state)
    return {"ok": True, "watch_id": wid, "ack_source": "todoist"}


if __name__ == "__main__":
    raise SystemExit(main())
