#!/usr/bin/env python3
"""松野さんの判断ログ（owner_decisions）の週次まとめ — 314 業務品質監査係が読む材料。

社員ごとに「提案に対して松野さんがどう判断したか」を数え、
直して送った例・見送った例を並べて、プロンプトやコードの直しどころを見つける。

  python scripts/jarvis_owner_decisions_weekly.py                 # 直近7日を標準出力へ（Markdown）
  python scripts/jarvis_owner_decisions_weekly.py --days 14 --out output/x.md
  python scripts/jarvis_owner_decisions_weekly.py --mark-reviewed # 読んだ行に review_week を付ける
  python scripts/jarvis_owner_decisions_weekly.py --loopware --improvement-logs --obsidian-dir <dir>
                                                                  # ループウェアの節・候補・改善ログ・週報

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

sys.path.insert(0, str(Path(__file__).resolve().parent))

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
    # 迷った・未判断は NG（見送り）に混ぜない（2026-11-08 松野さん）
    "hesitated": "迷った",
    "unseen": "未判断",
    "rule_accept": "送り手ルール採用",
    "rule_once": "今回だけ",
}
NEGATIVE = {"skipped", "dismiss", "skip"}
REASON_LABEL = {
    "promo": "宣伝・通知",
    "handled": "対応済み",
    "notnow": "今は不要",
    "hesitate": "迷う",
    # 契約 v1（apps/loopware/lib/decisionContract.ts）
    "no_reply": "回答不要",
    "self_or_grok": "自分発信・Grok部長",
    "not_important": "そもそも重要でない",
    "other": "その他",
    "area": "エリア外",
    "yield": "利回り不足",
    "price": "価格",
    "age_structure": "築年・構造",
    "loan": "融資が付きにくい",
    "no_time": "時間がない",
    "unsure": "迷った",
    "need_info": "情報が足りない",
    "waiting": "誰かの返事待ち",
}


def reason_text(row: dict[str, Any]) -> str:
    tags = (row.get("payload") or {}).get("reason_tags") or []
    parts = [REASON_LABEL.get(str(t), str(t)) for t in tags]
    if row.get("note"):
        parts.append(str(row["note"]))
    return "・".join(parts)


def employee_of(row: dict[str, Any]) -> str:
    if row.get("employee"):
        return str(row["employee"])
    payload = row.get("payload") or {}
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


def summarize(rows: list[dict[str, Any]], *, since: datetime, until: datetime) -> str:
    by_emp: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_emp[employee_of(r)].append(r)

    out: list[str] = [
        f"# 松野さんの判断ログ 週次まとめ（{since:%Y-%m-%d}〜{until:%Y-%m-%d}）",
        "",
        f"- 判断の件数: {len(rows)} 件（owner_decisions）",
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
            ex.append(
                f"- 見送り: {r.get('partner') or ''}｜{(r.get('subject') or '')[:50]}"
                + (f"（理由: {reason_text(r)}）" if reason_text(r) else "")
            )
        if ex:
            details += ["", f"## {EMPLOYEE_LABEL.get(emp, emp)}", *ex]

    src = Counter(str(r.get("source") or "-") for r in rows)
    out += ["", "経路: " + "・".join(f"{k} {v}" for k, v in src.most_common())]
    if not rows:
        out += ["", "今週は判断ログがありません（直す材料なし）。"]
    return "\n".join(out + details) + "\n"


def client():
    from supabase import create_client

    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY 未設定")
    return create_client(url, key)


def fetch(sb, since: datetime) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        r = (
            sb.table("owner_decisions")
            .select("*")
            .gte("decided_at", since.isoformat())
            .order("decided_at")
            .range(start, start + 999)
            .execute()
        )
        batch = r.data or []
        rows.extend(batch)
        if len(batch) < 1000:
            return rows
        start += 1000


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--out", help="Markdown の書き出し先（省略時は標準出力）")
    ap.add_argument("--mark-reviewed", action="store_true", help="読んだ行に review_week を付ける")
    ap.add_argument("--loopware", action="store_true",
                    help="ループウェアの節（ルール候補・効いたルール・残っている理由）を足し、候補を loopware に置く")
    ap.add_argument("--obsidian-dir", help="松野さん用の週報を <dir>/YYYY-Www.md に書く（例: Obsidian の 01_Journaling/判断ログ）")
    ap.add_argument("--improvement-logs", action="store_true", help="各社員フォルダの logs/改善ログ.md に今週の行を足す")
    args = ap.parse_args(argv)

    until = datetime.now(JST)
    since = until - timedelta(days=args.days)
    week = until.strftime("%G-W%V")
    sb = client()
    rows = fetch(sb, since)
    md = summarize(rows, since=since, until=until)
    if args.loopware or args.obsidian_dir or args.improvement_logs:
        import jarvis_loopware_weekly as lw

        lw.attach_from_email(sb, rows)
        cands = lw.hypotheses(rows, rejected=lw.rejected_ids(sb))
        if args.loopware:
            md += lw.sections(rows, cands)
            lw.publish_candidates(sb, cands, week=week)
        if args.obsidian_dir:
            d = Path(args.obsidian_dir).expanduser()
            d.mkdir(parents=True, exist_ok=True)
            (d / f"{week}.md").write_text(lw.obsidian_note(rows, cands, week=week), encoding="utf-8")
            print(f"# wrote {d / f'{week}.md'}", file=sys.stderr)
        if args.improvement_logs:
            import jarvis_learned_rules as lr

            for emp, lines in lw.improvement_lines(rows, week=week).items():
                book = lr.rulebook_path(emp)
                if not book or not lines:
                    continue
                log = book.parent / "logs" / "改善ログ.md"
                log.parent.mkdir(parents=True, exist_ok=True)
                head = "" if log.exists() else "# 改善ログ（ループウェア）\n\n直したこと・効いたか。314 が土曜に足す。\n\n"
                with log.open("a", encoding="utf-8") as f:
                    f.write(head + "\n".join(lines) + "\n")
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(md, encoding="utf-8")
        print(f"# wrote {args.out} rows={len(rows)}", file=sys.stderr)
    else:
        sys.stdout.write(md)
    if args.mark_reviewed and rows:
        ids = [r["id"] for r in rows if not r.get("review_week")]
        for i in range(0, len(ids), 200):
            sb.table("owner_decisions").update({"review_week": week}).in_("id", ids[i : i + 200]).execute()
        print(f"# marked review_week={week} rows={len(ids)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
