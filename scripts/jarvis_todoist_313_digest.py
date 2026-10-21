#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""313 完了候補ダイジェスト → Slack #consult（見るだけ）→ 了承後 close.

Phase 1: ボタンUIなし。投稿は Webhook。close は `--apply --select` /
`--auto-close-confirm`（確認のみ）。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a

  # オーナー確認列を収集＋#consult 投稿（既定）
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_313_digest.py

  # 投稿せず本文だけ
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_313_digest.py --dry-run

  # 確認のみを Jarvis 完了（コメント必須）
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_313_digest.py --apply --auto-close-confirm

  # 要判断を人了承後に close（番号はダイジェストの #）
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_313_digest.py --apply --select 1
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
STATE_PATH = REPO / ".jarvis_state" / "todoist_313_digest.json"
PY = Path("/Users/matsunomasaharu2/selenium_env/venv/bin/python")
JST = timezone(timedelta(hours=9))
MAX_L1 = 10

DEFAULT_LANES = [
    "ai_raimo",
    "apps",
    "properties",
    "kamiooya",
    "kazoku",
    "agent_team",
    "kodate",
    "kanji",
    "theme_stock",
]

# 確認のみ（Jarvis close 可）— タイトル／メモの弱いヒューリスティック
CONFIRM_RE = re.compile(
    r"(表確認|UI確認|確認のみ|launchd|resume|既完了|一致／不一致|一致/不一致|"
    r"観測可能な復旧|フォローのクローズ)",
    re.I,
)
# 要オーナー判断を強制
NEED_OWNER_RE = re.compile(
    r"(要ボス|検討|どうする|振込|解約|退会|資金|年額|対外|送信して|HOLD|"
    r"方針|Ambiguous|自信なし)",
    re.I,
)
EXCLUDE_RE = re.compile(r"(対外送信|振込実行|解約実行|課金変更)", re.I)

LANE_LINE_RE = re.compile(
    r"^\s*\[(?P<section>[^\]]+)\]\s+(?P<tid>\S+)\s+(?P<title>.+?)\s*$"
)


def _now_iso() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def _load_state() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        return {"proposals": [], "last_digest_at": None, "closed_ids": []}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"proposals": [], "last_digest_at": None, "closed_ids": []}


def _save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _classify(title: str) -> str:
    """confirm_only | need_owner | exclude"""
    t = title or ""
    if EXCLUDE_RE.search(t):
        return "exclude"
    if NEED_OWNER_RE.search(t):
        return "need_owner"
    if CONFIRM_RE.search(t):
        return "confirm_only"
    # オーナー確認にいるがシグナル弱い → 人判断（ノイズより安全側）
    return "need_owner"


def _collect_lane(lane: str) -> list[dict[str, Any]]:
    cmd = [
        str(PY),
        str(REPO / "scripts" / "jarvis_todoist_api.py"),
        "lane",
        "--id",
        lane,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO))
    if proc.returncode != 0:
        print(f"# lane skip {lane}: {(proc.stderr or proc.stdout)[:200]}", file=sys.stderr)
        return []
    out: list[dict[str, Any]] = []
    for line in (proc.stdout or "").splitlines():
        m = LANE_LINE_RE.match(line)
        if not m:
            continue
        if m.group("section") != "オーナー確認":
            continue
        title = m.group("title").strip()
        kind = _classify(title)
        if kind == "exclude":
            continue
        out.append(
            {
                "lane": lane,
                "task_id": m.group("tid"),
                "title": title,
                "kind": kind,
                "section": "オーナー確認",
            }
        )
    return out


def _collect(lanes: list[str]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for lane in lanes:
        items.extend(_collect_lane(lane))
    # 確認のみを先に、その後レーン横断でラウンドロビン（1レーン独占を防ぐ）
    confirm = [i for i in items if i.get("kind") == "confirm_only"]
    need = [i for i in items if i.get("kind") == "need_owner"]
    by_lane: dict[str, list[dict[str, Any]]] = {}
    for it in need:
        by_lane.setdefault(str(it.get("lane") or "?"), []).append(it)
    for v in by_lane.values():
        v.sort(key=lambda x: str(x.get("title") or ""))
    rr: list[dict[str, Any]] = []
    while by_lane and len(confirm) + len(rr) < MAX_L1:
        progress = False
        for lane in list(by_lane.keys()):
            if len(confirm) + len(rr) >= MAX_L1:
                break
            bucket = by_lane[lane]
            if not bucket:
                del by_lane[lane]
                continue
            rr.append(bucket.pop(0))
            progress = True
            if not bucket:
                del by_lane[lane]
        if not progress:
            break
    merged = confirm + rr
    capped: list[dict[str, Any]] = []
    for it in merged[:MAX_L1]:
        it = dict(it)
        it["n"] = len(capped) + 1
        capped.append(it)
    return capped


def _format_slack(items: list[dict[str, Any]], *, note: str = "") -> str:
    confirm = [i for i in items if i.get("kind") == "confirm_only"]
    need = [i for i in items if i.get("kind") == "need_owner"]
    lines = [
        "【相談】313 完了候補確認｜L1ダイジェスト（見るだけ）",
        "",
        "📌 要ボス: 要判断のみ（確認のみは Jarvis 可）",
        "",
        f"確認のみ（最大・Jarvis可 / --auto-close-confirm）: {len(confirm)}件",
    ]
    if not confirm:
        lines.append("- （なし）")
    else:
        for it in confirm:
            lines.append(
                f"- #{it['n']} [{it.get('lane')}] {str(it.get('title') or '')[:70]} — id={it.get('task_id')}"
            )
    lines.extend(["", f"要オーナー判断（閉じて N）: {len(need)}件"])
    if not need:
        lines.append("- （なし）")
    else:
        for it in need:
            lines.append(
                f"- #{it['n']} [{it.get('lane')}] {str(it.get('title') or '')[:70]} — id={it.get('task_id')}"
            )
    lines.extend(
        [
            "",
            "次: Jarvisに依頼",
            "担当メモ: 確認のみ→313 --apply --auto-close-confirm／要判断→「閉じて N」→ --apply --select N",
            "橋渡し: 新規起票は312。313は close のみ",
        ]
    )
    if note:
        lines.extend(["", f"参考: {note}"])
    return "\n".join(lines)


def _post_webhook(text: str, *, channel: str = "consult") -> int:
    env_key = (
        "SLACK_WEBHOOK_AI_TEAM_CONSULT"
        if channel == "consult"
        else "SLACK_WEBHOOK_AI_TEAM_REPORT"
    )
    url = (os.environ.get(env_key) or "").strip()
    fallback = False
    if not url and channel == "consult":
        url = (os.environ.get("SLACK_WEBHOOK_AI_TEAM_REPORT") or "").strip()
        fallback = True
    if not url:
        print(f"❌ {env_key} がありません", file=sys.stderr)
        return 2
    body_text = text
    if fallback:
        body_text = "【#consult】\n" + text
    payload = {"text": body_text, "username": "313 完了候補確認"}
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            print(
                f"✅ #{channel} 投稿 OK status={resp.status}"
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


def _complete_task(it: dict[str, Any], *, dry_run: bool, reason: str) -> dict[str, Any]:
    lane = str(it.get("lane") or "")
    tid = str(it.get("task_id") or "")
    title = str(it.get("title") or "")
    kind = str(it.get("kind") or "need_owner")
    if not lane or not tid:
        return {"ok": False, "error": "missing lane/task_id", "title": title}

    if kind == "confirm_only":
        comment = (
            "【Jarvis】タスク完了したよ（確認のみクローズ）\n"
            f"サマリ: 313 digest 確認のみ（{reason}）— {title[:80]}\n"
            "アウトプット:\n"
            "- [313 flow](docs/AIエージェントチーム/300_品質・タスク運用管理室/313_完了候補確認係/flow.md)\n"
        )
    else:
        comment = (
            "【Jarvis】タスク完了したよ（松野確認OK）\n"
            f"サマリ: 313 digest 了承後 close（{reason}）— {title[:80]}\n"
            "アウトプット:\n"
            "- [313 flow](docs/AIエージェントチーム/300_品質・タスク運用管理室/313_完了候補確認係/flow.md)\n"
        )

    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "lane": lane,
            "task_id": tid,
            "title": title,
            "kind": kind,
        }

    cmd = [
        str(PY),
        str(REPO / "scripts" / "jarvis_todoist_api.py"),
        "complete-task",
        "--lane",
        lane,
        "--task-id",
        tid,
        "--comment",
        comment[:1900],
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO))
    if proc.returncode != 0:
        return {
            "ok": False,
            "error": (proc.stderr or proc.stdout or "").strip()[:500],
            "lane": lane,
            "task_id": tid,
            "title": title,
            "kind": kind,
        }
    return {
        "ok": True,
        "lane": lane,
        "task_id": tid,
        "title": title,
        "kind": kind,
        "raw": (proc.stdout or "")[:300],
    }


def cmd_digest(args: argparse.Namespace) -> int:
    lanes = [x.strip() for x in (args.lanes or ",".join(DEFAULT_LANES)).split(",") if x.strip()]
    items = _collect(lanes)
    note = f"lanes={','.join(lanes)} max={MAX_L1}"
    text = _format_slack(items, note=note)

    state = _load_state()
    state["proposals"] = items
    state["last_digest_at"] = _now_iso()
    state["last_digest_text"] = text
    _save_state(state)

    print(text)
    print()
    print(f"📎 313 digest: candidates={len(items)} state={STATE_PATH.name}")

    if args.dry_run:
        print("（--dry-run: Slack 未投稿）")
        return 0
    if not items and not args.post_empty:
        print("候補0件のため Slack 投稿をスキップ（--post-empty で強制可）")
        return 0
    return _post_webhook(text, channel="consult")


def cmd_apply(args: argparse.Namespace) -> int:
    state = _load_state()
    cands: list[dict[str, Any]] = list(state.get("proposals") or [])
    if not cands and not args.refresh:
        raise SystemExit("提案がありません。先に digest を実行するか --refresh を付けてください。")

    if args.refresh or not cands:
        lanes = [x.strip() for x in (args.lanes or ",".join(DEFAULT_LANES)).split(",") if x.strip()]
        cands = _collect(lanes)
        state["proposals"] = cands
        _save_state(state)

    chosen: list[dict[str, Any]] = []
    if args.auto_close_confirm:
        chosen = [c for c in cands if c.get("kind") == "confirm_only"]
        if not chosen:
            print("確認のみ候補がありません")
            return 0
        reason = "auto-close-confirm"
    else:
        select = (args.select or "").strip().lower()
        if not select:
            raise SystemExit("--select 1,2 または --auto-close-confirm が必要です")
        if select in ("all", "*"):
            raise SystemExit(
                "L1は一括closeしません。番号指定か --auto-close-confirm（確認のみ）を使ってください。"
            )
        nums = set()
        for part in re.split(r"[,\s]+", select):
            if part.isdigit():
                nums.add(int(part))
        for c in cands:
            if int(c.get("n") or 0) in nums:
                chosen.append(c)
        if not chosen:
            raise SystemExit(f"番号に一致する候補がありません: {select}")
        reason = f"select={select}"

    dry = bool(args.dry_run)
    results = []
    closed_ids = list(state.get("closed_ids") or [])
    for c in chosen:
        r = _complete_task(c, dry_run=dry, reason=reason)
        results.append(r)
        if r.get("ok") and r.get("task_id") and not dry:
            closed_ids.append(str(r["task_id"]))

    state["closed_ids"] = closed_ids[-200:]
    state["last_apply_at"] = _now_iso()
    state["last_apply_results"] = results
    _save_state(state)

    print("📎 Todoist完了（313 digest）" + (" DRY-RUN" if dry else ""))
    for r in results:
        if r.get("ok"):
            prefix = "[dry] " if dry else ""
            print(
                f"- {prefix}closed [{r.get('kind')}] [{r.get('lane')}] "
                f"id={r.get('task_id')} {r.get('title')}"
            )
        else:
            print(f"- FAIL: {r.get('error')} / {r.get('title')}", file=sys.stderr)

    # 確認のみ一括のとき #report に短報
    if (
        not dry
        and args.auto_close_confirm
        and any(x.get("ok") for x in results)
        and not args.skip_report
    ):
        ok_lines = [
            f"- [{x.get('lane')}] {str(x.get('title') or '')[:60]}"
            for x in results
            if x.get("ok")
        ]
        report = (
            "【報告】313 完了候補確認・確認のみクローズ\n\n"
            "📌 要ボス: なし\n\n"
            + "\n".join(ok_lines)
            + "\n\n参考: 313 digest --auto-close-confirm"
        )
        _post_webhook(report, channel="report")

    if not dry and any(not x.get("ok") for x in results):
        ops = (os.environ.get("SLACK_WEBHOOK_AI_TEAM_OPS") or "").strip()
        if ops:
            msg = "【ops】313 完了候補確認 — close失敗\n" + "\n".join(
                f"- {x.get('error')}" for x in results if not x.get("ok")
            )
            try:
                urllib.request.urlopen(
                    urllib.request.Request(
                        ops,
                        data=json.dumps(
                            {"text": msg, "username": "313 完了候補確認"}
                        ).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    ),
                    timeout=20,
                )
            except Exception:
                pass

    return 0 if all(x.get("ok") for x in results) else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="313 完了候補ダイジェスト → #consult → 了承後 close")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--lanes", default=",".join(DEFAULT_LANES), help="カンマ区切り lane id")
    p.add_argument("--post-empty", action="store_true")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--select", default=None, help="了承番号（要判断の close）")
    p.add_argument(
        "--auto-close-confirm",
        action="store_true",
        help="確認のみ候補を Jarvis が complete-task",
    )
    p.add_argument("--refresh", action="store_true", help="apply前に lane を再収集")
    p.add_argument("--skip-report", action="store_true", help="auto-close 時の #report 省略")
    args = p.parse_args(argv)

    if not args.apply and os.environ.get("JARVIS_TODOIST_313_DIGEST_DISABLE", "").strip() in (
        "1",
        "true",
        "yes",
    ):
        print("📎 313 digest: disabled (JARVIS_TODOIST_313_DIGEST_DISABLE=1)")
        return 0
    if args.apply:
        return cmd_apply(args)
    return cmd_digest(args)


if __name__ == "__main__":
    raise SystemExit(main())
