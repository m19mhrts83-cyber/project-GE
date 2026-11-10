#!/usr/bin/env python3
"""コミュニケーション台帳（comm hub）— メールの取込（パートナー以外）。

設計: Claude Doc「コミュニケーション集約DB 設計案」Phase 4 ＋「自分の足跡」（2026-11-10 松野さん了承）。
パートナーとのメールは 5.やり取り.md 経由で jarvis_comm_hub.py が入れる。ここではそれ以外を入れる。

  ingest-triage : 仕分け済みの要確認メール（triage_items lane=general kind=mail）→ category=inquiry
                  triage_items.comm_item_id と comm_links(triage_item) でつなぐ
  ingest-sent   : 自分が送ったメール（Gmail「送信済み」）→ category=self, direction=outbound
                  宛先がパートナーのものは md 側で入るので入れない。認証コード・パスワード系は入れない

台帳は「書き足すだけ」（既存行は触らない）。出どころは source_ref に Gmail の id を残す。

  ~/selenium_env/venv/bin/python scripts/jarvis_comm_hub_mail.py ingest-triage --days 120 --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_comm_hub_mail.py ingest-triage --apply
  ~/selenium_env/venv/bin/python scripts/jarvis_comm_hub_mail.py ingest-sent --account admin --account estate --days 30 --apply
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta
from email.utils import getaddresses, parseaddr
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

MANUAL_DIR = REPO / "215_kamiooya" / "C1_cursor" / "1b_Cursorマニュアル"
if not (MANUAL_DIR / "token_livingsupport.json").is_file():
    # worktree にはトークン（git 管理外）が無い → Mac の本線 checkout を使う
    _main = Path.home() / "git-repos" / "215_kamiooya" / "C1_cursor" / "1b_Cursorマニュアル"
    if _main.is_dir():
        MANUAL_DIR = _main
TOKEN_BY_ACCOUNT = {
    "admin": "token_livingsupport.json",
    "estate": "token_estate.json",
}
BODY_MAX = 8000

# 台帳に絶対に入れない（設計書「取込ゲート」: 銀行・認証コード・パスワード系）
SECRET_RE = re.compile(
    r"(確認コード|認証コード|ワンタイム|OTP|パスワード|password|暗証|口座番号|"
    r"カード番号|verification code|security code|2段階|二段階)",
    re.I,
)

# triage_items.status → comm_items.work_status
WORK_BY_TRIAGE = {
    "pending": "needs_reply",
    "sent": "done",
    "skipped": "no_action",
    "todoist": "waiting",
    "later": "waiting",
}


# ------------------------------------------------------------------ 共通


def _parse_jst(s: str) -> datetime | None:
    s = (s or "").strip()
    for fmt in ("%Y/%m/%d %H:%M", "%Y-%m-%d %H:%M", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=JST)
        except ValueError:
            continue
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=JST)
    except ValueError:
        return None


def is_secret_mail(subject: str, body: str) -> bool:
    return bool(SECRET_RE.search(subject or "") or SECRET_RE.search((body or "")[:600]))


def _obj(x: Any) -> dict[str, Any]:
    if isinstance(x, dict):
        return x
    if isinstance(x, str):
        try:
            v = json.loads(x)
            return v if isinstance(v, dict) else {}
        except ValueError:
            return {}
    return {}


# ------------------------------------------------------------------ triage → inquiry


def item_from_triage(t: dict[str, Any]) -> dict[str, Any] | None:
    """triage_items（general/mail）の1行 → comm_items 行。日時が読めなければ None。"""
    occurred = _parse_jst(str(t.get("received_at") or "")) or _parse_jst(str(t.get("created_at") or ""))
    if occurred is None:
        return None
    subject = str(t.get("subject") or "")
    body = str(t.get("original_body") or "")[:BODY_MAX]
    if is_secret_mail(subject, body):
        return None
    account = str(t.get("account") or "admin")
    msg_id = str(t.get("gmail_message_id") or "")
    external_id = f"gmail:{msg_id}" if msg_id else f"triage:{t['id']}"
    name = str(t.get("partner") or t.get("from_email") or "")
    status = str(t.get("status") or "pending")
    payload = _obj(t.get("payload"))
    return {
        "channel": "gmail",
        "account": account,
        "external_id": external_id,
        "thread_key": f"gmail:{t.get('gmail_thread_id')}" if t.get("gmail_thread_id") else None,
        "occurred_at": occurred.isoformat(),
        "direction": "inbound",
        "party_id": None,
        "category": "inquiry",
        "tags": [x for x in [str(t.get("channel") or ""), str(payload.get("source") or "")] if x][:4],
        "ingest_status": "ready",
        "work_status": WORK_BY_TRIAGE.get(status, "new"),
        "priority": t.get("priority"),
        "subject": subject[:500] or None,
        "summary": (str(t.get("summary") or "")[:500]) or None,
        "body_text": body or None,
        "context_header": f"{name}｜{t.get('from_email') or ''}｜gmail({account})｜相手→自分｜{occurred.strftime('%Y-%m-%d %H:%M')}",
        "source_ref": {
            "source": "triage_items",
            "triage_id": t["id"],
            "account": account,
            "gmail_thread_id": t.get("gmail_thread_id"),
            "gmail_message_id": msg_id or None,
            "from_email": t.get("from_email"),
        },
        "payload": {},
    }


def fetch_general_mail(sb, since: datetime) -> list[dict[str, Any]]:
    cols = (
        "id,status,subject,partner,from_email,priority,summary,original_body,received_at,"
        "created_at,channel,account,gmail_thread_id,gmail_message_id,payload,comm_item_id"
    )
    out: list[dict[str, Any]] = []
    start = 0
    while True:
        r = (
            sb.table("triage_items")
            .select(cols)
            .eq("lane", "general")
            .eq("kind", "mail")
            .gte("created_at", since.isoformat())
            .order("created_at")
            .range(start, start + 499)
            .execute()
        )
        rows = r.data or []
        out.extend(rows)
        if len(rows) < 500:
            return out
        start += 500


def cmd_ingest_triage(args: argparse.Namespace) -> int:
    from jarvis_comm_hub import client, insert_items, link_items

    sb = client()
    since = datetime.now(JST) - timedelta(days=args.days)
    rows = fetch_general_mail(sb, since)
    items: list[dict[str, Any]] = []
    by_ext: dict[str, str] = {}
    skipped_secret = 0
    for t in rows:
        it = item_from_triage(t)
        if it is None:
            skipped_secret += 1
            continue
        if it["external_id"] in by_ext:
            continue
        by_ext[it["external_id"]] = t["id"]
        items.append(it)
    print(f"# triage general/mail: {len(rows)} 行 → 台帳候補 {len(items)} 件（除外 {skipped_secret}）")
    if not args.apply:
        if items:
            print(json.dumps(items[0], ensure_ascii=False, indent=2)[:1500])
        print("📮 dry-run（--apply で書き込み）")
        return 0
    ids = insert_items(sb, items)
    links = []
    linked = 0
    for ext, tid in by_ext.items():
        iid = ids.get(ext)
        if not iid:
            continue
        links.append({"item_id": iid, "target_type": "triage_item", "target_id": tid, "role": "queue"})
        sb.table("triage_items").update({"comm_item_id": iid}).eq("id", tid).is_("comm_item_id", "null").execute()
        linked += 1
    link_items(sb, links)
    print(f"📮 inquiry in_db={len(ids)} linked={linked}")
    return 0


# ------------------------------------------------------------------ 送信済み → self


def gmail_service(account: str):
    sys.path.insert(0, str(MANUAL_DIR))
    from gmail_to_yoritoori import build_service_for_token  # type: ignore
    from gmail_api_scopes import GMAIL_SCOPES_READONLY, resolve_read_scopes_for_token  # type: ignore

    env = (os.environ.get(f"GMAIL_{account.upper()}_TOKEN_PATH") or "").strip()
    token = Path(env) if env else MANUAL_DIR / TOKEN_BY_ACCOUNT[account]
    if not token.is_file():
        raise RuntimeError(f"token missing: {account}")
    try:
        scopes = resolve_read_scopes_for_token(json.loads(token.read_text(encoding="utf-8")))
    except Exception:  # noqa: BLE001
        scopes = []
    service, email = build_service_for_token(
        token, scopes=scopes or list(GMAIL_SCOPES_READONLY), open_browser=False
    )
    if not service:
        raise RuntimeError(f"Gmail service failed: {account}")
    return service, (email or "").lower()


def item_from_sent(msg: dict[str, Any], *, account: str, partner_filter) -> dict[str, Any] | None:
    from jarvis_night_triage_general import _extract_body, _header_map, _parse_internal_dt

    payload = msg.get("payload") or {}
    h = _header_map(payload)
    subject = h.get("subject") or "(件名なし)"
    body = _extract_body(payload, BODY_MAX)
    if is_secret_mail(subject, body):
        return None
    rcpts = [a.lower() for _, a in getaddresses([h.get("to", ""), h.get("cc", "")]) if a]
    if not rcpts:
        return None
    if any(partner_filter(a) for a in rcpts):
        return None  # パートナー宛は 5.やり取り.md 経由で入る
    from jarvis_kurashift_re_inquiry_channel import is_self_email

    if all(is_self_email(a) for a in rcpts):
        return None  # 自分宛（[Grok調査] 等のエージェント間の受け渡し・送信前の確認用）は本人の発言ではない
    occurred = _parse_internal_dt(str(msg.get("internalDate") or "0"))
    if occurred is None:
        return None
    to_name = (h.get("to") or "").split("<")[0].strip().strip('"') or rcpts[0]
    return {
        "channel": "gmail",
        "account": account,
        "external_id": f"gmail:{msg['id']}",
        "thread_key": f"gmail:{msg.get('threadId')}",
        "occurred_at": occurred.isoformat(),
        "direction": "outbound",
        "party_id": None,
        "category": "self",
        "tags": ["sent_mail"],
        "ingest_status": "ready",
        "work_status": "done",
        "subject": subject[:500],
        "summary": (msg.get("snippet") or "")[:500] or None,
        "body_text": body or None,
        "context_header": f"{to_name}｜{rcpts[0]}｜gmail({account})｜自分→相手｜{occurred.strftime('%Y-%m-%d %H:%M')}",
        "source_ref": {
            "source": "gmail_sent",
            "account": account,
            "gmail_thread_id": msg.get("threadId"),
            "gmail_message_id": msg["id"],
            "to": rcpts[:5],
        },
        "payload": {},
    }


def cmd_ingest_sent(args: argparse.Namespace) -> int:
    from jarvis_comm_hub import client, resolve_contact_yaml
    from jarvis_night_triage_general import is_partner_address, load_partner_filters

    emails, domains = load_partner_filters(resolve_contact_yaml())

    def partner_filter(a: str) -> bool:
        return is_partner_address(a, emails, domains)

    items: list[dict[str, Any]] = []
    for account in args.account or ["admin"]:
        try:
            service, me = gmail_service(account)
        except Exception as e:  # noqa: BLE001
            print(f"# {account}: skip ({e})")
            continue
        q = f"in:sent newer_than:{max(1, args.days)}d"
        ids: list[str] = []
        page = None
        while len(ids) < args.max:
            kw: dict[str, Any] = {"userId": "me", "q": q, "maxResults": min(100, args.max - len(ids))}
            if page:
                kw["pageToken"] = page
            resp = service.users().messages().list(**kw).execute()
            ids += [m["id"] for m in resp.get("messages") or []]
            page = resp.get("nextPageToken")
            if not page:
                break
        n0 = len(items)
        for mid in ids:
            msg = service.users().messages().get(userId="me", id=mid, format="full").execute()
            it = item_from_sent(msg, account=account, partner_filter=partner_filter)
            if it:
                items.append(it)
        print(f"# {account}（{me}）: 送信 {len(ids)} 通 → 台帳候補 {len(items) - n0} 件")
    if not args.apply:
        if items:
            print(json.dumps(items[0], ensure_ascii=False, indent=2)[:1200])
        print("📤 dry-run（--apply で書き込み）")
        return 0
    from jarvis_comm_hub import insert_items

    ids_db = insert_items(client(), items)
    print(f"📤 self(sent) in_db={len(ids_db)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s1 = sub.add_parser("ingest-triage", help="要確認メール（triage general/mail）→ inquiry")
    s1.add_argument("--days", type=int, default=120)
    g1 = s1.add_mutually_exclusive_group()
    g1.add_argument("--dry-run", action="store_true")
    g1.add_argument("--apply", action="store_true")
    s1.set_defaults(func=cmd_ingest_triage)

    s2 = sub.add_parser("ingest-sent", help="自分の送信メール → self")
    s2.add_argument("--account", action="append", choices=sorted(TOKEN_BY_ACCOUNT))
    s2.add_argument("--days", type=int, default=3)
    s2.add_argument("--max", type=int, default=500)
    g2 = s2.add_mutually_exclusive_group()
    g2.add_argument("--dry-run", action="store_true")
    g2.add_argument("--apply", action="store_true")
    s2.set_defaults(func=cmd_ingest_sent)

    args = ap.parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
