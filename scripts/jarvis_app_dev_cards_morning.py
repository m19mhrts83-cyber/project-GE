#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""アプリ開発統括の Jarvis向けカードを朝に要約する。

Grok チャンネルは API で読めないため、次を正とする:
  1) estate Gmail 件名 [Grok開発]（ルーティン末尾で統括が送る）
  2) ローカル inbox（チャンネルからコピペ可）
     ~/.jarvis_state ではなく repo: .jarvis_state/app_dev_cards_inbox.md

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_app_dev_cards_morning.py
  ~/selenium_env/venv/bin/python scripts/jarvis_app_dev_cards_morning.py --mark-prompted
  ~/selenium_env/venv/bin/python scripts/jarvis_app_dev_cards_morning.py --dry-run

朝バンドル: jarvis_morning_mac_refresh.py から呼ばれる。
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
MANUAL = REPO / "215_kamiooya" / "C1_cursor" / "1b_Cursorマニュアル"
STATE_PATH = REPO / ".jarvis_state" / "app_dev_cards.json"
INBOX_PATH = REPO / ".jarvis_state" / "app_dev_cards_inbox.md"
DIGEST_PATH = REPO / ".jarvis_state" / "app_dev_cards_digest.md"
JST = ZoneInfo("Asia/Tokyo")
SUBJECT_PREFIX = "[Grok開発]"
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
]

CARD_BLOCK_RE = re.compile(
    r"📎\s*Jarvis向け\s*[（(](?P<kind>実装|材料)[）)]\s*\n(?P<body>.*?)(?=\n📎\s*Jarvis向け|\n#\s|\Z)",
    re.S,
)


def now_iso() -> str:
    return datetime.now(JST).isoformat()


def load_state() -> dict[str, Any]:
    empty = {
        "processed_mail_ids": [],
        "prompted_card_ids": [],
        "queue": {},
        "last_run_at": None,
        "last_digest_at": None,
        "last_queue_at": None,
    }
    if not STATE_PATH.is_file():
        return dict(empty)
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("bad state")
        data.setdefault("processed_mail_ids", [])
        data.setdefault("prompted_card_ids", [])
        data.setdefault("queue", {})
        if not isinstance(data["queue"], dict):
            data["queue"] = {}
        return data
    except Exception:
        return dict(empty)


def save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state["last_run_at"] = now_iso()
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def gmail_service():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    path = MANUAL / "token_estate.json"
    if not path.is_file():
        raise FileNotFoundError(f"token not found: {path}")
    creds = Credentials.from_authorized_user_file(str(path), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        path.write_text(creds.to_json(), encoding="utf-8")
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def decode_body(payload: dict) -> str:
    texts: list[str] = []

    def walk(part: dict) -> None:
        mime = (part.get("mimeType") or "").lower()
        body = part.get("body") or {}
        data = body.get("data")
        if data and mime in ("text/plain", "text/html"):
            raw = base64.urlsafe_b64decode(data + "==")
            text = raw.decode("utf-8", errors="replace")
            if mime == "text/html":
                text = re.sub(r"<[^>]+>", " ", text)
                text = re.sub(r"\s+", " ", text)
            texts.append(text)
        for ch in part.get("parts") or []:
            walk(ch)

    walk(payload)
    return "\n".join(texts)[:80000]


def header_map(headers: list[dict]) -> dict[str, str]:
    out: dict[str, str] = {}
    for h in headers or []:
        out[(h.get("name") or "").lower()] = h.get("value") or ""
    return out


def fetch_grok_dev_mails(*, days: int = 14, max_results: int = 20) -> list[dict[str, Any]]:
    print("使用アカウント: estate / Gmail API（[Grok開発] 受信）")
    svc = gmail_service()
    q = f'subject:"{SUBJECT_PREFIX}" newer_than:{days}d'
    res = (
        svc.users()
        .messages()
        .list(userId="me", q=q, maxResults=max_results)
        .execute()
    )
    out: list[dict[str, Any]] = []
    for item in res.get("messages") or []:
        mid = item.get("id")
        if not mid:
            continue
        msg = svc.users().messages().get(userId="me", id=mid, format="full").execute()
        hm = header_map(msg.get("payload", {}).get("headers") or [])
        out.append(
            {
                "id": mid,
                "subject": hm.get("subject", ""),
                "date": hm.get("date", ""),
                "body": decode_body(msg.get("payload") or {}),
                "source": "gmail",
            }
        )
    return out


def parse_field(body: str, keys: list[str]) -> str:
    for key in keys:
        m = re.search(
            rf"^[\-\*\s]*{re.escape(key)}\s*[:：]\s*(.+)$",
            body,
            re.M,
        )
        if m:
            return m.group(1).strip()
    return ""


def parse_cards(text: str, *, source: str, source_id: str = "") -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for m in CARD_BLOCK_RE.finditer(text or ""):
        kind = m.group("kind")
        body = (m.group("body") or "").strip()
        app = parse_field(body, ["アプリ", "対象アプリ"])
        want = parse_field(body, ["やりたいこと", "欲しいもの"])
        where = parse_field(body, ["触りそうな場所", "用途"])
        risk_raw = parse_field(body, ["リスク"])
        risk = "高" if "高" in risk_raw else ("低" if "低" in risk_raw else ("—" if kind == "材料" else "不明"))
        done = parse_field(body, ["完了条件"])
        raw = m.group(0).strip()
        cid = hashlib.sha1(
            f"{kind}|{app}|{want}|{risk}|{raw[:200]}".encode("utf-8")
        ).hexdigest()[:12]
        cards.append(
            {
                "id": cid,
                "kind": kind,
                "app": app or "（未記入）",
                "want": want
                or (body.splitlines()[0][:120] if body else "（未記入）"),
                "where": where,
                "risk": risk,
                "done": done,
                "raw": raw,
                "source": source,
                "source_id": source_id,
            }
        )
    return cards


def load_inbox_text() -> str:
    if not INBOX_PATH.is_file():
        return ""
    return INBOX_PATH.read_text(encoding="utf-8", errors="replace")


def collect_cards(
    *,
    days: int,
    skip_gmail: bool,
    state: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    notes: list[str] = []
    cards: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add_all(items: list[dict[str, Any]]) -> None:
        for c in items:
            if c["id"] in seen:
                continue
            seen.add(c["id"])
            cards.append(c)

    inbox = load_inbox_text()
    if inbox.strip():
        add_all(parse_cards(inbox, source="inbox", source_id="inbox"))
        notes.append(f"inbox={INBOX_PATH.name}")
    else:
        notes.append("inbox=空")

    if not skip_gmail:
        try:
            mails = fetch_grok_dev_mails(days=days)
            processed = set(state.get("processed_mail_ids") or [])
            fresh = 0
            for mail in mails:
                add_all(
                    parse_cards(
                        mail["body"],
                        source="gmail",
                        source_id=mail["id"],
                    )
                )
                if mail["id"] not in processed:
                    fresh += 1
            notes.append(f"gmail={len(mails)}件(うち未処理ID目安{fresh})")
        except Exception as e:
            notes.append(f"gmail=ERROR({e})")
    else:
        notes.append("gmail=skip")

    return cards, notes


def classify(
    cards: list[dict[str, Any]], prompted: set[str]
) -> dict[str, list[dict[str, Any]]]:
    low: list[dict[str, Any]] = []
    high: list[dict[str, Any]] = []
    material: list[dict[str, Any]] = []
    for c in cards:
        if c["id"] in prompted:
            continue
        if c["kind"] == "材料":
            material.append(c)
        elif c["risk"] == "低":
            low.append(c)
        elif c["risk"] == "高":
            high.append(c)
        else:
            high.append(c)  # 不明は確認側
    return {"low": low, "high": high, "material": material}


def render_digest(
    groups: dict[str, list[dict[str, Any]]],
    *,
    notes: list[str],
) -> str:
    lines = [
        "📎 アプリ開発カード（朝）",
        f"- 取得: {' / '.join(notes)}",
        f"- 低・未処理（即実行候補）: {len(groups['low'])}",
    ]
    for i, c in enumerate(groups["low"][:8], 1):
        lines.append(f"  {i}. [{c['app']}] {c['want']}")
    lines.append(f"- 高・要承認: {len(groups['high'])}")
    for i, c in enumerate(groups["high"][:8], 1):
        lines.append(f"  {i}. [{c['app']}] {c['want']}")
    lines.append(f"- 材料依頼: {len(groups['material'])}")
    for i, c in enumerate(groups["material"][:5], 1):
        lines.append(f"  {i}. [{c['app']}] {c['want']}")
    if not any(groups.values()):
        lines.append("- （未処理カードなし）")
    else:
        lines.append(
            "- 次: 低は「やって」で実装可。高は松野OK後。"
            " inbox へチャンネル全文を貼っても可。"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-gmail", action="store_true")
    ap.add_argument(
        "--mark-prompted",
        action="store_true",
        help="今回要約したカードを prompted 済みにする",
    )
    ap.add_argument(
        "--mark-mail-seen",
        action="store_true",
        help="取得した Gmail ID を processed に入れる",
    )
    args = ap.parse_args()

    if os_env_disabled():
        print("# skip: JARVIS_APP_DEV_CARDS_DISABLE=1")
        return 0

    state = load_state()
    cards, notes = collect_cards(
        days=args.days,
        skip_gmail=args.skip_gmail,
        state=state,
    )
    prompted = set(state.get("prompted_card_ids") or [])
    groups = classify(cards, prompted)
    digest = render_digest(groups, notes=notes)
    print(digest, end="")

    DIGEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    DIGEST_PATH.write_text(digest, encoding="utf-8")

    if args.dry_run:
        return 0

    if args.mark_prompted:
        ids = [c["id"] for g in groups.values() for c in g]
        merged = list(dict.fromkeys([*(state.get("prompted_card_ids") or []), *ids]))
        state["prompted_card_ids"] = merged[-200:]
        state["last_digest_at"] = now_iso()

    if args.mark_mail_seen and not args.skip_gmail:
        try:
            mails = fetch_grok_dev_mails(days=args.days)
            mids = [m["id"] for m in mails]
            merged = list(
                dict.fromkeys([*(state.get("processed_mail_ids") or []), *mids])
            )
            state["processed_mail_ids"] = merged[-100:]
        except Exception as e:
            print(f"# mark-mail-seen failed: {e}", file=sys.stderr)

    # 朝バンドル既定: 要約は残す。prompted は明示時のみ
    save_state(state)
    return 0


def os_env_disabled() -> bool:
    return (os.environ.get("JARVIS_APP_DEV_CARDS_DISABLE") or "").strip() in (
        "1",
        "true",
        "yes",
    )


if __name__ == "__main__":
    raise SystemExit(main())
