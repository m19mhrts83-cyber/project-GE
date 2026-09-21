#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SecondBrain / Genspark → Todoist 候補提案（了承後 create）.

Phase 3b: 無言の自動起票はしない。提案 → 松野了承 → `--apply`。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  export PATH="$HOME/.local/bin:$HOME/.genspark-tool-cli/bin:$PATH"

  # 最新1件を提案
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_sb_propose.py --latest

  # 会議 ID 指定
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_sb_propose.py \\
    --meeting-id 71f8fa17-23fc-41f3-b78f-b3859416b615

  # キーワード検索の先頭ヒット
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_sb_propose.py --keyword LEAF

  # 了承後（番号は提案ブロックの #）
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_sb_propose.py \\
    --apply --select 1
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_sb_propose.py \\
    --apply --select all --mine-only
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
STATE_PATH = REPO / ".jarvis_state" / "todoist_sb_propose.json"
SIGNALS_PATH = REPO / "config" / "todoist_extract_signals.yaml"
PY = Path("/Users/matsunomasaharu2/selenium_env/venv/bin/python")
JST = timezone(timedelta(hours=9))

# 自分の Action Items を優先（Genspark 表記ゆれ）
MINE_NAME_RE = re.compile(r"松野|マサハル|matsuno|masaharu", re.I)

ACTION_SECTION_RE = re.compile(
    r"(?im)^##\s*Action\s*Items?\s*\n(.*?)(?=^##\s|\Z)",
    re.S,
)
BULLET_RE = re.compile(r"(?m)^\s*[-*•]\s+(.+)$")
# **誰**: 内容 — (期限…) [状態]
ASSIGNEE_ITEM_RE = re.compile(
    r"^\*\*(.+?)\*\*\s*[:：]\s*(.+?)(?:\s*[—–-]\s*\([^)]*\))?(?:\s*\[[^\]]*\])?\s*$"
)

LANE_HINTS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"幹事|飲み会|懇親会|新年会|BBQ|遊愛会", re.I), "kanji"),
    (re.compile(r"家族|珠己|円香|千景|家族会議", re.I), "kazoku"),
    (re.compile(r"戸建|土地値|楽待|健美家|物件調査|千三つ", re.I), "kodate"),
    (
        re.compile(
            r"LEAF|ミニテック|ホームプランナー|修繕|退去|原状|空室|管理会社|Grandole|キャラメル",
            re.I,
        ),
        "properties",
    ),
    (re.compile(r"神大家|WeStudy|グルコン|幹事標準|815|オプチャ", re.I), "kamiooya"),
    (
        re.compile(
            r"Todoist|ダッシュボード|KURASHIFT|アプリ|phase\d|FRIDAY|GenCode|Mesh",
            re.I,
        ),
        "apps",
    ),
    (re.compile(r"Raimo|チャプロ|Cursor|Grok|AI|Jarvis|Genspark|SecondBrain", re.I), "ai_raimo"),
]


def _now_iso() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def _load_yaml_signals() -> dict[str, Any]:
    if not SIGNALS_PATH.is_file():
        return {}
    try:
        import yaml  # type: ignore

        return yaml.safe_load(SIGNALS_PATH.read_text(encoding="utf-8")) or {}
    except Exception:
        # 最小パーサ（リストの pattern だけ）
        text = SIGNALS_PATH.read_text(encoding="utf-8")
        out: dict[str, Any] = {"self_signals": [], "partner_signals": [], "weak_keywords": []}
        section = None
        for line in text.splitlines():
            if line.startswith("self_signals:"):
                section = "self_signals"
            elif line.startswith("partner_signals:"):
                section = "partner_signals"
            elif line.startswith("weak_keywords:"):
                section = "weak_keywords"
            elif section in ("self_signals", "partner_signals") and "pattern:" in line:
                m = re.search(r"pattern:\s*(.+)$", line)
                if m:
                    out[section].append({"pattern": m.group(1).strip().strip("\"'")})
            elif section == "weak_keywords" and line.strip().startswith("- "):
                out["weak_keywords"].append(line.strip()[2:].strip())
        return out


def _load_state() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        return {"proposals": [], "last_propose_at": None, "created_ids": []}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"proposals": [], "last_propose_at": None, "created_ids": []}


def _save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _guess_lane(text: str, default: str = "ai_raimo") -> str:
    for pat, lane in LANE_HINTS:
        if pat.search(text):
            return lane
    return default


def _clean_title(raw: str, *, max_len: int = 80) -> str:
    t = re.sub(r"\s+", " ", raw).strip()
    t = re.sub(r"\s*[—–-]\s*\(期限[^)]*\)\s*", "", t)
    t = re.sub(r"\s*\[[^\]]*\]\s*$", "", t)
    if len(t) > max_len:
        t = t[: max_len - 1] + "…"
    return t


def _fetch_meeting_summary(meeting_id: str) -> dict[str, Any]:
    cmd = [
        str(PY),
        str(REPO / "scripts" / "jarvis_genspark_meeting_fetch.py"),
        "get",
        "--task-id",
        meeting_id,
        "--detail-level",
        "summary",
        "--json",
        "--shaped",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO))
    if proc.returncode != 0:
        raise SystemExit(
            f"meeting get 失敗: {(proc.stderr or proc.stdout or '').strip()[:500]}"
        )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise SystemExit(f"meeting JSON 解析失敗: {e}") from e


def _list_or_search(
    *, latest: bool, keyword: str | None, page_size: int = 5
) -> list[dict[str, Any]]:
    script = REPO / "scripts" / "jarvis_genspark_meeting_fetch.py"
    if keyword:
        cmd = [
            str(PY),
            str(script),
            "search",
            "--keyword",
            keyword,
            "--page-size",
            str(page_size),
            "--json",
            "--shaped",
        ]
    else:
        cmd = [
            str(PY),
            str(script),
            "list",
            "--page-size",
            str(page_size),
            "--json",
            "--shaped",
        ]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO))
    if proc.returncode != 0:
        raise SystemExit(
            f"meeting list/search 失敗: {(proc.stderr or proc.stdout or '').strip()[:500]}"
        )
    data = json.loads(proc.stdout)
    notes = data.get("notes") or []
    if latest and notes:
        return [notes[0]]
    return list(notes)


def _extract_action_items(summary: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    m = ACTION_SECTION_RE.search(summary or "")
    if not m:
        return out
    body = m.group(1)
    for bm in BULLET_RE.finditer(body):
        line = bm.group(1).strip()
        am = ASSIGNEE_ITEM_RE.match(line)
        if am:
            assignee, content = am.group(1).strip(), am.group(2).strip()
        else:
            assignee, content = "", line
        mine = bool(MINE_NAME_RE.search(assignee)) if assignee else False
        title = _clean_title(content)
        if not title:
            continue
        out.append(
            {
                "source": "action_item",
                "level": "L2",
                "assignee": assignee,
                "mine": mine,
                "title": title,
                "raw": line,
                "lane": _guess_lane(f"{assignee} {content}"),
            }
        )
    return out


def _summary_without_action_items(summary: str) -> str:
    """Action Items 節は L2 専用。シグナル走査から除外する。"""
    return ACTION_SECTION_RE.sub("\n", summary or "")


def _extract_signal_hits(summary: str, signals: dict[str, Any]) -> list[dict[str, Any]]:
    """本文から self / partner / weak を拾う（Action Items 以外）。"""
    text = _summary_without_action_items(summary)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    hits: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(level: str, pattern: str, line: str, lane: str | None = None) -> None:
        key = _clean_title(line, max_len=100).lower()
        if key in seen or len(key) < 8:
            return
        if ASSIGNEE_ITEM_RE.match(line.lstrip("-*• ").strip()):
            return
        seen.add(key)
        hits.append(
            {
                "source": "signal",
                "level": level,
                "assignee": "",
                "mine": str(level).startswith("L1"),
                "title": _clean_title(line),
                "raw": line,
                "pattern": pattern,
                "lane": lane or _guess_lane(line),
            }
        )

    for line in lines:
        if line.startswith("#") or len(line) > 160:
            continue
        for sig in signals.get("self_signals") or []:
            pat = str(sig.get("pattern") or "")
            if pat and pat in line:
                add(str(sig.get("level") or "L1a"), pat, line)
        for sig in signals.get("partner_signals") or []:
            pat = str(sig.get("pattern") or "")
            if pat and pat in line:
                add(str(sig.get("level") or "L3"), pat, line)
        for wk in signals.get("weak_keywords") or []:
            w = str(wk)
            if not (w and w in line):
                continue
            if len(line) > 100 or "仮決定" in line or "Rationale" in line:
                continue
            if any(x in line for x in ("する", "ください", "お願い", "確認", "対応")):
                add("L4", w, line)

    return hits


def _dedupe_candidates(cands: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for c in cands:
        key = re.sub(r"\s+", "", c.get("title") or "").lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def _build_candidates(
    meeting: dict[str, Any], signals: dict[str, Any], *, mine_first: bool = True
) -> list[dict[str, Any]]:
    summary = meeting.get("summary") or ""
    if not isinstance(summary, str):
        summary = json.dumps(summary, ensure_ascii=False)
    actions = _extract_action_items(summary)
    signals_hits = _extract_signal_hits(summary, signals)
    # Action Items を先に。同趣旨の signal は落とす
    action_titles = {re.sub(r"\s+", "", a["title"]).lower() for a in actions}
    filtered_sig = [
        s
        for s in signals_hits
        if re.sub(r"\s+", "", s["title"]).lower() not in action_titles
    ]
    cands = _dedupe_candidates(actions + filtered_sig)
    if mine_first:
        cands.sort(key=lambda c: (0 if c.get("mine") else 1, c.get("level") or "Z"))
    # meeting meta
    mid = meeting.get("id")
    mtitle = meeting.get("title") or ""
    for i, c in enumerate(cands, 1):
        c["n"] = i
        c["meeting_id"] = mid
        c["meeting_title"] = mtitle
        c["project_url"] = meeting.get("project_url") or ""
    return cands


def _print_propose_block(
    meeting: dict[str, Any], cands: list[dict[str, Any]], *, mine_only_hint: bool
) -> None:
    print("📎 Todoist起票候補（SB/Genspark）")
    print(f"- 会議: {meeting.get('title') or '（無題）'}")
    print(f"- id: {meeting.get('id')}")
    if meeting.get("created_at"):
        print(f"- created_at: {meeting.get('created_at')}")
    if meeting.get("project_url"):
        print(f"- url: {meeting.get('project_url')}")
    if not cands:
        print("- （候補なし — Action Items / シグナルヒットなし）")
        print("了承後の起票は不要です。")
        return
    for c in cands:
        who = f" @{c['assignee']}" if c.get("assignee") else ""
        mine = " ★自分" if c.get("mine") else ""
        print(
            f"- [{c['n']}][{c.get('lane')}][{c.get('level')}]{mine}{who} {c.get('title')}"
        )
    print("了承なら「起票して N」または:")
    print(
        "  …/jarvis_todoist_sb_propose.py --apply --select 1"
        + ("  # 自分分だけなら --mine-only" if mine_only_hint else "")
    )


def cmd_propose(args: argparse.Namespace) -> int:
    signals = _load_yaml_signals()
    meeting_id = (args.meeting_id or "").strip() or None
    if not meeting_id:
        notes = _list_or_search(
            latest=bool(args.latest) or not args.keyword,
            keyword=args.keyword,
            page_size=max(1, int(args.page_size or 5)),
        )
        if not notes:
            raise SystemExit("会議が見つかりません")
        meeting_id = str(notes[0].get("id") or "")
        if not meeting_id:
            raise SystemExit("会議 id が空です")
        if args.keyword and not args.latest and len(notes) > 1:
            print(f"# search hits={len(notes)} → 先頭を使用: {meeting_id}", file=sys.stderr)

    meeting = _fetch_meeting_summary(meeting_id)
    cands = _build_candidates(meeting, signals, mine_first=True)
    if args.mine_only:
        cands = [c for c in cands if c.get("mine")]
        for i, c in enumerate(cands, 1):
            c["n"] = i

    state = _load_state()
    state["proposals"] = cands
    state["meeting"] = {
        "id": meeting.get("id"),
        "title": meeting.get("title"),
        "project_url": meeting.get("project_url"),
        "created_at": meeting.get("created_at"),
    }
    state["last_propose_at"] = _now_iso()
    _save_state(state)

    if args.json:
        print(json.dumps({"meeting": state["meeting"], "candidates": cands}, ensure_ascii=False, indent=2))
    else:
        _print_propose_block(meeting, cands, mine_only_hint=True)
    return 0


def _create_task(cand: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
    lane = str(cand.get("lane") or "ai_raimo")
    title = str(cand.get("title") or "").strip()
    if not title:
        return {"ok": False, "error": "empty title"}
    # タイトル先頭にレーン印（既存規約）
    if not title.startswith("["):
        title = f"[{lane}] {title}"
    meeting_title = cand.get("meeting_title") or ""
    meeting_id = cand.get("meeting_id") or ""
    note_parts = [
        f"出典: SB/Genspark",
        f"会議: {meeting_title}" if meeting_title else "",
        f"meeting_id: {meeting_id}" if meeting_id else "",
        f"level: {cand.get('level')}",
        f"assignee: {cand.get('assignee')}" if cand.get("assignee") else "",
    ]
    note = " / ".join(p for p in note_parts if p)
    comment = (
        f"サマリ: SB候補から起票（{cand.get('level')}）\n"
        f"アウトプット:\n"
        f"- meeting_id: `{meeting_id}`\n"
    )
    if cand.get("project_url"):
        comment += f"- [会議]({cand['project_url']})\n"

    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "lane": lane,
            "title": title,
            "note": note,
        }

    cmd = [
        str(PY),
        str(REPO / "scripts" / "jarvis_todoist_api.py"),
        "create-task",
        "--lane",
        lane,
        "--title",
        title,
        "--note",
        note,
        "--comment",
        comment,
        "--json",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO))
    if proc.returncode != 0:
        return {
            "ok": False,
            "error": (proc.stderr or proc.stdout or "").strip()[:500],
            "lane": lane,
            "title": title,
        }
    try:
        data = json.loads(proc.stdout.strip().splitlines()[-1])
    except Exception:
        data = {"ok": True, "raw": proc.stdout.strip()[:300]}
    data["lane"] = lane
    data["title"] = title
    return data


def cmd_apply(args: argparse.Namespace) -> int:
    state = _load_state()
    cands: list[dict[str, Any]] = list(state.get("proposals") or [])
    if not cands:
        raise SystemExit(
            "提案がありません。先に --latest / --meeting-id で propose してください。"
        )

    select = (args.select or "").strip().lower()
    if not select:
        raise SystemExit("--select 1,2 または --select all が必要です")

    chosen: list[dict[str, Any]] = []
    if select in ("all", "*"):
        chosen = list(cands)
    else:
        nums = set()
        for part in re.split(r"[,\s]+", select):
            if part.isdigit():
                nums.add(int(part))
        for c in cands:
            if int(c.get("n") or 0) in nums:
                chosen.append(c)
        if not chosen:
            raise SystemExit(f"番号に一致する候補がありません: {select}")

    if args.mine_only:
        chosen = [c for c in chosen if c.get("mine")]
        if not chosen:
            raise SystemExit("--mine-only だが自分宛候補がありません")

    dry = bool(args.dry_run)
    results = []
    created_ids = list(state.get("created_ids") or [])
    for c in chosen:
        r = _create_task(c, dry_run=dry)
        results.append(r)
        if r.get("ok") and r.get("id") and not dry:
            created_ids.append(str(r["id"]))

    state["created_ids"] = created_ids[-100:]
    state["last_apply_at"] = _now_iso()
    state["last_apply_results"] = results
    _save_state(state)

    print("📎 Todoist起票（SB/Genspark）" + (" DRY-RUN" if dry else ""))
    for r in results:
        if r.get("ok"):
            if dry:
                print(f"- [dry] [{r.get('lane')}] {r.get('title')}")
            else:
                print(f"- created id={r.get('id')} lane={r.get('lane')} {r.get('title')}")
                if r.get("url"):
                    print(f"  url={r.get('url')}")
        else:
            print(f"- FAIL: {r.get('error')} / {r.get('title')}", file=sys.stderr)
    ok = all(x.get("ok") for x in results)
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="SB/Genspark → Todoist 候補提案（了承後 create）"
    )
    p.add_argument("--meeting-id", default=None, help="Genspark meeting / task id")
    p.add_argument("--latest", action="store_true", help="最新1件を提案")
    p.add_argument("--keyword", default=None, help="search の先頭ヒットを提案")
    p.add_argument("--page-size", type=int, default=5)
    p.add_argument(
        "--mine-only",
        action="store_true",
        help="松野さん宛 Action Items のみ（propose / apply 共通）",
    )
    p.add_argument("--json", action="store_true", help="JSON 出力（propose）")
    p.add_argument(
        "--apply",
        action="store_true",
        help="直近の提案から create-task（了承後のみ）",
    )
    p.add_argument(
        "--select",
        default=None,
        help="起票する番号（例: 1 または 1,3 または all）",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="--apply 時に create せず内容だけ表示",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.apply:
        return cmd_apply(args)
    if not (args.meeting_id or args.latest or args.keyword):
        args.latest = True
    return cmd_propose(args)


if __name__ == "__main__":
    sys.exit(main())
