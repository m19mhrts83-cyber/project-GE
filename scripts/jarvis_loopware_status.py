#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ループウェアの見張り用の1ファイル（loopware_status.json）を作る。AI は使わない。

見張る人（315 鮮度監視・番頭さん・ホーク）は、このファイルだけを読めばよい。
  - 入口ごと（slack / loopware / dashboard / kurashift / script）の最後の判断と7日の件数
    → 前の週は入っていたのに今週 0 件の入口＝記録が止まっている
  - 週次分析（今週の学び）が置かれた時刻 → 土曜 15 時までに無ければ止まっている
  - 判断デスクの判断待ち件数・今週の粒（採った／見送った／迷った／未判断）
  - 採用したルールのうち、まだルール帳に入っていないもの（反映待ち）

書き出し: .jarvis_state/loopware/status.json（追跡しない）と sync_meta.loopware_status（クラウドの見張り用）

  python scripts/jarvis_loopware_status.py            # 書き出して要約を表示（問題があれば終了コード 1）
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / ".jarvis_state" / "loopware" / "status.json"
JST = ZoneInfo("Asia/Tokyo")
SOURCES = ("slack", "loopware", "dashboard", "kurashift", "script")


def _coarse(s: str) -> str:
    s = (s or "").lower()
    for k in SOURCES:
        if s.startswith(k):
            return k
    if s.startswith("trade"):
        return "kurashift"
    return "script"


def _outcome(r: dict[str, Any]) -> str:
    import jarvis_loopware_weekly as lw

    return lw.outcome(r)


def build_status(rows: list[dict[str, Any]], *, now: datetime, candidates_meta: dict[str, Any] | None,
                 pending_desk: int | None) -> dict[str, Any]:
    """rows は直近14日の owner_decisions（decided_at, source, action, surface, payload）"""
    week_ago = now - timedelta(days=7)
    this_week: Counter = Counter()
    prev_week: Counter = Counter()
    last_at: dict[str, str] = {}
    outcomes: Counter = Counter()
    pending_rules = 0
    for r in rows:
        src = _coarse(str(r.get("source") or ""))
        at = str(r.get("decided_at") or "")
        try:
            t = datetime.fromisoformat(at.replace("Z", "+00:00"))
        except ValueError:
            continue
        if t >= week_ago:
            this_week[src] += 1
            outcomes[_outcome(r)] += 1
        else:
            prev_week[src] += 1
        if at > last_at.get(src, ""):
            last_at[src] = at
        pl = r.get("payload") if isinstance(r.get("payload"), dict) else {}
        if r.get("surface") == "rule_review" and r.get("action") == "rule_accept" and not pl.get("book_applied_at"):
            pending_rules += 1

    problems: list[str] = []
    for s in SOURCES:
        if s == "script":
            continue
        if prev_week[s] >= 3 and this_week[s] == 0:
            problems.append(f"入口 {s} の記録が今週 0 件（先週 {prev_week[s]} 件）")
    published_at = (candidates_meta or {}).get("at")
    # 土曜 15 時を過ぎて、今週の学びがまだ置かれていない
    sat = (now.astimezone(JST) - timedelta(days=(now.astimezone(JST).weekday() - 5) % 7)).replace(
        hour=15, minute=0, second=0, microsecond=0)
    if now.astimezone(JST) >= sat:
        ok = False
        if published_at:
            try:
                ok = datetime.fromisoformat(str(published_at).replace("Z", "+00:00")) >= sat - timedelta(hours=9)
            except (ValueError, TypeError):
                ok = False
        if not ok:
            problems.append("今週の学び（週次分析）がまだ置かれていません（土曜 9:00 の機械チェックを確認）")
    if pending_rules:
        problems.append(f"採用したのにルール帳へ未反映 {pending_rules} 件（jarvis_loopware_apply_rules.py）")

    last_any = max(last_at.values()) if last_at else None
    return {
        "checked_at": now.astimezone(JST).isoformat(timespec="seconds"),
        "last_decision_at": last_any,
        "sources": {s: {"last_at": last_at.get(s), "week": this_week[s], "prev_week": prev_week[s]} for s in SOURCES},
        "week": {k: outcomes[k] for k in ("take", "ng", "hesitate", "none", "later", "note")},
        "weekly": {
            "published_at": published_at,
            "week": (candidates_meta or {}).get("week"),
            "candidates": len((candidates_meta or {}).get("candidates") or []),
        },
        "desk_pending": pending_desk,
        "rules_pending_apply": pending_rules,
        "problems": problems,
    }


def main() -> int:
    from jarvis_loopware_weekly import _sb  # noqa: PLC0415

    sb = _sb()
    now = datetime.now(timezone.utc)
    since = (now - timedelta(days=14)).isoformat()
    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        res = (
            sb.table("owner_decisions").select("decided_at,source,action,surface,payload")
            .gte("decided_at", since).order("decided_at").range(start, start + 999).execute()
        )
        rows += res.data or []
        if len(res.data or []) < 1000:
            break
        start += 1000
    meta = sb.table("sync_meta").select("value").eq("key", "loopware_rule_candidates").limit(1).execute()
    try:
        cm = json.loads((meta.data or [{}])[0].get("value") or "{}")
    except (ValueError, TypeError):
        cm = {}
    pend = sb.table("triage_items").select("id", count="exact").eq("status", "pending").in_("lane", ["partner", "general"]).limit(1).execute()
    status = build_status(rows, now=now, candidates_meta=cm, pending_desk=getattr(pend, "count", None))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    sb.table("sync_meta").upsert(
        {"key": "loopware_status", "value": json.dumps(status, ensure_ascii=False), "updated_at": now.isoformat()},
        on_conflict="key",
    ).execute()
    w = status["week"]
    print(f"loopware: 今週 採った{w['take']} 見送った{w['ng']} 迷った{w['hesitate']} 未判断{w['none']}・判断待ち {status['desk_pending']}")
    for p in status["problems"]:
        print(f"⚠ {p}")
    return 1 if status["problems"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
