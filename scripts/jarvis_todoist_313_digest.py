#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""313 完了候補ダイジェスト → Slack #consult（見るだけ）→ 了承後 close.

Phase 1: ボタンUIなし。投稿は Webhook。close は `--apply --select` /
`--auto-close-confirm`（確認のみ）。

番号は **✅N**（期日超過の 📅N と区別）。返信拾い: `jarvis_todoist_313_slack_ingest.py`。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a

  # オーナー確認列を収集＋#consult 投稿（既定）
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_313_digest.py

  # 投稿せず本文だけ
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_313_digest.py --dry-run

  # 確認のみを Jarvis 完了（コメント必須）
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_313_digest.py --apply --auto-close-confirm

  # 要判断を人了承後に close（番号はダイジェストの ✅N）
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_313_digest.py --apply --select '✅1'
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
_MAC_PY = Path("/Users/matsunomasaharu2/selenium_env/venv/bin/python")
PY = _MAC_PY if _MAC_PY.is_file() else Path(sys.executable)
JST = timezone(timedelta(hours=9))
MAX_L1 = 5
AGENT_ID = "313"
AGENT_ROLE = "完了候補確認"
ITEM_MARK = "✅"  # 期日超過は 📅（別投稿・記号で区別）
USERNAME = f"{AGENT_ID} {AGENT_ROLE}"

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


def _short_title(raw: str, width: int = 46) -> str:
    """Slack で折り返して読みにくくならないよう、タイトルを頭だけにする。"""
    t = " ".join(str(raw or "").split())
    t = re.sub(r"\s*\[[0-9a-f]{8,}\]\s*", " ", t)
    t = re.sub(r"\s*·\s*更新\s*\d{4}-\d{2}-\d{2}T\S*", "", t)
    t = t.strip(" -—·")
    if len(t) <= width:
        return t
    head = t[:width]
    for sep in ("：", "。", " — ", " - ", " "):
        i = head.rfind(sep)
        if i >= width * 0.5:
            return head[:i].rstrip("：。 -—") + "…"
    return head.rstrip() + "…"



def _parse_select_nums(select: str) -> set[int]:
    """「✅1,✅3」「閉じて ✅2」「1,3」を番号集合に。"""
    nums: set[int] = set()
    for m in re.finditer(rf"(?:{re.escape(ITEM_MARK)})?\s*(\d+)", select or ""):
        nums.add(int(m.group(1)))
    return nums


def _item_line(it: dict[str, Any]) -> str:
    """1件＝✅番号＋タイトルを Todoist リンク（タップで詳細）。"""
    title = _short_title(it.get("title"))
    task_id = str(it.get("task_id") or "")
    label = (
        f"<https://app.todoist.com/app/task/{task_id}|{title}>"
        if task_id
        else title
    )
    lane = str(it.get("lane") or "").replace("_", " ")
    return f"*{ITEM_MARK}{it['n']}.* {label}  _({lane})_"


def _format_slack(items: list[dict[str, Any]], *, note: str = "") -> str:
    confirm = [i for i in items if i.get("kind") == "confirm_only"]
    need = [i for i in items if i.get("kind") == "need_owner"]
    stamp = datetime.now(JST).strftime("%m/%d %H:%M")
    lines = [
        f"【相談】{AGENT_ID} {AGENT_ROLE}",
        f"📋 *完了候補*（{ITEM_MARK}番号・最大{MAX_L1}）",
        f"要判断 *{len(need)}件* ／ 確認のみ {len(confirm)}件 ／ {stamp}",
    ]
    if need:
        lines.extend(["", "*判断してほしいもの*", ""])
        lines.append("\n\n".join(_item_line(it) for it in need))
    if confirm:
        lines.extend(["", "*確認のみ（返事不要・閉じてOK）*", ""])
        lines.append("\n\n".join(_item_line(it) for it in confirm))
    if not items:
        lines.extend(["", "対象なし（オーナー確認は空です）"])
    lines.extend(
        [
            "",
            f"*閉じてよければ {ITEM_MARK}番号で返信（またはボタン）*",
            f"「完了する」ボタン → 1件ずつ完了（確認画面／アプリ内）",
            f"「閉じて {ITEM_MARK}1,{ITEM_MARK}3」または「{ITEM_MARK}1,3」→ 番号で完了",
            "「全部残す」→ 何もしない（次回また出ます）",
            "タイトルリンク → Todoist 詳細（リンクだけでは完了しません）",
            "※期日超過は別投稿の 📅番号（このスレでは完了のみ）",
            "",
            f"次: 人判断（閉じて {ITEM_MARK}N）",
            "",
            "担当メモ: 確認のみは自動クローズ対象・要判断は据え置き",
            "",
            "橋渡し: 新規起票は312（この係は閉じるだけ）",
        ]
    )
    if note:
        lines.extend(["", f"_{note}_"])
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
    payload = {"text": body_text, "username": USERNAME}
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

    author = (os.environ.get("TODOIST_313_AUTHOR") or "Jarvis").strip()
    out_link = f"https://app.todoist.com/app/task/{tid}"
    if kind == "confirm_only":
        head = f"【{author}】タスク完了したよ（確認のみクローズ）"
        why = "確認のみ"
    else:
        head = f"【{author}】タスク完了したよ（松野確認OK）"
        why = "了承後 close"
    comment = (
        f"{head}\n"
        f"サマリ: Todoist完了候補確認 — {why}（{reason}）: {title[:80]}\n"
        "アウトプット:\n"
        f"- [該当タスク]({out_link})\n"
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

    if not items and not args.post_empty:
        print("候補0件のため Slack 投稿をスキップ（--post-empty で強制可）")
        return 0

    # Block Kit（完了ボタン）— Bot 本線／無ければ URL ボタン＋Webhook
    try:
        from jarvis_todoist_313_slack_blocks import (  # type: ignore
            build_close_blocks,
            prefer_url_mode,
            post_slack,
        )
    except ImportError:
        sys.path.insert(0, str(REPO / "scripts"))
        from jarvis_todoist_313_slack_blocks import (  # type: ignore
            build_close_blocks,
            prefer_url_mode,
            post_slack,
        )

    url_mode = prefer_url_mode(force_url=bool(getattr(args, "url_buttons", False)))
    for it in items:
        it["title_short"] = _short_title(it.get("title"))
    payload = build_close_blocks(
        items,
        header_text="313 完了候補確認",
        fallback_text=text,
        url_mode=url_mode,
    )
    if getattr(args, "blocks_preview", False):
        print("# blocks preview url_mode=", url_mode)
        print(json.dumps(payload, ensure_ascii=False, indent=2)[:4000])
    if args.dry_run:
        print("（--dry-run: Slack 未投稿）")
        return 0
    return post_slack(
        payload,
        dry_run=False,
        force_webhook=bool(getattr(args, "force_webhook", False)),
        force_url_buttons=url_mode,
    )


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
        select = (args.select or "").strip()
        if not select:
            raise SystemExit(
                f"--select {ITEM_MARK}1,{ITEM_MARK}2 または --auto-close-confirm が必要です"
            )
        if select.lower() in ("all", "*"):
            raise SystemExit(
                "L1は一括closeしません。番号指定か --auto-close-confirm（確認のみ）を使ってください。"
            )
        nums = _parse_select_nums(select)
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

    print("📎 Todoist完了候補確認（313 digest）" + (" DRY-RUN" if dry else ""))
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
        and any(x.get("ok") for x in results)
        and not args.skip_report
    ):
        ok_lines = [
            f"- [{x.get('lane')}] {str(x.get('title') or '')[:60]}"
            for x in results
            if x.get("ok")
        ]
        mode = (
            "確認のみを閉じました"
            if args.auto_close_confirm
            else "了承（閉じて N）で閉じました"
        )
        report = (
            f"【報告】{AGENT_ID} {AGENT_ROLE}｜{mode}\n\n"
            + "\n".join(ok_lines)
            + "\n\nコメント付きで完了。次回ダイジェストから外れます"
        )
        _post_webhook(report, channel="report")

    if not dry and any(not x.get("ok") for x in results):
        ops = (os.environ.get("SLACK_WEBHOOK_AI_TEAM_OPS") or "").strip()
        if ops:
            msg = f"【ops】{AGENT_ID} {AGENT_ROLE} — close失敗\n" + "\n".join(
                f"- {x.get('error')}" for x in results if not x.get("ok")
            )
            try:
                urllib.request.urlopen(
                    urllib.request.Request(
                        ops,
                        data=json.dumps(
                            {"text": msg, "username": USERNAME}
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
    p.add_argument(
        "--select",
        default=None,
        help=f"了承番号（要判断の close。例 {ITEM_MARK}1,{ITEM_MARK}3 または 1,3）",
    )
    p.add_argument(
        "--auto-close-confirm",
        action="store_true",
        help="確認のみ候補を Jarvis が complete-task",
    )
    p.add_argument("--refresh", action="store_true", help="apply前に lane を再収集")
    p.add_argument("--skip-report", action="store_true", help="auto-close 時の #report 省略")
    p.add_argument(
        "--url-buttons",
        action="store_true",
        help="完了を URL ボタンにする（Interactivity 不要・確認画面あり）",
    )
    p.add_argument(
        "--force-webhook",
        action="store_true",
        help="Bot があっても Incoming Webhook で投稿",
    )
    p.add_argument(
        "--blocks-preview",
        action="store_true",
        help="Block Kit JSON を表示（dry-run と併用可）",
    )
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
