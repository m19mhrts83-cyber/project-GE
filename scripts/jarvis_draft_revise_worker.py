#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""下書きレビュー（Nody /drafts）の「まとめて直す」を Mac で処理する。

Nody（Vercel）は従量課金の AI API を呼ばない。画面は revise_request.status=queued を書くだけで、
このワーカー（launchd/cursor_revise_worker_runner.sh・45秒ごと）が Cursor Agent CLI（定額）で書き直す。
夜間トリアージの下書き見直しキュー（jarvis_triage_cursor_revise_worker.py）と同じ作り。

  1. queued を拾って running にする
  2. 箇所つきのダメ出し（声を文字にしたもの）＋採用済みルール（211 learned_rules.md）で直す
  3. 新しい版（by=ai）を足し、done にする。判断ログ owner_decisions（surface=draft_review, action=revise）に1行

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  python scripts/jarvis_draft_revise_worker.py            # 処理
  python scripts/jarvis_draft_revise_worker.py --dry-run  # 拾うだけ
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from jarvis_draft_decision_log import rules_context  # noqa: E402
from jarvis_owner_decision_log import contract_row  # noqa: E402

STALE_RUNNING_MIN = 15  # running のまま止まったもの（Mac が寝た等）は拾い直す


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def comments_note(comments: list[dict[str, Any]]) -> str:
    out = []
    for c in comments:
        q = str(c.get("quote") or "")
        out.append(f"「{q[:60]}」→ {c.get('text', '')}" if q else str(c.get("text", "")))
    return " / ".join(out)[:2000]


def build_prompt(*, text: str, comments: list[dict[str, Any]], recipient: str, channel: str, context: str | None) -> str:
    """apps/loopware/lib/draftCore.ts の buildRevisePrompt と同じ中身（Python 版）"""
    lines = []
    for i, c in enumerate(comments, 1):
        q = str(c.get("quote") or "")
        where = f"「{q[:300]}」の箇所" if q else "全体"
        lines.append(f"{i}. {where}: {str(c.get('text') or '')[:600]}")
    parts = [
        "あなたは松野さんの文面アシスタントです。松野さんのダメ出しに従って、下書きを直してください。",
        "",
        "守ること:",
        "- ダメ出しされた箇所と、それに伴って直す必要がある所だけを直す。ほかの文はそのまま残す（言い回しを勝手に変えない）",
        "- 声で話したダメ出しなので、言い間違いや「えーと」は意図をくんで読む",
        "- 事実・数字・名前は、ダメ出しで指示がない限り変えない。分からないことを作らない",
        "- 改行や記号（■、・）の形は元に合わせる",
        "- ファイルの読み書きやコマンドの実行はしない。答えだけを返す",
        "",
        f"宛先: {recipient}（{channel}）",
    ]
    if context:
        parts += ["", "前提・守るルール:", context[:3000], ""]
    parts += ["ダメ出し:", *lines, "", "下書き:", "<<<", text, ">>>", ""]
    parts.append(
        'JSON だけを返す。形: {"text":"直した全文","changes":[{"before":"直す前の短い抜き出し","after":"直した後",'
        '"why":"どのダメ出しに対応したか"}],"rule_hint":"次の下書きにも効きそうな一般化したルール（なければ空）"}'
    )
    return "\n".join(parts)


def parse_result(raw: str) -> dict[str, Any] | None:
    s = (raw or "").strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", s)
    if m:
        s = m.group(1).strip()
    a, b = s.find("{"), s.rfind("}")
    if a < 0 or b <= a:
        return None
    try:
        obj = json.loads(s[a : b + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict) or not isinstance(obj.get("text"), str) or not obj["text"].strip():
        return None
    changes = [
        {"before": str(c.get("before", "")), "after": str(c.get("after", "")), "why": str(c.get("why", ""))}
        for c in (obj.get("changes") or [])
        if isinstance(c, dict)
    ][:30]
    hint = obj.get("rule_hint")
    return {"text": obj["text"], "changes": changes, "rule_hint": hint.strip() if isinstance(hint, str) else ""}


def next_label(versions: list[dict[str, Any]]) -> str:
    n = 0
    for v in versions:
        m = re.fullmatch(r"v(\d+)", str(v.get("label", "")))
        if m:
            n = max(n, int(m.group(1)))
    return f"v{n + 1}"


def current(versions: list[dict[str, Any]]) -> dict[str, Any] | None:
    for v in reversed(versions):
        if not v.get("reverted"):
            return v
    return None


def revision_row(draft: dict[str, Any], base: dict[str, Any], new: dict[str, Any], comments: list[dict[str, Any]], hint: str) -> dict[str, Any]:
    """owner_decisions の1行（Nody の logRevision と同じ形）"""
    sm = difflib.SequenceMatcher(None, base["text"], new["text"])
    note = comments_note(comments)
    row = contract_row(
        surface="draft_review",
        action="revise",
        source="script:draft_revise_worker",
        target_type="draft",
        target_id=f"{draft['id']}:{base['label']}->{new['label']}",
        employee="211",
        subject=draft.get("case_name"),
        note=note or None,
        ai_proposal=base["text"][:4000],
        payload={
            "case": draft.get("case_name"),
            "recipient": draft.get("recipient"),
            "channel": draft.get("channel"),
            "draft_id": draft["id"],
            "version_from": base["label"],
            "version_to": new["label"],
            "by": "ai",
            "engine": "cursor",
            "comments": comments,
            "reason": note or None,
            "reason_missing": not note,
            "rule_hint": hint or None,
            "edit_ratio": round(1 - sm.ratio(), 3),
        },
        idem_key=f"draft:{draft['id']}:{base['label']}->{new['label']}:revise",
    )
    row["payload"] = {k: v for k, v in row["payload"].items() if v is not None}
    row.update({"partner": draft.get("recipient"), "channel": draft.get("channel"), "final_text": new["text"][:8000], "edited": True, "kind": "draft"})
    return row


def update_locked(sb, draft_id: str, change: Callable[[dict[str, Any]], dict[str, Any] | None]) -> dict[str, Any] | None:
    """読み直してから書く（画面からダメ出しが同時に届いても落とさない）"""
    for _ in range(5):
        res = sb.table("draft_reviews").select("*").eq("id", draft_id).limit(1).execute()
        if not res.data:
            return None
        row = res.data[0]
        patch = change(row)
        if patch is None:
            return row
        patch["updated_at"] = now_iso()
        up = sb.table("draft_reviews").update(patch).eq("id", draft_id).eq("updated_at", row["updated_at"]).execute()
        if up.data:
            return up.data[0]
    raise RuntimeError("同時更新が続いて保存できませんでした")


def process(sb, draft: dict[str, Any], generate: Callable[[str], str]) -> str:
    rr = dict(draft.get("revise_request") or {})
    did = draft["id"]

    def mark_running(row: dict[str, Any]):
        r = row.get("revise_request") or {}
        if r.get("requested_at") != rr.get("requested_at") or r.get("status") not in ("queued", "running"):
            return None  # 取り消された
        return {"revise_request": {**r, "status": "running", "started_at": now_iso()}}

    row = update_locked(sb, did, mark_running)
    if not row or (row.get("revise_request") or {}).get("status") != "running":
        return "skip"

    versions = row.get("versions") or []
    base = next((v for v in versions if v.get("label") == rr.get("base") and not v.get("reverted")), None) or current(versions)
    comments = rr.get("comments") or []
    ctx = "\n".join(x for x in (rules_context(row["recipient"]), row.get("context")) if x) or None
    try:
        if not base:
            raise RuntimeError("版がありません")
        result = parse_result(generate(build_prompt(text=base["text"], comments=comments, recipient=row["recipient"], channel=row["channel"], context=ctx)))
        if not result:
            raise RuntimeError("AI の返事を読めませんでした")
        if result["text"] == base["text"]:
            raise RuntimeError("AI が何も直しませんでした")
    except Exception as e:  # noqa: BLE001
        err = str(e)[:400]
        update_locked(sb, did, lambda r: {"revise_request": {**(r.get("revise_request") or {}), "status": "error", "error": err, "finished_at": now_iso()}})
        return f"error: {err}"

    new_box: dict[str, Any] = {}

    def save(r: dict[str, Any]):
        vs = list(r.get("versions") or [])
        new = {
            "label": next_label(vs),
            "text": result["text"][:20000],
            "at": now_iso(),
            "by": "ai",
            "base": base["label"],
            "comments": comments,
            "changes": result["changes"],
            "engine": "cursor",
        }
        new_box["v"] = new
        vs.append(new)
        return {"versions": vs, "revise_request": {**(r.get("revise_request") or {}), "status": "done", "finished_at": now_iso(), "result": new["label"]}}

    saved = update_locked(sb, did, save)
    new = new_box["v"]
    try:
        log = revision_row(saved or row, base, new, comments, result["rule_hint"])
        dup = sb.table("owner_decisions").select("id").eq("payload->>idem_key", log["payload"]["idem_key"]).limit(1).execute()
        if not dup.data:
            sb.table("owner_decisions").insert(log).execute()
    except Exception as e:  # noqa: BLE001 — 判断ログの失敗で直しは止めない
        print(f"# owner_decisions soft-fail: {e}", file=sys.stderr)
    return f"done {base['label']}->{new['label']}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=3)
    args = ap.parse_args(argv)
    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        print("# JARVIS_SUPABASE_* 未設定", file=sys.stderr)
        return 1
    from supabase import create_client

    sb = create_client(url, key)
    rows = (
        sb.table("draft_reviews").select("*").in_("revise_request->>status", ["queued", "running"])
        .order("updated_at").limit(args.limit * 2).execute().data or []
    )
    todo = []
    for r in rows:
        rr = r.get("revise_request") or {}
        if rr.get("status") == "running":
            started = rr.get("started_at") or ""
            try:
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(started.replace("Z", "+00:00"))).total_seconds() / 60
            except ValueError:
                age = STALE_RUNNING_MIN + 1
            if age < STALE_RUNNING_MIN:
                continue
        todo.append(r)
    todo = todo[: args.limit]
    if not todo:
        print("# draft revise: queued=0")
        return 0
    if args.dry_run:
        for r in todo:
            print(f"# would revise {r['id']} {r.get('case_name')}")
        return 0
    from jarvis_night_triage import cursor_generate  # noqa: PLC0415 — Mac にしか無い CLI を使う

    for r in todo:
        print(f"# draft revise {r['id']} {r.get('case_name')}: {process(sb, r, cursor_generate)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
