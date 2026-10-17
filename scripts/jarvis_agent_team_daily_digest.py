#!/usr/bin/env python3
"""AIエージェントチーム — Slack 日次集約（第1段階・通知のみ）。

Todoist `agent_team` の列件数＋物件ゲート（114）の未判断Bを集計し、
`#report` に1通投稿する。指示・承認ボタンは後段（第2/3段階）。

例:
  python scripts/jarvis_agent_team_daily_digest.py --dry-run
  python scripts/jarvis_agent_team_daily_digest.py --post
  python scripts/jarvis_agent_team_daily_digest.py --post --force

無効化: JARVIS_AGENT_TEAM_DAILY_DIGEST_DISABLE=1
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.parse
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"
POST = SCRIPTS / "jarvis_slack_webhook_post.py"
STATE_PATH = REPO / ".jarvis_state" / "agent_team_daily_digest.json"
GATE_STATE = REPO / ".jarvis_state" / "property_gate.json"
JST = ZoneInfo("Asia/Tokyo")
PY = sys.executable

_OPEN_DECISIONS = ("yes", "no", "sent", "skipped")


def _today() -> str:
    return datetime.now(JST).date().isoformat()


def _disabled() -> bool:
    return (os.environ.get("JARVIS_AGENT_TEAM_DAILY_DIGEST_DISABLE") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _load_state() -> dict:
    if not STATE_PATH.is_file():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(st: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(st, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _todoist_section_counts() -> tuple[Counter[str], list[str]]:
    """agent_team レーンのセクション別件数と、オーナー確認タイトル先頭。"""
    sys.path.insert(0, str(SCRIPTS))
    import jarvis_todoist_api as td  # noqa: WPS433

    cfg = td._load_yaml()
    td._use_lane_token(cfg, "agent_team")
    lane = td._lane(cfg, "agent_team")
    proj = td._project_for_lane(cfg, lane)
    pid = proj["project_id"]
    tasks = td._paginate_results(
        f"/tasks?project_id={urllib.parse.quote(pid)}", cfg=cfg
    )
    sid_to_name = {v: k for k, v in (proj.get("section_ids") or {}).items()}
    counts: Counter[str] = Counter()
    owner_titles: list[str] = []
    # agent_team は専用プロジェクト → 全件（work_bundle 同居フィルタは不要）
    for t in tasks:
        sec = sid_to_name.get(str(t.get("section_id") or ""), "（無所属）")
        counts[sec] += 1
        if sec == "オーナー確認":
            title = str(t.get("content") or "").strip()
            if title:
                owner_titles.append(title[:60])
    return counts, owner_titles[:8]


def _gate_open_b() -> tuple[int, int]:
    """未判断B（カード投稿済）／保留登録件数。"""
    if not GATE_STATE.is_file():
        return 0, 0
    try:
        st = json.loads(GATE_STATE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0, 0
    open_b = 0
    deferred = 0
    for d in (st.get("deals") or {}).values():
        if not isinstance(d, dict):
            continue
        if d.get("lane") != "B":
            continue
        decision = str(d.get("decision") or "")
        if decision in _OPEN_DECISIONS:
            continue
        if d.get("cleaned_at") or d.get("cleaned_reason"):
            continue
        if d.get("b_deferred_at") and not d.get("b_card_posted_at"):
            deferred += 1
            continue
        if d.get("b_card_posted_at"):
            open_b += 1
        elif d.get("b_deferred_at"):
            deferred += 1
    return open_b, deferred


def build_digest() -> tuple[str, dict]:
    counts, owner_titles = _todoist_section_counts()
    open_b, deferred_b = _gate_open_b()
    owner_n = int(counts.get("オーナー確認", 0))
    progress_n = int(counts.get("進行中", 0))
    todo_n = int(counts.get("未着手", 0))
    hold_n = int(counts.get("HOLD", 0))
    consult_n = owner_n + open_b  # 人が見る優先枠

    lines = [
        f"【AIチーム・日次集約】{_today()}",
        "通知のみ（第1段階）。判断は #consult／オーナー確認へ。",
        "",
        "*■ 今日見てほしい（優先）*",
        f"• 要確認（Todoist オーナー確認）: {owner_n}件",
        f"• 要判断（114 Bカード未決）: {open_b}件"
        + (f"（保留キュー {deferred_b}）" if deferred_b else ""),
    ]
    if owner_titles:
        lines.append("• オーナー確認の先頭:")
        for t in owner_titles:
            lines.append(f"  – {t}")
    if consult_n == 0:
        lines.append("• （優先枠ゼロ。定常のみ）")

    lines += [
        "",
        "*■ 進捗サマリ（Todoist agent_team）*",
        f"• 進行中 {progress_n} ／ 未着手 {todo_n} ／ HOLD {hold_n}",
        "",
        "*■ エラー*",
        "• 本ダイジェストは件数通知のみ。障害は各係が #ops へ即時投稿（集約しない）",
        "",
        "詳細: docs/AIエージェントチーム/33_Slack日次集約_第1段階_20261017.md",
    ]
    meta = {
        "date": _today(),
        "owner_confirm": owner_n,
        "open_b": open_b,
        "deferred_b": deferred_b,
        "progress": progress_n,
        "todo": todo_n,
        "hold": hold_n,
        "consult_priority": consult_n,
    }
    return "\n".join(lines), meta


def post_slack(text: str, *, dry_run: bool) -> dict:
    if dry_run:
        return {"ok": True, "dry_run": True}
    if not POST.is_file():
        return {"ok": False, "error": "jarvis_slack_webhook_post.py missing"}
    r = subprocess.run(
        [PY, str(POST), "--channel", "report", "--text", text],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    return {
        "ok": r.returncode == 0,
        "rc": r.returncode,
        "stdout": (r.stdout or "").strip()[:300],
        "stderr": (r.stderr or "").strip()[:300],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="投稿せず本文を表示")
    ap.add_argument("--post", action="store_true", help="#report へ投稿")
    ap.add_argument("--force", action="store_true", help="同日再投稿を許可")
    args = ap.parse_args()

    if _disabled():
        print("⏭ JARVIS_AGENT_TEAM_DAILY_DIGEST_DISABLE=1")
        return 0

    st = _load_state()
    if st.get("disabled"):
        print("⏭ state disabled")
        return 0

    text, meta = build_digest()
    print(text)
    print("KURASHIFT_RESULT:" + json.dumps({"ok": True, **meta}, ensure_ascii=False))

    if args.dry_run and not args.post:
        return 0
    if not args.post:
        print("（投稿するには --post。確認のみは --dry-run）", file=sys.stderr)
        return 0

    if not args.force and st.get("last_post_date") == _today():
        print("already posted today（--force で再投稿）")
        return 0

    pr = post_slack(text, dry_run=False)
    print(f"slack: {pr}")
    if pr.get("ok"):
        st["last_post_date"] = _today()
        st["last_meta"] = meta
        st["last_posted_at"] = datetime.now(JST).isoformat()
        _save_state(st)
    return 0 if pr.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
