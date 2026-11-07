#!/usr/bin/env python3
"""松野さんの判断ログ（owner_decisions）の週次まとめ — 314 業務品質監査係が読む材料。

社員ごとに「提案に対して松野さんがどう判断したか」を数え、
直して送った例・見送った例を並べて、プロンプトやコードの直しどころを見つける。

読む表（どちらも読むだけ）:
  - owner_decisions                    triage・Slack の 312/313・S9・Loopware 313
  - task_loop_topics / task_loop_decisions   Loopware 312（扱いを決める・拾い漏れ）
出すもの: 今週と前週の 承認／修正／見送り（件数・母数・率）、理由タグの共通パターン
（2件以上だけ。根拠 ID つき）、改善台帳（output/improvements.md）の効果測定。

  python scripts/jarvis_owner_decisions_weekly.py                 # 直近7日を標準出力へ（Markdown）
  python scripts/jarvis_owner_decisions_weekly.py --days 14 --out output/x.md
  python scripts/jarvis_owner_decisions_weekly.py --mark-reviewed # 読んだ行に review_week を付ける
  python scripts/jarvis_owner_decisions_weekly.py --ledger <314>/output/improvements.md

DB は読むだけ（--mark-reviewed のときだけ review_week を書く）。秘密の値は出さない。
"""
from __future__ import annotations

import argparse
import difflib
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")

# triage の lane → 提案した社員（判定 / 下書き）
LANE_EMPLOYEE = {
    "partner": "111+211",   # 111 パートナー連絡整理係（未返信判定）＋ 211 返信案内下書き係
    "general": "116",       # 116 メール要対応係
    "openchat": "112",      # 112 LINE 同期監視係
}
EMPLOYEE_LABEL = {
    "111+211": "111 パートナー連絡整理係＋211 返信案内下書き係",
    "116": "116 メール要対応係",
    "112": "112 LINE同期監視係",
    "vendor": "業者返信（211 / 115）",
    "312": "312 Todoist起票整理係",
    "313": "313 完了候補確認係",
    "S9": "S9 管理会社 採用／見送り",
    "312L": "312 Todoist起票整理係（Loopware）",
    "313L": "313 完了候補確認係（Loopware）",
}
ACTION_LABEL = {
    "sent": "送った",
    "skipped": "見送り",
    "snoozed": "後で",
    "done": "回答不要・対応済み",
    "create": "起票",
    "dismiss": "見送り",
    "close": "完了",
    "reschedule": "延期",
    "adopt": "採用",
    "skip": "見送り",
    "drop": "やめる",
    "merge": "寄せて完了",
    "use": "案をそのまま",
    "edit_use": "案を直して",
    "none_of_above": "どれも違う",
}
NEGATIVE = {"skipped", "dismiss", "skip", "none_of_above"}

# 提案に対する松野さんの判断を3つに分ける（週次比較の物差し）
#   承認 = 提案どおり／修正 = 提案を直して使った・別の扱いにした／見送り = 提案を採らなかった
# sent は edited で 承認／修正 に分ける。ここに無い action は「その他」。
VERDICT = {
    "create": "承認", "close": "承認", "merge": "承認", "adopt": "承認", "use": "承認",
    "done": "承認",
    "edit_use": "修正", "reschedule": "修正", "drop": "修正",
    "skipped": "見送り", "dismiss": "見送り", "skip": "見送り", "none_of_above": "見送り",
    "snoozed": "見送り",
}
VERDICTS = ("承認", "修正", "見送り")
# 改善台帳で使える指標名
METRICS = ("件数", "承認率", "修正率", "見送り率")


def employee_of(row: dict[str, Any]) -> str:
    payload = row.get("payload") or {}
    if row.get("surface") == "loopware_312":
        return "312L"
    if row.get("surface") == "todoist_313" and payload.get("kind") == "loopware":
        return "313L"
    if row.get("employee"):
        return str(row["employee"])
    if "slack_vr_action" in payload:
        return "vendor"
    return LANE_EMPLOYEE.get(str(row.get("lane") or ""), str(row.get("lane") or "other"))


def edit_ratio(before: str | None, after: str | None) -> float | None:
    """0 = そのまま、1 = 全部書き換え。"""
    if not before or not after:
        return None
    return round(1 - difflib.SequenceMatcher(None, before, after).ratio(), 3)


def short_diff(before: str, after: str, limit: int = 14) -> str:
    lines = list(
        difflib.unified_diff(
            before.splitlines(), after.splitlines(), lineterm="", n=0
        )
    )[2:]
    lines = [x for x in lines if not x.startswith("@@")]
    if len(lines) > limit:
        lines = lines[:limit] + [f"…（他 {len(lines) - limit} 行）"]
    return "\n".join(lines)


def verdict_of(row: dict[str, Any]) -> str:
    act = str(row.get("action") or "")
    if act == "sent":
        return "修正" if row.get("edited") else "承認"
    return VERDICT.get(act, "その他")


def reason_tags_of(row: dict[str, Any]) -> list[str]:
    tags = row.get("reason_tags")
    if tags is None:
        tags = (row.get("payload") or {}).get("reason_tags")
    return [str(t) for t in (tags or []) if str(t).strip()]


def ref_of(row: dict[str, Any]) -> str:
    """根拠 ID（判断ログの行 ID ＋ Todoist ID があれば）。"""
    ref = f"#{row.get('id')}"
    if row.get("target_type") == "todoist_task" and row.get("target_id") not in (None, "", "-"):
        ref += f"(todoist {row['target_id']})"
    return ref


def metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    c = Counter(verdict_of(r) for r in rows)
    out: dict[str, Any] = {"件数": n}
    for v in VERDICTS:
        out[f"{v}数"] = c[v]
        out[f"{v}率"] = (c[v] / n) if n else None
    return out


def _pct(x: float | None) -> str:
    return "-" if x is None else f"{x:.0%}"


def _delta(cur: float | None, prev: float | None) -> str:
    if cur is None or prev is None:
        return ""
    d = round((cur - prev) * 100)
    return f"（前週比 {d:+d}pt）" if d else "（前週と同じ）"


def comparison_table(cur: list[dict[str, Any]], prev: list[dict[str, Any]]) -> list[str]:
    by_c: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_p: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in cur:
        by_c[employee_of(r)].append(r)
    for r in prev:
        by_p[employee_of(r)].append(r)
    emps = sorted(set(by_c) | set(by_p), key=lambda e: (-len(by_c.get(e, [])), e))
    lines = [
        "## 今週と前週（承認／修正／見送り）",
        "",
        "承認＝提案どおり、修正＝直して使った・別の扱い（延期・やめる）、見送り＝提案を採らなかった（どれも違う・後でを含む）。",
        "",
        "| 社員 | 今週 件数 | 承認 | 修正 | 見送り | 前週 件数 | 前週 承認／修正／見送り |",
        "|---|---|---|---|---|---|---|",
    ]
    for e in emps:
        mc, mp = metrics(by_c.get(e, [])), metrics(by_p.get(e, []))
        cells = []
        for v in VERDICTS:
            cells.append(
                f"{mc[v + '数']}/{mc['件数']} {_pct(mc[v + '率'])}{_delta(mc[v + '率'], mp[v + '率'])}"
            )
        prev_cells = "／".join(_pct(mp[v + "率"]) for v in VERDICTS) if mp["件数"] else "-"
        lines.append(
            f"| {EMPLOYEE_LABEL.get(e, e)} | {mc['件数']} | {' | '.join(cells)} | {mp['件数']} | {prev_cells} |"
        )
    if not emps:
        lines.append("| （なし） | 0 | - | - | - | 0 | - |")
    return lines


def pattern_section(rows: list[dict[str, Any]]) -> list[str]:
    """理由タグ・見送り理由の共通パターン。2件以上だけ候補にし、1件は一般化しない。"""
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        if verdict_of(r) == "承認":
            continue
        keys = reason_tags_of(r) or ([str(r["note"]).strip()[:40]] if r.get("note") else [])
        for k in keys:
            groups[(employee_of(r), k)].append(r)
    common = sorted(
        ((k, v) for k, v in groups.items() if len(v) >= 2), key=lambda kv: -len(kv[1])
    )
    single = [(k, v) for k, v in groups.items() if len(v) == 1]
    lines = ["## 共通パターン（同じ理由が2件以上）", ""]
    if common:
        lines += ["| 社員 | 理由 | 件数 | 判断の内訳 | 根拠 ID |", "|---|---|---|---|---|"]
        for (emp, tag), rs in common:
            vc = Counter(verdict_of(r) for r in rs)
            refs = " ".join(ref_of(r) for r in rs[:8]) + (" …" if len(rs) > 8 else "")
            lines.append(
                f"| {EMPLOYEE_LABEL.get(emp, emp)} | {tag} | {len(rs)} | "
                f"{'・'.join(f'{k} {n}' for k, n in vc.most_common())} | {refs} |"
            )
        lines += [
            "",
            "→ 314 はここから改善候補を最大3件、「コード条件分岐／プロンプト／運用ルール／松野判断が必要」に分けて"
            " output/improvements.md に足す。",
        ]
    else:
        lines.append("- なし（改善候補にする材料はまだ無い）")
    if single:
        lines += [
            "",
            f"1件だけの理由 {len(single)} 種（一般化しない。来週以降に重なったら候補）: "
            + "、".join(f"{t}{ref_of(v[0])}" for (_e, t), v in single[:10]),
        ]
    return lines


def parse_ledger(text: str) -> list[dict[str, str]]:
    """improvements.md の表（| ID | 状態 | 社員 | 指標 | 改善前 | … |）を読む。"""
    rows: list[dict[str, str]] = []
    header: list[str] | None = None
    for ln in text.splitlines():
        if not ln.strip().startswith("|"):
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if header is None:
            if "ID" in cells and "状態" in cells:
                header = cells
            continue
        if set("".join(cells)) <= set("-: "):
            continue
        rows.append(dict(zip(header, cells)))
    return rows


def ledger_section(ledger: list[dict[str, str]], cur: list[dict[str, Any]]) -> list[str]:
    """実装済みの改善について、指標の今の値を改善前と並べる（効果測定）。"""
    by_emp: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in cur:
        by_emp[employee_of(r)].append(r)
    targets = [x for x in ledger if x.get("状態") in ("実装済", "効果測定中")]
    lines = ["## 前回までの改善の効果（output/improvements.md）", ""]
    if not targets:
        lines.append("- 効果を測る改善はまだ無い（状態が「実装済」「効果測定中」の行が無い）")
        return lines
    lines += ["| ID | 社員 | 指標 | 改善前 | 今週 | 母数 |", "|---|---|---|---|---|---|"]
    for x in targets:
        emp, met = x.get("社員", ""), x.get("指標", "")
        m = metrics(by_emp.get(emp, []))
        now = m.get(met)
        now_s = str(now) if met == "件数" else _pct(now)
        lines.append(
            f"| {x.get('ID', '')} | {EMPLOYEE_LABEL.get(emp, emp)} | {met} | {x.get('改善前', '')} | {now_s} | {m['件数']} |"
        )
    lines += ["", "→ 効果が無い（または逆に悪化）なら、原因と再改善案を週次レビューの「提案」に書く。"]
    return lines


def summarize(
    rows: list[dict[str, Any]],
    *,
    since: datetime,
    until: datetime,
    prev_rows: list[dict[str, Any]] | None = None,
    ledger: list[dict[str, str]] | None = None,
    read_errors: list[str] | None = None,
) -> str:
    by_emp: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_emp[employee_of(r)].append(r)

    out: list[str] = [
        f"# 松野さんの判断ログ 週次まとめ（{since:%Y-%m-%d}〜{until:%Y-%m-%d}）",
        "",
        f"- 判断の件数: {len(rows)} 件（owner_decisions＋task_loop）",
        "- 見方: 見送りが多い社員＝提案の出しすぎ（判定・閾値）、"
        "直して送るが多い社員＝下書きのプロンプト、を直す候補",
        "",
        "| 社員 | 件数 | 内訳 | 見送り率 | 直して送った率 | 平均書き換え |",
        "|---|---|---|---|---|---|",
    ]
    details: list[str] = []
    for emp in sorted(by_emp, key=lambda e: -len(by_emp[e])):
        rs = by_emp[emp]
        acts = Counter(str(r.get("action")) for r in rs)
        neg = sum(acts[a] for a in NEGATIVE)
        sent = [r for r in rs if r.get("action") == "sent" and r.get("ai_proposal")]
        edited = [r for r in sent if r.get("edited")]
        ratios = [
            x
            for x in (edit_ratio(r.get("ai_proposal"), r.get("final_text")) for r in sent)
            if x is not None
        ]
        breakdown = "・".join(f"{ACTION_LABEL.get(a, a)} {n}" for a, n in acts.most_common())
        out.append(
            f"| {EMPLOYEE_LABEL.get(emp, emp)} | {len(rs)} | {breakdown} | "
            f"{neg / len(rs):.0%} | "
            f"{(len(edited) / len(sent)) if sent else 0:.0%}（{len(edited)}/{len(sent)}） | "
            f"{(sum(ratios) / len(ratios)) if ratios else 0:.0%} |"
        )

        ex: list[str] = []
        for r in sorted(
            edited,
            key=lambda r: -(edit_ratio(r.get("ai_proposal"), r.get("final_text")) or 0),
        )[:3]:
            ex.append(
                f"- 直して送った: {r.get('partner') or ''}｜{(r.get('subject') or '')[:40]}"
                f"（書き換え {edit_ratio(r.get('ai_proposal'), r.get('final_text')):.0%}）\n"
                "```diff\n"
                + short_diff(str(r.get("ai_proposal") or ""), str(r.get("final_text") or ""))
                + "\n```"
            )
        for r in [r for r in rs if r.get("action") in NEGATIVE][:5]:
            tags = reason_tags_of(r)
            ex.append(
                f"- 見送り: {r.get('partner') or ''}｜{(r.get('subject') or '')[:50]}"
                + (f"（理由: {r.get('note')}）" if r.get("note") else "")
                + (f"［{'・'.join(tags)}］" if tags else "")
                + f" {ref_of(r)}"
            )
        if ex:
            details += ["", f"## {EMPLOYEE_LABEL.get(emp, emp)}", *ex]

    src = Counter(str(r.get("source") or "-") for r in rows)
    out += ["", "経路: " + "・".join(f"{k} {v}" for k, v in src.most_common())]
    tables = Counter(str(r.get("_table") or "owner_decisions") for r in rows)
    out += ["読んだ表: " + "・".join(f"{k} {v}" for k, v in tables.most_common())]
    for e in read_errors or []:
        out += [f"- ⚠ 読めなかった: {e}（この表の判断は数に入っていない）"]
    if not rows:
        out += ["", "今週は判断ログがありません（直す材料なし）。"]
    out += ["", *comparison_table(rows, prev_rows or [])]
    out += ["", *pattern_section(rows)]
    out += ["", *ledger_section(ledger or [], rows)]
    return "\n".join(out + details) + "\n"


def client():
    from supabase import create_client

    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY 未設定")
    return create_client(url, key)


def _fetch_all(sb, table: str, time_col: str, since: datetime) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        r = (
            sb.table(table)
            .select("*")
            .gte(time_col, since.isoformat())
            .order(time_col)
            .range(start, start + 999)
            .execute()
        )
        batch = r.data or []
        rows.extend(batch)
        if len(batch) < 1000:
            return rows
        start += 1000


def fetch(sb, since: datetime) -> list[dict[str, Any]]:
    return _fetch_all(sb, "owner_decisions", "decided_at", since)


def task_loop_rows(
    decisions: list[dict[str, Any]], topics: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """Loopware 312（task_loop_decisions）を owner_decisions と同じ形にそろえる。"""
    out: list[dict[str, Any]] = []
    for d in decisions:
        t = topics.get(str(d.get("topic_id"))) or {}
        tids = t.get("todoist_task_ids") or []
        out.append(
            {
                "id": f"tl:{str(d.get('id'))[:8]}",
                "_table": "task_loop",
                "decided_at": d.get("updated_at") or d.get("created_at"),
                "surface": "loopware_312",
                "action": d.get("choice"),
                "source": d.get("decided_via") or "app",
                "employee": "312",
                "target_type": "todoist_task" if tids else "task_loop_topic",
                "target_id": (tids[0] if tids else str(d.get("topic_id"))[:8]),
                "subject": (t.get("topic_text") or "")[:80],
                "ai_proposal": d.get("before_text"),
                "final_text": d.get("final_text") or d.get("after_text"),
                "edited": d.get("choice") == "edit_use",
                "note": d.get("free_note"),
                "reason_tags": d.get("reason_tags") or [],
                "payload": {"history_n": len(d.get("history") or [])},
            }
        )
    return out


def fetch_task_loop(sb, since: datetime) -> list[dict[str, Any]]:
    decisions = _fetch_all(sb, "task_loop_decisions", "updated_at", since)
    ids = sorted({str(d.get("topic_id")) for d in decisions if d.get("topic_id")})
    topics: dict[str, dict[str, Any]] = {}
    for i in range(0, len(ids), 200):
        r = sb.table("task_loop_topics").select("*").in_("id", ids[i : i + 200]).execute()
        for t in r.data or []:
            topics[str(t["id"])] = t
    return task_loop_rows(decisions, topics)


def fetch_all_sources(sb, since: datetime) -> tuple[list[dict[str, Any]], list[str]]:
    """両方の表を読む。片方が読めなくても止めず、読めなかったことを残す。"""
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for name, fn in (("owner_decisions", fetch), ("task_loop", fetch_task_loop)):
        try:
            rows.extend(fn(sb, since))
        except Exception as exc:  # noqa: BLE001 — 表が無い・権限なしなど
            errors.append(f"{name}: {str(exc)[:120]}")
    rows.sort(key=lambda r: str(r.get("decided_at") or ""))
    return rows, errors


def split_weeks(
    rows: list[dict[str, Any]], *, since: datetime
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cur, prev = [], []
    for r in rows:
        raw = str(r.get("decided_at") or "")
        try:
            at = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            cur.append(r)
            continue
        if at.tzinfo is None:
            at = at.replace(tzinfo=JST)
        (cur if at >= since else prev).append(r)
    return cur, prev


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--out", help="Markdown の書き出し先（省略時は標準出力）")
    ap.add_argument("--mark-reviewed", action="store_true", help="読んだ行に review_week を付ける")
    ap.add_argument(
        "--ledger",
        default=str(
            Path(__file__).resolve().parents[1]
            / "docs/AIエージェントチーム/300_品質・タスク運用管理室/314_業務品質監査係/output/improvements.md"
        ),
        help="改善台帳（効果測定に使う）",
    )
    args = ap.parse_args(argv)

    until = datetime.now(JST)
    since = until - timedelta(days=args.days)
    sb = client()
    both, errors = fetch_all_sources(sb, since - timedelta(days=args.days))
    rows, prev_rows = split_weeks(both, since=since)
    ledger_path = Path(args.ledger)
    ledger = parse_ledger(ledger_path.read_text(encoding="utf-8")) if ledger_path.exists() else []
    md = summarize(
        rows, since=since, until=until, prev_rows=prev_rows, ledger=ledger, read_errors=errors
    )
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(md, encoding="utf-8")
        print(f"# wrote {args.out} rows={len(rows)}", file=sys.stderr)
    else:
        sys.stdout.write(md)
    if args.mark_reviewed and rows:
        week = until.strftime("%G-W%V")
        # review_week は owner_decisions にだけある（task_loop は読むだけ）
        ids = [
            r["id"] for r in rows
            if r.get("_table", "owner_decisions") == "owner_decisions" and not r.get("review_week")
        ]
        for i in range(0, len(ids), 200):
            sb.table("owner_decisions").update({"review_week": week}).in_("id", ids[i : i + 200]).execute()
        print(f"# marked review_week={week} rows={len(ids)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
