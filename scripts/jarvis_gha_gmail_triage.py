#!/usr/bin/env python3
"""
Jarvis: GHA / クラウド向け Gmail（admin）差分トリアージ → Supabase triage_items

Mac の OneDrive 取込に依存せず、admin INBOX の未返信候補を upsert する。
パートナー MD 全文・CHRLINE は対象外（Mac 残）。

  # ローカル dry-run
  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  python scripts/jarvis_gha_gmail_triage.py --dry-run --limit 5

  # 本番 push
  python scripts/jarvis_gha_gmail_triage.py --push --limit 20

GHA では GMAIL_CREDENTIALS_B64 / GMAIL_ADMIN_TOKEN_B64 をファイルに展開してから実行。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
MANUAL = REPO / "215_kamiooya" / "C1_cursor" / "1b_Cursorマニュアル"
CONTACT = (
    Path.home()
    / "Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部"
    / "C2_ルーティン作業/26_パートナー社への相談/000_共通/連絡先一覧.yaml"
)
# CI: checkout 内の連絡先コピーがあれば使う
CONTACT_CI = (
    REPO
    / "215_kamiooya/C1_cursor/1b_Cursorマニュアル/連絡先一覧.snapshot.yaml"
)


def now_iso() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S%z")


def resolve_contact() -> Path:
    if CONTACT.is_file():
        return CONTACT
    if CONTACT_CI.is_file():
        return CONTACT_CI
    # 最小フォールバック（パートナー除外なしで動くが推奨しない）
    return CONTACT


def maybe_gemini_draft(subject: str, body: str, from_email: str) -> str | None:
    key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if not key:
        return None
    try:
        import urllib.request

        model = os.environ.get("GEMINI_MODEL") or "gemini-flash-latest"
        prompt = (
            "あなたは秘書です。次のメールに対する短い日本語の返信下書きを1通だけ書いてください。"
            "挨拶と要点、次のアクション提案まで。署名は不要。\n\n"
            f"From: {from_email}\nSubject: {subject}\n\n{body[:2500]}"
        )
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={key}"
        )
        payload = json.dumps(
            {"contents": [{"parts": [{"text": prompt}]}]}
        ).encode()
        req = urllib.request.Request(
            url, data=payload, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.load(r)
        parts = (
            data.get("candidates")
            or [{}]
        )[0].get("content", {}).get("parts") or []
        text = "".join(p.get("text") or "" for p in parts).strip()
        return text or None
    except Exception as e:
        print(f"# gemini draft skipped: {e}", file=sys.stderr)
        return None


def candidates_to_rows(cands: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sys.path.insert(0, str(REPO / "scripts"))
    from jarvis_night_triage_general import classify_general_kind

    rows = []
    for c in cands:
        draft = maybe_gemini_draft(
            c.get("subject") or "",
            c.get("body") or "",
            c.get("from_email") or "",
        )
        # カード上の「要約」にはしない。全文は original_body。短いメモのみ。
        body_full = c.get("body") or ""
        summary = f"（本文 {len(body_full)} 文字・全文はカード内）" if body_full else ""
        kind = c.get("kind") or classify_general_kind(
            c.get("subject") or "",
            body_full,
            c.get("from_email") or "",
        )
        priority = "high" if kind == "mail" else "low"
        if c.get("priority") in ("high", "med", "low"):
            # candidate 側の明示を優先（mail=high / skim=low）
            if kind == "mail":
                priority = "high"
            elif kind == "skim":
                priority = "low"
        rows.append(
            {
                "id": f"gha-{c['id']}",
                "lane": "general",
                "kind": kind,
                "status": "pending",
                "partner": c.get("partner") or c.get("partner_name"),
                "folder": c.get("folder") or None,
                "subject": c.get("subject"),
                "received_at": c.get("received_at"),
                "summary": summary or None,
                "draft_text": draft if kind == "mail" else None,
                "original_body": (c.get("body") or "")[:8000] or None,
                "priority": priority,
                "channel": c.get("channel") or "gmail",
                "account": "admin",
                "gmail_thread_id": c.get("gmail_thread_id"),
                "gmail_message_id": c.get("gmail_message_id"),
                "from_email": c.get("from_email"),
                "payload": {
                    "source": "gha_gmail_triage",
                    "message_id_header": c.get("message_id_header"),
                    "ingest_kind": kind,
                },
                "updated_at": now_iso(),
            }
        )
    return rows


def push_rows(rows: list[dict[str, Any]]) -> int:
    from supabase import create_client

    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_* 未設定")
    sb = create_client(url, key)
    # Web で閉じた行は pending に戻さない
    PROTECTED = {"sent", "skipped", "snoozed", "done"}
    remote_map: dict[str, str] = {}
    try:
        r = (
            sb.table("triage_items")
            .select("id,status")
            .in_("status", list(PROTECTED))
            .execute()
        )
        remote_map = {str(x["id"]): str(x["status"]) for x in (r.data or [])}
    except Exception as e:
        print(f"# protected merge skipped: {e}", file=sys.stderr)
    for row in rows:
        rid = row["id"]
        if rid in remote_map and row.get("status") == "pending":
            row["status"] = remote_map[rid]
    n = 0
    for i in range(0, len(rows), 40):
        chunk = rows[i : i + 40]
        sb.table("triage_items").upsert(chunk, on_conflict="id").execute()
        n += len(chunk)
    meta = now_iso()
    sb.table("sync_meta").upsert(
        [
            {"key": "gha_triage_pushed_at", "value": meta, "updated_at": meta},
            {"key": "triage_source", "value": "gha", "updated_at": meta},
        ],
        on_conflict="key",
    ).execute()
    return n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--push", action="store_true")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--lookback-days", type=int, default=7)
    args = ap.parse_args(argv)

    sys.path.insert(0, str(REPO / "scripts"))
    from jarvis_night_triage_general import find_general_unreplied

    contact = resolve_contact()
    print(f"# contact={contact} exists={contact.is_file()}", file=sys.stderr)
    cands = find_general_unreplied(
        contact_yaml=contact,
        lookback_days=args.lookback_days,
        max_threads=args.limit,
    )
    print(f"# candidates={len(cands)}", file=sys.stderr)
    rows = candidates_to_rows(cands[: args.limit])
    for r in rows[:5]:
        print(
            f"  - {r['received_at']} {r.get('from_email')} | {r.get('subject')}",
            file=sys.stderr,
        )
    if args.dry_run or not args.push:
        print(json.dumps({"count": len(rows), "dry_run": True}, ensure_ascii=False))
        return 0
    n = push_rows(rows)
    # 既存 pending の物件紹介を KURASHIFT 担当として除外（要確認から外す）
    try:
        from supabase import create_client
        from jarvis_night_triage_general import skip_pending_kurashift_property_triage

        url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
        key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
        if url and key:
            # GHA 上ではローカル token が無いことがある → status のみ skip
            mark_read = Path(
                os.environ.get("GMAIL_ADMIN_TOKEN_PATH")
                or (MANUAL / "token_livingsupport.json")
            ).is_file()
            cleaned = skip_pending_kurashift_property_triage(
                create_client(url, key),
                mark_gmail_read=mark_read,
                dry_run=False,
            )
            print(
                f"# cleanup_re_pending matched={cleaned.get('matched')} "
                f"read_ok={cleaned.get('gmail_read_ok')}",
                file=sys.stderr,
            )
    except Exception as e:
        print(f"# cleanup_re_pending skipped: {e}", file=sys.stderr)
    # ダイジェスト更新（失敗しても triage push は成功扱い）
    try:
        sys.path.insert(0, str(REPO / "scripts"))
        from jarvis_other_mail_digest import build_and_maybe_push

        build_and_maybe_push(do_push=True, use_llm=True, reclassify=True)
    except Exception as e:
        print(f"# other_mail_digest skipped: {e}", file=sys.stderr)
    print(json.dumps({"upserted": n, "source": "gha"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
