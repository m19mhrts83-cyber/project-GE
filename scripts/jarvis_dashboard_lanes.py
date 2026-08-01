#!/usr/bin/env python3
"""
Jarvis: コンテンツレーン要約 → cards JSON（＋任意 Supabase upsert）

  python scripts/jarvis_dashboard_lanes.py
  python scripts/jarvis_dashboard_lanes.py --push
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
YAML_PATH = REPO / "config" / "dashboard_lanes.yaml"
OUT_PATH = REPO / ".jarvis_state" / "dashboard_cards.json"

HEADING_RE = re.compile(r"^###\s+(.+)$")
CHECK_RE = re.compile(r"^- \[( |x|X)\]\s+(.+)$")


def now_iso() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S%z")


def expand(p: str, ctx: dict[str, str]) -> Path:
    s = p
    for k, v in ctx.items():
        s = s.replace("{" + k + "}", v)
    return Path(s).expanduser()


def card_id(lane: str, source: str, title: str) -> str:
    h = hashlib.sha1(f"{lane}|{source}|{title}".encode()).hexdigest()[:16]
    return f"{lane}_{h}"


def parse_headings(path: Path, take: int) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()
    items: list[dict[str, str]] = []
    i = 0
    while i < len(lines):
        m = HEADING_RE.match(lines[i].strip())
        if not m:
            i += 1
            continue
        title = m.group(1).strip()
        body_lines: list[str] = []
        i += 1
        while i < len(lines) and not HEADING_RE.match(lines[i].strip()):
            if lines[i].strip():
                body_lines.append(lines[i].strip())
            i += 1
            if len(body_lines) >= 4:
                # skip rest until next heading
                while i < len(lines) and not HEADING_RE.match(lines[i].strip()):
                    i += 1
                break
        summary = " ".join(body_lines)[:280]
        items.append({"title": title[:160], "summary": summary})
    return items[-take:] if take > 0 else items


def parse_checklist(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        m = CHECK_RE.match(line.strip())
        if not m:
            continue
        done = m.group(1).lower() == "x"
        title = m.group(2).strip()
        out.append(
            {
                "title": title[:160],
                "summary": "完了" if done else "未着手",
                "status_hint": "done" if done else "open",
            }
        )
    return out


def parse_journal_dir(path: Path, take: int) -> list[dict[str, str]]:
    if not path.is_dir():
        return []
    files = sorted(path.glob("2026-*.md"), reverse=True)[:take]
    out = []
    for f in files:
        text = f.read_text(encoding="utf-8", errors="ignore")
        # first non-empty non-heading lines
        body = []
        for line in text.splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            body.append(s)
            if len(body) >= 3:
                break
        out.append(
            {
                "title": f"Journal {f.stem}",
                "summary": " ".join(body)[:280] or "(本文なし)",
            }
        )
    return out


def collect() -> dict[str, Any]:
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
    cards: list[dict[str, Any]] = []
    for lane in reg.get("lanes") or []:
        lane_id = lane.get("id") or "misc"
        for src in lane.get("sources") or []:
            path = expand(str(src.get("path") or ""), ctx)
            take = int(src.get("take") or 8)
            kind = src.get("kind") or "yoritoori"
            tag = src.get("tag") or ""
            if kind == "checklist":
                raw = parse_checklist(path)
            elif kind == "journal_recent":
                raw = parse_journal_dir(path, take)
            else:
                raw = parse_headings(path, take)
            for it in raw:
                title = it["title"]
                if tag:
                    title = f"[{tag}] {title}"
                prompt = (
                    f"ダッシュボード「{lane.get('title')}」の次を調べて:\n"
                    f"- {title}\n- 出典: {path}\n"
                    f"要約: {it.get('summary') or ''}"
                )
                cards.append(
                    {
                        "id": card_id(lane_id, str(path), title),
                        "lane": lane_id,
                        "kind": kind,
                        "title": title[:200],
                        "summary": it.get("summary") or "",
                        "status": "active",
                        "source_path": str(path),
                        "cursor_prompt": prompt,
                        "sort_key": title[:40],
                        "payload": {"status_hint": it.get("status_hint")},
                        "updated_at": now_iso(),
                    }
                )
    # upsert 同一バッチ内の id 重複を除去（後勝ち）
    dedup: dict[str, dict[str, Any]] = {}
    for c in cards:
        dedup[c["id"]] = c
    cards = list(dedup.values())
    return {
        "updated_at": now_iso(),
        "counts": {
            "total": len(cards),
            **{
                lid: sum(1 for c in cards if c["lane"] == lid)
                for lid in {c["lane"] for c in cards}
            },
        },
        "cards": cards,
    }


def push_supabase(result: dict[str, Any]) -> int:
    from supabase import create_client

    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_* 未設定")
    sb = create_client(url, key)
    # Web でアーカイブ済みの id は上書きで active に戻さない
    remote_arch: dict[str, Any] = {}
    try:
        r = (
            sb.table("cards")
            .select("id,status,archived_at")
            .eq("status", "archived")
            .execute()
        )
        remote_arch = {x["id"]: x for x in (r.data or [])}
    except Exception as e:
        print(f"# cards archive merge skipped: {e}", file=sys.stderr)

    rows = []
    for c in result.get("cards") or []:
        st = c.get("status") or "active"
        arch_at = c.get("archived_at")
        if st != "archived" and c["id"] in remote_arch:
            st = "archived"
            arch_at = remote_arch[c["id"]].get("archived_at")
        row = {
            "id": c["id"],
            "lane": c["lane"],
            "kind": c.get("kind") or "note",
            "title": c["title"],
            "summary": c.get("summary"),
            "status": st,
            "source_path": c.get("source_path"),
            "cursor_prompt": c.get("cursor_prompt"),
            "payload": c.get("payload") or {},
            "sort_key": c.get("sort_key"),
            "updated_at": c.get("updated_at") or now_iso(),
        }
        if arch_at:
            row["archived_at"] = arch_at
        rows.append(row)
    n = 0
    for i in range(0, len(rows), 40):
        chunk = rows[i : i + 40]
        sb.table("cards").upsert(chunk, on_conflict="id").execute()
        n += len(chunk)
    sb.table("sync_meta").upsert(
        {"key": "cards_pushed_at", "value": now_iso(), "updated_at": now_iso()},
        on_conflict="key",
    ).execute()
    return n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--push", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    result = collect()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"# wrote {OUT_PATH} total={result['counts']['total']}", file=sys.stderr)
    for k, v in result["counts"].items():
        if k != "total":
            print(f"  {k}: {v}")
    if args.push:
        n = push_supabase(result)
        print(f"# pushed {n}", file=sys.stderr)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
