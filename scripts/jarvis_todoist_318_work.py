#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""318 Todoist消化係 — ①自律実行（FlowForge node_run_a＝2-1・node_halt_check＝2-2）の部品.

既定はオフ。`jarvis_todoist_318_triage.py run --execute-auto` を明示した時だけ使う。
追加の有料 AI API は呼ばない。Phase 1 の --emit-packet／--ai-answers と同じ「材料出し → Claude Code（定額枠）→ 結果取り込み」:

  1) run --execute-auto
       ① の件を 2-2（始める前の確認）に通し、通った件だけ作業の材料を work/packet.json に書く（最大 5 件）
  2) この実行の Claude Code が packet を読み、調査・資料確認・文面下書きをして work/results.json を書く
       {"results": [{task_id, work_id, snapshot_id, status, summary, artifacts:[{name, content}], remaining,
                     actions_taken:[...], requested_operations:[...], reason}]}
  3) run --execute-auto --work-results .jarvis_state/todoist_318/work/results.json
       2-2（大事な操作の直前の確認）→ 成果物を work/<task_id>/<run_id>/ に保存 → 進捗・成果物・残作業を判断履歴へ

決まり（コードで縛る）:
- 作業の範囲は基準ファイルの work_scope（調査・資料確認・文面下書き）。読めなければ始めない
- 対外送信・削除・支払い・契約・マージ・デプロイ・他エージェント依頼（とコード修正・PR）は止めて②へ。本人操作は③へ
- 停止スイッチ・時間上限なら新しく着手・取り込みをしない（残りは packet に残す＝中断点）
- ②へ移した件（承認待ち）は、本人の回答が来るまで自動で再実行しない
- 大規模は始めずに週次計画へ。Todoist は閉じない（この部品は Todoist に触らない）
- 内容が変わった件の結果は使わない（packet の snapshot_id と、取り込み時に読み直した内容を比べる）
"""
from __future__ import annotations

import json
import re
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

MAX_ITEMS = 5
MAX_ARTIFACTS = 5
MAX_ARTIFACT_CHARS = 20000
PACKET_STALE_DAYS = 3  # これより古い材料は取り込まない（内容が変わっていなくても、もう一度材料を出し直す）
STATUSES = ("done", "partial", "needs_decision", "needs_owner")

PACKET_NOTE = (
    "①自律実行の材料（非公開の置き場だけ）。items[] ごとに allowed_actions の範囲（調査・資料確認・文面下書き）だけで作業し、"
    " results.json に {results: [{task_id, work_id, snapshot_id（そのまま）, status: done|partial|needs_decision|needs_owner,"
    " summary, artifacts: [{name, content}], remaining, actions_taken: [...], requested_operations: [...], reason}]} を書く。"
    " 対外送信・削除・支払い・契約・マージ・デプロイ・他エージェントへの依頼・コード修正・PR 作成はしない（要るなら"
    " requested_operations に書いて status=needs_decision）。本人の操作が要るなら status=needs_owner。Todoist は閉じない・書かない"
)


class ScopeError(Exception):
    pass


def load_scope(criteria_path: Path) -> dict[str, Any]:
    """基準ファイルの work_scope。無い・壊れている時は ScopeError（範囲が分からないまま始めない）。"""
    try:
        import yaml  # noqa: PLC0415

        d = yaml.safe_load(criteria_path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        raise ScopeError(f"作業範囲が読めない（{type(e).__name__}）") from e
    ws = (d or {}).get("work_scope") if isinstance(d, dict) else None
    if not isinstance(ws, dict) or not ws.get("decision_id"):
        raise ScopeError("基準ファイルに work_scope（decision_id 付き）が無い")
    allowed = [str(x) for x in (ws.get("allowed_actions") or [])]
    appr = ws.get("approval_operations") or {}
    owner = ws.get("owner_operations") or {}
    words = [str(x) for x in (ws.get("approval_words") or [])]
    if not allowed or not isinstance(appr, dict) or not appr or not isinstance(owner, dict) or not words:
        raise ScopeError("work_scope の形が想定外")
    if set(allowed) - {"research", "read", "draft"}:
        raise ScopeError("work_scope の allowed_actions に今回の範囲外がある（調査・資料確認・文面下書きだけ）")
    if any(len(w) < 2 for w in words):
        raise ScopeError("work_scope の approval_words に1文字の語（誤判定のもと）")
    return {
        "decision_id": str(ws["decision_id"]),
        "allowed_actions": allowed,
        "approval_operations": {str(k): str(v) for k, v in appr.items()},
        "owner_operations": {str(k): str(v) for k, v in owner.items()},
        "approval_words": words,
    }


# ---------------------------------------------------------------------------
# 2-2 始める前の確認
# ---------------------------------------------------------------------------


def precheck(
    text: str,
    *,
    scope: dict[str, Any],
    large: bool,
    owner_op_hit: bool,
    approval_wait: bool,
    stop_reason: str,
) -> tuple[str, str]:
    """(decision, 理由)。decision: start／to2／to3／weekly／hold（今回は着手しない・分類はそのまま）。"""
    if stop_reason:
        return "hold", f"新しく着手しない（{stop_reason}）"
    if approval_wait:
        return "hold", "承認待ち（②へ移した件）。本人の回答が来るまで自動で再実行しない"
    hits = [w for w in scope["approval_words"] if w.lower() in text.lower()]
    if hits:
        return "to2", "①の実行前確認: 承認が要る操作の語（" + "・".join(hits[:3]) + "）"
    if owner_op_hit:
        return "to3", "①の実行前確認: 本人の操作が要る手がかり"
    if large:
        return "weekly", "大規模: AIでは進めず、既存タスクのまま週次計画へ"
    return "start", ""


def new_work_id(now: datetime) -> str:
    return f"w318-{now.strftime('%Y%m%dT%H%M%S')}-{secrets.token_hex(3)}"


def packet_item(t: dict, comments: list[dict], snap_id: str, plan: dict[str, Any], scope: dict[str, Any],
                *, work_id: str, run_id: str, now: datetime) -> dict[str, Any]:
    return {
        "work_id": work_id,
        "task_id": str(t.get("id")),
        "snapshot_id": snap_id,
        "emitted_at": now.isoformat(timespec="seconds"),
        "emitted_run_id": run_id,
        "title": str(t.get("content") or ""),
        "description": str(t.get("description") or "")[:1500],
        "labels": [str(x) for x in (t.get("labels") or [])],
        "due": (t.get("due") or {}).get("date"),
        "deadline": (t.get("deadline") or {}).get("date"),
        "recent_comments": [str(c.get("content") or "")[:400] for c in comments[-5:]],
        "plan": plan.get("plan"),
        "allowed_actions": scope["allowed_actions"],
        "forbidden": sorted(scope["approval_operations"]) + sorted(scope["owner_operations"]),
        "limits": plan.get("limits"),
    }


def read_packet(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"items": []}
    d = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(d, dict) or not isinstance(d.get("items"), list):
        raise ValueError("作業の材料の形が想定外")
    return d


def merge_packet(old: list[dict[str, Any]], new: list[dict[str, Any]], *, resolved: set[str], active_ids: set[str],
                 now: datetime) -> list[dict[str, Any]]:
    """前回の材料のうち、まだ結果が来ていない・タスクが残っている・新しい材料で置き換わっていない件を残す。"""
    new_tids = {x["task_id"] for x in new}
    keep = []
    for x in old:
        if x.get("work_id") in resolved or x.get("task_id") in new_tids or x.get("task_id") not in active_ids:
            continue
        if _stale(x, now):
            continue
        keep.append(x)
    return (keep + new)[: MAX_ITEMS * 2]


def _stale(item: dict[str, Any], now: datetime) -> bool:
    try:
        at = datetime.fromisoformat(str(item.get("emitted_at") or ""))
    except ValueError:
        return True
    return now - at > timedelta(days=PACKET_STALE_DAYS)


# ---------------------------------------------------------------------------
# 2-1 結果の取り込み（2-2 大事な操作の直前の確認つき）
# ---------------------------------------------------------------------------

SAFE_NAME_RE = re.compile(r"[^0-9A-Za-z_\-ぁ-んァ-ヶー一-龠々（）()・]+")


def safe_name(name: str, n: int) -> str:
    raw = str(name or "")
    m = re.match(r"^(.*)\.[A-Za-z0-9]{1,5}$", raw)  # 拡張子だけ外す（中の「.」や「/」は記号として潰す）
    base = SAFE_NAME_RE.sub("_", m.group(1) if m else raw).strip("_")[:50] or "artifact"
    return f"{n:02d}_{base}.md"


def safe_tid(tid: str) -> str:
    s = re.sub(r"[^0-9A-Za-z_\-]", "_", str(tid))[:40]
    if not s or set(s) == {"_"}:
        raise ValueError("task_id の形が想定外")
    return s


def judge_result(res: dict[str, Any], scope: dict[str, Any]) -> tuple[str, str, list[str]]:
    """(outcome, 理由, 申告された止める操作)。outcome: done／partial／to2／to3／invalid。"""
    status = str(res.get("status") or "")
    if status not in STATUSES:
        return "invalid", f"status が想定外（{status!r}）", []
    taken = [str(x) for x in (res.get("actions_taken") or [])]
    bad = [a for a in taken if a not in scope["allowed_actions"]]
    req = [str(x) for x in (res.get("requested_operations") or [])]
    appr = [scope["approval_operations"].get(x, x) for x in req if x not in scope["owner_operations"]]
    owner = [scope["owner_operations"][x] for x in req if x in scope["owner_operations"]]
    if bad:
        # 範囲外の操作をしたと申告 → 成果物を取り込まず②（人が確かめる）
        return "to2", "範囲外の操作を申告（" + "・".join(bad[:3]) + "）。成果物は取り込まない", bad
    if appr or status == "needs_decision":
        why = "承認が要る操作（" + "・".join(appr[:3]) + "）" if appr else "AI が判断を求めた"
        return "to2", why + "。止めて②へ（明示承認まで再実行しない）", appr
    if owner or status == "needs_owner":
        return "to3", "本人の操作が要る" + ("（" + "・".join(owner[:3]) + "）" if owner else ""), owner
    if not str(res.get("summary") or "").strip():
        return "invalid", "summary が空", []
    if status == "partial" and not str(res.get("remaining") or "").strip():
        return "invalid", "途中なのに残作業が空", []
    return status, "", []


def import_results(
    results: list[dict[str, Any]],
    packet: list[dict[str, Any]],
    *,
    scope: dict[str, Any],
    current_snap: Callable[[str], str | None],
    work_dir: Path,
    run_id: str,
    now: datetime,
    dry_run: bool,
    stop_check: Callable[[], str],
) -> tuple[list[dict[str, Any]], str]:
    """結果を 1 件ずつ確かめて取り込む。(各件の結末, 途中で止めた理由)。成果物は dry-run では保存しない。"""
    by_work = {str(x.get("work_id")): x for x in packet}
    out: list[dict[str, Any]] = []
    stopped = ""
    for res in results[:MAX_ITEMS]:
        if not isinstance(res, dict):
            out.append({"task_id": "", "outcome": "invalid", "reason": "結果の形が想定外"})
            continue
        tid = str(res.get("task_id") or "")
        wid = str(res.get("work_id") or "")
        why = stop_check()
        if why:
            stopped = why  # 中断点: 残りは取り込まず packet に残る
            break
        item = by_work.get(wid)
        row: dict[str, Any] = {"task_id": tid, "work_id": wid}
        if not item or item.get("task_id") != tid:
            out.append({**row, "outcome": "discarded", "reason": "材料（packet）に無い作業の結果"})
            continue
        if str(res.get("snapshot_id") or "") != str(item.get("snapshot_id")):
            out.append({**row, "outcome": "discarded", "reason": "結果の snapshot_id が材料と違う"})
            continue
        if _stale(item, now):
            out.append({**row, "outcome": "discarded", "reason": f"材料が {PACKET_STALE_DAYS} 日より古い"})
            continue
        try:
            cur = current_snap(tid)
        except Exception as e:  # noqa: BLE001
            out.append({**row, "outcome": "unverified", "reason": f"今の内容を読めない（{type(e).__name__}）。取り込まない"})
            continue
        if cur is None:
            out.append({**row, "outcome": "discarded", "reason": "タスクが無くなった（完了・削除）"})
            continue
        if cur != item.get("snapshot_id"):
            out.append({**row, "outcome": "discarded", "reason": "材料を出した後に内容が変わった（結果は使わない）"})
            continue
        outcome, reason, ops = judge_result(res, scope)
        row.update(outcome=outcome, reason=reason, operations=ops,
                   summary=str(res.get("summary") or "").strip()[:400],
                   remaining=str(res.get("remaining") or "").strip()[:400])
        if outcome in ("done", "partial"):
            arts = [a for a in (res.get("artifacts") or []) if isinstance(a, dict) and str(a.get("content") or "").strip()]
            if len(arts) > MAX_ARTIFACTS:
                row["note"] = f"成果物は先頭 {MAX_ARTIFACTS} 件だけ保存"
            names = [safe_name(a.get("name"), i) for i, a in enumerate(arts[:MAX_ARTIFACTS], 1)]
            row["artifact_names"] = names
            if not dry_run:
                try:
                    d = work_dir / safe_tid(tid) / run_id
                    d.mkdir(parents=True, exist_ok=True)
                    for nm, a in zip(names, arts):
                        (d / nm).write_text(str(a.get("content"))[:MAX_ARTIFACT_CHARS] + "\n", encoding="utf-8")
                    progress = {k: row.get(k) for k in ("task_id", "work_id", "outcome", "summary", "remaining", "artifact_names")}
                    progress.update(run_id=run_id, saved_at=now.isoformat(timespec="seconds"),
                                    actions_taken=[str(x) for x in (res.get("actions_taken") or [])])
                    (d / "progress.json").write_text(json.dumps(progress, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                    row["saved_dir"] = str(d.relative_to(work_dir))
                except Exception as e:  # noqa: BLE001
                    row.update(outcome="save_failed", reason=f"成果物を保存できない（{type(e).__name__}）。次の回にやり直す")
        out.append(row)
    return out, stopped


def format_work_comment(r: dict[str, Any], run_id: str, prefix: str, id_label: str) -> str:
    """取り込んだ結果から【318】コメントを作る（成果物の中身は書かない。名前と件数だけ）。"""
    oc = r.get("outcome")
    names = r.get("artifact_names") or []
    arts = f"内部に {len(names)} 件保存（" + "・".join(n.split("_", 1)[-1].removesuffix(".md") for n in names[:3]) + "）" if names else "なし"
    if oc == "done":
        lines = [f"{prefix}やり切った", f"要約: {r.get('summary', '')[:200]}", f"成果物: {arts}",
                 "残作業: " + (r.get("remaining") or "なし（完了にするかは松野さんが決める。Todoist は閉じていない）")[:200]]
    elif oc == "partial":
        lines = [f"{prefix}途中", f"要約: {r.get('summary', '')[:200]}", f"成果物: {arts}", f"残作業: {r.get('remaining', '')[:200]}"]
    elif oc == "to3":
        lines = [f"{prefix}本人作業", f"要約: AI の作業中に本人の操作が要ると分かった（{r.get('reason', '')[:120]}）", "成果物: なし",
                 "残作業: 松野さんの操作"]
    else:
        lines = [f"{prefix}要判断", f"要約: AI の作業を止めた（{r.get('reason', '')[:120]}）", "成果物: なし",
                 "必要な判断: 進めてよいか（承認されるまで自動で再実行しない）"]
    lines.append(f"{id_label}{run_id}")
    return "\n".join(lines)
