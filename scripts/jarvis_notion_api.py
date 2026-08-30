#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Notion REST API（Jarvis 本線）。MCP には頼らない。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_notion_api.py whoami
  ~/selenium_env/venv/bin/python scripts/jarvis_notion_api.py probe
  ~/selenium_env/venv/bin/python scripts/jarvis_notion_api.py search --query 'マイカー通勤'
  ~/selenium_env/venv/bin/python scripts/jarvis_notion_api.py lane --id kazoku
  ~/selenium_env/venv/bin/python scripts/jarvis_notion_api.py update-status --page-id ... --lane kazoku --status 進行中
  ~/selenium_env/venv/bin/python scripts/jarvis_notion_api.py create-task --lane kazoku --title '例'
  ~/selenium_env/venv/bin/python scripts/jarvis_notion_api.py archive-page --page-id ...
  # 家族コーチ（別WS／別 Integration のとき）
  ~/selenium_env/venv/bin/python scripts/jarvis_notion_api.py --token-env NOTION_FAMILY_API_TOKEN whoami
  ~/selenium_env/venv/bin/python scripts/jarvis_notion_api.py --token-env NOTION_FAMILY_API_TOKEN get-page
  ~/selenium_env/venv/bin/python scripts/jarvis_notion_api.py --token-env NOTION_FAMILY_API_TOKEN family-probe

正本トークン: .env.jarvis_private の NOTION_API_TOKEN（既定）
家族コーチ用: NOTION_FAMILY_API_TOKEN（--token-env で指定）
値は標準出力に出さない。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
YAML_PATH = REPO / "config" / "notion_task_dbs.yaml"
FAMILY_YAML_PATH = REPO / "config" / "notion_family_coaching.yaml"
NOTION_VERSION = "2022-06-28"
API = "https://api.notion.com/v1"

# main() が --token-env で上書き
_TOKEN_ENV = "NOTION_API_TOKEN"


def _token() -> str:
    env_key = (_TOKEN_ENV or "NOTION_API_TOKEN").strip() or "NOTION_API_TOKEN"
    tok = (os.environ.get(env_key) or "").strip()
    if not tok and env_key == "NOTION_API_TOKEN":
        tok = (os.environ.get("NOTION_TOKEN") or "").strip()
    if not tok:
        print(f"ERROR: {env_key} 未設定（.env.jarvis_private）", file=sys.stderr)
        sys.exit(2)
    return tok


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_token()}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _normalize_page_id(raw: str) -> str:
    page_id = (raw or "").replace("-", "").strip()
    if len(page_id) == 32:
        return (
            f"{page_id[:8]}-{page_id[8:12]}-{page_id[12:16]}-"
            f"{page_id[16:20]}-{page_id[20:]}"
        )
    return (raw or "").strip()


def _load_family_cfg() -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ImportError:
        print("ERROR: PyYAML が必要です", file=sys.stderr)
        sys.exit(2)
    if not FAMILY_YAML_PATH.is_file():
        return {}
    data = yaml.safe_load(FAMILY_YAML_PATH.read_text(encoding="utf-8")) or {}
    return dict(data)


def _req(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{API}{path}",
        data=data,
        headers=_headers(),
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", "replace")[:400]
        print(f"ERROR: HTTP {e.code} {path}: {err}", file=sys.stderr)
        sys.exit(1)


def _load_lanes() -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ImportError:
        print("ERROR: PyYAML が必要です", file=sys.stderr)
        sys.exit(2)
    data = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8")) or {}
    return dict(data.get("lanes") or {})


def _title_from_props(props: dict[str, Any], title_prop: str | None = None) -> str:
    if title_prop and title_prop in props:
        block = props[title_prop]
        return "".join(t.get("plain_text") or "" for t in (block.get("title") or [])).strip()
    for block in props.values():
        if block.get("type") == "title":
            return "".join(t.get("plain_text") or "" for t in (block.get("title") or [])).strip()
    return "(無題)"


def _status_from_props(props: dict[str, Any], status_prop: str | None = None) -> str:
    keys = [status_prop] if status_prop else []
    keys.extend(k for k in props if k not in keys)
    for key in keys:
        block = props.get(key) or {}
        if block.get("type") == "status":
            return ((block.get("status") or {}).get("name") or "").strip()
        if block.get("type") == "select" and key in ("ステータス", status_prop):
            return ((block.get("select") or {}).get("name") or "").strip()
    return ""


def cmd_whoami(_: argparse.Namespace) -> int:
    data = _req("GET", "/users/me")
    bot = data.get("bot") or {}
    print(
        json.dumps(
            {
                "ok": True,
                "type": data.get("type"),
                "bot_name": data.get("name") or "",
                "workspace": bot.get("workspace_name") or "",
            },
            ensure_ascii=False,
        )
    )
    return 0


def cmd_probe(_: argparse.Namespace) -> int:
    who = _req("GET", "/users/me")
    bot = who.get("bot") or {}
    lanes = _load_lanes()
    rows = []
    for lane_id, cfg in lanes.items():
        db_id = cfg.get("database_id")
        try:
            db = _req("GET", f"/databases/{db_id}")
            title = "".join(t.get("plain_text") or "" for t in (db.get("title") or []))
            rows.append({"lane": lane_id, "ok": True, "title": title})
        except SystemExit:
            rows.append({"lane": lane_id, "ok": False, "title": ""})
    print(
        json.dumps(
            {
                "ok": all(r["ok"] for r in rows),
                "bot_name": who.get("name") or "",
                "workspace": bot.get("workspace_name") or "",
                "lanes": rows,
            },
            ensure_ascii=False,
        )
    )
    return 0 if all(r["ok"] for r in rows) else 1


def cmd_search(args: argparse.Namespace) -> int:
    payload: dict[str, Any] = {
        "query": args.query,
        "page_size": min(max(args.limit, 1), 20),
        "filter": {"value": "page", "property": "object"},
    }
    data = _req("POST", "/search", payload)
    items = []
    for r in data.get("results") or []:
        props = r.get("properties") or {}
        items.append(
            {
                "id": r.get("id"),
                "url": r.get("url"),
                "title": _title_from_props(props),
                "status": _status_from_props(props),
            }
        )
    print(json.dumps({"ok": True, "count": len(items), "items": items}, ensure_ascii=False))
    return 0


def cmd_lane(args: argparse.Namespace) -> int:
    lanes = _load_lanes()
    cfg = lanes.get(args.id)
    if not cfg:
        print(f"ERROR: 未知の lane: {args.id}（{', '.join(lanes)}）", file=sys.stderr)
        return 2
    data = _req(
        "POST",
        f"/databases/{cfg['database_id']}/query",
        {"page_size": min(max(args.limit, 1), 50)},
    )
    items = []
    for r in data.get("results") or []:
        props = r.get("properties") or {}
        items.append(
            {
                "id": r.get("id"),
                "url": r.get("url"),
                "title": _title_from_props(props, cfg.get("title_prop")),
                "status": _status_from_props(props, cfg.get("status_prop")),
            }
        )
    print(
        json.dumps(
            {
                "ok": True,
                "lane": args.id,
                "title": cfg.get("title"),
                "board_url": cfg.get("board_url"),
                "count": len(items),
                "items": items,
            },
            ensure_ascii=False,
        )
    )
    return 0


def cmd_update_status(args: argparse.Namespace) -> int:
    lanes = _load_lanes()
    cfg = lanes.get(args.lane)
    if not cfg:
        print(f"ERROR: 未知の lane: {args.lane}", file=sys.stderr)
        return 2
    allowed = list(cfg.get("open_statuses") or []) + list(cfg.get("done_statuses") or [])
    if args.status not in allowed:
        print(f"ERROR: 未対応ステータス: {args.status}（{allowed}）", file=sys.stderr)
        return 2
    page_id = _normalize_page_id(args.page_id)
    _req(
        "PATCH",
        f"/pages/{page_id}",
        {"properties": {cfg["status_prop"]: {"status": {"name": args.status}}}},
    )
    print(json.dumps({"ok": True, "page_id": page_id, "status": args.status}, ensure_ascii=False))
    return 0


def cmd_create_task(args: argparse.Namespace) -> int:
    lanes = _load_lanes()
    cfg = lanes.get(args.lane)
    if not cfg:
        print(f"ERROR: 未知の lane: {args.lane}", file=sys.stderr)
        return 2
    title = (args.title or "").strip()
    if not title:
        print("ERROR: --title が空です", file=sys.stderr)
        return 2
    title_prop = cfg.get("title_prop") or "名前"
    status_prop = cfg.get("status_prop") or "ステータス"
    initial = (args.status or "").strip() or (cfg.get("initial_status") or "未着手")
    props: dict[str, Any] = {
        title_prop: {"title": [{"text": {"content": title[:2000]}}]},
        status_prop: {"status": {"name": initial}},
    }
    due_prop = cfg.get("due_prop")
    due = (args.due or "").strip()
    if due_prop and due:
        props[due_prop] = {"date": {"start": due}}
    body: dict[str, Any] = {
        "parent": {"database_id": cfg["database_id"]},
        "properties": props,
    }
    note = (args.note or "").strip()
    if note:
        body["children"] = [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": note[:1900]}}]
                },
            }
        ]
    page = _req("POST", "/pages", body)
    print(
        json.dumps(
            {
                "ok": True,
                "lane": args.lane,
                "page_id": page.get("id"),
                "url": page.get("url"),
                "title": title,
                "status": initial,
            },
            ensure_ascii=False,
        )
    )
    return 0


def cmd_archive_page(args: argparse.Namespace) -> int:
    page_id = _normalize_page_id(args.page_id)
    if not page_id:
        print("ERROR: --page-id が必要", file=sys.stderr)
        return 2
    page = _req("PATCH", f"/pages/{page_id}", {"archived": True})
    print(
        json.dumps(
            {"ok": True, "page_id": page_id, "archived": True, "url": page.get("url")},
            ensure_ascii=False,
        )
    )
    return 0


def cmd_get_page(args: argparse.Namespace) -> int:
    family = _load_family_cfg()
    page_id = _normalize_page_id(
        args.page_id
        or os.environ.get("NOTION_FAMILY_COACHING_PAGE_ID")
        or (family.get("root_page_id") or "")
    )
    if not page_id:
        print(
            "ERROR: --page-id / NOTION_FAMILY_COACHING_PAGE_ID / "
            "config/notion_family_coaching.yaml root_page_id が必要",
            file=sys.stderr,
        )
        return 2
    page = _req("GET", f"/pages/{page_id}")
    props = page.get("properties") or {}
    title = _title_from_props(props)
    if not title and isinstance(page.get("properties"), dict):
        title = "(無題)"
    # タイトルが properties に無いページ型もある
    if title in ("", "(無題)"):
        # 一部は title が無い → children 先頭で補完はしない（軽量）
        pass
    children = _req("GET", f"/blocks/{page_id}/children?page_size={min(max(args.limit, 1), 50)}")
    child_rows = []
    for b in children.get("results") or []:
        btype = b.get("type") or ""
        summary = ""
        block = b.get(btype) or {}
        if btype == "child_page":
            summary = (block.get("title") or "").strip()
        elif btype == "child_database":
            summary = (block.get("title") or "").strip()
        elif btype in ("paragraph", "heading_1", "heading_2", "heading_3", "bulleted_list_item", "numbered_list_item"):
            rich = block.get("rich_text") or []
            summary = "".join(t.get("plain_text") or "" for t in rich).strip()[:120]
        elif btype == "meeting_notes":
            summary = "(meeting_notes)"
        child_rows.append(
            {
                "id": b.get("id"),
                "type": btype,
                "summary": summary,
                "has_children": bool(b.get("has_children")),
            }
        )
    print(
        json.dumps(
            {
                "ok": True,
                "page_id": page_id,
                "url": page.get("url"),
                "title": title,
                "archived": bool(page.get("archived")),
                "token_env": _TOKEN_ENV,
                "children_count": len(child_rows),
                "children": child_rows,
            },
            ensure_ascii=False,
        )
    )
    return 0


def cmd_family_probe(_: argparse.Namespace) -> int:
    family = _load_family_cfg()
    page_id = _normalize_page_id(
        os.environ.get("NOTION_FAMILY_COACHING_PAGE_ID") or (family.get("root_page_id") or "")
    )
    who = _req("GET", "/users/me")
    bot = who.get("bot") or {}
    page_ok = False
    page_title = ""
    page_err = ""
    if page_id:
        try:
            page = _req("GET", f"/pages/{page_id}")
            page_ok = True
            page_title = _title_from_props(page.get("properties") or {})
        except SystemExit:
            page_err = "page_fetch_failed"
    else:
        page_err = "no_page_id"
    print(
        json.dumps(
            {
                "ok": page_ok,
                "bot_name": who.get("name") or "",
                "workspace": bot.get("workspace_name") or "",
                "token_env": _TOKEN_ENV,
                "root_page_id": page_id,
                "page_ok": page_ok,
                "page_title": page_title,
                "page_error": page_err,
                "source_kinds": list(family.get("source_kinds") or []),
                "yaml": str(FAMILY_YAML_PATH),
            },
            ensure_ascii=False,
        )
    )
    return 0 if page_ok else 1


def main() -> int:
    global _TOKEN_ENV
    p = argparse.ArgumentParser(description="Notion REST API（Jarvis 本線）")
    p.add_argument(
        "--token-env",
        default="NOTION_API_TOKEN",
        help="Bearer トークンの環境変数名（既定 NOTION_API_TOKEN。家族は NOTION_FAMILY_API_TOKEN）",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("whoami", help="ボット／ワークスペース確認")
    sub.add_parser("probe", help="登録レーンの DB 接続確認")
    sub.add_parser("family-probe", help="家族コーチ root ページ接続確認")

    s = sub.add_parser("search", help="ページ検索")
    s.add_argument("--query", required=True)
    s.add_argument("--limit", type=int, default=10)

    s = sub.add_parser("lane", help="レーン看板の一覧")
    s.add_argument("--id", required=True, help="properties / kodate / kazoku / kamiooya / ai_raimo")
    s.add_argument("--limit", type=int, default=20)

    s = sub.add_parser("update-status", help="ステータス更新")
    s.add_argument("--page-id", required=True)
    s.add_argument("--lane", required=True)
    s.add_argument("--status", required=True)

    s = sub.add_parser("create-task", help="レーン看板にタスク新規")
    s.add_argument("--lane", required=True)
    s.add_argument("--title", required=True)
    s.add_argument("--status", default="", help="省略時は lane の initial_status")
    s.add_argument("--due", default="", help="YYYY-MM-DD（due_prop があるレーンのみ）")
    s.add_argument("--note", default="", help="本文1段落")

    s = sub.add_parser("archive-page", help="ページをアーカイブ（削除に近い整理）")
    s.add_argument("--page-id", required=True)

    s = sub.add_parser("get-page", help="ページメタ＋直下ブロック一覧（家族コーチ棚卸し用）")
    s.add_argument("--page-id", default="", help="省略時は FAMILY page id / yaml")
    s.add_argument("--limit", type=int, default=50)

    args = p.parse_args()
    _TOKEN_ENV = (args.token_env or "NOTION_API_TOKEN").strip() or "NOTION_API_TOKEN"
    if args.cmd == "whoami":
        return cmd_whoami(args)
    if args.cmd == "probe":
        return cmd_probe(args)
    if args.cmd == "search":
        return cmd_search(args)
    if args.cmd == "lane":
        return cmd_lane(args)
    if args.cmd == "update-status":
        return cmd_update_status(args)
    if args.cmd == "create-task":
        return cmd_create_task(args)
    if args.cmd == "archive-page":
        return cmd_archive_page(args)
    if args.cmd == "get-page":
        return cmd_get_page(args)
    if args.cmd == "family-probe":
        return cmd_family_probe(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
