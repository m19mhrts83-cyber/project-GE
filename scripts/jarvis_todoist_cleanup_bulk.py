#!/usr/bin/env python3
"""Todoist の片付けを Nody（/313/bulk）でまとめて判断する材料づくりと反映（313 の出口）。

背景（松野さん 2026-11-17）: スター付きメール由来のタスクが Todoist に大量に流れ込んだ。
メールの判断デスクと同じように、まとめて「完了／日を変える／残す／削除」を選びたい。

- snapshot … 片付け候補を集め、おすすめ（完了・削除・残す）と理由を付けて
  sync_meta.todoist_cleanup_snapshot に置く。
- reflect  … Nody で確定した判断（owner_decisions surface=todoist_313, payload.bulk=true）を Todoist に反映。
  反映したら action=done（target_type=cleanup_apply）を足す（元の行は書き換えない）。反映後に snapshot も更新。

決まりごと:
- 勝手に閉じない。完了・削除は松野さんが選んだものだけ（おすすめは初期値で、選ばなければ何もしない）。
- 「残す」は14日間は候補から外す。日を変えたものは新しい日が来るまで外れる。
- 対象は CLEAN_LABELS のラベルが付いた未完了タスク（まずスター起票）。足すときはここに足す。

試す: python3 scripts/jarvis_todoist_cleanup_bulk.py --mode snapshot --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

JST = timezone(timedelta(hours=9))
SURFACE = "todoist_313"
SNAPSHOT_KEY = "todoist_cleanup_snapshot"
CLEAN_LABELS = {"スター起票"}
HOLD_DAYS = 14
MAX_CARDS = 120

PROMO_RE = re.compile(r"(セミナー|キャンペーン|イベント案内|おすすめイベント|新製品|特典|優待|ポイント|紹介|ご案内|応募|アンケート|動画)")
MONEY_RE = re.compile(r"(入金|着金|送金|振込|支払|納付|引落|請求)")
REPLY_RE = re.compile(r"(返信|回答|連絡|依頼|提出|再提出|設定|登録)")
PAST_RE = re.compile(r"経過済み")


def _io():
    import jarvis_todoist_312_collect as c  # noqa: PLC0415

    return c


def _d(s: Any) -> date | None:
    try:
        return date.fromisoformat(str(s)[:10]) if s else None
    except ValueError:
        return None


def parse_description(desc: str) -> dict[str, str]:
    """スター起票のタスク説明（送信者／件名／日付／要件／URL）を読む。"""
    out = {"sender": "", "subject": "", "mail_date": "", "summary": "", "gmail_url": ""}
    for line in (desc or "").splitlines():
        for key, label in (("sender", "送信者："), ("subject", "件名："), ("mail_date", "日付："), ("summary", "要件：")):
            if line.startswith(label):
                out[key] = line[len(label):].strip()
        if line.startswith("https://mail.google.com/"):
            out["gmail_url"] = line.strip()
    return out


def suggest(title: str, info: dict[str, str]) -> tuple[str, str]:
    """おすすめ（close / drop / keep）と理由。初期値で、松野さんが直す。"""
    text = f"{title} {info.get('subject', '')} {info.get('summary', '')}"
    if MONEY_RE.search(text) or REPLY_RE.search(info.get("summary", "") + title):
        if PAST_RE.search(text):
            return "close", "期限や開催日が過ぎている。済んでいれば完了"
        return "keep", "お金・返信・手続きの動きがある"
    if PAST_RE.search(text):
        return "close", "期限や開催日が過ぎている"
    if PROMO_RE.search(text):
        return "drop", "案内・特典・紹介の類。急がない"
    return "keep", "中身を見て判断"


def card(t: dict[str, Any], *, today: date) -> dict[str, Any]:
    info = parse_description(t.get("description") or "")
    title = str(t.get("content") or "")
    rec, why = suggest(title, info)
    md = _d(info["mail_date"])
    due = _d((t.get("due") or {}).get("date"))
    return {
        "id": str(t["id"]),
        "title": title,
        **info,
        "due": due.isoformat() if due else None,
        "added_at": str(t.get("added_at") or "")[:10],
        "age_days": (today - md).days if md else None,
        "suggest": rec,
        "why": why,
        "priority": t.get("priority"),
    }


def build_snapshot(*, tasks: list[dict[str, Any]], held: set[str], today: date, now: datetime) -> dict[str, Any]:
    cards: list[dict[str, Any]] = []
    for t in tasks:
        if t.get("checked") or t.get("is_deleted") or t.get("parent_id"):
            continue
        if not (set(t.get("labels") or []) & CLEAN_LABELS):
            continue
        if str(t["id"]) in held:
            continue
        due = _d((t.get("due") or {}).get("date"))
        if due and due > today:
            continue  # 日を変えたものは、その日が来るまで出さない
        cards.append(card(t, today=today))
    order = {"close": 0, "drop": 1, "keep": 2}
    cards.sort(key=lambda c: (order[c["suggest"]], -(c["age_days"] or 0)))
    return {
        "v": 1,
        "generated_at": now.isoformat(timespec="seconds"),
        "labels": sorted(CLEAN_LABELS),
        "total": len(cards),
        "cards": cards[:MAX_CARDS],
    }


def held_ids(now: datetime) -> set[str]:
    """最近「残す」を選んだタスク（候補から外す）。"""
    c = _io()
    since = (now - timedelta(days=HOLD_DAYS)).isoformat()
    rows = c.sb("owner_decisions", params={
        "select": "target_id", "surface": f"eq.{SURFACE}", "action": "eq.defer",
        "target_type": "eq.todoist_task", "decided_at": f"gte.{since}", "limit": "2000",
    }) or []
    return {str(r["target_id"]) for r in rows}


def tasks_by_label() -> list[dict[str, Any]]:
    import urllib.parse  # noqa: PLC0415

    c = _io()
    rows: list[dict[str, Any]] = []
    for label in sorted(CLEAN_LABELS):
        cursor = None
        for _ in range(10):
            path = f"tasks?label={urllib.parse.quote(label)}&limit=200" + (f"&cursor={urllib.parse.quote(cursor)}" if cursor else "")
            data = c.todoist(path) or {}
            rows.extend(data.get("results") or [])
            cursor = data.get("next_cursor")
            if not cursor:
                break
    return rows


def put_snapshot(snap: dict[str, Any]) -> None:
    c = _io()
    c.sb("sync_meta", params={"on_conflict": "key"}, method="POST", prefer="resolution=merge-duplicates,return=minimal", body={
        "key": SNAPSHOT_KEY, "value": json.dumps(snap, ensure_ascii=False), "updated_at": datetime.now(JST).isoformat(),
    })


def snapshot(*, dry: bool, now: datetime) -> int:
    c = _io()
    tasks = c.active_tasks()
    labelled = [t for t in tasks if set(t.get("labels") or []) & CLEAN_LABELS]
    print(f"Todoist から {len(tasks)} 件取得、対象ラベル付き {len(labelled)} 件、プロジェクト {len({t.get('project_id') for t in tasks})} 個")
    if not labelled:
        # 一覧に出てこないときはラベルで直接引く（取り方の違いか、見えるアカウントの違いかを切り分ける）
        by_label = tasks_by_label()
        print(f"ラベルで直接取得 {len(by_label)} 件")
        have = {str(t["id"]) for t in tasks}
        tasks = tasks + [t for t in by_label if str(t["id"]) not in have]
    snap = build_snapshot(tasks=tasks, held=held_ids(now), today=now.date(), now=now)
    by: dict[str, int] = {}
    for x in snap["cards"]:
        by[x["suggest"]] = by.get(x["suggest"], 0) + 1
    print(f"片付け候補 {snap['total']} 件（表示 {len(snap['cards'])}）: {by}")
    if dry:
        for x in snap["cards"][:8]:
            print(f"  [{x['suggest']}] {x['title'][:40]}｜{x['why']}")
        return 0
    put_snapshot(snap)
    return 0


def apply_one(row: dict[str, Any], *, dry: bool) -> str:
    """1件を Todoist に反映。戻り値は結果（ok / gone / failed:…）。"""
    c = _io()
    tid = str(row["target_id"])
    action = row["action"]
    due = (row.get("payload") or {}).get("due")
    if dry:
        print(f"dry: {action} {tid} {due or ''}")
        return "dry"
    try:
        if action == "close":
            c.todoist(f"tasks/{tid}/close", method="POST")
        elif action == "drop":
            c.todoist(f"tasks/{tid}", method="DELETE")
        elif action == "reschedule":
            body = {"due_date": due} if due else {"due_string": "no date"}
            c.todoist(f"tasks/{tid}", method="POST", body=body)
        else:
            return "skip"
        return "ok"
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return "gone"  # もう無い（別の場所で片付いた）
        print(f"::warning::{action} {tid}: HTTP {e.code} {e.read().decode(errors='replace')[:200]}")
        return f"failed:{e.code}"


def reflect(*, dry: bool, now: datetime) -> int:
    from jarvis_owner_decision_log import contract_row  # noqa: PLC0415

    c = _io()
    since = (now - timedelta(days=HOLD_DAYS)).isoformat()
    rows = c.sb("owner_decisions", params={
        "select": "id,action,target_id,subject,payload,decided_at", "surface": f"eq.{SURFACE}",
        "target_type": "eq.todoist_task", "action": "in.(close,drop,reschedule)",
        "decided_at": f"gte.{since}", "order": "decided_at.asc", "limit": "500",
    }) or []
    rows = [r for r in rows if (r.get("payload") or {}).get("bulk")]
    done_ids = {
        str(r["target_id"])
        for r in c.sb("owner_decisions", params={
            "select": "target_id", "surface": f"eq.{SURFACE}", "action": "eq.done",
            "target_type": "eq.cleanup_apply", "decided_at": f"gte.{since}", "limit": "2000",
        }) or []
    }
    todo = [r for r in rows if str(r["id"]) not in done_ids]
    # 同じタスクを続けて選び直したら最後の1つだけ反映
    last: dict[str, str] = {}
    for r in todo:
        last[str(r["target_id"])] = str(r["id"])
    n = {"ok": 0, "gone": 0, "failed": 0, "superseded": 0}
    by_action = {"close": 0, "drop": 0, "reschedule": 0}
    for r in todo:
        rid = str(r["id"])
        if last[str(r["target_id"])] != rid:
            res = "superseded"
        else:
            res = apply_one(r, dry=dry)
        key = "failed" if res.startswith("failed") else ("superseded" if res == "superseded" else ("gone" if res == "gone" else "ok"))
        n[key] += 1
        if key == "ok" and not dry:
            by_action[r["action"]] += 1
        if dry or res.startswith("failed"):
            continue  # 失敗は次回また試す
        c.sb("owner_decisions", method="POST", prefer="return=minimal", body=contract_row(
            surface=SURFACE, action="done", source="script_todoist_cleanup", target_type="cleanup_apply",
            target_id=rid, employee="313", payload={"task_id": str(r["target_id"]), "applied": r["action"], "result": res},
            idem_key=f"todoist_cleanup_applied:{rid}",
        ))
    print(f"cleanup reflect: 待ち {len(todo)} 件 → {n}")
    if todo and not dry:
        snapshot(dry=False, now=now)
        if n["ok"]:
            c.post_consult(
                f"{'🟡' if n['failed'] else '🟢'} *Todoist の片付けを反映しました*\n"
                f"完了 {by_action['close']}／削除 {by_action['drop']}／日を変更 {by_action['reschedule']}"
                + (f"／失敗 {n['failed']}（次回また試します）" if n["failed"] else ""),
                dry=False,
            )
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mode", choices=["snapshot", "reflect"], default="snapshot")
    ap.add_argument("--dry-run", action="store_true", help="DB・Todoist・Slack に書かない")
    a = ap.parse_args(argv)
    need = ["JARVIS_SUPABASE_URL", "JARVIS_SUPABASE_SERVICE_ROLE_KEY", "TODOIST_API_TOKEN"]
    miss = [k for k in need if not os.environ.get(k)]
    if miss:
        print("未設定: " + ", ".join(miss), file=sys.stderr)
        return 2
    now = datetime.now(JST)
    try:
        return reflect(dry=a.dry_run, now=now) if a.mode == "reflect" else snapshot(dry=a.dry_run, now=now)
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode(errors='replace')[:300]}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
