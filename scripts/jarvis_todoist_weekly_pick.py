#!/usr/bin/env python3
"""今週の9件（Nody /week）の材料づくりと、確定した割付の Todoist 反映。

日曜の夜に松野さんが Nody で「今週の9件」を選ぶ（2026-11-10 松野さん決定）。
- snapshot … 日曜 17:00 JST: 先週の結果・残り・候補（入口で残った話題も）を集め、
  おすすめ9件と「選ぶ理由」の案を付けて sync_meta.weekly_pick_snapshot に置く。#consult に「Nody で開く」
- reflect  … 30分ごと: Nody で確定した割付（owner_decisions surface=weekly_pick action=commit）を
  Todoist に反映する（期日を入れる／外す、入口の話題をタスクにする、やめる・AIへはコメント）。
  反映したら同じ表に action=done（target_type=weekly_commit）を足す（元の行は書き換えない）。

決まりごと:
- 確定は目の前の1週間（月・水・金の枠）。次の週は候補の順番だけ。2〜3週先は締切・支払い・行事だけ拾う。
- 外との約束・行事・支払いの期日（hard）は外さない。
- 312 はタスクを閉じない（「やめる」はコメントだけ残し、片付けは 313）。
- AI が作るタスクには 🦾依頼 を付ける（jarvis_todoist_mark）。

試す: python3 scripts/jarvis_todoist_weekly_pick.py --mode snapshot --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from jarvis_todoist_mark import AI_MARK, REQUESTED_MARK, mark_title, strip_mark  # noqa: E402

JST = timezone(timedelta(hours=9))
SURFACE = "weekly_pick"
SNAPSHOT_KEY = "weekly_pick_snapshot"
PICK_DAYS = (0, 2, 4)  # 月・水・金
PER_DAY = 3
RULE_VERSION = "rule-v1"  # おすすめと理由をルールで作った版。AI に替えたら上げる

PARTNER_LABELS = {"properties", "Tcell", "kamiooya", "キャラメル", "GrandoleI", "ミニテック", "kodate"}
FAMILY_LABELS = {"kazoku", "family"}
MONEY_RE = re.compile(r"(振込|支払|引落|請求|入金|返済|融資|保険|見積)")
HARD_RE = re.compile(r"(期限|締切|〆切|振込|支払|引落|説明会|入試|行事|参加証|更新前)")
OWNER_HINT_RE = re.compile(r"(\[要ボス\]|\[要判断\]|\[メール要対応\]|\[資料待ち\]|【松野さん】|ボス実施|ボスが)")
SKIP_RE = re.compile(r"\[要フォロー\]")
# 土日祝はエージェントの自動化を進める日（松野さん 2026-11-12）。この日付に置いた自動化タスクは
# 週次ピックの候補にも日付消しにも入れない。祝日は Todoist 側で土日同様に置く運用。
AGENT_RE = re.compile(r"(\[自律化\]|自動化|エージェント作成)")

PICK_TEXT = {
    "deadline": "締切まであと{n}日",
    "overdue": "締切を{n}日過ぎている",
    "waiting_other": "相手を{n}日待たせている",
    "partner_money": "パートナー・お金の仕事なので週の頭に",
    "carried": "{n}週残っているので、分けてでも進める",
    "small": "小さくてすぐ終わる",
    "interest": "興味・勢いがある",
    "inlet": "入口で{n}日待っている",
    "planned": "前の週の見通しでこの週に置いていた",
}


# ---- 日付 --------------------------------------------------------------------


def target_monday(today: date) -> date:
    """割り付ける週の月曜。月曜ならその日、ほかは次の月曜（日曜夜→翌日）。"""
    return today if today.weekday() == 0 else today + timedelta(days=7 - today.weekday())


def pick_dates(monday: date) -> list[str]:
    return [(monday + timedelta(days=d)).isoformat() for d in PICK_DAYS]


def _d(s: Any) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def due_of(t: dict[str, Any]) -> date | None:
    return _d((t.get("due") or {}).get("date"))


def deadline_of(t: dict[str, Any]) -> date | None:
    return _d((t.get("deadline") or {}).get("date"))


# ---- 判定（ルール） ----------------------------------------------------------


def is_owner_task(t: dict[str, Any]) -> bool:
    """松野さんが自分で動くタスクか。🤖（AIが進める）と監視の通知・子タスクは外す。"""
    if t.get("checked") or t.get("is_deleted"):
        return False
    if t.get("parent_id"):
        return False
    content = t.get("content") or ""
    if SKIP_RE.search(content):
        return False
    du = due_of(t)
    if du and du.weekday() >= 5 and AGENT_RE.search(content):
        return False  # 土日のエージェント自動化枠
    labels = set(t.get("labels") or [])
    if content.lstrip().startswith(AI_MARK):
        return "要ボス" in labels or bool(OWNER_HINT_RE.search(content))
    return True  # 印なし（本人）と 🦾依頼


def is_hard(t: dict[str, Any]) -> bool:
    """外との約束・行事・支払いの日付。週次で外さない。"""
    if deadline_of(t):
        return True
    labels = set(t.get("labels") or [])
    title = strip_mark(t.get("content") or "")
    return bool(due_of(t) and (labels & FAMILY_LABELS or HARD_RE.search(title)))


def _days_between(a: date, b: date) -> int:
    return (b - a).days


def reasons_for(
    t: dict[str, Any], *, today: date, weeks_carried: int, week: tuple[date, date] | None = None
) -> tuple[int, list[dict[str, str]]]:
    """点数と「選ぶ理由」の案（多い順に最大3つ）。"""
    labels = set(t.get("labels") or [])
    title = strip_mark(t.get("content") or "")
    cands: list[tuple[int, str, int]] = []  # (点, tag, n)

    limit = deadline_of(t) or (due_of(t) if is_hard(t) else None)
    if limit:
        left = _days_between(today, limit)
        if left < 0:
            cands.append((60, "overdue", -left))
        elif left <= 14:  # それより先は「2〜3週先の動かせない日付」で見る
            cands.append((max(60 - left * 4, 12), "deadline", left))
    du = due_of(t)
    if week and du and week[0] <= du <= week[1] and not limit:
        cands.append((30, "planned", 0))
    if weeks_carried:
        cands.append((25 + 10 * weeks_carried, "carried", weeks_carried))
    added = _d(t.get("added_at"))
    waiting = "[メール要対応]" in title or "返信待ち" in labels or "資料待ち" in labels or "返信" in title
    if waiting and added:
        n = max(_days_between(added, today), 0)
        cands.append((min(n, 30) + 10, "waiting_other", n))
    if labels & PARTNER_LABELS or MONEY_RE.search(title) or "[メール要対応]" in title:
        cands.append((20, "partner_money", 0))
    if "quick" in labels:
        cands.append((8, "small", 0))

    pri = {4: 25, 3: 15, 2: 5}.get(int(t.get("priority") or 1), 0)  # API の 4 = p1
    score = pri + sum(c[0] for c in cands)
    cands.sort(key=lambda c: -c[0])
    # 理由タグは契約の語に寄せる（過ぎている＝締切）
    out = [{"tag": "deadline" if tag == "overdue" else tag, "text": PICK_TEXT[tag].format(n=n)} for _, tag, n in cands[:3]]
    return score, out


def candidate(
    t: dict[str, Any], *, today: date, weeks_carried: int, left_from_last: bool, week: tuple[date, date] | None = None
) -> dict[str, Any]:
    score, reasons = reasons_for(t, today=today, weeks_carried=weeks_carried, week=week)
    due, dl = due_of(t), deadline_of(t)
    return {
        "kind": "task",
        "id": str(t["id"]),
        "title": strip_mark(t.get("content") or ""),
        "mark": "ai" if (t.get("content") or "").lstrip().startswith(AI_MARK)
        else "requested" if (t.get("content") or "").lstrip().startswith(REQUESTED_MARK) else "none",
        "labels": t.get("labels") or [],
        "priority": {4: "p1", 3: "p2", 2: "p3"}.get(int(t.get("priority") or 1), "p4"),
        "due": due.isoformat() if due else None,
        "deadline": dl.isoformat() if dl else None,
        "hard": is_hard(t),
        "left_from_last": left_from_last,
        "weeks_carried": weeks_carried,
        "score": score,
        "reasons": reasons,
        "url": f"https://app.todoist.com/app/task/{t['id']}",
    }


def recommend(cands: list[dict[str, Any]], days: list[str], per_day: int = PER_DAY) -> list[dict[str, str]]:
    """上から per_day×日数 件を曜日に置く。締切がある物はその前の日に、パートナー・お金は月曜に寄せる。"""
    slots: dict[str, list[str]] = {d: [] for d in days}
    picked = [c for c in cands if c["kind"] == "task"][: per_day * len(days)]

    def place(c: dict[str, Any], prefer: list[str]) -> None:
        for d in prefer:
            if len(slots[d]) < per_day:
                slots[d].append(c["id"])
                return

    limit_first = sorted(picked, key=lambda c: (c.get("deadline") or (c["due"] if c["hard"] else None) or "9999"))
    for c in limit_first:
        lim = c.get("deadline") or (c["due"] if c["hard"] else None)
        tags = {r["tag"] for r in c["reasons"]}
        if lim:
            before = [d for d in days if d <= lim] or days[:1]
            place(c, before + [d for d in days if d not in before])
        elif "partner_money" in tags or "waiting_other" in tags:
            place(c, days)
        else:
            place(c, list(reversed(days)) if "small" not in tags else days)
    return [{"id": i, "day": d} for d in days for i in slots[d]]


def inlet_candidate(topic: dict[str, Any], *, today: date) -> dict[str, Any]:
    created = _d(topic.get("created_at")) or today
    n = max(_days_between(created, today), 0)
    text = (topic.get("topic_text") or "").strip()
    return {
        "kind": "inlet",
        "id": str(topic["id"]),
        "title": text.splitlines()[0][:80] if text else "(お題)",
        "body": text[:400],
        "source_ref": topic.get("source_ref"),
        "waited_days": n,
        "score": 10 + min(n, 20),
        "reasons": [{"tag": "inlet", "text": PICK_TEXT["inlet"].format(n=n)}],
    }


def build_snapshot(
    *,
    tasks: list[dict[str, Any]],
    completed_last_week: list[dict[str, Any]],
    pick_history: dict[str, int],
    inlet_topics: list[dict[str, Any]],
    today: date,
    now: datetime,
) -> dict[str, Any]:
    monday = target_monday(today)
    days = pick_dates(monday)
    prev_mon = monday - timedelta(days=7)
    owner = [t for t in tasks if is_owner_task(t)]

    left_ids: set[str] = set()
    for t in owner:
        du = due_of(t)
        if du and du < monday:
            left_ids.add(str(t["id"]))

    cands = [
        candidate(t, today=today, weeks_carried=pick_history.get(str(t["id"]), 0), left_from_last=str(t["id"]) in left_ids,
                  week=(monday, monday + timedelta(days=6)))
        for t in owner
    ]
    cands.sort(key=lambda c: (-c["score"], c["title"]))
    inlet = sorted((inlet_candidate(x, today=today) for x in inlet_topics), key=lambda c: -c["score"])

    rec = recommend(cands, days)
    rec_ids = {r["id"] for r in rec}
    next_preview = [c["id"] for c in cands if c["id"] not in rec_ids][:9]

    week_end = monday + timedelta(days=6)
    dated_in_week = [
        {"id": c["id"], "title": c["title"], "date": c["due"], "hard": c["hard"]}
        for c in cands
        if c["due"] and monday.isoformat() <= c["due"] <= week_end.isoformat()
    ]
    ahead_from, ahead_to = week_end + timedelta(days=1), week_end + timedelta(days=21)
    hard_ahead = []
    for t in owner:
        lim = deadline_of(t) or (due_of(t) if is_hard(t) else None)
        if lim and ahead_from <= lim <= ahead_to:
            hard_ahead.append({"id": str(t["id"]), "title": strip_mark(t.get("content") or ""), "date": lim.isoformat()})
    hard_ahead.sort(key=lambda x: x["date"])

    added_last = sum(1 for t in owner if (_d(t.get("added_at")) or date.min) >= prev_mon)
    return {
        "v": 1,
        "rule_version": RULE_VERSION,
        "generated_at": now.isoformat(timespec="seconds"),
        "week": monday.isoformat(),
        "days": days,
        "per_day": PER_DAY,
        "last": {
            "week": prev_mon.isoformat(),
            "done": len(completed_last_week),
            "done_titles": [strip_mark(x.get("content") or "")[:60] for x in completed_last_week][:20],
            "left": len(left_ids),
            "added": added_last,
            "owner_open": len(owner),
        },
        "candidates": cands[:60],
        "inlet": inlet[:15],
        "recommended": rec,
        "next_preview": next_preview,
        "dated_in_week": dated_in_week,
        "hard_ahead": hard_ahead[:20],
    }


def plan_ops(plan: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """確定した割付 → Todoist への操作の並び（純粋。テスト用）。"""
    ops: list[tuple[str, dict[str, Any]]] = []
    for x in plan.get("set_due") or []:
        if x.get("id") and _d(x.get("date")):
            ops.append(("set_due", {"id": str(x["id"]), "date": str(x["date"])[:10]}))
    for i in plan.get("clear_due") or []:
        ops.append(("clear_due", {"id": str(i)}))
    for x in plan.get("notes") or []:
        if x.get("id") and x.get("text"):
            ops.append(("comment", {"id": str(x["id"]), "text": str(x["text"])[:1000]}))
    for x in plan.get("inlet") or []:
        if x.get("topic_id") and x.get("title"):
            ops.append(("inlet", {"topic_id": str(x["topic_id"]), "title": str(x["title"])[:200],
                                  "date": (str(x["date"])[:10] if _d(x.get("date")) else None),
                                  "source_ref": x.get("source_ref")}))
    for x in plan.get("inlet_skip") or []:
        ops.append(("inlet_skip", {"topic_id": str(x)}))
    return ops


# ---- 外部 API（312 collect と同じ部品） --------------------------------------


def _io():
    import jarvis_todoist_312_collect as c  # noqa: PLC0415

    return c


def completed_between(since: date, until: date) -> list[dict[str, Any]]:
    c = _io()
    q = urllib.parse.urlencode({"since": f"{since.isoformat()}T00:00:00", "until": f"{until.isoformat()}T23:59:59", "limit": 200})
    try:
        data = c.todoist(f"tasks/completed/by_due_date?{q}") or {}
    except urllib.error.HTTPError as e:
        print(f"::warning::completed by_due_date: HTTP {e.code}")
        return []
    items = data.get("items") or data.get("results") or []
    return [x for x in items if is_owner_task({**x, "checked": False})]


def pick_counts() -> dict[str, int]:
    """これまで何週「今週やる」に置かれたか（残り続けの目安）。"""
    c = _io()
    rows = c.sb("owner_decisions", params={
        "select": "target_id,payload", "surface": f"eq.{SURFACE}", "action": "eq.pick",
        "target_type": "eq.todoist_task", "order": "decided_at.desc", "limit": "2000",
    }) or []
    seen: dict[str, set[str]] = {}
    for r in rows:
        wk = str((r.get("payload") or {}).get("week") or "")
        seen.setdefault(str(r["target_id"]), set()).add(wk)
    return {k: len(v) for k, v in seen.items()}


def open_inlet_topics() -> list[dict[str, Any]]:
    c = _io()
    return c.sb("task_loop_topics", params={
        "select": "id,topic_text,source_ref,created_at,status", "status": "eq.open",
        "source_kind": "eq.slack", "order": "created_at.asc", "limit": "30",
    }) or []


def put_snapshot(snap: dict[str, Any]) -> None:
    c = _io()
    c.sb("sync_meta", params={"on_conflict": "key"}, method="POST", prefer="resolution=merge-duplicates,return=minimal", body={
        "key": SNAPSHOT_KEY, "value": json.dumps(snap, ensure_ascii=False), "updated_at": datetime.now(JST).isoformat(),
    })


def snapshot(*, dry: bool, now: datetime, notify: bool) -> int:
    c = _io()
    today = now.date()
    monday = target_monday(today)
    tasks = c.active_tasks()
    done = completed_between(monday - timedelta(days=7), monday - timedelta(days=1))
    snap = build_snapshot(
        tasks=tasks, completed_last_week=done, pick_history=pick_counts(),
        inlet_topics=open_inlet_topics(), today=today, now=now,
    )
    last = snap["last"]
    print(f"週 {snap['week']}: 候補 {len(snap['candidates'])} 件（入口 {len(snap['inlet'])}）、おすすめ {len(snap['recommended'])} 件、"
          f"先週 完了 {last['done']}／残り {last['left']}／追加 {last['added']}")
    if dry:
        print(json.dumps({k: snap[k] for k in ("week", "days", "last", "recommended", "hard_ahead")}, ensure_ascii=False, indent=1))
        return 0
    put_snapshot(snap)
    if notify:
        url = c.nody_url("/week", now)
        text = (
            f"🟡 *今週の9件を選ぶ準備ができました*（{snap['week']} の週）\n"
            f"先週: 完了 {last['done']} 件／残り {last['left']} 件／追加 {last['added']} 件。松野さん対応の残り {last['owner_open']} 件\n"
            f"残った理由を選んでから、おすすめ9件を直して月・水・金に置いてください。\n<{url}|Nody で開く>"
        )
        c.post_consult(text, dry=False)
    return 0


def _todoist_update(task_id: str, body: dict[str, Any]) -> None:
    _io().todoist(f"tasks/{task_id}", method="POST", body=body)


def apply_ops(ops: list[tuple[str, dict[str, Any]]], *, week: str, dry: bool) -> dict[str, int]:
    c = _io()
    n = {"set_due": 0, "clear_due": 0, "comment": 0, "inlet": 0, "inlet_skip": 0, "failed": 0}
    for kind, x in ops:
        try:
            if dry:
                print(f"dry: {kind} {json.dumps(x, ensure_ascii=False)}")
            elif kind == "set_due":
                _todoist_update(x["id"], {"due_date": x["date"]})
            elif kind == "clear_due":
                _todoist_update(x["id"], {"due_string": "no date"})
            elif kind == "comment":
                c.todoist("comments", method="POST", body={"task_id": x["id"], "content": f"【Jarvis】\nサマリ: {x['text']}\nアウトプット:\n- 今週の9件（{week} の週）"})
            elif kind == "inlet":
                task: dict[str, Any] = {"content": mark_title(f"[312] {x['title']}", requested=True), "labels": ["312"],
                                        "description": f"今週の9件（{week} の週）で入口から入れた。\n出典: {x.get('source_ref') or '-'}"}
                if x.get("date"):
                    task["due_date"] = x["date"]
                created = c.todoist("tasks", method="POST", body=task) or {}
                c.sb("task_loop_topics", params={"id": f"eq.{x['topic_id']}"}, method="PATCH", prefer="return=minimal",
                     body={"status": "decided", "todoist_task_ids": [str(created.get("id") or "")] if created.get("id") else []})
            elif kind == "inlet_skip":
                c.sb("task_loop_topics", params={"id": f"eq.{x['topic_id']}"}, method="PATCH", prefer="return=minimal", body={"status": "decided"})
            n[kind] += 1
        except urllib.error.HTTPError as e:
            n["failed"] += 1
            print(f"::warning::{kind} {x}: HTTP {e.code} {e.read().decode(errors='replace')[:200]}")
    return n


def reflect(*, dry: bool, now: datetime) -> int:
    from jarvis_owner_decision_log import contract_row  # noqa: PLC0415

    c = _io()
    since = (now - timedelta(days=14)).isoformat()
    commits = c.sb("owner_decisions", params={
        "select": "id,decided_at,target_id,payload", "surface": f"eq.{SURFACE}", "action": "eq.commit",
        "decided_at": f"gte.{since}", "order": "decided_at.asc", "limit": "50",
    }) or []
    if not commits:
        print("weekly reflect: 反映待ちなし")
        return 0
    applied = {
        str(r["target_id"])
        for r in c.sb("owner_decisions", params={
            "select": "target_id", "surface": f"eq.{SURFACE}", "action": "eq.done",
            "target_type": "eq.weekly_commit", "decided_at": f"gte.{since}", "limit": "200",
        }) or []
    }
    latest: dict[str, dict[str, Any]] = {}
    for r in commits:
        latest[str(r["target_id"])] = r  # 同じ週を確定し直したら最後の1つだけ反映
    for r in commits:
        cid = str(r["id"])
        if cid in applied:
            continue
        week = str(r["target_id"])
        superseded = latest[week]["id"] != r["id"]
        result = {"superseded": True} if superseded else apply_ops(plan_ops((r.get("payload") or {}).get("plan") or {}), week=week, dry=dry)
        print(f"weekly reflect: commit {cid}（{week}）→ {result}")
        if dry:
            continue
        row = contract_row(surface=SURFACE, action="done", source="script_weekly_pick", target_type="weekly_commit",
                           target_id=cid, employee="312", payload={"week": week, "result": result}, idem_key=f"weekly_pick_applied:{cid}")
        c.sb("owner_decisions", method="POST", body=row, prefer="return=minimal")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mode", choices=["snapshot", "reflect"], default="snapshot")
    ap.add_argument("--dry-run", action="store_true", help="DB・Todoist に書かず Slack に出さない")
    ap.add_argument("--no-notify", action="store_true", help="snapshot で #consult に出さない")
    a = ap.parse_args(argv)
    need = ["JARVIS_SUPABASE_URL", "JARVIS_SUPABASE_SERVICE_ROLE_KEY", "TODOIST_API_TOKEN"]
    miss = [k for k in need if not os.environ.get(k)]
    if miss:
        print("未設定: " + ", ".join(miss), file=sys.stderr)
        return 2
    now = datetime.now(JST)
    try:
        if a.mode == "reflect":
            return reflect(dry=a.dry_run, now=now)
        return snapshot(dry=a.dry_run, now=now, notify=not a.no_notify)
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode(errors='replace')[:300]}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
