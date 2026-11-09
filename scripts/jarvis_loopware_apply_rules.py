#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""loopware で「採用」「取り消す」されたルールを、各社員のルール帳（learned_rules.md）へ反映する。

人は loopware で1回押すだけ。ここは機械が、1ルール=1コミットでルール帳を書き換える。
（PR 作成と自動マージは呼び出し側。ルール帳はテスト通過で自動マージしてよい種類）

  python scripts/jarvis_loopware_apply_rules.py --dry-run
  python scripts/jarvis_loopware_apply_rules.py --commit       # 1ルール=1コミット

読む: owner_decisions surface=rule_review
  rule_accept（payload.rule_line・employee・text・candidate_id）→ ## 確定ルール に足す（R<社員>-<連番>）
  rule_once  → 何もしない（今回だけ）
  rule_reject → 何もしない（候補側が8週間出さない）
  rule_revert（payload.rule_id）→ その行を消す
書く: 反映した行の payload に rule_id・book_applied_at（取り消しは book_reverted_at）
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))

import jarvis_learned_rules as lr  # noqa: E402

JST = ZoneInfo("Asia/Tokyo")
PLACEHOLDER = "（最大10行。まだありません）"


def next_rule_id(text: str, employee: str) -> str:
    nums = [int(n) for n in re.findall(rf"R{re.escape(employee)}-(\d+)", text)]
    return f"R{employee}-{(max(nums) + 1) if nums else 1:03d}"


def add_rule(text: str, *, employee: str, rule_line: str, today: str, evidence: list[Any], note: str) -> tuple[str, str]:
    """## 確定ルール の末尾に1行足す。戻り値: (新しい本文, ルール番号)"""
    rid = next_rule_id(text, employee)
    ev = ",".join(str(e) for e in evidence if e)[:80]
    parts = [rid, *[p.strip() for p in rule_line.split("|")], f"v1 {today}"]
    if ev:
        parts.append(f"根拠 {ev}")
    if note:
        parts.append(note.replace("|", "／")[:120])
    line = "- " + " | ".join(p for p in parts if p)
    lines = text.splitlines()
    try:
        start = next(i for i, l in enumerate(lines) if re.match(r"^##\s+確定ルール", l))
    except StopIteration:
        lines += ["", "## 確定ルール", ""]
        start = len(lines) - 2
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    body = [l for l in lines[start + 1 : end] if l.strip() != PLACEHOLDER]
    while body and not body[-1].strip():
        body.pop()
    while body and not body[0].strip():
        body.pop(0)
    new_section = ["", *body, line, ""]
    out = lines[: start + 1] + new_section + lines[end:]
    return "\n".join(out).rstrip("\n") + "\n", rid


def remove_rule(text: str, rule_id: str) -> tuple[str, bool]:
    lines = text.splitlines()
    kept = [l for l in lines if not re.match(rf"^\s*-\s+{re.escape(rule_id)}\s*\|", l)]
    return "\n".join(kept).rstrip("\n") + "\n", len(kept) != len(lines)


def _git_commit(path: Path, msg: str) -> None:
    subprocess.run(["git", "add", str(path)], check=True)
    subprocess.run(["git", "commit", "-q", "-m", msg], check=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--commit", action="store_true", help="1ルール=1コミット")
    args = ap.parse_args(argv)
    from jarvis_loopware_weekly import _sb  # noqa: PLC0415

    sb = _sb()
    res = (
        sb.table("owner_decisions").select("id,action,target_id,payload,decided_at")
        .eq("surface", "rule_review").in_("action", ["rule_accept", "rule_revert"])
        .order("decided_at").limit(200).execute()
    )
    today = datetime.now(JST).strftime("%Y-%m-%d")
    done = 0
    for r in res.data or []:
        pl = dict(r.get("payload") or {})
        emp = str(pl.get("employee") or "")
        path = lr.rulebook_path(emp)
        if not path or not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if r["action"] == "rule_accept" and not pl.get("book_applied_at") and pl.get("rule_line"):
            new, rid = add_rule(text, employee=emp, rule_line=str(pl["rule_line"]), today=today,
                                evidence=list(pl.get("evidence") or []), note=str(pl.get("text") or ""))
            book = lr.parse_rulebook(new, str(path))
            if book.warnings:
                print(f"# skip {r['id']}: {book.warnings}", file=sys.stderr)
                continue
            print(f"+ {path.relative_to(lr.REPO)} {rid} {pl['rule_line']}")
            if args.dry_run:
                continue
            path.write_text(new, encoding="utf-8")
            pl.update(rule_id=rid, book_applied_at=datetime.now(JST).isoformat(timespec="seconds"))
            if args.commit:
                _git_commit(path, f"rules({emp}): {rid} {pl.get('text') or pl['rule_line']}\n\nloopware で採用（判断ログ id={r['id']}）")
        elif r["action"] == "rule_revert" and not pl.get("book_reverted_at") and pl.get("rule_id"):
            new, hit = remove_rule(text, str(pl["rule_id"]))
            if not hit:
                continue
            print(f"- {path.relative_to(lr.REPO)} {pl['rule_id']}")
            if args.dry_run:
                continue
            path.write_text(new, encoding="utf-8")
            pl["book_reverted_at"] = datetime.now(JST).isoformat(timespec="seconds")
            if args.commit:
                _git_commit(path, f"rules({emp}): {pl['rule_id']} を取り消し\n\nloopware で取り消し（判断ログ id={r['id']}）")
        else:
            continue
        sb.table("owner_decisions").update({"payload": pl}).eq("id", r["id"]).execute()
        done += 1
    print(f"# applied {done}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
