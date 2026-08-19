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

正本トークン: .env.jarvis_private の NOTION_API_TOKEN
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
NOTION_VERSION = "2022-06-28"
API = "https://api.notion.com/v1"


def _token() -> str:
    tok = (os.environ.get("NOTION_API_TOKEN") or os.environ.get("NOTION_TOKEN") or "").strip()
    if not tok:
        print("ERROR: NOTION_API_TOKEN 未設定（.env.jarvis_private）", file=sys.stderr)
        sys.exit(2)
    return tok


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_token()}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


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
    page_id = args.page_id.replace("-", "")
    if len(page_id) == 32:
        page_id = f"{page_id[:8]}-{page_id[8:12]}-{page_id[12:16]}-{page_id[16:20]}-{page_id[20:]}"
    _req(
        "PATCH",
        f"/pages/{page_id}",
        {"properties": {cfg["status_prop"]: {"status": {"name": args.status}}}},
    )
    print(json.dumps({"ok": True, "page_id": page_id, "status": args.status}, ensure_ascii=False))
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Notion REST API（Jarvis 本線）")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("whoami", help="ボット／ワークスペース確認")
    sub.add_parser("probe", help="登録レーンの DB 接続確認")

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

    args = p.parse_args()
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
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
