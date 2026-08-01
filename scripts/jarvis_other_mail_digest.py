#!/usr/bin/env python3
"""
パートナー以外の pending メールからダイジェストを生成し sync_meta へ保存。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  python scripts/jarvis_other_mail_digest.py
  python scripts/jarvis_other_mail_digest.py --push
  python scripts/jarvis_other_mail_digest.py --no-llm --push

呼び出し元: jarvis_dashboard_push / jarvis_gha_gmail_triage（push 後）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
STATE_DIR = REPO / ".jarvis_state" / "night_triage"
OUT_PATH = STATE_DIR / "other_mail_digest.json"


def now_iso() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S%z")


def client():
    from supabase import create_client

    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY 未設定")
    return create_client(url, key)


def fetch_pending_other(sb) -> list[dict[str, Any]]:
    r = (
        sb.table("triage_items")
        .select(
            "id,lane,kind,status,partner,subject,summary,priority,from_email,received_at"
        )
        .eq("status", "pending")
        .neq("lane", "partner")
        .neq("kind", "activity")
        .order("received_at", desc=True)
        .limit(80)
        .execute()
    )
    return list(r.data or [])


def rule_digest(items: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(items)
    if n == 0:
        return {
            "generated_at": now_iso(),
            "pending_count": 0,
            "overview": "パートナー以外の未読はありません。",
            "action_items": [],
            "lines": [],
            "via": "rule",
        }
    domains: Counter[str] = Counter()
    for it in items:
        frm = (it.get("from_email") or it.get("partner") or "不明").strip()
        dom = frm.split("@")[-1] if "@" in frm else frm
        domains[dom] += 1
    top = "、".join(f"{d}×{c}" for d, c in domains.most_common(3))
    action: list[dict[str, Any]] = []
    for it in items:
        pri = (it.get("priority") or "").lower()
        if pri in ("high", "attention"):
            action.append(
                {
                    "id": it.get("id"),
                    "subject": it.get("subject") or "（件名なし）",
                    "from": it.get("from_email") or it.get("partner"),
                    "reason": "優先度ヒント: 要確認",
                }
            )
        if len(action) >= 5:
            break
    lines = []
    for it in items[:5]:
        who = it.get("from_email") or it.get("partner") or "—"
        lines.append(f"{who}: {it.get('subject') or '（件名なし）'}")
    return {
        "generated_at": now_iso(),
        "pending_count": n,
        "overview": (
            f"未読 {n} 件。主な差出: {top or '—'}。"
            "ざざっと見て、残したいものだけ開いてください。"
        ),
        "action_items": action,
        "lines": lines,
        "via": "rule",
    }


def gemini_digest(items: list[dict[str, Any]], api_key: str) -> dict[str, Any] | None:
    if not items or not api_key:
        return None
    models = [
        (os.environ.get("GEMINI_MODEL") or "").strip(),
        "gemini-flash-latest",
        "gemini-flash-lite-latest",
    ]
    models = [m for i, m in enumerate(models) if m and m not in models[:i]]

    catalog = []
    for it in items[:40]:
        catalog.append(
            {
                "id": it.get("id"),
                "from": it.get("from_email") or it.get("partner"),
                "subject": it.get("subject"),
                "summary": (it.get("summary") or "")[:160],
                "priority": it.get("priority"),
                "lane": it.get("lane"),
            }
        )
    prompt = f"""あなたは秘書です。パートナー以外の未読メール一覧から、ホーム画面用の短いダイジェストを作ってください。

入力（JSON）:
{json.dumps(catalog, ensure_ascii=False)}

次の JSON のみを返してください（Markdown不可）:
{{
  "overview": "全体の状況を2〜4文。どんなメールが来ているか。返信不要が多い旨も可。",
  "action_items": [
    {{"id": "対象のid", "subject": "件名", "from": "差出", "reason": "なぜ対応候補か（短く）"}}
  ],
  "lines": ["補足1行", "補足2行"]
}}

ルール:
- action_items は最大5件。本当に期限・依頼・確認待ちっぽいものだけ。なければ空配列。
- lines は最大5行。一覧の雰囲気が分かる短文。
- 捏造しない。id は入力にあるものだけ。
"""

    last_err = ""
    for model in models:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={api_key}"
        )
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 1024},
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            last_err = str(e)[:200]
            continue
        cands = data.get("candidates") or []
        if not cands:
            last_err = "empty candidates"
            continue
        parts = (((cands[0] or {}).get("content") or {}).get("parts")) or []
        text = "\n".join(
            p.get("text", "") for p in parts if isinstance(p, dict) and p.get("text")
        ).strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            m = re.search(r"\{[\s\S]*\}", text)
            if not m:
                last_err = "json parse"
                continue
            try:
                obj = json.loads(m.group(0))
            except json.JSONDecodeError:
                last_err = "json parse2"
                continue
        if not isinstance(obj, dict):
            continue
        ids = {str(it.get("id")) for it in items}
        actions = []
        for a in obj.get("action_items") or []:
            if not isinstance(a, dict):
                continue
            aid = str(a.get("id") or "")
            if aid and aid not in ids:
                continue
            actions.append(
                {
                    "id": aid or None,
                    "subject": a.get("subject") or "（件名なし）",
                    "from": a.get("from"),
                    "reason": a.get("reason") or "",
                }
            )
        lines = [str(x) for x in (obj.get("lines") or []) if str(x).strip()][:5]
        return {
            "generated_at": now_iso(),
            "pending_count": len(items),
            "overview": str(obj.get("overview") or "").strip()
            or rule_digest(items)["overview"],
            "action_items": actions[:5],
            "lines": lines,
            "via": f"gemini:{model}",
        }
    print(f"# digest llm failed: {last_err}", file=sys.stderr)
    return None


def push_digest(sb, digest: dict[str, Any]) -> None:
    meta = now_iso()
    sb.table("sync_meta").upsert(
        {
            "key": "other_mail_digest",
            "value": json.dumps(digest, ensure_ascii=False),
            "updated_at": meta,
        },
        on_conflict="key",
    ).execute()


def build_and_maybe_push(*, do_push: bool, use_llm: bool) -> dict[str, Any]:
    sb = client()
    items = fetch_pending_other(sb)
    digest = None
    if use_llm:
        key = (os.environ.get("GEMINI_API_KEY") or "").strip()
        digest = gemini_digest(items, key)
    if digest is None:
        digest = rule_digest(items)

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(digest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if do_push:
        push_digest(sb, digest)
        print(f"# other_mail_digest pushed pending={digest.get('pending_count')} via={digest.get('via')}", file=sys.stderr)
    else:
        print(f"# other_mail_digest dry pending={digest.get('pending_count')} via={digest.get('via')}", file=sys.stderr)
    return digest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="その他メール・ダイジェスト")
    ap.add_argument("--push", action="store_true", help="sync_meta へ保存")
    ap.add_argument("--no-llm", action="store_true", help="ルールのみ（Gemini なし）")
    args = ap.parse_args(argv)
    digest = build_and_maybe_push(do_push=args.push, use_llm=not args.no_llm)
    print(json.dumps(digest, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
