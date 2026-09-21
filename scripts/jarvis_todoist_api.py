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
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_api.py complete-task --task-id … --comment 'タスク完了したよ（Jarvis）'
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_api.py seed-nokori --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_api.py seed-nokori --apply

正本トークン: .env.jarvis_private の TODOIST_API_TOKEN
設定: config/todoist_projects.yaml
値は標準出力に出さない。
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
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
YAML_PATH = REPO / "config" / "todoist_projects.yaml"
NOKORI_MD = REPO / "docs" / "残り棚_アプリ受け入れ_20260830.md"
COMPLETE_PHRASE = "タスク完了したよ"
DEFAULT_API = "https://api.todoist.com/api/v1"


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
    done_names = set(lane.get("done_sections") or ["完了"])
    sid_to_name = {v: k for k, v in (proj.get("section_ids") or {}).items()}

    filtered: list[dict[str, Any]] = []
    for t in tasks:
        labels = [str(x) for x in (t.get("labels") or [])]
        # work_bundle 同居レーンは lane_label 必須。専用プロジェクトは全件。
        if args.id != "properties" and label and label not in labels:
            pkey = str(lane.get("project_key") or "")
            if pkey == "work_bundle":
                continue
        if hide_done:
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


def cmd_create_task(args: argparse.Namespace) -> int:
    cfg = _load_yaml()
    lane = _lane(cfg, args.lane)
    proj = _project_for_lane(cfg, lane)
    section = args.status or lane.get("initial_section") or "未着手"
    sid = _section_id(proj, section)
    labels = [str(lane.get("lane_label") or args.lane)]
    if args.label:
        labels.extend([x.strip() for x in args.label.split(",") if x.strip()])
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


def cmd_update_status(args: argparse.Namespace) -> int:
    cfg = _load_yaml()
    lane = _lane(cfg, args.lane)
    proj = _project_for_lane(cfg, lane)
    sid = _section_id(proj, args.status)
    _move_to_section(args.task_id, sid, cfg=cfg)
    print(f"moved id={args.task_id} section={args.status}")
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
    # optional: move to 完了 section before close
    if lane:
        proj = _project_for_lane(cfg, lane)
        done = (lane.get("done_sections") or ["完了"])[0]
        try:
            sid = _section_id(proj, done)
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

    u = sub.add_parser("update-status")
    u.add_argument("--task-id", required=True)
    u.add_argument("--lane", required=True)
    u.add_argument("--status", required=True)

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
        "comment": cmd_comment,
        "complete-task": cmd_complete_task,
        "seed-nokori": cmd_seed_nokori,
    }
    return dispatch[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
