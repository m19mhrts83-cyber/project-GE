#!/usr/bin/env python3
"""管理会社・事前確認への返信を estate Gmail から拾い、判定案＋返信下書きを出す。

方針（2026-08-27）:
  - 初回事前確認（定型）: 送信前確認不要（S9）
  - 2回目以降の返信メール: 下書きを出し、松野承認後のみ送信（対外確認）
  - 空室対象にするか（vacancy_listing_ok）は人手確定 → YAML → Supabase sync

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_grok_mgmt_reply_apply.py --days 14 --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_grok_mgmt_reply_apply.py --days 14 --write-drafts
  # 判定確定後:
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_mgmt_vendor_list.py \\
    --mark ID --status replied --vacancy-listing-ok true
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_mgmt_vendor_sync.py --apply

使用アカウント: estate / Gmail API
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

REPO = Path(__file__).resolve().parents[1]
MANUAL = REPO / "215_kamiooya" / "C1_cursor" / "1b_Cursorマニュアル"
STATE_PATH = REPO / ".jarvis_state" / "mgmt_precheck_reply.json"
DRAFT_DIR = REPO / ".jarvis_state" / "mgmt_reply_drafts"
PY = Path("/Users/matsunomasaharu2/selenium_env/venv/bin/python")
LIST_SCRIPT = REPO / "scripts" / "jarvis_kurashift_mgmt_vendor_list.py"
SYNC_SCRIPT = REPO / "scripts" / "jarvis_kurashift_mgmt_vendor_sync.py"
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]

sys.path.insert(0, str(REPO / "scripts"))
from jarvis_kurashift_mgmt_vendor_list import (  # noqa: E402
    ensure_precheck_fields,
    load_list,
    mark_vendor,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def today_jst() -> str:
    # rough; enough for filenames
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d")


def load_state() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        return {"processed_ids": [], "last_run_at": None, "proposals": []}
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"processed_ids": [], "last_run_at": None, "proposals": []}
        data.setdefault("processed_ids", [])
        data.setdefault("proposals", [])
        return data
    except Exception:
        return {"processed_ids": [], "last_run_at": None, "proposals": []}


def save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state["last_run_at"] = now_iso()
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def gmail_service():
    path = MANUAL / "token_estate.json"
    if not path.is_file():
        raise FileNotFoundError(f"token not found: {path}")
    creds = Credentials.from_authorized_user_file(str(path), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        path.write_text(creds.to_json(), encoding="utf-8")
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def body_text(payload: dict[str, Any]) -> str:
    def walk(p: dict[str, Any]) -> str:
        if (p.get("mimeType") or "").startswith("multipart/"):
            for c in p.get("parts") or []:
                t = walk(c)
                if t:
                    return t
        if p.get("mimeType") in ("text/plain", "text/html"):
            data = (p.get("body") or {}).get("data")
            if data:
                raw = base64.urlsafe_b64decode(data.encode()).decode("utf-8", "replace")
                raw = re.sub(r"<[^>]+>", " ", raw)
                return raw
        return ""

    return walk(payload or {})


def header_map(headers: list[dict[str, str]]) -> dict[str, str]:
    return {h.get("name", "").lower(): h.get("value", "") for h in headers}


def domain_from_url(url: str) -> str:
    u = (url or "").strip()
    if not u:
        return ""
    if "://" not in u:
        u = "https://" + u
    try:
        host = (urlparse(u).hostname or "").lower()
    except Exception:
        return ""
    if host.startswith("www."):
        host = host[4:]
    return host


def guess_intent(text: str) -> str:
    t = text or ""
    if any(
        x in t
        for x in (
            "ご協力できず",
            "お断り",
            "対応しておりません",
            "お受けでき",
            "仲介業を行ってい",
            "お力になれ",
        )
    ):
        return "ng"
    if any(
        x in t
        for x in (
            "よろしくお願い",
            "ご連絡ありがとうございます",
            "お電話",
            "詳細",
            "可能です",
            "大丈夫です",
            "協力",
            "お受けできます",
            "募集",
            "管理",
        )
    ):
        return "ok_or_unclear"
    return "unclear"


def suggest_vacancy(intent: str) -> str:
    if intent == "ng":
        return "false"
    if intent == "ok_or_unclear":
        return "review"  # 人手で true/false
    return "review"


def match_vendors(
    from_hdr: str, subject: str, body: str, vendors: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    blob = f"{from_hdr} {subject} {body}".lower()
    hits: list[dict[str, Any]] = []
    for v in vendors:
        ensure_precheck_fields(v)
        st = str(v.get("status") or "")
        if st not in ("contacted", "replied", "pending"):
            continue
        name = str(v.get("name") or "").strip()
        email = str(v.get("contact_email") or "").strip().lower()
        url_dom = domain_from_url(str(v.get("url") or v.get("contact_url") or ""))
        score = 0
        if email and email in from_hdr.lower():
            score += 5
        if email and "@" in email:
            dom = email.split("@", 1)[1]
            if dom and dom in from_hdr.lower():
                score += 2
        if url_dom and url_dom in from_hdr.lower():
            score += 4
        if name and len(name) >= 4 and name.lower() in blob:
            score += 3
        if score >= 3:
            hits.append({**v, "_match_score": score})
    hits.sort(key=lambda x: -int(x.get("_match_score") or 0))
    return hits


def draft_reply_body(*, vendor_name: str, intent: str, their_snippet: str) -> str:
    """2回目以降用の返信下書き（送信は松野承認後）。"""
    if intent == "ng":
        return (
            f"{vendor_name} 御中\n\n"
            "お世話になります。松野です。\n\n"
            "ご丁寧なご返信ありがとうございます。\n"
            "ご事情承知いたしました。また機会がございましたらよろしくお願いいたします。\n\n"
            "松野真治\n"
            "matsuno.estate@gmail.com\n"
            "090-9670-7595\n"
        )
    # ok / unclear — 空室対象可否の確認を深掘りしつつ礼
    return (
        f"{vendor_name} 御中\n\n"
        "お世話になります。松野です。\n\n"
        "ご返信ありがとうございます。\n"
        "今後空室が出た際のご紹介・募集のご協力について、引き続きお願いできれば幸いです。\n"
        "戸別管理についても、差し支えなければ可否だけお知らせください。\n\n"
        "資料フォルダは初回メールの Drive リンクをご覧ください。\n"
        "追加で必要な情報があればお申し付けください。\n\n"
        "松野真治\n"
        "matsuno.estate@gmail.com\n"
        "090-9670-7595\n"
        "\n"
        "---\n"
        f"（相手文面抜粋）{their_snippet[:200]}\n"
    )


def write_draft(prop: dict[str, Any]) -> Path:
    DRAFT_DIR.mkdir(parents=True, exist_ok=True)
    vid = str(prop.get("vendor_id") or "unknown")
    safe = re.sub(r"[^\w\-一-龥]+", "_", vid)[:80]
    path = DRAFT_DIR / f"{today_jst()}_{safe}.md"
    intent = str(prop.get("intent_guess") or "unclear")
    vac = suggest_vacancy(intent)
    mark_ok = (
        f'--mark {vid} --status replied --vacancy-listing-ok true '
        f'--note "precheck_reply:ok"'
    )
    mark_ng = (
        f'--mark {vid} --status skip --vacancy-listing-ok false '
        f'--note "precheck_reply:ng"'
    )
    body = draft_reply_body(
        vendor_name=str(prop.get("vendor_name") or ""),
        intent=intent,
        their_snippet=str(prop.get("snippet") or ""),
    )
    text = (
        f"# 管理会社返信 — 判定・返信下書き\n\n"
        f"- 日時: {now_iso()}\n"
        f"- vendor: `{vid}` / {prop.get('vendor_name')}\n"
        f"- From: {prop.get('from')}\n"
        f"- Subject: {prop.get('subject')}\n"
        f"- intent_guess: **{intent}**\n"
        f"- vacancy_listing 提案: **{vac}**（review=人手確定）\n"
        f"- gmail_id: `{prop.get('message_id')}`\n\n"
        f"## 判定（松野へ）\n\n"
        f"空室対策メールの対象に含めますか？\n\n"
        f"- OK なら:\n```\n{mark_ok}\n```\n"
        f"- NG なら:\n```\n{mark_ng}\n```\n"
        f"確定後: `jarvis_kurashift_mgmt_vendor_sync.py --apply`\n\n"
        f"## 返信メール下書き（2回目以降 · **承認後のみ送信**）\n\n"
        f"From: matsuno.estate@gmail.com\n"
        f"To: （相手 From）\n"
        f"Subject: Re: {prop.get('subject')}\n\n"
        f"```\n{body}```\n\n"
        f"## 送信ルール\n\n"
        f"- 初回事前確認（定型）: 確認不要\n"
        f"- 本下書き（2回目以降）: **松野承認後**に Jarvis が送信\n"
    )
    path.write_text(text, encoding="utf-8")
    return path


def run(
    *,
    days: int,
    apply: bool,
    dry_run: bool,
    write_drafts: bool,
) -> dict[str, Any]:
    print("使用アカウント: estate / Gmail API（管理会社・事前確認返信）")
    state = load_state()
    processed = set(str(x) for x in (state.get("processed_ids") or []))
    data = load_list()
    vendors = [v for v in (data.get("vendors") or []) if isinstance(v, dict)]
    contacted = [
        v
        for v in vendors
        if str(v.get("status") or "") in ("contacted", "replied")
    ]

    svc = gmail_service()
    q = f"newer_than:{max(1, days)}d -from:me -subject:[Grok"
    res = svc.users().messages().list(userId="me", q=q, maxResults=50).execute()
    msgs = res.get("messages") or []
    proposals: list[dict[str, Any]] = []
    draft_paths: list[str] = []
    applied = 0

    for m in msgs:
        mid = m["id"]
        if mid in processed:
            continue
        full = svc.users().messages().get(userId="me", id=mid, format="full").execute()
        hm = header_map(full.get("payload", {}).get("headers") or [])
        subject = hm.get("subject") or ""
        frm = hm.get("from") or ""
        body = body_text(full.get("payload") or {})[:4000]
        if any(
            x in frm.lower()
            for x in ("kenbiya", "noreply", "newsletter", "westudy", "emailme", "cowcamo")
        ):
            continue
        hits = match_vendors(frm, subject, body, contacted or vendors)
        if not hits:
            continue
        intent = guess_intent(body + "\n" + subject)
        top = hits[0]
        prop = {
            "message_id": mid,
            "subject": subject[:120],
            "from": frm[:160],
            "vendor_id": top.get("id"),
            "vendor_name": top.get("name"),
            "match_score": top.get("_match_score"),
            "intent_guess": intent,
            "vacancy_suggest": suggest_vacancy(intent),
            "snippet": (body or "")[:240].replace("\n", " "),
            "send_policy": "followup_needs_approval",
        }
        proposals.append(prop)
        if write_drafts:
            p = write_draft(prop)
            draft_paths.append(str(p))
            prop["draft_path"] = str(p)

        if apply and not dry_run and intent == "ng":
            mark_vendor(
                str(top["id"]),
                status="skip",
                note="precheck_reply:ng",
                vacancy_listing_ok="false",
                dry_run=False,
            )
            applied += 1
            processed.add(mid)

    if apply and not dry_run:
        state["processed_ids"] = sorted(processed)[-500:]
        if applied and SYNC_SCRIPT.is_file():
            subprocess.run(
                [str(PY), str(SYNC_SCRIPT), "--apply"],
                cwd=str(REPO),
                check=False,
            )

    state["proposals"] = proposals[-30:]
    save_state(state)

    out = {
        "ok": True,
        "days": days,
        "proposals": proposals,
        "draft_paths": draft_paths,
        "contacted_vendors": len(contacted),
        "auto_applied_ng": applied,
        "dry_run": dry_run or not apply,
        "note": (
            "OK確定は人手。下書き送信は承認後。"
            "初回定型のみ確認不要。"
        ),
    }
    print("📎 管理会社・事前確認返信")
    print(f"- 提案: {len(proposals)} 件 · contacted/replied台帳 {len(contacted)}")
    print(f"- 下書き: {len(draft_paths)} 件")
    print(f"- 自動NG適用: {applied}")
    for d in draft_paths:
        print(f"  draft: {d}")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    print(
        "MGMT_REPLY_APPLY:"
        + json.dumps({k: out[k] for k in out if k != "proposals"}, ensure_ascii=False)
    )
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--apply", action="store_true", help="NGのみ自動 skip+sync")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--write-drafts",
        action="store_true",
        help="判定・返信下書き MD を .jarvis_state/mgmt_reply_drafts/ へ",
    )
    args = ap.parse_args()
    dry = args.dry_run or not args.apply
    run(
        days=args.days,
        apply=bool(args.apply),
        dry_run=dry,
        write_drafts=bool(args.write_drafts),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
