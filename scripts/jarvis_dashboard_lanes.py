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


def collect(max_per_lane: int | None = None) -> dict[str, Any]:
    """Collect candidate cards from sources.

    max_per_lane:
      None → YAML lane.max_auto_cards（未設定時 0＝自動カードなし）
      0 → ソースからの自動カードを作らない（digest 専用運用）
      N → レーンあたり最大 N 件
    """
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
        if max_per_lane is None:
            lim = int(
                lane.get(
                    "max_auto_cards",
                    reg.get("default_max_auto_cards", 0),
                )
            )
        else:
            lim = int(max_per_lane)
        if lim <= 0:
            continue
        lane_cards: list[dict[str, Any]] = []
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
                lane_cards.append(
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
        cards.extend(lane_cards[-lim:])
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


def _lane_ctx(reg: dict[str, Any]) -> dict[str, str]:
    return {
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


def gather_lane_blocks(
    lane: dict[str, Any], ctx: dict[str, str], *, take_cap: int = 40
) -> list[dict[str, str]]:
    """処置要約用にソース抜粋を集める。"""
    blocks: list[dict[str, str]] = []
    for src in lane.get("sources") or []:
        path = expand(str(src.get("path") or ""), ctx)
        take = int(src.get("take") or 8)
        kind = src.get("kind") or "yoritoori"
        tag = src.get("tag") or ""
        if kind == "checklist":
            raw = [x for x in parse_checklist(path) if x.get("status_hint") != "done"][
                :take
            ]
        elif kind == "journal_recent":
            raw = parse_journal_dir(path, take)
        else:
            raw = parse_headings(path, take)
        for it in raw:
            title = it["title"]
            if tag:
                title = f"[{tag}] {title}"
            blocks.append(
                {
                    "title": title[:160],
                    "summary": (it.get("summary") or "")[:400],
                    "source_path": str(path),
                    "kind": kind,
                }
            )
            if len(blocks) >= take_cap:
                return blocks
    return blocks


def _parse_gemini_json(text: str) -> Any | None:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}|\[[\s\S]*\]", t)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None


def gemini_action_items(
    lane_title: str,
    blocks: list[dict[str, str]],
    *,
    api_key: str,
    max_n: int,
) -> list[dict[str, Any]] | None:
    if not blocks or not api_key or max_n <= 0:
        return None
    models = [
        (os.environ.get("GEMINI_MODEL") or "").strip(),
        "gemini-flash-latest",
        "gemini-flash-lite-latest",
    ]
    models = [m for i, m in enumerate(models) if m and m not in models[:i]]
    prompt = f"""あなたは不動産大家の秘書 Jarvis です。レーン「{lane_title}」の出典抜粋から、
いま処置（返信・手配・確認・登録）が必要そうな項目だけを抽出してください。
単なる情報共有・完了済み・雑談は除外。

入力JSON（抜粋）:
{json.dumps(blocks[:36], ensure_ascii=False)}

次の JSON のみ（Markdown不可）:
{{
  "items": [
    {{
      "title": "短い処置タイトル（40字以内）",
      "summary": "何をすべきか1〜3文",
      "suggested_due": "YYYY-MM-DD または null",
      "source_excerpt": "根拠となる短い引用",
      "source_title": "入力の title に近いもの"
    }}
  ]
}}

ルール:
- items は最大 {max_n} 件
- 処置が無ければ items は空配列
- suggested_due が不明なら null
"""
    import urllib.error
    import urllib.request

    for model in models:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={api_key}"
        )
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.25, "maxOutputTokens": 2048},
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            print(f"# action_summary gemini {model}: {e}", file=sys.stderr)
            continue
        cands = data.get("candidates") or []
        if not cands:
            continue
        parts = (((cands[0] or {}).get("content") or {}).get("parts")) or []
        text = "\n".join(
            p.get("text", "") for p in parts if isinstance(p, dict) and p.get("text")
        ).strip()
        obj = _parse_gemini_json(text)
        if not isinstance(obj, dict):
            continue
        out: list[dict[str, Any]] = []
        for it in obj.get("items") or []:
            if not isinstance(it, dict):
                continue
            title = str(it.get("title") or "").strip()
            if not title:
                continue
            due = it.get("suggested_due")
            due_s = None
            if isinstance(due, str) and re.match(r"^\d{4}-\d{2}-\d{2}", due.strip()):
                due_s = due.strip()[:10]
            out.append(
                {
                    "title": title[:160],
                    "summary": str(it.get("summary") or "")[:800],
                    "suggested_due": due_s,
                    "source_excerpt": str(it.get("source_excerpt") or "")[:400],
                    "source_title": str(it.get("source_title") or "")[:160],
                }
            )
            if len(out) >= max_n:
                break
        return out
    return None


def fallback_action_items(
    blocks: list[dict[str, str]], max_n: int
) -> list[dict[str, Any]]:
    """Gemini 失敗時: 直近スニペットを処置候補として載せる。"""
    out: list[dict[str, Any]] = []
    for b in blocks[-max_n:]:
        title = (b.get("title") or "").strip()
        if not title:
            continue
        out.append(
            {
                "title": title[:160],
                "summary": (b.get("summary") or "")[:800] or "（出典スニペット）",
                "suggested_due": None,
                "source_excerpt": (b.get("summary") or "")[:400],
                "source_title": title[:160],
                "source_path": b.get("source_path"),
            }
        )
    return out


def collect_action_summaries(
    *,
    only_lane: str | None = None,
    force_max: int | None = None,
) -> dict[str, Any]:
    """Gemini（失敗時はスニペット）で kind=action_summary カードを生成。"""
    reg = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8")) or {}
    ctx = _lane_ctx(reg)
    api_key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    default_max = int(reg.get("default_action_summary_max", 5))
    cards: list[dict[str, Any]] = []
    meta: dict[str, Any] = {}

    for lane in reg.get("lanes") or []:
        lane_id = str(lane.get("id") or "misc")
        if only_lane and lane_id != only_lane:
            continue
        max_n = (
            force_max
            if force_max is not None
            else int(lane.get("action_summary_max", default_max))
        )
        if max_n <= 0:
            continue
        blocks = gather_lane_blocks(lane, ctx)
        via = "none"
        items: list[dict[str, Any]] = []
        if not blocks:
            meta[lane_id] = {"blocks": 0, "items": 0, "via": via}
            continue
        gem = gemini_action_items(
            str(lane.get("title") or lane_id),
            blocks,
            api_key=api_key,
            max_n=max_n,
        )
        if gem is not None:
            items = gem
            via = "gemini"
        else:
            items = fallback_action_items(blocks, max_n)
            via = "fallback_snippet"
        meta[lane_id] = {"blocks": len(blocks), "items": len(items), "via": via}

        for it in items:
            title = f"[処置] {it['title']}"
            src_path = it.get("source_path") or (
                blocks[0].get("source_path") if blocks else None
            )
            prompt = (
                f"ダッシュボード「{lane.get('title')}」の処置候補:\n"
                f"- {it['title']}\n"
                f"- 要約: {it.get('summary') or ''}\n"
                f"- 出典抜粋: {it.get('source_excerpt') or ''}\n"
                "Notion タスク化の可否と次の一手を提案して。"
            )
            cards.append(
                {
                    "id": card_id(lane_id, f"action_summary|{it.get('source_title') or ''}", it["title"]),
                    "lane": lane_id,
                    "kind": "action_summary",
                    "title": title[:200],
                    "summary": it.get("summary") or "",
                    "status": "active",
                    "source_path": src_path,
                    "cursor_prompt": prompt,
                    "sort_key": it["title"][:40],
                    "payload": {
                        "action_summary": True,
                        "suggested_due": it.get("suggested_due"),
                        "source_excerpt": it.get("source_excerpt"),
                        "source_title": it.get("source_title"),
                        "via": via,
                    },
                    "updated_at": now_iso(),
                }
            )

    dedup: dict[str, dict[str, Any]] = {}
    for c in cards:
        dedup[c["id"]] = c
    cards = list(dedup.values())
    return {
        "updated_at": now_iso(),
        "meta": meta,
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
    # Web で archived / promoted 済みの id は active に戻さない
    remote_locked: dict[str, Any] = {}
    try:
        r = (
            sb.table("cards")
            .select("id,status,archived_at,payload")
            .in_("status", ["archived", "promoted"])
            .execute()
        )
        remote_locked = {x["id"]: x for x in (r.data or [])}
    except Exception as e:
        print(f"# cards status merge skipped: {e}", file=sys.stderr)

    rows = []
    for c in result.get("cards") or []:
        st = c.get("status") or "active"
        arch_at = c.get("archived_at")
        payload = c.get("payload") or {}
        if c["id"] in remote_locked:
            locked = remote_locked[c["id"]]
            st = locked.get("status") or st
            arch_at = locked.get("archived_at") or arch_at
            # Notion URL 等を落とさない
            if isinstance(locked.get("payload"), dict):
                payload = {**payload, **locked["payload"]}
        row = {
            "id": c["id"],
            "lane": c["lane"],
            "kind": c.get("kind") or "note",
            "title": c["title"],
            "summary": c.get("summary"),
            "status": st,
            "source_path": c.get("source_path"),
            "cursor_prompt": c.get("cursor_prompt"),
            "payload": payload,
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
    if any((c.get("kind") == "action_summary") for c in result.get("cards") or []):
        sb.table("sync_meta").upsert(
            {
                "key": "action_summary_pushed_at",
                "value": now_iso(),
                "updated_at": now_iso(),
            },
            on_conflict="key",
        ).execute()
    return n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--push", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument(
        "--max-per-lane",
        type=int,
        default=None,
        help="レーンあたり自動カード上限（省略時は YAML max_auto_cards、既定0）",
    )
    ap.add_argument(
        "--action-summary",
        action="store_true",
        help="Gemini 処置要約（kind=action_summary）を生成。max_auto_cards とは独立",
    )
    ap.add_argument("--lane", default="", help="--action-summary 時のレーン絞り込み")
    ap.add_argument(
        "--action-summary-max",
        type=int,
        default=None,
        help="処置要約のレーンあたり上限（省略時は YAML）",
    )
    args = ap.parse_args(argv)

    if args.action_summary:
        result = collect_action_summaries(
            only_lane=args.lane.strip() or None,
            force_max=args.action_summary_max,
        )
        out_path = REPO / ".jarvis_state" / "dashboard_action_summary.json"
    else:
        result = collect(max_per_lane=args.max_per_lane)
        out_path = OUT_PATH

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"# wrote {out_path} total={result['counts']['total']}", file=sys.stderr)
    if args.action_summary:
        for lid, m in (result.get("meta") or {}).items():
            print(
                f"  {lid}: blocks={m.get('blocks')} items={m.get('items')} via={m.get('via')}"
            )
    else:
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
