#!/usr/bin/env python3
"""千三つ — 不動産会社への第一問い合わせ（From=estate）／返信取込／運営相談パック。

使用アカウント: estate / Gmail API（token_estate.json。テンプレ YAML 参照）
既存 admin スレッドは poll 時 payload.account=mail_admin で admin token にフォールバック。
対外送信は UI 確認後のジョブのみ（取込時は送らない）。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_re_inquiry.py --preview-deal-id <uuid>
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_re_inquiry.py --send-deal-id <uuid> --to 'a@b.com' --i-confirm-send
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_re_inquiry.py --poll-replies
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_re_inquiry.py --build-ops-pack --deal-id <uuid>
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path
from typing import Any

import yaml
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

REPO = Path(__file__).resolve().parents[1]
MANUAL = REPO / "215_kamiooya" / "C1_cursor" / "1b_Cursorマニュアル"
TEMPLATE_PATH = REPO / "config" / "kurashift_re_inquiry_template.yaml"
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
]
ADMIN_TOKEN = "token_livingsupport.json"
ESTATE_TOKEN = "token_estate.json"
ACCOUNT_EMAIL = {
    "admin": "admin@livingsupport-matsu.co.jp",
    "estate": "matsuno.estate@gmail.com",
}
ACCOUNT_PAYLOAD = {
    "admin": "mail_admin",
    "estate": "mail_estate",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sb_client() -> Any:
    url = os.environ.get("JARVIS_SUPABASE_URL")
    key = os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY が必要です")
    from supabase import create_client

    return create_client(url, key)


def load_template() -> dict[str, Any]:
    return yaml.safe_load(TEMPLATE_PATH.read_text(encoding="utf-8")) or {}


def _token_name_for_account(account: str) -> str:
    acct = (account or "").strip().lower()
    if acct == "admin":
        return ADMIN_TOKEN
    if acct == "estate":
        return ESTATE_TOKEN
    tmpl = load_template()
    return str(tmpl.get("from_token") or ESTATE_TOKEN)


def gmail_for_account(account: str):
    token_name = _token_name_for_account(account)
    path = MANUAL / token_name
    if not path.is_file():
        raise FileNotFoundError(path)
    creds = Credentials.from_authorized_user_file(str(path), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def default_from_account() -> str:
    return str(load_template().get("from_account") or "estate")


def estate_email() -> str:
    return ACCOUNT_EMAIL["estate"]


def account_for_deal_with_sb(sb: Any, deal: dict[str, Any]) -> str:
    for m in list_messages(sb, deal):
        payload = m.get("payload") or {}
        if payload.get("account") == "mail_admin":
            return "admin"
        if payload.get("account") == "mail_estate":
            return "estate"
    sj = sj_of(deal)
    if sj.get("account") == "mail_admin":
        return "admin"
    return default_from_account()


def is_self_email(from_email: str) -> bool:
    addr = (from_email or "").strip().lower()
    if not addr:
        return False
    if addr.endswith("@livingsupport-matsu.co.jp"):
        return True
    if addr == estate_email():
        return True
    if addr == ACCOUNT_EMAIL["admin"]:
        return True
    return False


def header_map(headers: list[dict] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for h in headers or []:
        out[(h.get("name") or "").lower()] = h.get("value") or ""
    return out


def decode_body(payload: dict) -> str:
    parts = [payload]
    texts: list[str] = []
    while parts:
        p = parts.pop()
        body = p.get("body") or {}
        data = body.get("data")
        mime = (p.get("mimeType") or "").lower()
        if data and ("text/plain" in mime or not p.get("parts")):
            try:
                texts.append(base64.urlsafe_b64decode(data).decode("utf-8", "replace"))
            except Exception:
                pass
        for ch in p.get("parts") or []:
            parts.append(ch)
    return "\n".join(texts)[:12000]


def get_deal(sb: Any, deal_id: str) -> dict[str, Any]:
    resp = (
        sb.table("kurashift_re_deals")
        .select("*")
        .eq("id", deal_id)
        .limit(1)
        .execute()
    )
    rows = resp.data or []
    if not rows:
        raise SystemExit(f"deal not found: {deal_id}")
    return rows[0]


def sj_of(deal: dict[str, Any]) -> dict[str, Any]:
    sj = deal.get("summary_json")
    return dict(sj) if isinstance(sj, dict) else {}


def inquiry_fields(deal: dict[str, Any]) -> dict[str, Any]:
    """列があれば列、なければ summary_json（DDL 未適用時の箱）。"""
    sj = sj_of(deal)
    status = deal.get("inquiry_status") or sj.get("inquiry_status") or "none"
    thread = deal.get("inquiry_thread_id") or sj.get("inquiry_thread_id")
    sent = deal.get("inquiry_sent_at") or sj.get("inquiry_sent_at")
    return {"inquiry_status": status, "inquiry_thread_id": thread, "inquiry_sent_at": sent}


def update_inquiry(sb: Any, deal: dict[str, Any], **fields: Any) -> dict[str, Any]:
    """列更新を試し、失敗したら summary_json に書く。"""
    deal_id = deal["id"]
    sj = sj_of(deal)
    for k, v in fields.items():
        if k.startswith("inquiry_") or k in ("summary_json",):
            continue
    patch_cols = {k: v for k, v in fields.items() if k != "summary_json"}
    for k, v in list(patch_cols.items()):
        if k.startswith("inquiry_"):
            sj[k] = v
    sj_patch = fields.get("summary_json")
    if isinstance(sj_patch, dict):
        sj.update(sj_patch)
    payload = {"updated_at": now_iso(), "summary_json": sj, **patch_cols}
    try:
        sb.table("kurashift_re_deals").update(payload).eq("id", deal_id).execute()
        return payload
    except Exception:
        # 列が無い環境
        soft = {"updated_at": now_iso(), "summary_json": sj}
        sb.table("kurashift_re_deals").update(soft).eq("id", deal_id).execute()
        return soft


def messages_table_ok(sb: Any) -> bool:
    try:
        sb.table("kurashift_re_deal_messages").select("id").limit(1).execute()
        return True
    except Exception:
        return False


def insert_message(sb: Any, deal: dict[str, Any], row: dict[str, Any]) -> str:
    """DB 表があれば insert。無ければ summary_json.messages に追記。"""
    if messages_table_ok(sb):
        try:
            ins = sb.table("kurashift_re_deal_messages").insert(row).execute()
            return (ins.data or [{}])[0].get("id") or "ok"
        except Exception as e:
            # unique gmail_id
            if "duplicate" in str(e).lower() or "23505" in str(e):
                return "dup"
            raise
    sj = sj_of(deal)
    msgs = list(sj.get("messages") or [])
    gid = row.get("gmail_id")
    if gid and any(m.get("gmail_id") == gid for m in msgs):
        return "dup"
    msgs.append({**row, "id": row.get("gmail_id") or f"local-{len(msgs)+1}"})
    update_inquiry(sb, deal, summary_json={"messages": msgs})
    return "json"


def list_messages(sb: Any, deal: dict[str, Any]) -> list[dict[str, Any]]:
    if messages_table_ok(sb):
        resp = (
            sb.table("kurashift_re_deal_messages")
            .select("*")
            .eq("deal_id", deal["id"])
            .order("occurred_at")
            .execute()
        )
        return list(resp.data or [])
    return list(sj_of(deal).get("messages") or [])


def build_preview(deal: dict[str, Any], *, to_email: str | None = None) -> dict[str, Any]:
    tmpl = load_template()
    title = str(deal.get("title") or "物件")
    max_len = int(tmpl.get("title_short_max") or 40)
    title_short = title if len(title) <= max_len else title[: max_len - 1] + "…"
    subject = str(tmpl.get("subject_template") or "物件資料のご依頼（{title_short}）").format(
        title_short=title_short
    )
    company = (os.environ.get("COMPANY_NAME") or "").strip()
    rep = (os.environ.get("REPRESENTATIVE_NAME") or "").strip()
    personal = (os.environ.get("PERSONAL_NAME") or "").strip()
    from_acct = str(tmpl.get("from_account") or "estate")
    if from_acct == "estate" and personal:
        sig_t = personal
    else:
        sig_t = str(tmpl.get("signature_template") or "").format(
            company_name=company, representative_name=rep
        ).strip()
    body = str(tmpl.get("body_template") or "").format(signature=sig_t).strip()
    sj = sj_of(deal)
    if not to_email:
        _, parsed = parseaddr(str(sj.get("from") or ""))
        to_email = (parsed or "").strip()
    return {
        "deal_id": deal["id"],
        "to": to_email,
        "subject": subject,
        "body": body,
        "from_account": tmpl.get("from_account") or "admin",
        "ops_notion_url": tmpl.get("ops_notion_url") or "",
    }


def send_inquiry(
    sb: Any,
    deal_id: str,
    *,
    to_email: str,
    subject: str | None,
    body: str | None,
    confirm: bool,
    dry_run: bool,
) -> dict[str, Any]:
    from_acct = default_from_account()
    print(f"使用アカウント: {from_acct} / Gmail API（第一問い合わせ送信）")
    deal = get_deal(sb, deal_id)
    prev = build_preview(deal, to_email=to_email)
    to_email = (to_email or prev["to"] or "").strip()
    subject = (subject or prev["subject"]).strip()
    body = (body or prev["body"]).strip()
    if not to_email or "@" not in to_email:
        return {"ok": False, "error": "to email required"}
    if not confirm and not dry_run:
        return {"ok": False, "error": "need --i-confirm-send or --dry-run"}

    # at-most-once: 既に送信済みならスキップ
    existing = list_messages(sb, deal)
    for m in existing:
        if (
            m.get("kind") == "first_inquiry"
            and m.get("direction") == "outbound"
            and m.get("gmail_id")
        ):
            out = {
                "ok": True,
                "skipped": "already_sent",
                "deal_id": deal_id,
                "gmail_id": m.get("gmail_id"),
                "thread_id": m.get("thread_id"),
            }
            print(f"KURASHIFT_RESULT:{json.dumps(out, ensure_ascii=False)}")
            return out

    fields = inquiry_fields(deal)
    if fields.get("inquiry_status") in ("awaiting_reply", "has_reply"):
        out = {"ok": True, "skipped": "inquiry_already_active", "deal_id": deal_id}
        print(f"KURASHIFT_RESULT:{json.dumps(out, ensure_ascii=False)}")
        return out

    result = {
        "ok": True,
        "deal_id": deal_id,
        "to": to_email,
        "subject": subject,
        "dry_run": dry_run,
    }
    if dry_run:
        result["body_preview"] = body[:400]
        print(f"KURASHIFT_RESULT:{json.dumps(result, ensure_ascii=False)}")
        return result

    # 先に sending を書いてから送る（クラッシュ時の二重送信を抑止）
    update_inquiry(sb, deal, inquiry_status="sending")
    deal = get_deal(sb, deal_id)

    try:
        svc = gmail_for_account(from_acct)
        msg = MIMEText(body, _charset="utf-8")
        msg["to"] = to_email
        msg["subject"] = subject
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
        sent = (
            svc.users()
            .messages()
            .send(userId="me", body={"raw": raw})
            .execute()
        )
    except Exception as e:
        update_inquiry(sb, deal, inquiry_status="draft")
        out = {"ok": False, "error": f"send_failed:{type(e).__name__}:{e}", "deal_id": deal_id}
        print(f"KURASHIFT_RESULT:{json.dumps(out, ensure_ascii=False)}")
        return out

    gmail_id = sent.get("id")
    thread_id = sent.get("threadId")
    from_email = ACCOUNT_EMAIL.get(from_acct, estate_email())
    payload_account = ACCOUNT_PAYLOAD.get(from_acct, "mail_estate")
    insert_message(
        sb,
        deal,
        {
            "deal_id": deal_id,
            "direction": "outbound",
            "kind": "first_inquiry",
            "gmail_id": gmail_id,
            "thread_id": thread_id,
            "from_email": from_email,
            "to_email": to_email,
            "subject": subject,
            "body_text": body,
            "occurred_at": now_iso(),
            "payload": {"account": payload_account},
        },
    )
    update_inquiry(
        sb,
        deal,
        inquiry_status="awaiting_reply",
        inquiry_thread_id=thread_id,
        inquiry_sent_at=now_iso(),
    )
    if deal.get("status") == "info":
        try:
            sb.table("kurashift_re_deals").update(
                {"status": "viewing", "updated_at": now_iso()}
            ).eq("id", deal_id).execute()
        except Exception:
            pass
    result.update(
        {
            "gmail_id": gmail_id,
            "thread_id": thread_id,
            "inquiry_status": "awaiting_reply",
        }
    )
    print(f"📎 inquiry_send: to={to_email} thread={thread_id}")
    print(f"KURASHIFT_RESULT:{json.dumps(result, ensure_ascii=False)}")
    return result


def poll_replies(sb: Any, *, deal_id: str | None = None, dry_run: bool = False) -> dict[str, Any]:
    print("使用アカウント: estate（主）+ admin（既存スレッド） / Gmail API（返信取込）")
    q = sb.table("kurashift_re_deals").select("*").limit(200)
    if deal_id:
        q = q.eq("id", deal_id)
    deals = q.execute().data or []
    svc_cache: dict[str, Any] = {}
    appended = 0
    scanned = 0
    for deal in deals:
        acct = account_for_deal_with_sb(sb, deal)
        if acct not in svc_cache:
            try:
                svc_cache[acct] = gmail_for_account(acct)
            except Exception as e:
                print(f"# gmail {acct}: {type(e).__name__}: {e}")
                continue
        svc = svc_cache[acct]
        payload_account = ACCOUNT_PAYLOAD.get(acct, "mail_estate")
        fields = inquiry_fields(deal)
        thread_id = fields.get("inquiry_thread_id")
        if not thread_id:
            # summary_json メッセージから推定
            msgs = list_messages(sb, deal)
            for m in msgs:
                if m.get("direction") == "outbound" and m.get("thread_id"):
                    thread_id = m["thread_id"]
                    break
        if not thread_id:
            continue
        scanned += 1
        try:
            full = (
                svc.users()
                .threads()
                .get(userId="me", id=thread_id, format="full")
                .execute()
            )
        except Exception as e:
            print(f"# thread {thread_id}: {type(e).__name__}: {e}")
            continue
        existing = {m.get("gmail_id") for m in list_messages(sb, deal) if m.get("gmail_id")}
        for m in full.get("messages") or []:
            mid = m.get("id")
            if not mid or mid in existing:
                continue
            payload = m.get("payload") or {}
            hm = header_map(payload.get("headers"))
            from_raw = hm.get("from", "")
            _, from_email = parseaddr(from_raw)
            from_email = (from_email or "").lower()
            is_self = is_self_email(from_email)
            direction = "outbound" if is_self else "inbound"
            kind = "first_inquiry" if is_self else "reply"
            date_hdr = hm.get("date", "")
            try:
                occurred = parsedate_to_datetime(date_hdr) if date_hdr else datetime.now(timezone.utc)
                if occurred.tzinfo is None:
                    occurred = occurred.replace(tzinfo=timezone.utc)
            except Exception:
                occurred = datetime.now(timezone.utc)
            row = {
                "deal_id": deal["id"],
                "direction": direction,
                "kind": kind,
                "gmail_id": mid,
                "thread_id": thread_id,
                "from_email": from_email,
                "to_email": parseaddr(hm.get("to", ""))[1],
                "subject": hm.get("subject") or "",
                "body_text": decode_body(payload),
                "occurred_at": occurred.isoformat(),
                "payload": {"account": payload_account},
            }
            if dry_run:
                print(f"  dry-run would add {direction} {mid} {row['subject'][:60]}")
                continue
            r = insert_message(sb, deal, row)
            if r != "dup":
                appended += 1
                if direction == "inbound":
                    update_inquiry(sb, deal, inquiry_status="has_reply")
                    deal = get_deal(sb, deal["id"])  # refresh sj
    out = {"ok": True, "scanned_threads": scanned, "appended": appended, "dry_run": dry_run}
    print(f"📎 inquiry_poll: scanned={scanned} appended={appended}")
    print(f"KURASHIFT_RESULT:{json.dumps(out, ensure_ascii=False)}")
    return out


def build_ops_pack(sb: Any, deal_id: str) -> dict[str, Any]:
    deal = get_deal(sb, deal_id)
    tmpl = load_template()
    msgs = list_messages(sb, deal)
    lines = [
        f"【千三つ・運営相談パック】{deal.get('title')}",
        f"deal_id: {deal_id}",
        f"status: {deal.get('status')} / inquiry: {inquiry_fields(deal).get('inquiry_status')}",
        f"area: {deal.get('area') or '—'} / structure: {deal.get('structure') or '—'}",
        f"price_man: {deal.get('price_man')} / yield: {deal.get('yield_pct')}",
        f"source: {deal.get('source')}",
        "",
    ]
    grok = sj_of(deal).get("grok")
    if isinstance(grok, dict) and grok:
        lines.extend(
            [
                "【Grok 調査要約】",
                f"  駐車場: {grok.get('parking') or '—'}",
                f"  倍率/方式: {grok.get('land_ratio') or '—'} ({grok.get('land_method') or '—'})",
                f"  土地値100%: {grok.get('land100') or '—'}",
                f"  人口: {grok.get('population_eval') or '—'}",
                f"  聞く価値: {grok.get('listen_value') or '—'} — {grok.get('reason_line') or ''}",
                "",
            ]
        )
    lines.extend(
        [
        "【Notion 購入判断メモ】",
        str(tmpl.get("ops_notion_url") or ""),
        "",
        "【メール経緯】",
        ]
    )
    for m in msgs:
        lines.append(
            f"— {m.get('occurred_at','')} [{m.get('direction')}/{m.get('kind')}] "
            f"{m.get('from_email')} → {m.get('to_email')}"
        )
        lines.append(f"件名: {m.get('subject')}")
        lines.append((m.get("body_text") or "")[:3000])
        lines.append("")
    body = "\n".join(lines)
    title = f"運営相談: {(deal.get('title') or '')[:80]}"
    meta = {
        "deal_id": deal_id,
        "notion_url": tmpl.get("ops_notion_url"),
        "source": "re_deal_ops_pack",
    }
    # lane=realestate（制約未更新なら general）
    try:
        ins = (
            sb.table("kurashift_consultations")
            .insert(
                {
                    "title": title,
                    "body": body,
                    "lane": "realestate",
                    "status": "open",
                    "metadata": meta,
                    "updated_at": now_iso(),
                }
            )
            .execute()
        )
    except Exception:
        ins = (
            sb.table("kurashift_consultations")
            .insert(
                {
                    "title": title,
                    "body": body,
                    "lane": "general",
                    "status": "open",
                    "metadata": {**meta, "lane_fallback": "general"},
                    "updated_at": now_iso(),
                }
            )
            .execute()
        )
    cid = (ins.data or [{}])[0].get("id")
    out = {"ok": True, "consultation_id": cid, "deal_id": deal_id, "message_count": len(msgs)}
    print(f"📎 ops_pack: consultation={cid} messages={len(msgs)}")
    print(f"KURASHIFT_RESULT:{json.dumps(out, ensure_ascii=False)}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview-deal-id", default="")
    ap.add_argument("--send-deal-id", default="")
    ap.add_argument("--to", default="")
    ap.add_argument("--subject", default="")
    ap.add_argument("--body", default="")
    ap.add_argument("--i-confirm-send", action="store_true")
    ap.add_argument("--poll-replies", action="store_true")
    ap.add_argument("--deal-id", default="", help="poll/pack の対象絞り込み")
    ap.add_argument("--build-ops-pack", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    sb = sb_client()

    if args.preview_deal_id:
        deal = get_deal(sb, args.preview_deal_id)
        prev = build_preview(deal, to_email=args.to or None)
        print(json.dumps(prev, ensure_ascii=False, indent=2))
        print(f"KURASHIFT_RESULT:{json.dumps({'ok': True, **prev}, ensure_ascii=False)}")
        return 0
    if args.send_deal_id:
        r = send_inquiry(
            sb,
            args.send_deal_id,
            to_email=args.to,
            subject=args.subject or None,
            body=args.body or None,
            confirm=args.i_confirm_send,
            dry_run=args.dry_run,
        )
        return 0 if r.get("ok") else 1
    if args.poll_replies:
        r = poll_replies(sb, deal_id=args.deal_id or None, dry_run=args.dry_run)
        return 0 if r.get("ok") else 1
    if args.build_ops_pack:
        if not args.deal_id:
            raise SystemExit("--deal-id required with --build-ops-pack")
        r = build_ops_pack(sb, args.deal_id)
        return 0 if r.get("ok") else 1
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
