#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""下書きの判断ログ — 松野さんが下書きを直した点・言ったことを owner_decisions に残す。

チャットで作る下書き（運営・パートナー・LINE などの返信／報告）は、Slack の判断デスクを通らない。
その直し（v1→v2 など）を1件ずつ owner_decisions（surface=draft_review）に記録し、
既存のループウェアに乗せる:

  記録（このスクリプト） → 土曜の週次（jarvis_loopware_weekly.py）が同じ相手への直し2回以上で
  言い回しルール候補を出す → 松野さんが loopware で採用 → 211 の learned_rules.md「確定ルール」
  → 次の下書きの前に `context` で読む

使い方（リポジトリルートから。JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY を値を表示せず読み込む）:

  # 直しを1件記録（版のファイル2つを渡す）。理由が分からなければ --reason を省く → 質問として残る
  python scripts/jarvis_draft_decision_log.py log \
    --case 20261107_次のご提案 --recipient 今村さん --channel chatwork \
    --from-file v1.txt --to-file v2.txt --from-label v1 --to-label v2 \
    --change-type 方針 --reason '松野さんの言葉を短く' \
    --rule-hint '運営への提案は検証済みの数字を根拠に添える'

  # 最終版（送ったもの）は --final（action=sent・edited=true）
  # --sql は DB に書かず INSERT 文を出す（MCP などから流すとき）。--dry-run は行を表示するだけ

  # 下書きを書く前に読む（採用済みルール・参照例・最近の直し）
  python scripts/jarvis_draft_decision_log.py context --recipient 今村さん

  # 下書きを Nody の「下書きを直す」に置く → 松野さんが箇所ごとに声でダメ出し → まとめて Mac の Cursor が直す → 差分
  #   画面で版が進むたびに判断ログ（draft_review）が自動で残る。--sql は INSERT 文だけ出す
  python scripts/jarvis_draft_decision_log.py push --case 20261109_完了報告 --recipient 今村さん \
    --channel chatwork --file draft.txt
  # 直し終わった（確定した）文面を受け取る
  python scripts/jarvis_draft_decision_log.py pull --id <push で出たID>

記録しないもの: 会員の個人情報、秘密、ローカルパス。本文は前後の版を最大4000字まで（service_role のみ読める表）。
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import jarvis_learned_rules as lr  # noqa: E402
from jarvis_owner_decision_log import contract_row  # noqa: E402

SURFACE = "draft_review"
NODY_URL = os.environ.get("LOOPWARE_URL", "https://jarvis-loopware.vercel.app").rstrip("/")
EMPLOYEE = "211"  # 返信案内下書き係（ルール帳の置き場）
CHANNELS = ("chatwork", "mail", "line", "slack", "doc", "other")
CHANGE_TYPES = ("言い回し", "トーン", "追加", "削除", "事実訂正", "方針", "構成", "その他")
TEXT_MAX = 4000
DIFF_MAX = 3000


def diff_summary(before: str, after: str) -> dict[str, Any]:
    """機械で取れる直しの量。言葉の意味づけは人（理由）と週次の 314 が行う"""
    a = before.splitlines()
    b = after.splitlines()
    sm = difflib.SequenceMatcher(None, before, after)
    added = removed = 0
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b).get_opcodes():
        if tag in ("replace", "delete"):
            removed += i2 - i1
        if tag in ("replace", "insert"):
            added += j2 - j1
    udiff = "\n".join(difflib.unified_diff(a, b, "before", "after", n=0, lineterm=""))
    return {
        "edit_ratio": round(1 - sm.ratio(), 3),
        "lines_added": added,
        "lines_removed": removed,
        "diff": udiff[:DIFF_MAX],
    }


def build_row(
    *,
    case: str,
    recipient: str,
    channel: str,
    before: str,
    after: str,
    from_label: str,
    to_label: str,
    change_types: list[str],
    reason: str | None,
    rule_hint: str | None,
    final: bool,
    source: str = "script",
) -> dict[str, Any]:
    if channel not in CHANNELS:
        raise ValueError(f"channel は {', '.join(CHANNELS)} のどれか")
    bad = [t for t in change_types if t not in CHANGE_TYPES]
    if bad:
        raise ValueError(f"change-type が不明: {bad}（{', '.join(CHANGE_TYPES)}）")
    if not case.strip() or not recipient.strip():
        raise ValueError("case と recipient は必須")
    if before == after:
        raise ValueError("前後の版が同じです")
    action = "sent" if final else "revise"
    target = f"{case}:{from_label}->{to_label}"
    summary = diff_summary(before, after)
    payload: dict[str, Any] = {
        "case": case,
        "recipient": recipient,
        "version_from": from_label,
        "version_to": to_label,
        "change_types": change_types,
        "reason": reason or None,
        "reason_missing": not reason,
        "rule_hint": rule_hint or None,
        "edit_ratio": summary["edit_ratio"],
        "lines_added": summary["lines_added"],
        "lines_removed": summary["lines_removed"],
        "diff": summary["diff"],
    }
    payload = {k: v for k, v in payload.items() if v is not None}
    row = contract_row(
        surface=SURFACE,
        action=action,
        source=source,
        target_type="draft",
        target_id=target,
        employee=EMPLOYEE,
        subject=case,
        note=reason,
        ai_proposal=before[:TEXT_MAX],
        payload=payload,
        idem_key=f"draft:{target}:{action}",
    )
    row.update({
        "partner": recipient[:200],
        "channel": channel,
        "final_text": after[:TEXT_MAX],
        "edited": True,
        "kind": "draft",
    })
    return row


def _sql_lit(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (dict, list)):
        return "$j$" + json.dumps(v, ensure_ascii=False) + "$j$::jsonb"
    s = str(v)
    if "$t$" in s:
        raise ValueError("本文に $t$ が含まれるため SQL を作れません")
    return "$t$" + s + "$t$"


def to_sql(row: dict[str, Any]) -> str:
    cols = list(row.keys())
    vals = ", ".join(_sql_lit(row[c]) for c in cols)
    return (
        f"insert into public.owner_decisions ({', '.join(cols)})\n"
        f"select {vals}\n"
        f"where not exists (select 1 from public.owner_decisions "
        f"where payload->>'idem_key' = {_sql_lit(row['payload']['idem_key'])})\n"
        f"returning id;"
    )


def _client():
    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        return None
    from supabase import create_client  # noqa: PLC0415

    return create_client(url, key)


def insert(row: dict[str, Any]) -> str:
    sb = _client()
    if sb is None:
        raise RuntimeError("JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY が必要です（--sql で INSERT 文だけ出せます）")
    dup = sb.table("owner_decisions").select("id").eq("payload->>idem_key", row["payload"]["idem_key"]).limit(1).execute()
    if dup.data:
        return f"登録済み: id={dup.data[0]['id']}"
    res = sb.table("owner_decisions").insert(row).execute()
    return f"記録: id={res.data[0]['id']}"


def context_text(recipient: str, recent: list[dict[str, Any]] | None = None, book: lr.RuleBook | None = None) -> str:
    """下書きを書く前に読む材料（採用済みルール → 参照例 → 最近の直し）"""
    book = book or lr.load_rulebook(EMPLOYEE)
    probe = {"partner": recipient}
    lines = [f"# 下書きの前に読む — {recipient}", "", "## 採用済みの言い回しルール（必ず守る）"]
    rules = lr.rewrite_lines(book, probe)
    lines += [f"- {rid}: {text}" for rid, text in rules] or ["- （まだありません）"]
    examples = [r for r in book.rules if r.status == "example" and (not r.conds or r.matches(probe))]
    if examples:
        lines += ["", "## 参照例"] + [f"- {r.id}: {r.note}" for r in examples]
    lines += ["", "## 最近の直し（候補。ルールではない）"]
    if recent is None:
        lines.append("- （DBに接続していないため省略）")
    elif not recent:
        lines.append("- （まだありません）")
    for r in recent or []:
        pl = r.get("payload") or {}
        why = pl.get("reason") or "理由未確認"
        hint = f" → 候補: {pl['rule_hint']}" if pl.get("rule_hint") else ""
        types = "・".join(pl.get("change_types") or [])
        lines.append(f"- {str(r.get('decided_at') or '')[:10]} {pl.get('case', '')} {pl.get('version_from', '')}→{pl.get('version_to', '')} [{types}] {why}{hint}")
    lines += ["", "書いたあと、上のルールに沿っているかを一言添えて見せる。使ったルール番号は記録時に --applied-rule で残す。"]
    return "\n".join(lines) + "\n"


def rules_context(recipient: str, book: lr.RuleBook | None = None) -> str | None:
    """Nody の AI に渡す前提（採用済みの言い回しルールだけ）。無ければ None"""
    book = book or lr.load_rulebook(EMPLOYEE)
    rules = lr.rewrite_lines(book, {"partner": recipient})
    if not rules:
        return None
    return "採用済みの言い回しルール（必ず守る）:\n" + "\n".join(f"- {rid}: {text}" for rid, text in rules)


def fetch_recent(recipient: str, limit: int) -> list[dict[str, Any]] | None:
    sb = _client()
    if sb is None:
        return None
    res = (
        sb.table("owner_decisions").select("decided_at,action,payload")
        .eq("surface", SURFACE).eq("partner", recipient)
        .order("decided_at", desc=True).limit(limit).execute()
    )
    return res.data or []


def draft_review_row(*, case: str, recipient: str, channel: str, text: str, context: str | None) -> dict[str, Any]:
    if channel not in CHANNELS:
        raise ValueError(f"channel は {', '.join(CHANNELS)} のどれか")
    if not case.strip() or not recipient.strip() or not text.strip():
        raise ValueError("case・recipient・本文は必須")
    from datetime import datetime, timezone  # noqa: PLC0415

    v1 = {"label": "v1", "text": text[:20000], "at": datetime.now(timezone.utc).isoformat(), "by": "agent"}
    return {
        "case_name": case[:200],
        "recipient": recipient[:200],
        "channel": channel,
        "context": (context or "")[:6000] or None,
        "versions": [v1],
        "source": "script",
    }


def draft_review_sql(row: dict[str, Any]) -> str:
    cols = list(row.keys())
    return (
        f"insert into public.draft_reviews ({', '.join(cols)})\n"
        f"values ({', '.join(_sql_lit(row[c]) for c in cols)})\nreturning id;"
    )


def pull_text(row: dict[str, Any]) -> str:
    versions = [v for v in (row.get("versions") or []) if not v.get("reverted")]
    if not versions:
        return "（版がありません）\n"
    cur = versions[-1]
    head = f"# {row.get('case_name')} — {row.get('recipient')} / {row.get('status')} / いまの版 {cur.get('label')}（全{len(versions)}版）"
    notes = []
    for v in versions[1:]:
        for c in v.get("comments") or []:
            where = f"「{c.get('quote', '')[:40]}」" if c.get("quote") else "全体"
            notes.append(f"- {v.get('label')} {where}: {c.get('text', '')}")
    body = [head, "", cur.get("text", "")]
    if notes:
        body += ["", "## 松野さんのダメ出し", *notes]
    return "\n".join(body).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    subs = ap.add_subparsers(dest="command", required=True)
    lg = subs.add_parser("log", help="直しを1件記録")
    lg.add_argument("--case", required=True, help="下書きの案件名（例 20261107_次のご提案）")
    lg.add_argument("--recipient", required=True, help="宛先（例 今村さん・運営・LEAF）")
    lg.add_argument("--channel", required=True, choices=CHANNELS)
    lg.add_argument("--from-file", type=Path, required=True)
    lg.add_argument("--to-file", type=Path, required=True)
    lg.add_argument("--from-label", default="before")
    lg.add_argument("--to-label", default="after")
    lg.add_argument("--change-type", action="append", default=[], choices=CHANGE_TYPES)
    lg.add_argument("--reason", help="松野さんの言葉・理由（分からなければ省く＝質問として残す）")
    lg.add_argument("--rule-hint", help="次回にも効く形に言い換えたルール候補")
    lg.add_argument("--applied-rule", action="append", default=[], help="この下書きで効かせたルール番号")
    lg.add_argument("--final", action="store_true", help="送った最終版（action=sent）")
    out = lg.add_mutually_exclusive_group()
    out.add_argument("--dry-run", action="store_true")
    out.add_argument("--sql", action="store_true", help="INSERT 文を出す（DBには書かない）")
    cx = subs.add_parser("context", help="下書きの前に読む")
    cx.add_argument("--recipient", required=True)
    cx.add_argument("--limit", type=int, default=5)
    ps = subs.add_parser("push", help="下書きを Nody の「下書きを直す」に置く")
    ps.add_argument("--case", required=True)
    ps.add_argument("--recipient", required=True)
    ps.add_argument("--channel", required=True, choices=CHANNELS)
    ps.add_argument("--file", type=Path, required=True)
    ps.add_argument("--no-context", action="store_true", help="採用済みルールを AI に渡さない")
    ps.add_argument("--sql", action="store_true", help="INSERT 文を出す（DBには書かない）")
    pl = subs.add_parser("pull", help="直し終わった文面を受け取る")
    pl.add_argument("--id", required=True)
    args = ap.parse_args(argv)

    if args.command == "push":
        ctx = None if args.no_context else rules_context(args.recipient)
        row = draft_review_row(case=args.case, recipient=args.recipient, channel=args.channel,
                               text=args.file.read_text(encoding="utf-8"), context=ctx)
        if args.sql:
            print(draft_review_sql(row))
            return 0
        sb = _client()
        if sb is None:
            raise RuntimeError("JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY が必要です（--sql で INSERT 文だけ出せます）")
        res = sb.table("draft_reviews").insert(row).execute()
        rid = res.data[0]["id"]
        print(f"ID: {rid}\nNody: {NODY_URL}/drafts/{rid}")
        return 0

    if args.command == "pull":
        sb = _client()
        if sb is None:
            raise RuntimeError("JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY が必要です")
        res = sb.table("draft_reviews").select("*").eq("id", args.id).limit(1).execute()
        if not res.data:
            raise ValueError("その ID の下書きはありません")
        print(pull_text(res.data[0]), end="")
        return 0

    if args.command == "context":
        print(context_text(args.recipient, fetch_recent(args.recipient, args.limit)), end="")
        return 0

    row = build_row(
        case=args.case, recipient=args.recipient, channel=args.channel,
        before=args.from_file.read_text(encoding="utf-8"), after=args.to_file.read_text(encoding="utf-8"),
        from_label=args.from_label, to_label=args.to_label, change_types=args.change_type,
        reason=args.reason, rule_hint=args.rule_hint, final=args.final,
    )
    if args.applied_rule:
        row["payload"]["applied_rules"] = args.applied_rule
    if args.dry_run:
        print(json.dumps(row, ensure_ascii=False, indent=2))
    elif args.sql:
        print(to_sql(row))
    else:
        print(insert(row))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, RuntimeError) as exc:
        raise SystemExit(str(exc))
