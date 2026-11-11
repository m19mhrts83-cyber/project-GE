#!/usr/bin/env python3
"""資料作成ループ（Nody /slides）をエージェントから動かす道具。AI は呼ばない（AI はこれを使うエージェント自身）。

使い方（~/git-repos で .env.jarvis_private を読んでから）:
  python apps/loopware/scripts/slides_loop.py state                      # いまのデッキ・選んだ内容・資料の基準（JSON）
  python apps/loopware/scripts/slides_loop.py put --file deck.json [--dry-run]   # 案や反映案を Nody に置く
  python apps/loopware/scripts/slides_loop.py log-fix --deck ID --before a.md --after b.md [--note ..] [--intent typo|intent]
  python apps/loopware/scripts/slides_loop.py export --deck ID           # そのデッキの判断ログ（slide_plan / slide_fix / slide_rule）

環境変数: JARVIS_SUPABASE_URL, JARVIS_SUPABASE_SERVICE_ROLE_KEY（値は表示しない）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

META_KEY = "loopware_slides"
ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
DECK_RE = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")


def env() -> tuple[str, str]:
    url = os.environ.get("JARVIS_SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL") or ""
    key = os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or ""
    if not url or not key:
        sys.exit("JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY が未設定です（.env.jarvis_private を読んでください）")
    return url.rstrip("/"), key


def rest(method: str, path: str, body=None, prefer: str | None = None):
    url, key = env()
    req = urllib.request.Request(f"{url}/rest/v1/{path}", method=method)
    req.add_header("apikey", key)
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("Content-Type", "application/json")
    if prefer:
        req.add_header("Prefer", prefer)
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    try:
        with urllib.request.urlopen(req, data=data, timeout=30) as r:
            raw = r.read().decode() or "null"
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        sys.exit(f"Supabase {method} {path.split('?')[0]} 失敗: {e.code} {e.read().decode()[:300]}")


def validate_deck(d: dict) -> list[str]:
    errs = []
    if not DECK_RE.match(str(d.get("id", ""))):
        errs.append("id は英数字と - _ . で80字まで（例 2026-11-dx-gojokai）")
    if not str(d.get("title", "")).strip():
        errs.append("title が空")
    if d.get("stage") not in ("plan", "review", "done"):
        errs.append("stage は plan / review / done")
    for p in d.get("plans", []) or []:
        if not ID_RE.match(str(p.get("id", ""))) or not str(p.get("label", "")).strip():
            errs.append(f"plans の id/label が不正: {p.get('id')}")
    if len(d.get("plans", []) or []) > 4:
        errs.append("plans は4つまで（3つ推奨）")
    for a in d.get("axes", []) or []:
        if not ID_RE.match(str(a.get("key", ""))) or len(a.get("options", []) or []) < 2:
            errs.append(f"axes の key/options が不正: {a.get('key')}")
    ids = [p.get("id") for p in d.get("proposals", []) or []]
    if len(ids) != len(set(ids)):
        errs.append("proposals の id が重複")
    for p in d.get("proposals", []) or []:
        if not ID_RE.match(str(p.get("id", ""))) or not str(p.get("text", "")).strip():
            errs.append(f"proposals の id/text が不正: {p.get('id')}")
    if d.get("stage") == "plan" and not d.get("plans"):
        errs.append("stage=plan なら plans が要る")
    if d.get("stage") == "review" and not d.get("proposals"):
        errs.append("stage=review なら proposals が要る")
    return errs


def adopted_rules(rows: list[dict]) -> list[dict]:
    last: dict[str, dict] = {}
    for r in sorted(rows, key=lambda x: x.get("decided_at") or ""):
        last[r["target_id"]] = r
    out = []
    for k, r in last.items():
        if r["action"] == "rule_accept":
            pl = r.get("payload") or {}
            out.append({"id": k, "text": pl.get("text"), "concept": pl.get("concept"), "why": pl.get("why"), "at": r.get("decided_at")})
    return sorted(out, key=lambda x: x["at"] or "", reverse=True)


def cmd_state(_a) -> None:
    meta = rest("GET", f"sync_meta?key=eq.{META_KEY}&select=value")
    deck = None
    if meta:
        try:
            deck = json.loads(meta[0]["value"]) if isinstance(meta[0]["value"], str) else meta[0]["value"]
        except Exception:
            deck = None
    rules = rest("GET", "owner_decisions?surface=eq.slide_rule&select=action,target_id,payload,decided_at&order=decided_at.desc&limit=500") or []
    plan = None
    if deck:
        got = rest("GET", f"owner_decisions?surface=eq.slide_plan&target_id=eq.{urllib.parse.quote(deck['id'])}&select=payload,note,decided_at&order=decided_at.desc&limit=1") or []
        plan = got[0] if got else None
    print(json.dumps({"deck": deck, "chosen": plan, "slide_rules": adopted_rules(rules)}, ensure_ascii=False, indent=2))


def cmd_put(a) -> None:
    with open(a.file, encoding="utf-8") as f:
        deck = json.load(f)
    deck.setdefault("created_at", time.strftime("%Y-%m-%dT%H:%M:%S%z"))
    errs = validate_deck(deck)
    if errs:
        sys.exit("デッキの形が不正:\n- " + "\n- ".join(errs))
    if a.dry_run:
        print(json.dumps(deck, ensure_ascii=False, indent=2))
        print("(dry-run: 書き込みません)")
        return
    rest("POST", "sync_meta?on_conflict=key", [{"key": META_KEY, "value": json.dumps(deck, ensure_ascii=False)}], prefer="resolution=merge-duplicates,return=minimal")
    print(f"置きました: {deck['id']}（stage={deck['stage']}）→ https://jarvis-loopware.vercel.app/slides")


def cmd_log_fix(a) -> None:
    if not DECK_RE.match(a.deck):
        sys.exit("--deck が不正")
    before = open(a.before, encoding="utf-8").read()
    after = open(a.after, encoding="utf-8").read()
    row = {
        "surface": "slide_fix",
        "action": "comment",
        "source": "script",
        "target_type": "slide_deck",
        "target_id": a.deck,
        "subject": a.subject,
        "ai_proposal": before[:4000],
        "final_text": after[:8000],
        "edited": before != after,
        "note": (a.note or None),
        "payload": {
            "v": 1,
            "idem_key": f"slide-fix-{uuid.uuid4()}",
            "outcome": "note",
            "deck_id": a.deck,
            "fix_kind": a.intent,  # typo（打ち間違い）と intent（意図のある直し）を混ぜない
            "files": {"before": os.path.basename(a.before), "after": os.path.basename(a.after)},
        },
    }
    if a.dry_run:
        print(json.dumps({k: v for k, v in row.items() if k not in ("ai_proposal", "final_text")}, ensure_ascii=False, indent=2))
        return
    rest("POST", "owner_decisions", row, prefer="return=minimal")
    print(f"直しを記録しました: {a.deck}（{a.intent}）")


def cmd_export(a) -> None:
    d = urllib.parse.quote(a.deck)
    rows = rest(
        "GET",
        "owner_decisions?surface=in.(slide_plan,slide_fix,slide_rule)"
        f"&or=(target_id.eq.{d},target_id.like.{d}:*)"
        "&select=id,surface,action,target_id,subject,ai_proposal,final_text,note,payload,decided_at&order=decided_at.asc&limit=500",
    )
    print(json.dumps(rows, ensure_ascii=False, indent=2))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("state")
    p = sp.add_parser("put")
    p.add_argument("--file", required=True)
    p.add_argument("--dry-run", action="store_true")
    p = sp.add_parser("log-fix")
    p.add_argument("--deck", required=True)
    p.add_argument("--before", required=True)
    p.add_argument("--after", required=True)
    p.add_argument("--subject")
    p.add_argument("--note")
    p.add_argument("--intent", choices=["intent", "typo"], default="intent")
    p.add_argument("--dry-run", action="store_true")
    p = sp.add_parser("export")
    p.add_argument("--deck", required=True)
    a = ap.parse_args()
    {"state": cmd_state, "put": cmd_put, "log-fix": cmd_log_fix, "export": cmd_export}[a.cmd](a)


if __name__ == "__main__":
    main()
