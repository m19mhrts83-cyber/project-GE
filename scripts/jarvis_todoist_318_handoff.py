#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""318 Todoist消化係 Phase 2 の部品 — ②を /313/bulk へ、③を 312「今週の9件」へ、本人回答の取り込み、通知・報告の案.

FlowForge flow_HMy15MUxWiSpw5QgAPYa_8e4 のノード対応:
- node_human_review（/313/bulk で判断）… build_bulk_cards → sync_meta.todoist_318_bulk_queue
    既存の scripts/jarvis_todoist_cleanup_bulk.py（GHA 30分ごと）が snapshot に混ぜて画面に出す。
    松野さんの選択は既存どおり owner_decisions（surface=todoist_313, target_type=todoist_task）に残る。
    → fetch_owner_answers で読み戻し、318 の判断履歴へ入れて次回に再判定する。
- ③本人作業 … build_weekly_handoff → sync_meta.todoist_318_weekly_handoff
    既存の scripts/jarvis_todoist_weekly_pick.py（日曜 snapshot）が候補に入れ、理由「318: 本人の操作が要る」を付ける。
- node_znkxTG8H（#consult 通知）／end（#ai-hub 報告）… consult_text／hub_report_text（案。送るのはフラグを付けた時だけ）

313 との二重質問の防止（同じタスクは片方だけ）:
- 313 の 20:00 片付けが直近 36 時間に出した件は、318 は /313/bulk に載せない（313 の質問中）
- 318 が /313/bulk に載せた（published=true の）件は、313 の片付けが出さない（jarvis_todoist_313_cleanup.collect_items）
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

QUEUE_KEY = "todoist_318_bulk_queue"
HANDOFF_KEY = "todoist_318_weekly_handoff"
ANSWER_SURFACE = "todoist_313"
ANSWER_DAYS = 30  # この日数以内の本人回答を読む
ASKED_313_HOURS = 36  # 313 の片付けがこの時間内に出した件は 318 から聞かない
QUEUE_STALE_DAYS = 3  # cleanup_bulk 側: これより古いキューは 318 が止まったとみなして出さない
HANDOFF_STALE_DAYS = 8  # weekly_pick 側: 週をまたいだ古い受け渡しは使わない
BULK_PATH = "/313/bulk"
HANDOFF_REASON_TAG = "handoff_318"
HANDOFF_REASON_TEXT = "318: 本人の操作が要る"
ACTION_TEXT = {"close": "完了", "drop": "削除", "reschedule": "日を変える", "defer": "残す", "keep": "残す"}

SbFn = Callable[..., Any]


# ---------------------------------------------------------------------------
# 本人回答（owner_decisions）
# ---------------------------------------------------------------------------


def fetch_owner_answers(sb: SbFn, now: datetime) -> dict[str, dict[str, str]]:
    """surface=todoist_313 のタスク判断（/313/bulk・20:00 のボタン）を task_id ごとに最新1件。

    読めなければ例外のまま上げる（呼び出し側で安全停止。読取失敗を「回答なし」と扱わない）。
    """
    since = (now - timedelta(days=ANSWER_DAYS)).isoformat()
    rows = sb(
        "owner_decisions",
        params={
            "select": "id,action,target_id,decided_at",
            "surface": f"eq.{ANSWER_SURFACE}",
            "target_type": "eq.todoist_task",
            "decided_at": f"gte.{since}",
            "order": "decided_at.asc",
            "limit": "2000",
        },
    )
    if not isinstance(rows, list):
        raise ValueError("owner_decisions の応答の形が想定外")
    out: dict[str, dict[str, str]] = {}
    for r in rows:
        tid = str(r.get("target_id") or "")
        if not tid:
            continue
        out[tid] = {
            "action": str(r.get("action") or ""),
            "decided_at": str(r.get("decided_at") or ""),
            "decision_id": str(r.get("id") or ""),
        }
    return out


# ---------------------------------------------------------------------------
# 313 の 20:00 片付けとの重なり
# ---------------------------------------------------------------------------


def asked_by_313(path: Path, now: datetime) -> set[str] | None:
    """313 の片付けが直近に出した task_id。ファイルが無い＝出していない（空集合）。壊れている＝分からない（None）。"""
    if not path.is_file():
        return set()
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        at = datetime.fromisoformat(str(d.get("at") or ""))
    except Exception:  # noqa: BLE001
        return None
    if at.tzinfo is None:
        at = at.replace(tzinfo=now.tzinfo)
    if now - at > timedelta(hours=ASKED_313_HOURS):
        return set()
    return {str(x.get("task_id")) for x in (d.get("items") or []) if isinstance(x, dict) and x.get("task_id")}


def published_queue_ids(path: Path) -> set[str]:
    """313 片付け側で使う: 318 が /313/bulk に実際に載せた件。無い・壊れている・未公開なら空。"""
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return set()
    if not d.get("published"):
        return set()
    return {str(c.get("id")) for c in (d.get("cards") or []) if isinstance(c, dict) and c.get("id")}


# ---------------------------------------------------------------------------
# ② → /313/bulk のカード、③ → 今週の9件 の受け渡し
# ---------------------------------------------------------------------------


def _prev_text(row: dict[str, Any]) -> str:
    ans = row.get("owner_answer") or {}
    if not ans.get("action"):
        return ""
    return f"前回: {ACTION_TEXT.get(ans['action'], ans['action'])}（{str(ans.get('decided_at') or '')[:10]}）"


def build_bulk_cards(
    hist_tasks: dict[str, Any], active_by_id: dict[str, dict], asked_313: set[str]
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """履歴で ② かつ回答待ち（queue_state=pending）の件を、/313/bulk の CleanupCard と同じ形にする。"""
    cards: list[dict[str, Any]] = []
    n = {"gone": 0, "asked_313": 0}
    for tid, row in sorted(hist_tasks.items()):
        if row.get("last_category") != "2" or row.get("queue_state") != "pending":
            continue
        t = active_by_id.get(tid)
        if not t:
            n["gone"] += 1
            continue
        if tid in asked_313:
            n["asked_313"] += 1
            continue
        due = (t.get("due") or {}).get("date")
        reason = str(row.get("last_reason") or "松野さんの判断が要る")
        cards.append(
            {
                "id": tid,
                "title": str(t.get("content") or ""),
                "sender": "",
                "subject": "",
                "mail_date": "",
                "summary": "",
                "gmail_url": "",
                "due": str(due)[:10] if due else None,
                "added_at": str(t.get("added_at") or "")[:10],
                "age_days": None,
                "suggest": "keep",  # 推奨は「残す（判断して進め方を決める）」。完了・削除は本人が選んだ時だけ
                "why": f"318: {reason}",
                "priority": t.get("priority"),
                "origin": "318",
                "deadline": ((t.get("deadline") or {}).get("date") or None),
                "prev": _prev_text(row),
            }
        )
    return cards, n


def build_weekly_handoff(hist_tasks: dict[str, Any], active_by_id: dict[str, dict]) -> list[dict[str, Any]]:
    """履歴で ③ の件（既存タスクのまま）。312 の週次ピックが読む。題は Todoist から取り直すので持たない。"""
    out = []
    for tid, row in sorted(hist_tasks.items()):
        if row.get("last_category") != "3" or tid not in active_by_id:
            continue
        out.append({"id": tid, "reason": HANDOFF_REASON_TEXT, "detail": str(row.get("last_reason") or "")[:120],
                    "large": bool(row.get("last_large")), "since": str(row.get("last_evaluated") or "")[:10]})
    return out


def queue_doc(run_id: str, now: datetime, cards: list[dict[str, Any]], *, published: bool) -> dict[str, Any]:
    return {"v": 1, "run_id": run_id, "generated_at": now.isoformat(timespec="seconds"), "published": published, "cards": cards}


def handoff_doc(run_id: str, now: datetime, items: list[dict[str, Any]], *, published: bool) -> dict[str, Any]:
    return {"v": 1, "run_id": run_id, "generated_at": now.isoformat(timespec="seconds"), "published": published, "items": items}


def publish(sb: SbFn, key: str, value: dict[str, Any], now: datetime) -> None:
    """sync_meta に置く（既存の snapshot と同じ upsert）。本番 DB への書き込みなので --publish の時だけ呼ぶ。"""
    sb(
        "sync_meta",
        params={"on_conflict": "key"},
        method="POST",
        prefer="resolution=merge-duplicates,return=minimal",
        body={"key": key, "value": json.dumps(value, ensure_ascii=False), "updated_at": now.isoformat()},
    )


# ---------------------------------------------------------------------------
# 既存スクリプト側で使う読み口（cleanup_bulk・weekly_pick）
# ---------------------------------------------------------------------------


def _fresh(doc: Any, now: datetime, days: int) -> bool:
    if not isinstance(doc, dict) or not doc.get("published"):
        return False
    try:
        at = datetime.fromisoformat(str(doc.get("generated_at") or ""))
    except ValueError:
        return False
    if at.tzinfo is None:
        at = at.replace(tzinfo=now.tzinfo)
    return now - at <= timedelta(days=days)


def read_meta(sb: SbFn, key: str) -> Any:
    """sync_meta の値（JSON）。無ければ None。読めない時も None（既存の画面・週次は止めない）。"""
    try:
        rows = sb("sync_meta", params={"select": "value", "key": f"eq.{key}", "limit": "1"}) or []
        if not rows:
            return None
        v = rows[0].get("value")
        return json.loads(v) if isinstance(v, str) else v
    except Exception:  # noqa: BLE001
        return None


def merge_bulk_cards(
    base_cards: list[dict[str, Any]], queue: Any, *, active_by_id: dict[str, dict], held: set[str], now: datetime
) -> list[dict[str, Any]]:
    """cleanup_bulk の snapshot に 318 の②を足す。古い・未公開のキュー、閉じた件、「残す」14日中、重複は出さない。"""
    if not _fresh(queue, now, QUEUE_STALE_DAYS):
        return base_cards
    have = {str(c.get("id")) for c in base_cards}
    extra = []
    for c in queue.get("cards") or []:
        tid = str(c.get("id") or "")
        t = active_by_id.get(tid)
        if not tid or tid in have or tid in held or not t:
            continue
        extra.append({**c, "title": str(t.get("content") or c.get("title") or "")})
    return extra + base_cards  # 318 の判断依頼を先に


def handoff_map(doc: Any, now: datetime) -> dict[str, dict[str, Any]]:
    """weekly_pick 側: 使ってよい受け渡しだけ {task_id: item}。"""
    if not _fresh(doc, now, HANDOFF_STALE_DAYS):
        return {}
    return {str(x.get("id")): x for x in (doc.get("items") or []) if isinstance(x, dict) and x.get("id")}


# ---------------------------------------------------------------------------
# 通知・報告の案（送るのは --send-slack の時だけ）
# ---------------------------------------------------------------------------


def consult_text(new_cards: list[dict[str, Any]], total: int, url: str) -> str:
    """#consult へ出す判断依頼。313 の片付けと同じ件は載っていない（重なりは除外済み）。"""
    lines = [
        "【相談】318 Todoist消化・判断依頼",
        f"🟡 新しく判断が要る {len(new_cards)}件（待ち 合計 {total}件）",
        "",
    ]
    for c in new_cards[:5]:
        due = c.get("deadline") or c.get("due") or "期限なし"
        lines.append(f"・{str(c.get('title') or '')[:40]}")
        lines.append(f"　{str(c.get('why') or '')[:60]}｜{due}" + (f"｜{c['prev']}" if c.get("prev") else ""))
    if len(new_cards) > 5:
        lines.append(f"ほか {len(new_cards) - 5}件")
    lines += [
        "",
        f"<{url}|まとめて判断する（/313/bulk）>",
        "",
        "次: 人判断のみ",
        "担当メモ: 回答は /313/bulk で（Slack では選ばない）。翌朝 318 が読み戻して再判定",
        "橋渡し: 送信・削除などの実行は、画面で選んだものだけ反映される",
    ]
    return "\n".join(lines)


def hub_report_text(run: dict[str, Any]) -> str:
    c = run["counts"]
    sig = {"success": "🟢", "partial": "🟡", "failed": "🔴", "stopped": "⏸"}.get(run["result"], "")
    lines = [
        f"【報告】318 Todoist消化・{'定時' if run.get('trigger') == 'schedule' else '手動'}",
        f"{sig} {run['result']}" + (f"（{run['stop_reason']}）" if run.get("stop_reason") else ""),
        f"確認 {c['examined']}／変化なし {c['skipped_unchanged']}／回答取込 {c.get('answered', 0)}",
        f"①{c['cat1']} ②{c['cat2']} ③{c['cat3']}／繰越 {c['carried_over']}",
        f"/313/bulk 待ち {c.get('queued', 0)}／週次へ {c.get('handoff', 0)}",
    ]
    cmt = run.get("comments") or {}
    if cmt.get("enabled"):
        lines.append(f"【318】コメント {cmt.get('posted', 0)}件／照合待ち {cmt.get('unknown', 0)}")
    if run.get("errors"):
        lines.append(f"要確認 {len(run['errors'])}件")
    return "\n".join(lines)
