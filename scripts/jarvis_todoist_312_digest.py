#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""312 L1ダイジェスト → Slack #consult（見るだけ）→ 了承後 create.

Phase 1: ボタンUIなし。投稿は Webhook。create は `--apply --select`。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  export PATH="$HOME/.local/bin:$HOME/.genspark-tool-cli/bin:$PATH"

  # 候補収集＋#consult 投稿（既定）
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_312_digest.py

  # 投稿せず本文だけ
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_312_digest.py --dry-run

  # 了承後（番号はダイジェストの #）
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_312_digest.py --apply --select 1
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
STATE_PATH = REPO / ".jarvis_state" / "todoist_312_digest.json"
PY = Path("/Users/matsunomasaharu2/selenium_env/venv/bin/python")
JST = timezone(timedelta(hours=9))
MAX_L1 = 7


def _now_iso() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def _load_state() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        return {"proposals": [], "last_digest_at": None, "created_ids": []}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"proposals": [], "last_digest_at": None, "created_ids": []}


def _save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _run_json(cmd: list[str]) -> dict[str, Any]:
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO))
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    if proc.returncode != 0:
        raise RuntimeError(err or out or f"exit {proc.returncode}")
    # 最後の JSON オブジェクトを拾う
    text = out
    if not text.startswith("{"):
        # 先頭ログがある場合
        idx = text.rfind("\n{")
        if idx >= 0:
            text = text[idx + 1 :]
        elif "{" in text:
            text = text[text.index("{") :]
    return json.loads(text)


def _collect_sb(*, mine_only: bool) -> list[dict[str, Any]]:
    cmd = [
        str(PY),
        str(REPO / "scripts" / "jarvis_todoist_sb_propose.py"),
        "--latest",
        "--json",
    ]
    if mine_only:
        cmd.append("--mine-only")
    try:
        data = _run_json(cmd)
    except Exception as e:
        print(f"# sb_propose skip: {e}", file=sys.stderr)
        return []
    meeting = data.get("meeting") or {}
    out: list[dict[str, Any]] = []
    for c in data.get("candidates") or []:
        out.append(
            {
                "origin": "sb",
                "title": str(c.get("title") or "").strip(),
                "lane": str(c.get("lane") or "ai_raimo"),
                "summary": f"SB: {meeting.get('title') or '会議'}",
                "level": c.get("level") or "L1",
                "meeting_id": c.get("meeting_id") or meeting.get("id"),
                "project_url": c.get("project_url") or meeting.get("project_url"),
                "assignee": c.get("assignee"),
                "mine": bool(c.get("mine")),
            }
        )
    return out


def _collect_genmail() -> list[dict[str, Any]]:
    cmd = [
        str(PY),
        str(REPO / "scripts" / "jarvis_todoist_genmail_propose.py"),
        "--json",
    ]
    try:
        data = _run_json(cmd)
    except Exception as e:
        print(f"# genmail_propose skip: {e}", file=sys.stderr)
        return []
    out: list[dict[str, Any]] = []
    for c in data.get("proposals") or []:
        out.append(
            {
                "origin": "genmail",
                "title": str(c.get("title") or "").strip(),
                "lane": str(c.get("lane") or "ai_raimo"),
                "summary": str(c.get("summary") or "")[:200],
                "level": "L1",
                "fingerprint": c.get("fingerprint"),
                "account": c.get("account"),
            }
        )
    return out


DISMISS_DAYS = 14


def _dismiss_key(title: Any) -> str:
    return re.sub(r"\s+", " ", str(title or "").strip().lower())


def _active_dismissed(state: dict[str, Any], *, days: int = DISMISS_DAYS) -> set[str]:
    """見送り済みのキー（直近 days 日ぶんだけ再提案を抑える）。"""
    cutoff = datetime.now(JST) - timedelta(days=days)
    keys: set[str] = set()
    for row in state.get("dismissed") or []:
        try:
            at = datetime.fromisoformat(str(row.get("at")))
        except Exception:
            continue
        if at >= cutoff and row.get("key"):
            keys.add(str(row["key"]))
    return keys


def _merge(
    items: list[dict[str, Any]],
    *,
    max_items: int = MAX_L1,
    dismissed: set[str] | None = None,
) -> list[dict[str, Any]]:
    seen: set[str] = set(dismissed or set())
    merged: list[dict[str, Any]] = []
    for it in items:
        title = (it.get("title") or "").strip()
        if not title:
            continue
        key = re.sub(r"\s+", " ", title.lower())
        if key in seen:
            continue
        seen.add(key)
        it = dict(it)
        it["n"] = len(merged) + 1
        merged.append(it)
        if len(merged) >= max_items:
            break
    return merged


_JP_D = {"〇": 0, "零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
         "六": 6, "七": 7, "八": 8, "九": 9}
_JP_U = {"十": 10, "百": 100, "千": 1000}


def _jp_num(s: str) -> int | None:
    total = cur = 0
    for ch in s:
        if ch in _JP_D:
            cur = _JP_D[ch]
        elif ch in _JP_U:
            total += (cur or 1) * _JP_U[ch]
            cur = 0
        else:
            return None
    return total + cur


def _humanize_date(text: str) -> str:
    """年月日が漢数字のときだけ数字に（二千二十六年十月三十一日 → 2026/10/31）。"""

    def rep(m: re.Match[str]) -> str:
        y = _jp_num(m.group(1))
        if not y:
            return m.group(0)
        mo = _jp_num(m.group(2)) if m.group(2) else None
        day = _jp_num(m.group(3)) if m.group(3) else None
        if mo and day:
            return f"{y}/{mo}/{day}"
        if mo:
            return f"{y}年{mo}月"
        return f"{y}年"

    return re.sub(
        r"([〇一二三四五六七八九十百千]+)年"
        r"(?:([〇一二三四五六七八九十]+)月(?:([〇一二三四五六七八九十]+)日)?)?",
        rep,
        text,
    )


def _short_title(title: Any, limit: int = 44) -> str:
    t = re.sub(r"\s+", " ", _humanize_date(str(title or ""))).strip().rstrip("。．.")
    t = re.sub(r"\s*[—–-]\s*状況[:：].*$", "", t)
    t = re.sub(r"[（(]状況[:：][^）)]*[）)]", "", t).strip()
    if len(t) > limit:
        cut = t[: limit - 1]
        sep = cut.rfind(" — ")
        if sep >= limit // 2:
            cut = cut[:sep]
        t = cut.rstrip().rstrip(" —、・,.:：-") + "…"
    return t


def _item_line(it: dict[str, Any]) -> str:
    """1件＝タイトル1行。件ごとの空行で読みやすく（313と同型）。"""
    url = str(it.get("project_url") or "").strip()
    tail = f" · <{url}|会議>" if url else ""
    return f"*{it['n']}.* {_short_title(it.get('title'))}{tail}"


def _format_slack(items: list[dict[str, Any]], *, note: str = "") -> str:
    lines: list[str] = ["📋 *Todoist起票整理*", ""]
    if items:
        lines.extend(["*起票してよければ番号で返信*", ""])
        lines.append("\n\n".join(_item_line(it) for it in items))
    else:
        lines.append("候補なし（今回の登録はありません）")
    lines.extend(
        [
            "",
            "*返信の書き方*",
            "「起票して 1,3」→ その番号だけ Todoist に登録",
            "「全部見送り」→ 何もしない（次回また出ます）",
            "「会議」をタップ → 出典を確認",
            "",
            "次: 人判断（起票して N）",
            "担当メモ: 採用分だけ create＋コメント。L1のままでは登録しない",
            "橋渡し: 新規起票は312 ／ 完了closeは313",
        ]
    )
    if note:
        lines.extend(["", f"_{note}_"])
    return "\n".join(lines)


def _post_consult(text: str) -> int:
    url = (os.environ.get("SLACK_WEBHOOK_AI_TEAM_CONSULT") or "").strip()
    fallback = False
    if not url:
        url = (os.environ.get("SLACK_WEBHOOK_AI_TEAM_REPORT") or "").strip()
        fallback = True
    if not url:
        print("❌ SLACK_WEBHOOK_AI_TEAM_CONSULT / REPORT がありません", file=sys.stderr)
        return 2
    body_text = text
    if fallback:
        body_text = "【#consult】\n" + text
    payload = {
        "text": body_text,
        "username": "312 Todoist起票整理",
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            print(
                f"✅ #consult 投稿 OK status={resp.status}"
                + (" (fallback #report)" if fallback else "")
            )
            return 0
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        print(f"❌ Slack HTTP {e.code}: {err}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"❌ Slack failed: {e}", file=sys.stderr)
        return 1


def _create_task(it: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
    lane = str(it.get("lane") or "ai_raimo")
    title = str(it.get("title") or "").strip()
    if not title:
        return {"ok": False, "error": "empty title"}
    if not title.startswith("["):
        title = f"[{lane}] {title}"
    origin = it.get("origin") or "312"
    note = f"出典: 312 digest ({origin})"
    if it.get("summary"):
        note += f" / {it['summary']}"
    comment = (
        "【Jarvis】\n"
        f"サマリ: 312 L1了承後の①create（origin={origin}）\n"
        "アウトプット:\n"
    )
    if it.get("project_url"):
        comment += f"- [会議]({it['project_url']})\n"
    else:
        comment += "- [312 flow](docs/AIエージェントチーム/300_品質・タスク運用管理室/312_Todoist起票整理係/flow.md)\n"

    if dry_run:
        return {"ok": True, "dry_run": True, "lane": lane, "title": title}

    # properties は物件+PM必須 → digestでは ai_raimo に落とす
    if lane == "properties":
        lane = "ai_raimo"
        if title.startswith("[properties]"):
            title = "[ai_raimo]" + title[len("[properties]") :]

    labels = "quick"
    if origin == "sb":
        labels = "SecondBrain,quick"

    cmd = [
        str(PY),
        str(REPO / "scripts" / "jarvis_todoist_api.py"),
        "create-task",
        "--lane",
        lane,
        "--title",
        title,
        "--note",
        note[:1500],
        "--label",
        labels,
        "--comment",
        comment[:1900],
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
        data = {"ok": True, "raw": (proc.stdout or "")[:300]}
    data["lane"] = lane
    data["title"] = title
    return data


def cmd_digest(args: argparse.Namespace) -> int:
    state = _load_state()
    items: list[dict[str, Any]] = []
    if not args.skip_sb:
        items.extend(_collect_sb(mine_only=bool(args.mine_only)))
    if not args.skip_genmail:
        items.extend(_collect_genmail())
    merged = _merge(
        items,
        max_items=int(args.limit),
        dismissed=_active_dismissed(state),
    )
    note = "" if (not args.skip_sb and not args.skip_genmail) else (
        f"出典の一部をスキップ: SB={'on' if not args.skip_sb else 'off'} "
        f"GenMail={'on' if not args.skip_genmail else 'off'}"
    )
    text = _format_slack(merged, note=note)

    state["proposals"] = merged
    state["last_digest_at"] = _now_iso()
    state["last_digest_text"] = text
    _save_state(state)

    print(text)
    print()
    print(f"📎 312 digest: candidates={len(merged)} state={STATE_PATH.name}")

    if args.dry_run:
        print("（--dry-run: Slack 未投稿）")
        return 0
    if not merged and not args.post_empty:
        print("候補0件のため Slack 投稿をスキップ（--post-empty で強制可）")
        return 0
    return _post_consult(text)


def cmd_apply(args: argparse.Namespace) -> int:
    state = _load_state()
    cands: list[dict[str, Any]] = list(state.get("proposals") or [])
    if not cands:
        raise SystemExit("提案がありません。先に digest（引数なし）を実行してください。")

    select = (args.select or "").strip().lower()
    if not select:
        raise SystemExit("--select 1,2 または --select all が必要です")

    chosen: list[dict[str, Any]] = []
    if select in ("all", "*"):
        # L1方針: 一括createは禁止。明示 --i-confirm-all のみ
        if not args.i_confirm_all:
            raise SystemExit(
                "L1は一括createしません。番号指定か --i-confirm-all を付けてください。"
            )
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

    print("📎 Todoist起票（312 digest）" + (" DRY-RUN" if dry else ""))
    for r in results:
        if r.get("ok"):
            if dry:
                print(f"- [dry] [{r.get('lane')}] {r.get('title')}")
            else:
                print(f"- created id={r.get('id')} lane={r.get('lane')} {r.get('title')}")
        else:
            print(f"- FAIL: {r.get('error')} / {r.get('title')}", file=sys.stderr)

    # 失敗時は #ops
    if not dry and any(not x.get("ok") for x in results):
        ops = (os.environ.get("SLACK_WEBHOOK_AI_TEAM_OPS") or "").strip()
        if ops:
            msg = "【ops】312 Todoist起票整理 — create失敗\n" + "\n".join(
                f"- {x.get('error')}" for x in results if not x.get("ok")
            )
            try:
                urllib.request.urlopen(
                    urllib.request.Request(
                        ops,
                        data=json.dumps(
                            {"text": msg, "username": "312 Todoist起票整理"}
                        ).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    ),
                    timeout=20,
                )
            except Exception:
                pass

    return 0 if all(x.get("ok") for x in results) else 1


def cmd_dismiss(args: argparse.Namespace) -> int:
    state = _load_state()
    proposals = list(state.get("proposals") or [])
    if not proposals:
        raise SystemExit("見送る候補がありません（先に digest を実行）")
    sel = str(args.dismiss or "").strip().lower()
    if sel in ("all", "*"):
        chosen = proposals
    else:
        nums = {int(x) for x in re.split(r"[,\s]+", sel) if x.isdigit()}
        chosen = [c for c in proposals if int(c.get("n") or 0) in nums]
        if not chosen:
            raise SystemExit(f"番号に一致する候補がありません: {sel}")
    dismissed = list(state.get("dismissed") or [])
    now = _now_iso()
    for c in chosen:
        dismissed.append({"key": _dismiss_key(c.get("title")), "at": now})
    state["dismissed"] = dismissed
    state["proposals"] = [p for p in proposals if p not in chosen]
    _save_state(state)
    print(f"📎 見送り {len(chosen)}件（{DISMISS_DAYS}日は再提案しません）")
    for c in chosen:
        print(f"  - #{c.get('n')} {_short_title(c.get('title'))}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="312 L1ダイジェスト → #consult → 了承後 create")
    p.add_argument("--dry-run", action="store_true", help="Slack未投稿 / apply時はcreateしない")
    p.add_argument("--skip-sb", action="store_true")
    p.add_argument("--skip-genmail", action="store_true")
    p.add_argument("--mine-only", action="store_true", help="SBの自分宛のみ")
    p.add_argument("--limit", type=int, default=MAX_L1)
    p.add_argument("--post-empty", action="store_true", help="候補0でも投稿")
    p.add_argument("--dismiss", default=None, help="見送り: all または 1,3（14日再提案しない）")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--select", default=None)
    p.add_argument(
        "--i-confirm-all",
        action="store_true",
        help="--select all の明示了承（通常は番号指定）",
    )
    args = p.parse_args(argv)
    # 停止: ノイズ時は digest／Slack投稿を止める（applyは了承済み番号の消化のため許可）
    if not args.apply and os.environ.get("JARVIS_TODOIST_312_DIGEST_DISABLE", "").strip() in (
        "1",
        "true",
        "yes",
    ):
        print("📎 312 digest: disabled (JARVIS_TODOIST_312_DIGEST_DISABLE=1)")
        return 0
    if args.dismiss:
        return cmd_dismiss(args)
    if args.apply:
        return cmd_apply(args)
    return cmd_digest(args)


if __name__ == "__main__":
    raise SystemExit(main())
