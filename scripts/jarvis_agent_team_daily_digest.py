#!/usr/bin/env python3
"""AIエージェントチーム — Slack 日次集約（第1段階・通知のみ）。

Todoist `agent_team` の列件数＋物件ゲート（114）の未判断Bを集計し、
`#report` に1通投稿する。指示・承認ボタンは後段（第2/3段階）。

レイアウト方針（2026-10-18）: iPhone 幅前提。件数を先頭1行、優先は最大5件・
タイトルは短く省略、深いネスト・長パスは出さない。

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
import re
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

# iPhone Slack 1行目安（全角換算）。超えたら末尾を省略
_TITLE_MAX_CELLS = 22
_PRIORITY_SHOW = 5
# Todoist プロジェクト表示名（config lanes.agent_team / projects.agent_team.name）
_TODOIST_PJ_SHORT = "AIチーム"
_TODOIST_PJ_FULL = "AIエージェントチーム"
_PREFIX_RE = re.compile(
    r"^(\[AIエージェントチーム\]|【AIエージェントチーム】|AIエージェントチーム[｜|]\s*)"
)


def _today() -> str:
    return datetime.now(JST).date().isoformat()


def _today_short() -> str:
    """M/D（iPhone 見出し用。ゼロ埋めなし）。"""
    now = datetime.now(JST)
    return f"{now.month}/{now.day}"


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


def _cell_width(ch: str) -> int:
    """Rough display cells: CJK/fullwidth ≈ 2, else 1."""
    o = ord(ch)
    if (
        0x1100 <= o <= 0x115F
        or 0x2E80 <= o <= 0xA4CF
        or 0xAC00 <= o <= 0xD7A3
        or 0xF900 <= o <= 0xFAFF
        or 0xFE10 <= o <= 0xFE6F
        or 0xFF01 <= o <= 0xFF60
        or 0xFFE0 <= o <= 0xFFE6
        or 0x1F300 <= o <= 0x1FAFF
    ):
        return 2
    return 1


def shorten_title(raw: str, *, max_cells: int = _TITLE_MAX_CELLS) -> str:
    """Strip lane prefix and truncate for mobile one-line."""
    t = (raw or "").strip()
    t = _PREFIX_RE.sub("", t).strip()
    t = re.sub(r"\s+", " ", t)
    if not t:
        return "（無題）"
    cells = 0
    out: list[str] = []
    for ch in t:
        w = _cell_width(ch)
        if cells + w > max_cells:
            out.append("…")
            break
        out.append(ch)
        cells += w
    return "".join(out)


def _todoist_section_counts() -> tuple[Counter[str], list[str]]:
    """agent_team レーンのセクション別件数と、オーナー確認タイトル（全件・短縮前）。"""
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
                owner_titles.append(title)
    return counts, owner_titles


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


SLACK_WORKSPACE_URL = "https://aiwsnetwork.slack.com"
_CONSULT_LOOKBACK_HOURS = 72
_CONSULT_SHOW = 5
_CONSULT_HEAD_RE = re.compile(r"^[*_]*【相談】\s*")
_DONE_HEAD_RE = re.compile(r"^[*_]*【完了】\s*")
# 見出しキー＝先頭の社員番号（211／315／S9 など）。同じ係の相談は最新1件だけ出す
_KEY_RE = re.compile(r"^([0-9A-Za-z]{2,4})(?=\s|$|[｜|])")


def _consult_key(title: str) -> str:
    m = _KEY_RE.match(title.strip())
    return m.group(1) if m else title.strip()[:20]


def consult_open_links() -> list[dict]:
    """第2段階: #consult の要判断で、まだ返信も ✅ も無いものをリンクで集める。

    同じ見出しの相談が毎日出ていても最新1件だけにする。
    トークンが無い・API 失敗時は空（日次は従来どおり出す）。
    """
    if (os.environ.get("JARVIS_DIGEST_CONSULT_LINKS_DISABLE") or "").strip() in ("1", "true", "yes"):
        return []
    try:
        sys.path.insert(0, str(SCRIPTS))
        import jarvis_slack_report_fb_poll as fb  # noqa: E402

        token = fb.slack_token()
        cid = fb._channel_id(fb.load_config(), "consult")
        if not token or not cid:
            return []
        oldest = datetime.now(JST).timestamp() - _CONSULT_LOOKBACK_HOURS * 3600
        msgs = fb.history(cid, token=token, limit=100, oldest=oldest)
    except Exception as e:  # noqa: BLE001
        print(f"# consult links skip: {e}", file=sys.stderr)
        return []

    def _first(m: dict) -> str:
        t = str(m.get("text") or "").strip()
        return t.splitlines()[0] if t else ""

    seen: set[str] = set()
    out: list[dict] = []
    for m in msgs:  # 新しい順
        first = _first(m)
        if _DONE_HEAD_RE.match(first):
            # これより古い同じ係の相談は閉じたもの（ボタン判断の【完了】など）
            seen.add(_consult_key(_DONE_HEAD_RE.sub("", first).strip("* ")))
            continue
        if not _CONSULT_HEAD_RE.match(first):
            continue
        title = _CONSULT_HEAD_RE.sub("", first).strip("* ")
        key = _consult_key(title)
        if key in seen:
            continue
        seen.add(key)
        done = any(
            isinstance(r, dict) and r.get("name") == "white_check_mark"
            for r in (m.get("reactions") or [])
        )
        if done or int(m.get("reply_count") or 0) > 0:
            continue
        ts = str(m.get("ts") or "")
        out.append(
            {
                "title": re.split(r"\s*[｜|—]\s*|\s+:", title)[0],
                "url": f"{SLACK_WORKSPACE_URL}/archives/{cid}/p{ts.replace('.', '')}",
            }
        )
    return out


def build_digest() -> tuple[str, dict]:
    """iPhone向け短文。件数の出所（Todoist PJ／列）を明示→優先最大5件。"""
    counts, owner_titles = _todoist_section_counts()
    open_b, deferred_b = _gate_open_b()
    owner_n = int(counts.get("オーナー確認", 0))
    progress_n = int(counts.get("進行中", 0))
    todo_n = int(counts.get("未着手", 0))
    hold_n = int(counts.get("HOLD", 0))
    consult_n = owner_n + open_b  # 人が見る優先枠

    # 件数はすべて Todoist「AIエージェントチーム」Board の各列
    # B未決だけは物件ゲート（ダッシュ）— Todoist ではない
    b_bit = f"物件B未決{open_b}"
    if deferred_b:
        b_bit += f"(保留{deferred_b})"
    b_bit += "＝ダッシュ(Todoist外)"

    lines = [
        f"【日次】{_today_short()}",
        f"場所: Todoist「{_TODOIST_PJ_FULL}」",
        f"列件数: 確認{owner_n}／進行{progress_n}／未着手{todo_n}／HOLD{hold_n}",
        b_bit,
        "",
    ]

    if owner_n == 0 and open_b == 0:
        lines.append("今日見る: なし（オーナー確認列＝0）")
    else:
        lines.append(f"今日見る→同PJの「オーナー確認」列")
        shown = owner_titles[:_PRIORITY_SHOW]
        for i, raw in enumerate(shown, 1):
            lines.append(f"{i}. {shorten_title(raw)}")
        rest = max(0, owner_n - len(shown))
        if rest:
            lines.append(f"（他{rest}件→Todoist同PJ・同列）")
        if open_b:
            lines.append(f"＋物件B {open_b}件はカードで判断(#consult)")

    consult = consult_open_links()
    if consult:
        lines += ["", f"要判断（#consult・未返信 {len(consult)}件）"]
        for i, c in enumerate(consult[:_CONSULT_SHOW], 1):
            lines.append(f"{i}. <{c['url']}|{shorten_title(c['title'])}>")
        if len(consult) > _CONSULT_SHOW:
            lines.append(f"（他{len(consult) - _CONSULT_SHOW}件→#consult）")

    lines += [
        "",
        "障害→#ops（本通は件数のみ）",
    ]
    meta = {
        "date": _today(),
        "todoist_project": _TODOIST_PJ_FULL,
        "todoist_project_short": _TODOIST_PJ_SHORT,
        "owner_confirm": owner_n,
        "open_b": open_b,
        "deferred_b": deferred_b,
        "progress": progress_n,
        "todo": todo_n,
        "hold": hold_n,
        "consult_priority": consult_n,
        "priority_shown": min(_PRIORITY_SHOW, len(owner_titles)),
        "consult_open": len(consult),
        "layout": "iphone_v3",
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
