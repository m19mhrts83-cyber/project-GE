#!/usr/bin/env python3
"""レーン要約 digest → 処置ログ追記 ＋ 少数カード（kind=digest）生成。

  python scripts/jarvis_lane_digest.py
  python scripts/jarvis_lane_digest.py --push
  python scripts/jarvis_lane_digest.py --lane kazoku --push
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from jarvis_dashboard_lanes import (  # noqa: E402
    expand,
    parse_checklist,
    parse_headings,
    parse_journal_dir,
)
from jarvis_lane_log import LANE_META, append_lane_log, ensure_lane_log_tree  # noqa: E402

YAML_PATH = REPO / "config" / "dashboard_lanes.yaml"
DIGEST_OUT = REPO / ".jarvis_state" / "lane_digest.json"
DEFAULT_THEMES = 5


def now_iso() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S%z")


def load_env() -> None:
    env_path = REPO / ".env.jarvis_private"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip("\"'")
        if k and k not in os.environ:
            os.environ[k] = v


def theme_id(lane: str, title: str) -> str:
    h = hashlib.sha1(f"digest|{lane}|{title}".encode()).hexdigest()[:16]
    return f"{lane}_d_{h}"


def cluster_items(items: list[dict[str, str]], max_themes: int) -> list[dict[str, Any]]:
    """Group raw items into a few themes for confirmation."""
    if not items:
        return []
    buckets: dict[str, list[dict[str, str]]] = defaultdict(list)
    for it in items:
        title = it.get("title") or ""
        m = re.match(r"^\[([^\]]+)\]\s*(.*)$", title)
        if m:
            key = m.group(1).strip()
            rest = m.group(2).strip() or title
        elif re.search(r"\d{4}/\d{2}/\d{2}", title):
            key = "直近やり取り"
            rest = title
        elif it.get("status_hint") == "open":
            key = "未着手チェック"
            rest = title
        else:
            key = "その他メモ"
            rest = title
        buckets[key].append({**it, "title": rest})

    ordered = sorted(buckets.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:max_themes]
    themes: list[dict[str, Any]] = []
    for key, group in ordered:
        samples = group[-4:]
        bullets: list[str] = []
        bullet_objs: list[dict[str, str | None]] = []
        for g in samples:
            s = (g.get("summary") or "").strip()
            title = g["title"][:80]
            line = f"- {title}"
            if s:
                line += f"（{s[:160]}）"
            bullets.append(line)
            bullet_objs.append(
                {
                    "title": title,
                    "detail": (s[:400] if s else None),
                }
            )
        question = f"「{key}」まわりで、いまタスク化すべきことはありますか？"
        themes.append(
            {
                "theme": key,
                "count": len(group),
                "question": question,
                "bullets": bullets,
                "bullet_objs": bullet_objs,
                "summary": "\n".join([question, *bullets])[:1800],
            }
        )
    return themes


def collect_lane_raw(lane: dict[str, Any], ctx: dict[str, str]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for src in lane.get("sources") or []:
        path = expand(str(src.get("path") or ""), ctx)
        take = int(src.get("take") or 8)
        kind = src.get("kind") or "yoritoori"
        tag = src.get("tag") or ""
        if kind == "checklist":
            raw = parse_checklist(path)
            # open items only for digest
            raw = [x for x in raw if x.get("status_hint") != "done"][:take]
        elif kind == "journal_recent":
            raw = parse_journal_dir(path, take)
        else:
            raw = parse_headings(path, take)
        for it in raw:
            title = it["title"]
            if tag:
                title = f"[{tag}] {title}"
            items.append({**it, "title": title, "source_path": str(path), "kind": kind})
    return items


def build_digest(max_themes: int, only_lane: str | None) -> dict[str, Any]:
    reg = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8")) or {}
    ctx = {
        "partner_base": str(
            Path(
                os.environ.get("JARVIS_LANES_PARTNER_BASE")
                or reg.get("partner_base", "")
            ).expanduser()
        ),
        "obsidian_journal": str(
            Path(
                os.environ.get("JARVIS_LANES_OBSIDIAN_JOURNAL")
                or reg.get("obsidian_journal", "")
            ).expanduser()
        ),
        "kodate_actions": str(
            Path(
                os.environ.get("JARVIS_LANES_KODATE_ACTIONS")
                or reg.get("kodate_actions", "")
            ).expanduser()
        ),
    }
    lanes_out: dict[str, Any] = {}
    cards: list[dict[str, Any]] = []
    for lane in reg.get("lanes") or []:
        lane_id = str(lane.get("id") or "misc")
        if only_lane and lane_id != only_lane:
            continue
        max_t = int(lane.get("digest_themes") or max_themes)
        raw = collect_lane_raw(lane, ctx)
        themes = cluster_items(raw, max_t)
        lanes_out[lane_id] = {
            "title": lane.get("title") or LANE_META.get(lane_id, lane_id),
            "raw_count": len(raw),
            "themes": themes,
        }
        for th in themes:
            title = f"[確認] {th['theme']}（{th['count']}件分）"
            cards.append(
                {
                    "id": theme_id(lane_id, th["theme"]),
                    "lane": lane_id,
                    "kind": "digest",
                    "title": title[:200],
                    "summary": th["summary"],
                    "status": "active",
                    "source_path": None,
                    "cursor_prompt": (
                        f"レーン「{lane.get('title')}」の要約テーマ:\n"
                        f"{th['theme']}\n{th['summary']}\n"
                        "タスク化すべき点があれば提案して。"
                    ),
                    "sort_key": th["theme"][:40],
                    "payload": {
                        "digest": True,
                        "theme": th["theme"],
                        "question": th["question"],
                        "bullets": th.get("bullet_objs") or [],
                    },
                    "updated_at": now_iso(),
                }
            )
    return {
        "updated_at": now_iso(),
        "lanes": lanes_out,
        "cards": cards,
    }


def write_lane_logs(result: dict[str, Any]) -> None:
    ensure_lane_log_tree(list(result.get("lanes") or {}))
    for lid, data in (result.get("lanes") or {}).items():
        themes = data.get("themes") or []
        if not themes:
            append_lane_log(
                lid,
                "要約確認",
                f"- ソース件数: {data.get('raw_count', 0)}\n"
                "- テーマなし（ソース空 or 対象外）",
            )
            continue
        lines = [
            f"- ソース件数: {data.get('raw_count', 0)} → テーマ {len(themes)} 件",
            "- 各テーマについて「タスク化する？」をダッシュボードで確認してください。",
            "",
        ]
        for th in themes:
            lines.append(f"#### {th['theme']}（元 {th['count']} 件）")
            lines.append(f"- 問い: {th['question']}")
            lines.extend(th.get("bullets") or [])
            lines.append("")
        append_lane_log(lid, "要約確認", "\n".join(lines).rstrip())


def push_cards(cards: list[dict[str, Any]]) -> int:
    from supabase import create_client

    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_* 未設定")
    sb = create_client(url, key)

    # Don't revive archived digest ids
    remote_arch: set[str] = set()
    try:
        r = (
            sb.table("cards")
            .select("id")
            .eq("status", "archived")
            .execute()
        )
        remote_arch = {x["id"] for x in (r.data or [])}
    except Exception as e:
        print(f"# archive merge skipped: {e}", file=sys.stderr)

    rows = []
    for c in cards:
        if c["id"] in remote_arch:
            continue
        rows.append(
            {
                "id": c["id"],
                "lane": c["lane"],
                "kind": c.get("kind") or "digest",
                "title": c["title"],
                "summary": c.get("summary"),
                "status": "active",
                "source_path": c.get("source_path"),
                "cursor_prompt": c.get("cursor_prompt"),
                "payload": c.get("payload") or {},
                "sort_key": c.get("sort_key"),
                "updated_at": c.get("updated_at") or now_iso(),
            }
        )
    n = 0
    for i in range(0, len(rows), 40):
        chunk = rows[i : i + 40]
        sb.table("cards").upsert(chunk, on_conflict="id").execute()
        n += len(chunk)
    sb.table("sync_meta").upsert(
        {
            "key": "lane_digest",
            "value": json.dumps(
                {"updated_at": now_iso(), "card_ids": [c["id"] for c in rows]},
                ensure_ascii=False,
            ),
            "updated_at": now_iso(),
        },
        on_conflict="key",
    ).execute()
    return n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--push", action="store_true")
    ap.add_argument("--lane", default="")
    ap.add_argument("--themes", type=int, default=DEFAULT_THEMES)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-log", action="store_true", help="処置ログへ書かない")
    args = ap.parse_args(argv)

    load_env()
    result = build_digest(args.themes, args.lane.strip() or None)
    DIGEST_OUT.parent.mkdir(parents=True, exist_ok=True)
    DIGEST_OUT.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"# wrote {DIGEST_OUT} themes_cards={len(result.get('cards') or [])}",
        file=sys.stderr,
    )
    for lid, data in (result.get("lanes") or {}).items():
        print(
            f"  {lid}: raw={data.get('raw_count')} themes={len(data.get('themes') or [])}"
        )

    if not args.no_log:
        write_lane_logs(result)

    if args.push:
        n = push_cards(result.get("cards") or [])
        print(f"# pushed {n}", file=sys.stderr)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
