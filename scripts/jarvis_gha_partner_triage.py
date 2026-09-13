#!/usr/bin/env python3
"""
GHA: OneDrive パートナー `5.やり取り.md`（Graph 読取）→
Gmail／Chatwork 未返信判定 → triage_items。

LINE／iMessage は対象外（Mac 夜間トリアージ残）。

  python scripts/jarvis_gha_partner_triage.py --dry-run --limit 10
  python scripts/jarvis_gha_partner_triage.py --push --limit 30
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
MANUAL = REPO / "215_kamiooya" / "C1_cursor" / "1b_Cursorマニュアル"
PARTNER_BASE_REL = (
    "215_神・大家さん倶楽部/C2_ルーティン作業/26_パートナー社への相談"
)
CONTACT_REL = f"{PARTNER_BASE_REL}/000_共通/連絡先一覧.yaml"
CONTACT_CI = MANUAL / "連絡先一覧.snapshot.yaml"

sys.path.insert(0, str(REPO / "scripts"))


def now_iso() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S%z")


def materialize_contact(tmp: Path) -> Path:
    from jarvis_onedrive_graph import graph_configured, read_file

    dest = tmp / "連絡先一覧.yaml"
    if graph_configured():
        try:
            dest.write_bytes(read_file("onedrive", CONTACT_REL))
            return dest
        except Exception as e:
            print(f"# contact graph fail: {e}", file=sys.stderr)
    local = Path.home() / "Library/CloudStorage/OneDrive-個人用" / CONTACT_REL
    if local.is_file():
        dest.write_bytes(local.read_bytes())
        return dest
    if CONTACT_CI.is_file():
        dest.write_bytes(CONTACT_CI.read_bytes())
        return dest
    raise SystemExit("連絡先一覧.yaml 不可")


def read_md(folder: str) -> str | None:
    from jarvis_onedrive_graph import graph_configured, read_file

    rel = f"{PARTNER_BASE_REL}/{folder}/5.やり取り.md"
    try:
        if graph_configured():
            return read_file("onedrive", rel).decode("utf-8", errors="replace")
        p = Path.home() / "Library/CloudStorage/OneDrive-個人用" / rel
        if p.is_file():
            return p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        print(f"# md skip {folder}: {e}", file=sys.stderr)
    return None


def maybe_gemini_judge(c: dict[str, Any]) -> dict[str, Any]:
    """needs_reply / priority / summary / draft_text。API 無ければヒューリスティック。"""
    key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    subj = c.get("subject") or ""
    body = (c.get("body") or "")[:2500]
    partner = c.get("partner_name") or c.get("folder") or ""
    if not key:
        # 簡易: 受信で終わる未返信は要返信扱い
        return {
            "needs_reply": True,
            "priority": "medium",
            "summary": (c.get("summary") or subj)[:120],
            "reason": "no_gemini_default_need",
            "draft_text": "",
        }
    try:
        import urllib.request

        model = os.environ.get("GEMINI_MODEL") or "gemini-flash-latest"
        prompt = (
            "あなたは秘書です。パートナーからのメール未返信候補を判定してください。\n"
            "JSONのみ返してください:"
            '{"needs_reply":bool,"priority":"high|medium|low","summary":"一文",'
            '"reason":"短く","draft_text":"要返信なら短い返信下書き。不要なら空"}。\n\n'
            f"Partner: {partner}\nSubject: {subj}\n\n{body}"
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
        parts = (data.get("candidates") or [{}])[0].get("content", {}).get("parts") or []
        text = "".join(p.get("text") or "" for p in parts).strip()
        # fence strip
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        obj = json.loads(text.strip())
        return {
            "needs_reply": bool(obj.get("needs_reply")),
            "priority": obj.get("priority") or "medium",
            "summary": (obj.get("summary") or "")[:200],
            "reason": (obj.get("reason") or "")[:200],
            "draft_text": (obj.get("draft_text") or "").strip(),
        }
    except Exception as e:
        print(f"# gemini judge fail: {e}", file=sys.stderr)
        return {
            "needs_reply": True,
            "priority": "medium",
            "summary": (c.get("summary") or subj)[:120],
            "reason": f"gemini_fail:{type(e).__name__}",
            "draft_text": "",
        }


def _has_gmail_route(p: dict[str, Any]) -> bool:
    return bool(p.get("emails") or p.get("email_domains") or p.get("to_name_hints"))


def _has_chatwork_route(p: dict[str, Any]) -> bool:
    if p.get("chatwork_room_id") or p.get("chatwork_room_ids"):
        return True
    rooms = p.get("chatwork_rooms")
    return isinstance(rooms, dict) and bool(rooms)


def candidates_from_partners(*, lookback_days: int, max_partners: int) -> list[dict[str, Any]]:
    import yaml
    from jarvis_night_triage import (
        find_unreplied,
        find_unreplied_chat,
        parse_yoritoori_text,
    )

    with tempfile.TemporaryDirectory(prefix="jarvis_gha_pt_") as td:
        contact = materialize_contact(Path(td))
        config = yaml.safe_load(contact.read_text(encoding="utf-8")) or {}
        partners = config.get("partners") if isinstance(config, dict) else []
        if not isinstance(partners, list):
            partners = []

        mail_entries: list[dict[str, Any]] = []
        chat_entries: list[dict[str, Any]] = []
        n = 0
        for p in partners:
            folder = (p.get("folder") or "").strip()
            name = (p.get("name") or folder).strip()
            if not folder:
                continue
            want_mail = _has_gmail_route(p)
            want_cw = _has_chatwork_route(p)
            if not want_mail and not want_cw:
                continue
            n += 1
            if n > max_partners:
                break
            text = read_md(folder)
            if not text:
                continue
            entries = parse_yoritoori_text(text, folder, name)
            if want_mail:
                mail_entries.extend(entries)
            if want_cw:
                chat_entries.extend(entries)

        cands = find_unreplied(mail_entries, lookback_days)
        # Chatwork のみ（LINE/iMessage は Mac）
        for c in find_unreplied_chat(chat_entries, lookback_days):
            if (c.get("channel") or "") == "Chatwork":
                cands.append(c)
        cands.sort(key=lambda x: x.get("received_at") or "", reverse=True)
        return cands


def row_from_candidate(c: dict[str, Any], judge: dict[str, Any]) -> dict[str, Any]:
    needs = bool(judge.get("needs_reply"))
    channel = (c.get("channel") or "Gmail").strip() or "Gmail"
    iid = c.get("id") or hashlib.sha1(
        f"{c.get('folder')}|{channel}|{c.get('received_at')}|{c.get('subject')}".encode()
    ).hexdigest()[:12]
    status = "pending" if needs else "skipped"
    kind = "chat" if channel == "Chatwork" else "mail"
    prefix = "gha-cw-" if channel == "Chatwork" else "gha-p-"
    return {
        "id": f"{prefix}{iid}",
        "lane": "partner",
        "kind": kind,
        "status": status,
        "partner": c.get("partner_name"),
        "folder": c.get("folder"),
        "subject": c.get("subject"),
        "received_at": c.get("received_at"),
        "summary": judge.get("summary") or c.get("summary"),
        "draft_text": judge.get("draft_text") if needs else None,
        "original_body": (c.get("body") or "")[:8000] or None,
        "priority": "high"
        if (judge.get("priority") or "").startswith("h")
        else ("low" if (judge.get("priority") or "").startswith("l") else "med"),
        "channel": channel,
        "account": "admin",
        "from_email": None,
        "payload": {
            "source": "gha_partner_triage",
            "reason": judge.get("reason"),
            "channel_raw": c.get("channel_raw") or c.get("channel"),
        },
        "updated_at": now_iso(),
    }


def push_rows(rows: list[dict[str, Any]]) -> int:
    from supabase import create_client

    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_* 未設定")
    sb = create_client(url, key)
    PROTECTED = {"sent", "skipped", "snoozed", "done"}
    remote_map: dict[str, str] = {}
    try:
        r = (
            sb.table("triage_items")
            .select("id,status")
            .in_("status", list(PROTECTED))
            .execute()
        )
        for row in r.data or []:
            remote_map[str(row.get("id"))] = str(row.get("status"))
    except Exception as e:
        print(f"# protect lookup soft-fail: {e}", file=sys.stderr)

    to_up: list[dict[str, Any]] = []
    for row in rows:
        rid = str(row.get("id") or "")
        if rid in remote_map and remote_map[rid] in PROTECTED:
            # 閉じ済みは pending に戻さない
            if row.get("status") == "pending":
                continue
        to_up.append(row)
    if not to_up:
        return 0
    # chunk
    n = 0
    for i in range(0, len(to_up), 40):
        chunk = to_up[i : i + 40]
        sb.table("triage_items").upsert(chunk, on_conflict="id").execute()
        n += len(chunk)
    return n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--push", action="store_true")
    ap.add_argument("--limit", type=int, default=30, help="判定する候補の上限")
    ap.add_argument("--lookback-days", type=int, default=14)
    ap.add_argument("--max-partners", type=int, default=80)
    args = ap.parse_args(argv)

    cands = candidates_from_partners(
        lookback_days=args.lookback_days, max_partners=args.max_partners
    )
    n_mail = sum(1 for c in cands if (c.get("channel") or "Gmail") == "Gmail")
    n_cw = sum(1 for c in cands if (c.get("channel") or "") == "Chatwork")
    print(
        f"# unreplied candidates: total={len(cands)} gmail={n_mail} chatwork={n_cw}",
        file=sys.stderr,
    )
    rows: list[dict[str, Any]] = []
    for c in cands[: args.limit]:
        judge = maybe_gemini_judge(c)
        print(
            f"# [{c.get('folder')}][{c.get('channel') or 'Gmail'}] "
            f"needs={judge.get('needs_reply')} {(c.get('subject') or '')[:50]}",
            file=sys.stderr,
        )
        rows.append(row_from_candidate(c, judge))
        if os.environ.get("GEMINI_API_KEY"):
            time.sleep(1.2)

    if args.dry_run or not args.push:
        print(f"📎 partner triage dry-run rows={len(rows)}")
        if rows:
            print(json.dumps(rows[0], ensure_ascii=False, indent=2)[:800])
        return 0

    n = push_rows(rows)
    print(f"📎 partner triage pushed={n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
