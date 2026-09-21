#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Todoist REST API（Jarvis タスク正本・試験導入）。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_api.py whoami
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_api.py probe
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_api.py bootstrap --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_api.py bootstrap --write-config
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_api.py lane --id ai_raimo
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_api.py create-task --lane ai_raimo --title '[L-01] …'
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_api.py update-status --task-id … --lane ai_raimo --status 進行中
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_api.py update-status --task-id … --lane ai_raimo --status HOLD
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_api.py complete-task --task-id … --comment 'タスク完了したよ（Jarvis）'
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_api.py hold-review
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_api.py seed-nokori --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_api.py seed-nokori --apply

正本トークン: .env.jarvis_private の TODOIST_API_TOKEN
設定: config/todoist_projects.yaml
値は標準出力に出さない。

HOLD: update-status HOLD でコメント「HOLD since: YYYY-MM-DD」＋ due+30日。
1ヶ月レビューは hold-review / jarvis_todoist_hold_review.py。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
YAML_PATH = REPO / "config" / "todoist_projects.yaml"
NOKORI_MD = REPO / "docs" / "残り棚_アプリ受け入れ_20260830.md"
COMPLETE_PHRASE = "タスク完了したよ"
DEFAULT_API = "https://api.todoist.com/api/v1"
JST = ZoneInfo("Asia/Tokyo")
HOLD_SINCE_RE = re.compile(r"HOLD since:\s*(\d{4}-\d{2}-\d{2})", re.I)
HOLD_REVIEW_DAYS = 30


def _load_yaml() -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ImportError:
        print("ERROR: PyYAML が必要です", file=sys.stderr)
        sys.exit(2)
    if not YAML_PATH.is_file():
        print(f"ERROR: 設定がありません: {YAML_PATH}", file=sys.stderr)
        sys.exit(2)
    data = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8")) or {}
    return dict(data)


def _save_yaml(data: dict[str, Any]) -> None:
    try:
        import yaml  # type: ignore
    except ImportError:
        print("ERROR: PyYAML が必要です", file=sys.stderr)
        sys.exit(2)
    YAML_PATH.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def _token() -> str:
    tok = (os.environ.get("TODOIST_API_TOKEN") or "").strip()
    if not tok:
        print("ERROR: TODOIST_API_TOKEN 未設定（.env.jarvis_private）", file=sys.stderr)
        sys.exit(2)
    return tok


def _api_base(cfg: dict[str, Any] | None = None) -> str:
    base = ((cfg or {}).get("api_base") or DEFAULT_API).rstrip("/")
    return base


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_token()}",
        "Content-Type": "application/json",
    }


def _req(
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    *,
    cfg: dict[str, Any] | None = None,
    allow_empty: bool = False,
    raise_http: bool = False,
) -> Any:
    data = None if body is None else json.dumps(body).encode("utf-8")
    url = f"{_api_base(cfg)}{path}"
    req = urllib.request.Request(url, data=data, headers=_headers(), method=method)
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            raw = resp.read()
            if allow_empty or resp.status == 204 or not raw:
                return {"ok": True, "status": resp.status}
            return json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")[:800]
        if raise_http:
            raise
        print(f"ERROR: HTTP {e.code} {method} {path}: {err_body}", file=sys.stderr)
        sys.exit(1)


def _paginate_results(path: str, *, cfg: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    cursor: str | None = None
    while True:
        q = path
        if cursor:
            sep = "&" if "?" in path else "?"
            q = f"{path}{sep}cursor={urllib.parse.quote(cursor)}"
        data = _req("GET", q, cfg=cfg)
        if isinstance(data, list):
            out.extend(data)
            break
        if not isinstance(data, dict):
            break
        results = data.get("results")
        if isinstance(results, list):
            out.extend(results)
        elif data.get("id"):
            out.append(data)
            break
        cursor = data.get("next_cursor")
        if not cursor:
            break
    return out


def _ensure_complete_comment(raw: str, who: str = "") -> str:
    text = (raw or "").strip()
    who = (who or "").strip()
    phrase = COMPLETE_PHRASE
    if text.startswith(phrase):
        return text[:1900]
    extra = f"（{who}）" if who else ""
    if text:
        return f"{phrase}{extra} {text}"[:1900]
    return f"{phrase}{extra}"[:1900]


def _lane(cfg: dict[str, Any], lane_id: str) -> dict[str, Any]:
    lanes = cfg.get("lanes") or {}
    lane = lanes.get(lane_id)
    if not isinstance(lane, dict):
        print(f"ERROR: 未知の lane: {lane_id}", file=sys.stderr)
        sys.exit(2)
    return lane


def _project_for_lane(cfg: dict[str, Any], lane: dict[str, Any]) -> dict[str, Any]:
    key = str(lane.get("project_key") or "").strip()
    projects = cfg.get("projects") or {}
    proj = projects.get(key)
    if not isinstance(proj, dict):
        print(f"ERROR: project_key が不正: {key}", file=sys.stderr)
        sys.exit(2)
    pid = str(lane.get("project_id") or proj.get("project_id") or "").strip()
    if not pid:
        print(
            f"ERROR: project_id 未設定（lane/project）。先に bootstrap --write-config",
            file=sys.stderr,
        )
        sys.exit(2)
    return {**proj, "project_id": pid, "_key": key}


def _section_id(proj: dict[str, Any], section_name: str) -> str:
    ids = proj.get("section_ids") or {}
    sid = str(ids.get(section_name) or "").strip()
    if not sid:
        print(f"ERROR: section_id 未設定: {section_name}", file=sys.stderr)
        sys.exit(2)
    return sid


def cmd_whoami(_args: argparse.Namespace) -> int:
    cfg = _load_yaml()
    data = _req("GET", "/user", cfg=cfg)
    email = data.get("email") or data.get("full_name") or "?"
    print(f"ok user={email} id={data.get('id', '')}")
    return 0


def cmd_probe(_args: argparse.Namespace) -> int:
    cfg = _load_yaml()
    projects = _paginate_results("/projects", cfg=cfg)
    print(f"projects={len(projects)} layout={cfg.get('layout')}")
    for key, lane in (cfg.get("lanes") or {}).items():
        pid = str(lane.get("project_id") or "").strip()
        label = lane.get("lane_label") or key
        status = "ready" if pid else "NEED_BOOTSTRAP"
        print(f"  lane={key} label={label} project_id={pid or '-'} [{status}]")
    return 0


def cmd_bootstrap(args: argparse.Namespace) -> int:
    cfg = _load_yaml()
    dry = not args.write_config
    existing = {p.get("name"): p for p in _paginate_results("/projects", cfg=cfg)}
    section_cache: dict[str, dict[str, str]] = {}

    for key, proj in (cfg.get("projects") or {}).items():
        name = str(proj.get("name") or key)
        pid = str(proj.get("project_id") or "").strip()
        found = existing.get(name)
        if found and not pid:
            pid = str(found.get("id") or "")
            print(f"# reuse project name={name} id={pid}")
        elif pid:
            print(f"# keep project key={key} id={pid}")
        elif dry:
            print(f"# would create project name={name} view_style={proj.get('view_style')}")
            continue
        else:
            created = _req(
                "POST",
                "/projects",
                {
                    "name": name,
                    "view_style": proj.get("view_style") or "board",
                },
                cfg=cfg,
            )
            pid = str(created.get("id") or "")
            print(f"# created project name={name} id={pid}")
        proj["project_id"] = pid

        # sections
        if dry and not pid:
            continue
        if pid not in section_cache:
            secs = _paginate_results(f"/sections?project_id={urllib.parse.quote(pid)}", cfg=cfg)
            section_cache[pid] = {str(s.get("name")): str(s.get("id")) for s in secs}
        sid_map = dict(proj.get("section_ids") or {})
        for sec_name in cfg.get("default_sections") or []:
            if sec_name in section_cache[pid]:
                sid_map[sec_name] = section_cache[pid][sec_name]
                continue
            if dry:
                print(f"# would create section project={name} section={sec_name}")
                continue
            created_s = _req(
                "POST",
                "/sections",
                {"name": sec_name, "project_id": pid},
                cfg=cfg,
            )
            sid = str(created_s.get("id") or "")
            sid_map[sec_name] = sid
            section_cache[pid][sec_name] = sid
            print(f"# created section project={name} section={sec_name} id={sid}")
        proj["section_ids"] = sid_map

    # labels
    existing_labels = {
        str(x.get("name")): x for x in _paginate_results("/labels", cfg=cfg)
    }
    for lab in cfg.get("labels") or []:
        if lab in existing_labels:
            continue
        if dry:
            print(f"# would create label name={lab}")
            continue
        _req("POST", "/labels", {"name": lab}, cfg=cfg)
        print(f"# created label name={lab}")

    # sync lane project_ids from project_key
    for _lid, lane in (cfg.get("lanes") or {}).items():
        pkey = str(lane.get("project_key") or "")
        p = (cfg.get("projects") or {}).get(pkey) or {}
        lane["project_id"] = str(p.get("project_id") or "")

    if dry:
        print("# dry-run: 変更なし。適用は --write-config")
        return 0

    _save_yaml(cfg)
    print(f"# wrote {YAML_PATH}")
    return 0


def cmd_lane(args: argparse.Namespace) -> int:
    cfg = _load_yaml()
    lane = _lane(cfg, args.id)
    proj = _project_for_lane(cfg, lane)
    pid = proj["project_id"]
    tasks = _paginate_results(f"/tasks?project_id={urllib.parse.quote(pid)}", cfg=cfg)
    label = str(lane.get("lane_label") or args.id)
    hide_done = bool(lane.get("hide_done_on_board"))
    # Board「完了」列は廃止。done_sections 空なら列フィルタなし（close 済みは API に出ない）
    done_names = set(lane.get("done_sections") or [])
    sid_to_name = {v: k for k, v in (proj.get("section_ids") or {}).items()}

    filtered: list[dict[str, Any]] = []
    for t in tasks:
        labels = [str(x) for x in (t.get("labels") or [])]
        # work_bundle 同居レーンは lane_label 必須。専用プロジェクトは全件。
        if args.id != "properties" and label and label not in labels:
            pkey = str(lane.get("project_key") or "")
            if pkey == "work_bundle":
                continue
        if hide_done and done_names:
            sec = sid_to_name.get(str(t.get("section_id") or ""), "")
            if sec in done_names:
                continue
        filtered.append(t)

    print(f"lane={args.id} project={proj.get('name')} tasks={len(filtered)}")
    for t in filtered[:80]:
        sec = sid_to_name.get(str(t.get("section_id") or ""), "-")
        print(f"  [{sec}] {t.get('id')} {t.get('content')}")
    if len(filtered) > 80:
        print(f"  … +{len(filtered) - 80}")
    return 0


def _validate_properties_labels(cfg: dict[str, Any], labels: list[str]) -> None:
    """所有物件レーンは物件ラベル1＋PMラベル1必須。"""
    prop_keys = set((cfg.get("property_labels") or {}).keys())
    pm_keys = set((cfg.get("pm_labels") or {}).keys())
    have_prop = [x for x in labels if x in prop_keys]
    have_pm = [x for x in labels if x in pm_keys]
    if len(have_prop) != 1 or len(have_pm) != 1:
        print(
            "ERROR: --lane properties では物件ラベル1つ＋管理会社ラベル1つが必須です。"
            f" 例: --label GrandoleI,ミニテック"
            f" / 現在 labels={labels}"
            f" / 物件={sorted(prop_keys)} / PM={sorted(pm_keys)}",
            file=sys.stderr,
        )
        sys.exit(2)


def cmd_create_task(args: argparse.Namespace) -> int:
    cfg = _load_yaml()
    lane = _lane(cfg, args.lane)
    proj = _project_for_lane(cfg, lane)
    section = args.status or lane.get("initial_section") or "未着手"
    sid = _section_id(proj, section)
    labels = [str(lane.get("lane_label") or args.lane)]
    if args.label:
        labels.extend([x.strip() for x in args.label.split(",") if x.strip()])
    # 重複除去（順序維持）
    seen: set[str] = set()
    labels = [x for x in labels if not (x in seen or seen.add(x))]
    if args.lane == "properties":
        _validate_properties_labels(cfg, labels)
    body: dict[str, Any] = {
        "content": args.title.strip(),
        "project_id": proj["project_id"],
        "section_id": sid,
        "labels": labels,
    }
    if args.due:
        body["due_string"] = args.due
    if args.note:
        body["description"] = args.note
    created = _req("POST", "/tasks", body, cfg=cfg)
    tid = created.get("id")
    url = created.get("url") or ""
    if args.comment and tid:
        _req(
            "POST",
            "/comments",
            {"task_id": tid, "content": str(args.comment)[:1900]},
            cfg=cfg,
        )
    if section == "HOLD" and tid and not getattr(args, "no_hold_stamp", False):
        since = _stamp_hold(str(tid), cfg=cfg)
        due = since + timedelta(days=HOLD_REVIEW_DAYS)
        if not args.json:
            print(f"hold_stamp since={since.isoformat()} due={due.isoformat()}")
    if args.json:
        print(
            json.dumps(
                {
                    "ok": True,
                    "id": tid,
                    "lane": args.lane,
                    "section": section,
                    "url": url,
                    "commented": bool(args.comment),
                },
                ensure_ascii=False,
            )
        )
    else:
        print(f"created id={tid} lane={args.lane} section={section}")
        if args.url and url:
            print(f"url={url}")
        if args.comment:
            print(f"commented id={tid}")
    return 0


def _move_to_section(task_id: str, section_id: str, *, cfg: dict[str, Any]) -> None:
    # Prefer REST move; fall back to Sync API item_move.
    try:
        _req(
            "POST",
            f"/tasks/{urllib.parse.quote(task_id)}/move",
            {"section_id": section_id},
            cfg=cfg,
            allow_empty=True,
            raise_http=True,
        )
        return
    except urllib.error.HTTPError:
        pass
    cmd = {
        "type": "item_move",
        "uuid": str(uuid.uuid4()),
        "args": {"id": task_id, "section_id": section_id},
    }
    # Sync endpoint expects form-style or JSON depending on client; use form body.
    form = urllib.parse.urlencode(
        {"commands": json.dumps([cmd])}
    ).encode("utf-8")
    url = f"{_api_base(cfg)}/sync"
    headers = {
        "Authorization": f"Bearer {_token()}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    req = urllib.request.Request(url, data=form, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            raw = resp.read().decode("utf-8")
            data = json.loads(raw) if raw else {}
            status = (data.get("sync_status") or {}).get(cmd["uuid"])
            if status not in (None, "ok", True) and status != "ok":
                print(f"ERROR: sync move failed: {status}", file=sys.stderr)
                sys.exit(1)
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")[:800]
        print(f"ERROR: HTTP {e.code} sync move: {err_body}", file=sys.stderr)
        sys.exit(1)


def _jst_today() -> date:
    return datetime.now(JST).date()


def _hold_since_comment(day: date | None = None) -> str:
    d = day or _jst_today()
    return f"HOLD since: {d.isoformat()}"


def _stamp_hold(task_id: str, *, cfg: dict[str, Any], day: date | None = None) -> date:
    """HOLD 移設時: コメント印＋ due を JST 今日+30日。戻り値は since 日。"""
    since = day or _jst_today()
    due = since + timedelta(days=HOLD_REVIEW_DAYS)
    _req(
        "POST",
        "/comments",
        {"task_id": task_id, "content": _hold_since_comment(since)},
        cfg=cfg,
    )
    _req(
        "POST",
        f"/tasks/{urllib.parse.quote(task_id)}",
        {"due_date": due.isoformat()},
        cfg=cfg,
        allow_empty=True,
    )
    return since


def _parse_hold_since_from_comments(task_id: str, *, cfg: dict[str, Any]) -> date | None:
    comments = _paginate_results(
        f"/comments?task_id={urllib.parse.quote(task_id)}", cfg=cfg
    )
    best: date | None = None
    for c in comments:
        text = str(c.get("content") or "")
        m = HOLD_SINCE_RE.search(text)
        if not m:
            continue
        try:
            d = date.fromisoformat(m.group(1))
        except ValueError:
            continue
        if best is None or d > best:
            best = d
    return best


def _hold_since_from_activity(
    task_id: str, hold_section_id: str, *, cfg: dict[str, Any]
) -> date | None:
    """Activity moved → HOLD の最新 event_date（JST 日付）。"""
    path = (
        f"/activities?object_type=item&object_id={urllib.parse.quote(task_id)}"
        f"&event_type=moved&limit=50"
    )
    try:
        events = _paginate_results(path, cfg=cfg)
    except SystemExit:
        return None
    hold_sid = str(hold_section_id)
    best: date | None = None
    for e in events:
        if str(e.get("event_type") or "") != "moved":
            continue
        extra = e.get("extra_data") or {}
        if str(extra.get("section_id") or "") != hold_sid:
            continue
        raw = str(e.get("event_date") or "")
        if not raw:
            continue
        try:
            # 2026-09-21T13:42:03.155449Z
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            d = dt.astimezone(JST).date()
        except ValueError:
            continue
        if best is None or d > best:
            best = d
    return best


def cmd_update_status(args: argparse.Namespace) -> int:
    cfg = _load_yaml()
    lane = _lane(cfg, args.lane)
    proj = _project_for_lane(cfg, lane)
    status = str(args.status).strip()
    sid = _section_id(proj, status)
    _move_to_section(args.task_id, sid, cfg=cfg)
    print(f"moved id={args.task_id} section={status}")
    if status == "HOLD" and not getattr(args, "no_hold_stamp", False):
        since = _stamp_hold(args.task_id, cfg=cfg)
        due = since + timedelta(days=HOLD_REVIEW_DAYS)
        print(f"hold_stamp since={since.isoformat()} due={due.isoformat()}")
    return 0


def _lane_for_project_task(
    cfg: dict[str, Any], project_key: str, labels: list[str]
) -> str:
    """project_key + labels から表示用 lane id を推定。"""
    for lid, lane in (cfg.get("lanes") or {}).items():
        if str(lane.get("project_key") or "") != project_key:
            continue
        ll = str(lane.get("lane_label") or lid)
        pkey = str(lane.get("project_key") or "")
        if pkey == "work_bundle":
            if ll in labels:
                return str(lid)
        else:
            return str(lid)
    return project_key


def cmd_hold_review(args: argparse.Namespace) -> int:
    """HOLD 列を走査し、経過 HOLD_REVIEW_DAYS 日以上を報告。"""
    cfg = _load_yaml()
    today = _jst_today()
    raw_min = getattr(args, "min_days", None)
    min_days = HOLD_REVIEW_DAYS if raw_min is None else int(raw_min)
    due_only = bool(getattr(args, "due_only", False))
    items: list[dict[str, Any]] = []

    for pkey, proj in (cfg.get("projects") or {}).items():
        if not isinstance(proj, dict):
            continue
        sid_map = proj.get("section_ids") or {}
        hold_sid = sid_map.get("HOLD")
        if not hold_sid:
            continue
        hold_sid = str(hold_sid)
        pid = str(proj.get("project_id") or "")
        if not pid:
            continue
        tasks = _paginate_results(
            f"/tasks?project_id={urllib.parse.quote(pid)}", cfg=cfg
        )
        for t in tasks:
            if str(t.get("section_id") or "") != hold_sid:
                continue
            if t.get("checked") or t.get("is_completed"):
                continue
            tid = str(t.get("id") or "")
            labels = [str(x) for x in (t.get("labels") or [])]
            lane_id = _lane_for_project_task(cfg, str(pkey), labels)
            since = _parse_hold_since_from_comments(tid, cfg=cfg)
            source = "comment"
            if since is None:
                since = _hold_since_from_activity(tid, hold_sid, cfg=cfg)
                source = "activity" if since is not None else "unknown"
            if since is None:
                # 最終手段: added_at（新規作成直後に HOLD のケース）
                raw = str(t.get("added_at") or "")
                try:
                    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                    since = dt.astimezone(JST).date()
                    source = "added_at"
                except ValueError:
                    since = today
                    source = "unknown"
            days = (today - since).days
            if days < min_days:
                continue
            items.append(
                {
                    "task_id": tid,
                    "lane": lane_id,
                    "project": proj.get("name") or pkey,
                    "title": t.get("content") or "",
                    "since": since.isoformat(),
                    "days": days,
                    "source": source,
                    "url": t.get("url") or "",
                }
            )

    items.sort(key=lambda x: (-int(x["days"]), str(x["title"])))
    if getattr(args, "json", False):
        print(json.dumps({"ok": True, "count": len(items), "items": items}, ensure_ascii=False))
        return 0

    if not items:
        if not due_only:
            print("📎 HOLDレビュー（1ヶ月超）: 対象なし")
        return 0

    print("📎 HOLDレビュー（1ヶ月超）")
    for i, it in enumerate(items, 1):
        print(
            f"- [{i}] [{it['lane']}] {it['title']} — HOLD since {it['since']}（{it['days']}日・{it['source']}）"
        )
        print("  次: 延長 / 再開(進行中|未着手) / 閉じる")
    print("了承なら番号か方針を返信。")
    return 0


def cmd_hold_extend(args: argparse.Namespace) -> int:
    """延長: HOLD since を今日に更新＋ due+30。"""
    cfg = _load_yaml()
    since = _stamp_hold(args.task_id, cfg=cfg)
    due = since + timedelta(days=HOLD_REVIEW_DAYS)
    print(f"hold_extended id={args.task_id} since={since.isoformat()} due={due.isoformat()}")
    return 0


def cmd_hold_stamp_missing(args: argparse.Namespace) -> int:
    """HOLD 列で since 印が無いタスクに印＋due を付ける（UI移動の穴埋め）。"""
    if os.environ.get("JARVIS_TODOIST_HOLD_STAMP_DISABLE", "").strip() in (
        "1",
        "true",
        "yes",
    ):
        print("hold_stamp_missing: disabled")
        return 0
    cfg = _load_yaml()
    dry = bool(getattr(args, "dry_run", False))
    stamped: list[dict[str, Any]] = []
    skipped = 0

    for pkey, proj in (cfg.get("projects") or {}).items():
        if not isinstance(proj, dict):
            continue
        sid_map = proj.get("section_ids") or {}
        hold_sid = sid_map.get("HOLD")
        if not hold_sid:
            continue
        hold_sid = str(hold_sid)
        pid = str(proj.get("project_id") or "")
        if not pid:
            continue
        tasks = _paginate_results(
            f"/tasks?project_id={urllib.parse.quote(pid)}", cfg=cfg
        )
        for t in tasks:
            if str(t.get("section_id") or "") != hold_sid:
                continue
            if t.get("checked") or t.get("is_completed"):
                continue
            tid = str(t.get("id") or "")
            if not tid:
                continue
            existing = _parse_hold_since_from_comments(tid, cfg=cfg)
            if existing is not None:
                skipped += 1
                continue
            since = _hold_since_from_activity(tid, hold_sid, cfg=cfg)
            source = "activity"
            if since is None:
                since = _jst_today()
                source = "today"
            entry = {
                "task_id": tid,
                "project": proj.get("name") or pkey,
                "title": t.get("content") or "",
                "since": since.isoformat(),
                "source": source,
                "due": (since + timedelta(days=HOLD_REVIEW_DAYS)).isoformat(),
            }
            if not dry:
                _stamp_hold(tid, cfg=cfg, day=since)
            stamped.append(entry)

    if getattr(args, "json", False):
        print(
            json.dumps(
                {
                    "ok": True,
                    "dry_run": dry,
                    "stamped": len(stamped),
                    "skipped_has_stamp": skipped,
                    "items": stamped,
                },
                ensure_ascii=False,
            )
        )
        return 0

    mode = "dry-run" if dry else "apply"
    print(f"hold_stamp_missing ({mode}): stamped={len(stamped)} skipped_has_stamp={skipped}")
    for it in stamped:
        print(
            f"  [{it['project']}] {it['title'][:60]} since={it['since']} due={it['due']} ({it['source']})"
        )
    return 0


def cmd_comment(args: argparse.Namespace) -> int:
    cfg = _load_yaml()
    _req(
        "POST",
        "/comments",
        {"task_id": args.task_id, "content": args.text[:1900]},
        cfg=cfg,
    )
    print(f"commented id={args.task_id}")
    return 0


def cmd_complete_task(args: argparse.Namespace) -> int:
    cfg = _load_yaml()
    lane = _lane(cfg, args.lane) if args.lane else None
    comment = _ensure_complete_comment(args.comment or "", args.who or "")
    _req(
        "POST",
        "/comments",
        {"task_id": args.task_id, "content": comment},
        cfg=cfg,
    )
    # optional: move to done_sections[0] before close（空ならスキップ＝Board「完了」列なし）
    if lane:
        done_list = list(lane.get("done_sections") or [])
        if done_list:
            proj = _project_for_lane(cfg, lane)
            try:
                sid = _section_id(proj, done_list[0])
                _move_to_section(args.task_id, sid, cfg=cfg)
            except Exception:
                pass
    _req(
        "POST",
        f"/tasks/{urllib.parse.quote(args.task_id)}/close",
        cfg=cfg,
        allow_empty=True,
    )
    print(f"completed id={args.task_id}")
    return 0


def _parse_nokori_open() -> list[dict[str, str]]:
    if not NOKORI_MD.is_file():
        return []
    text = NOKORI_MD.read_text(encoding="utf-8")
    items: list[dict[str, str]] = []
    blocks = re.split(r"\n###\s+", text)
    for block in blocks[1:]:
        lines = block.strip().splitlines()
        if not lines:
            continue
        title = lines[0].strip()
        m = re.match(r"(L-\d+)\s+(.+)", title)
        if not m:
            continue
        lid, rest = m.group(1), m.group(2)
        status = ""
        intent = ""
        for ln in lines[1:]:
            if ln.startswith("- 状態:"):
                status = ln.split(":", 1)[1].strip()
            if ln.startswith("- 意図:"):
                intent = ln.split(":", 1)[1].strip()
        if status in ("done", "drop"):
            continue
        if status not in ("this-week", "open", "parked") and "this-week" not in status:
            # keep this-week and parked that are still actionable; skip unclear
            if not status.startswith("this-week") and status != "parked":
                continue
        items.append(
            {
                "id": lid,
                "title": f"[{lid}] {rest}",
                "note": intent,
                "status": status,
            }
        )
    return items


def cmd_seed_nokori(args: argparse.Namespace) -> int:
    cfg = _load_yaml()
    items = _parse_nokori_open()
    # Focus: this-week first, then parked if --include-parked
    selected = []
    for it in items:
        st = it["status"]
        if st.startswith("this-week") or st == "open":
            selected.append(it)
        elif args.include_parked and st == "parked":
            selected.append(it)
    print(f"candidates={len(selected)}")
    for it in selected:
        print(f"  {it['title']} ({it['status']})")
    if args.dry_run or not args.apply:
        print("# dry-run / 未 --apply。起票する場合: --apply")
        return 0
    lane_id = args.lane or "ai_raimo"
    for it in selected:
        ns = argparse.Namespace(
            lane=lane_id,
            title=it["title"],
            note=it.get("note") or "",
            due=None,
            status=None,
            label="L-id,inbox_review",
            url=False,
            comment="",
            json=False,
        )
        cmd_create_task(ns)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Jarvis Todoist API")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("whoami")
    sub.add_parser("probe")

    b = sub.add_parser("bootstrap")
    b.add_argument("--dry-run", action="store_true", help="互換: 既定が dry")
    b.add_argument(
        "--write-config",
        action="store_true",
        help="プロジェクト/セクション作成し YAML に ID を書く",
    )

    lane_p = sub.add_parser("lane")
    lane_p.add_argument("--id", required=True)

    c = sub.add_parser("create-task")
    c.add_argument("--lane", required=True)
    c.add_argument("--title", required=True)
    c.add_argument("--note", default="")
    c.add_argument("--due", default=None)
    c.add_argument("--status", default=None, help="セクション名（既定: 未着手）")
    c.add_argument("--label", default="", help="追加ラベル（カンマ区切り）")
    c.add_argument("--url", action="store_true")
    c.add_argument(
        "--comment",
        default="",
        help="作成直後に付けるコメント（サマリ・アウトプットリンク用）",
    )
    c.add_argument("--json", action="store_true", help="1行 JSON で結果出力")
    c.add_argument(
        "--no-hold-stamp",
        action="store_true",
        help="--status HOLD 時に since 印・due+30 を付けない",
    )

    u = sub.add_parser("update-status")
    u.add_argument("--task-id", required=True)
    u.add_argument("--lane", required=True)
    u.add_argument("--status", required=True)
    u.add_argument(
        "--no-hold-stamp",
        action="store_true",
        help="HOLD 移設時に since 印・due+30 を付けない",
    )

    hr = sub.add_parser("hold-review", help="HOLD 列の1ヶ月超一覧")
    hr.add_argument("--min-days", type=int, default=HOLD_REVIEW_DAYS)
    hr.add_argument("--json", action="store_true")
    hr.add_argument(
        "--due-only",
        action="store_true",
        help="対象0件なら何も出さない（月次ついで用）",
    )

    he = sub.add_parser("hold-extend", help="HOLD 延長（since 更新＋due+30）")
    he.add_argument("--task-id", required=True)

    hs = sub.add_parser(
        "hold-stamp-missing",
        help="HOLD 列で since 印が無いタスクに印＋due を付ける",
    )
    hs.add_argument("--dry-run", action="store_true")
    hs.add_argument("--json", action="store_true")

    cm = sub.add_parser("comment")
    cm.add_argument("--task-id", required=True)
    cm.add_argument("--text", required=True)

    done = sub.add_parser("complete-task")
    done.add_argument("--task-id", required=True)
    done.add_argument("--lane", default=None)
    done.add_argument("--comment", default="")
    done.add_argument("--who", default="")

    seed = sub.add_parser("seed-nokori")
    seed.add_argument("--dry-run", action="store_true")
    seed.add_argument("--apply", action="store_true")
    seed.add_argument("--lane", default="ai_raimo")
    seed.add_argument("--include-parked", action="store_true")

    args = p.parse_args()
    dispatch = {
        "whoami": cmd_whoami,
        "probe": cmd_probe,
        "bootstrap": cmd_bootstrap,
        "lane": cmd_lane,
        "create-task": cmd_create_task,
        "update-status": cmd_update_status,
        "hold-review": cmd_hold_review,
        "hold-extend": cmd_hold_extend,
        "hold-stamp-missing": cmd_hold_stamp_missing,
        "comment": cmd_comment,
        "complete-task": cmd_complete_task,
        "seed-nokori": cmd_seed_nokori,
    }
    return dispatch[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
