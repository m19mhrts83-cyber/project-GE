#!/usr/bin/env python3
"""714 議事録整理係 — Genspark/JPR から Notion Inbox 候補を提案し、了承後に作成。

無言の Notion 作成・Todoist 起票はしない。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  export PATH="$HOME/.local/bin:$HOME/.genspark-tool-cli/bin:$PATH"
  ~/selenium_env/venv/bin/python scripts/jarvis_meeting_minutes_curate.py scan
  ~/selenium_env/venv/bin/python scripts/jarvis_meeting_minutes_curate.py scan --mark-prompted
  ~/selenium_env/venv/bin/python scripts/jarvis_meeting_minutes_curate.py apply --select 1

停止: JARVIS_MEETING_MINUTES_CURATE_DISABLE=1 または state disabled
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
PY = Path("/Users/matsunomasaharu2/selenium_env/venv/bin/python")
STATE_PATH = REPO / ".jarvis_state" / "meeting_minutes_curate.json"
YAML_PATH = REPO / "config" / "notion_phone_meeting.yaml"
FETCH = REPO / "scripts" / "jarvis_genspark_meeting_fetch.py"
SB_PROPOSE = REPO / "scripts" / "jarvis_todoist_sb_propose.py"
REPORTS_DIR = (
    REPO
    / "docs"
    / "AIエージェントチーム"
    / "700_コーチング支援室"
    / "714_議事録整理係"
    / "reports"
)
OBSIDIAN_INDEX = (
    Path.home()
    / "Documents"
    / "500_Obsidian_r1"
    / "03_Literature Note(まとめノート)"
    / "録音メモ"
)
JST = timezone(timedelta(hours=9))
NOTION_VERSION = "2022-06-28"
API = "https://api.notion.com/v1"

FAMILY_RE = re.compile(
    r"家族会議|family[_\s-]?meeting|珠己|円香|千景|まどか|Journal週次",
    re.I,
)
PARTNER_RE = re.compile(
    r"LEAF|ミニテック|ホームプランナー|Tcell|銀行|税理士|Kneesbee|名古屋銀行|"
    r"Grandole|キャラメル|神大家|仲介|融資|修繕|退去|空室|パートナー",
    re.I,
)
ACTION_RE = re.compile(r"(?im)^##\s*Action\s*Items?\b")
MIN_SUMMARY_CHARS = 80


def _now_iso() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def _disabled(state: dict[str, Any]) -> bool:
    if os.environ.get("JARVIS_MEETING_MINUTES_CURATE_DISABLE", "").strip() in (
        "1",
        "true",
        "yes",
    ):
        return True
    return bool(state.get("disabled"))


def _load_state() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        return {
            "proposals": [],
            "saved": {},
            "last_prompted_at": None,
            "disabled": False,
        }
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"proposals": [], "saved": {}, "last_prompted_at": None}


def _save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _load_yaml() -> dict[str, Any]:
    if not YAML_PATH.is_file():
        return {}
    try:
        import yaml  # type: ignore

        return yaml.safe_load(YAML_PATH.read_text(encoding="utf-8")) or {}
    except Exception:
        text = YAML_PATH.read_text(encoding="utf-8")
        out: dict[str, Any] = {}
        for key in ("inbox_page_id", "hub_page_id", "token_env", "inbox_url"):
            m = re.search(rf"^{key}:\s*[\"']?([^\"'\n]+)", text, re.M)
            if m:
                out[key] = m.group(1).strip()
        return out


def _normalize_page_id(raw: str) -> str:
    page_id = (raw or "").replace("-", "").strip()
    if len(page_id) == 32:
        return (
            f"{page_id[:8]}-{page_id[8:12]}-{page_id[12:16]}-"
            f"{page_id[16:20]}-{page_id[20:]}"
        )
    return (raw or "").strip()


def _notion_token(cfg: dict[str, Any]) -> str:
    env_key = (cfg.get("token_env") or "NOTION_API_TOKEN").strip()
    tok = (os.environ.get(env_key) or os.environ.get("NOTION_API_TOKEN") or "").strip()
    if not tok:
        raise SystemExit(f"ERROR: {env_key} 未設定")
    return tok


def _notion_req(
    method: str, path: str, body: dict[str, Any] | None, token: str
) -> dict[str, Any]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{API}{path}",
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Notion HTTP {e.code}: {err[:500]}") from e


def _list_meetings(page_size: int = 15) -> list[dict[str, Any]]:
    cmd = [
        str(PY),
        str(FETCH),
        "list",
        "--page-size",
        str(page_size),
        "--json",
        "--shaped",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO))
    if proc.returncode != 0:
        raise SystemExit(
            f"genspark list 失敗: {(proc.stderr or proc.stdout or '')[:500]}"
        )
    data = json.loads(proc.stdout)
    return list(data.get("notes") or [])


def _get_summary(meeting_id: str) -> dict[str, Any]:
    cmd = [
        str(PY),
        str(FETCH),
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
        return {}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {}


def _meeting_id(note: dict[str, Any]) -> str:
    return str(
        note.get("id")
        or note.get("task_id")
        or note.get("meeting_id")
        or note.get("note_id")
        or ""
    ).strip()


def _title_of(note: dict[str, Any]) -> str:
    return str(
        note.get("title") or note.get("name") or note.get("subject") or "(無題)"
    ).strip()


def _score_candidate(
    note: dict[str, Any], summary: dict[str, Any], state: dict[str, Any]
) -> tuple[int, list[str]]:
    mid = _meeting_id(note)
    title = _title_of(note)
    body = str(
        summary.get("summary")
        or summary.get("text")
        or summary.get("content")
        or ""
    )
    blob = f"{title}\n{body}"
    reasons: list[str] = []
    score = 0

    if FAMILY_RE.search(blob):
        return -100, ["家族会議系のため除外"]
    saved = state.get("saved") or {}
    if mid and mid in saved:
        return -100, ["既に Notion 保存済"]

    if PARTNER_RE.search(blob):
        score += 3
        reasons.append("パートナー／物件語")
    if ACTION_RE.search(body) or "Action Item" in body or "宿題" in body:
        score += 2
        reasons.append("Action Items")
    if len(body) >= MIN_SUMMARY_CHARS:
        score += 1
        reasons.append(f"要約長≥{MIN_SUMMARY_CHARS}")
    if score <= 0 and len(body) < 40:
        return -100, ["短すぎ／信号なし"]
    if score <= 0:
        score = 0
        reasons.append("要目視（弱い候補）")
    return score, reasons


def cmd_scan(args: argparse.Namespace) -> int:
    state = _load_state()
    if _disabled(state):
        print("📎 714: disabled — skip")
        return 0

    notes = _list_meetings(page_size=args.page_size)
    proposals: list[dict[str, Any]] = []
    for note in notes:
        mid = _meeting_id(note)
        if not mid:
            continue
        summary = _get_summary(mid)
        score, reasons = _score_candidate(note, summary, state)
        if score < 0:
            continue
        title = _title_of(note)
        created = note.get("created_at") or note.get("date") or ""
        proposals.append(
            {
                "meeting_id": mid,
                "title": title,
                "created": created,
                "score": score,
                "reasons": reasons,
                "summary_preview": str(
                    summary.get("summary") or summary.get("text") or ""
                )[:240],
                "project_url": note.get("project_url") or note.get("url") or "",
            }
        )

    proposals.sort(
        key=lambda x: (-int(x["score"]), str(x.get("created") or "")),
    )
    state["proposals"] = proposals
    state["last_scan_at"] = _now_iso()
    if args.mark_prompted:
        state["last_prompted_at"] = _now_iso()
    _save_state(state)

    if not proposals:
        print("📎 議事録整理（714）: 新規候補なし")
        return 0

    print("📎 議事録整理（714）— Notion 残し候補")
    for i, p in enumerate(proposals, 1):
        print(
            f"- [{i}] score={p['score']} {p['title'][:60]}\n"
            f"  id={p['meeting_id']} reasons={', '.join(p['reasons'])}\n"
            f"  preview: {(p.get('summary_preview') or '')[:120]}"
        )
    print("了承なら: jarvis_meeting_minutes_curate.py apply --select N（または all）")
    print("※家族会議は除外済。無言作成はしない。")
    return 0


def _create_notion_page(
    *,
    title: str,
    body: str,
    meeting_id: str,
    project_url: str,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    token = _notion_token(cfg)
    parent = _normalize_page_id(str(cfg.get("inbox_page_id") or ""))
    if not parent:
        raise SystemExit("config/notion_phone_meeting.yaml の inbox_page_id が空")
    children: list[dict[str, Any]] = []
    meta = f"meeting_id: {meeting_id}"
    if project_url:
        meta += f"\nurl: {project_url}"
    for chunk in (meta, body or "(要約なし)"):
        children.append(
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {"type": "text", "text": {"content": chunk[:1900]}}
                    ]
                },
            }
        )
    page = _notion_req(
        "POST",
        "/pages",
        {
            "parent": {"page_id": parent},
            "properties": {
                "title": {
                    "title": [{"type": "text", "text": {"content": title[:2000]}}]
                }
            },
            "children": children,
        },
        token,
    )
    return page


def _append_obsidian_index(line: str) -> Path | None:
    try:
        OBSIDIAN_INDEX.mkdir(parents=True, exist_ok=True)
        day = datetime.now(JST).strftime("%Y%m%d")
        path = OBSIDIAN_INDEX / f"{day}_議事録索引追記.md"
        with path.open("a", encoding="utf-8") as f:
            if path.stat().st_size == 0:
                f.write(f"# 録音メモ索引追記 {day}\n\n")
            f.write(f"- {line}\n")
        return path
    except OSError as e:
        print(f"⚠️ Obsidian 索引失敗: {e}", file=sys.stderr)
        return None


def cmd_apply(args: argparse.Namespace) -> int:
    state = _load_state()
    if _disabled(state):
        print("📎 714: disabled — skip")
        return 0
    proposals = list(state.get("proposals") or [])
    if not proposals:
        print("候補がありません。先に scan してください。", file=sys.stderr)
        return 2

    select = (args.select or "").strip().lower()
    indices: list[int] = []
    if select == "all":
        indices = list(range(len(proposals)))
    else:
        try:
            n = int(select)
        except ValueError:
            print("--select は番号または all", file=sys.stderr)
            return 2
        if n < 1 or n > len(proposals):
            print(f"--select 範囲外: 1..{len(proposals)}", file=sys.stderr)
            return 2
        indices = [n - 1]

    cfg = _load_yaml()
    saved = dict(state.get("saved") or {})
    created: list[dict[str, Any]] = []

    for i in indices:
        p = proposals[i]
        mid = p["meeting_id"]
        if mid in saved:
            print(f"skip already saved: {mid}")
            continue
        summary = _get_summary(mid)
        body = str(summary.get("summary") or summary.get("text") or p.get("summary_preview") or "")
        day = (p.get("created") or _now_iso())[:10]
        title = f"[SB] {day} {p['title']}"[:200]
        if args.dry_run:
            print(f"DRY-RUN would create: {title}")
            continue
        page = _create_notion_page(
            title=title,
            body=body,
            meeting_id=mid,
            project_url=str(p.get("project_url") or ""),
            cfg=cfg,
        )
        url = page.get("url") or ""
        saved[mid] = {
            "notion_url": url,
            "page_id": page.get("id"),
            "title": title,
            "at": _now_iso(),
        }
        idx = _append_obsidian_index(f"{title} — {url} (id={mid})")
        created.append({"title": title, "url": url, "index": str(idx) if idx else ""})
        print(f"✅ Notion: {title}\n   {url}")
        if args.with_todoist and SB_PROPOSE.is_file():
            subprocess.run(
                [
                    str(PY),
                    str(SB_PROPOSE),
                    "--meeting-id",
                    mid,
                ],
                cwd=str(REPO),
            )

    if not args.dry_run:
        state["saved"] = saved
        _save_state(state)
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        day = datetime.now(JST).strftime("%Y-%m-%d")
        path = REPORTS_DIR / f"{day}_applied.md"
        lines = [f"# 714 apply {day}\n"]
        for c in created:
            lines.append(f"- {c['title']}: {c['url']}")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        # ogd retag for obsidian if any
        for c in created:
            if c.get("index"):
                rel = Path(c["index"])
                try:
                    rel_s = str(
                        rel.relative_to(
                            Path.home() / "Documents" / "500_Obsidian_r1"
                        )
                    )
                    subprocess.run(
                        [
                            str(PY),
                            str(REPO / "scripts" / "jarvis_obsidian_ogd_retag.py"),
                            rel_s,
                        ],
                        cwd=str(REPO),
                        capture_output=True,
                    )
                except Exception:
                    pass
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sc = sub.add_parser("scan", help="候補を列挙")
    sc.add_argument("--page-size", type=int, default=15)
    sc.add_argument("--mark-prompted", action="store_true")

    ap_apply = sub.add_parser("apply", help="了承後に Notion 作成")
    ap_apply.add_argument("--select", required=True, help="番号 or all")
    ap_apply.add_argument("--dry-run", action="store_true")
    ap_apply.add_argument(
        "--with-todoist",
        action="store_true",
        help="作成後に sb_propose を呼ぶ（起票は別途了承）",
    )

    args = ap.parse_args()
    if args.cmd == "scan":
        return cmd_scan(args)
    if args.cmd == "apply":
        return cmd_apply(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
