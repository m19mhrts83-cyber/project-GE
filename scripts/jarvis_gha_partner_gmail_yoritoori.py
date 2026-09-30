#!/usr/bin/env python3
"""
GHA / クラウド: パートナー Gmail → OneDrive `5.やり取り.md`（Graph 書込）＋既読。

本文のみ（MailGates・バイナリ添付は Mac 補完）。二重追記は件名＋日付で抑止。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  PYTHONPATH=scripts:215_kamiooya/C1_cursor/1b_Cursorマニュアル \\
    python scripts/jarvis_gha_partner_gmail_yoritoori.py --dry-run
  python scripts/jarvis_gha_partner_gmail_yoritoori.py --apply
"""
from __future__ import annotations

import argparse
import email.utils as email_utils
import os
import re
import sys
import tempfile
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
sys.path.insert(0, str(MANUAL))


def _now() -> datetime:
    return datetime.now(JST)


def format_date(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=JST)
    return dt.astimezone(JST).strftime("%Y/%m/%d %H:%M")


def materialize_contact_yaml(tmp: Path) -> Path:
    from jarvis_onedrive_graph import graph_configured, read_file

    dest = tmp / "連絡先一覧.yaml"
    if graph_configured():
        try:
            dest.write_bytes(read_file("onedrive", CONTACT_REL))
            print(f"# contact: graph {CONTACT_REL}", file=sys.stderr)
            return dest
        except Exception as e:
            print(f"# contact graph fail: {e}", file=sys.stderr)
    local = (
        Path.home()
        / "Library/CloudStorage/OneDrive-個人用"
        / CONTACT_REL
    )
    if local.is_file():
        dest.write_bytes(local.read_bytes())
        print(f"# contact: local {local}", file=sys.stderr)
        return dest
    if CONTACT_CI.is_file():
        dest.write_bytes(CONTACT_CI.read_bytes())
        print(f"# contact: snapshot {CONTACT_CI}", file=sys.stderr)
        return dest
    raise SystemExit("連絡先一覧.yaml を取得できません（Graph / local / snapshot）")


def yoritoori_rel(folder: str) -> str:
    return f"{PARTNER_BASE_REL}/{folder}/5.やり取り.md"


def already_in_md(text: str, partner_name: str, subject: str, date_yyyymmdd: str) -> bool:
    """件名＋日付（YYYY-MM-DD）の既存ブロックがあれば True。"""
    subj = (subject or "").strip()
    name = (partner_name or "").strip()
    for m in re.finditer(
        r"###\s+(\d{4}/\d{2}/\d{2})[^\n]*｜([^｜]+)｜",
        text,
    ):
        d = m.group(1).replace("/", "-")
        pn = m.group(2).strip()
        if d != date_yyyymmdd:
            continue
        if name and pn != name:
            continue
        # 直後ブロック内の件名
        start = m.end()
        end = text.find("\n### ", start)
        block = text[start : end if end > 0 else start + 2000]
        sm = re.search(r"\*\*件名\*\*:\s*(.+)", block)
        if sm and sm.group(1).strip() == subj:
            return True
        if not sm and subj and subj[:40] in block:
            return True
    return False


def append_inbound_block(
    old: str,
    *,
    partner_name: str,
    date_str: str,
    subject: str,
    body: str,
) -> str:
    from yoritoori_utils import insert_after_timeline_heading, make_summary

    summary = make_summary(body)
    subject_block = f"**件名**: {subject}\n" if subject else ""
    block = f"""

### {date_str}｜{partner_name}｜相手から返信｜{summary}

{subject_block}{body}

---
"""
    return insert_after_timeline_heading(old, block)


def process_one(
    service: Any,
    msg_id: str,
    resolver: Any,
    *,
    dry_run: bool,
    mark_read: bool,
) -> str:
    """追記したら 'appended' / スキップ理由文字列。"""
    from gmail_to_yoritoori import (  # type: ignore
        extract_email,
        parse_email_body,
    )
    from jarvis_onedrive_graph import append_text_graph, graph_configured, read_file

    full = service.users().messages().get(userId="me", id=msg_id, format="full").execute()
    headers = full.get("payload", {}).get("headers", [])
    from_val = next((h["value"] for h in headers if h["name"].lower() == "from"), None)
    to_val = next((h["value"] for h in headers if h["name"].lower() == "to"), "")
    cc_val = next((h["value"] for h in headers if h["name"].lower() == "cc"), "")
    from_date = next((h["value"] for h in headers if h["name"].lower() == "date"), None)
    subject = next((h["value"] for h in headers if h["name"].lower() == "subject"), "")

    email = extract_email(from_val)
    partner, match_kind = resolver.resolve(email, to_header=to_val or "", cc_header=cc_val or "")
    if not partner:
        return "no_partner"

    folder = partner.get("folder") or ""
    name = partner.get("name") or folder
    if not folder:
        return "no_folder"

    payload = full.get("payload", {})
    body = parse_email_body(payload) or ""
    if from_date:
        try:
            dt = email_utils.parsedate_to_datetime(from_date)
            date_str = format_date(dt)
        except (TypeError, ValueError):
            date_str = format_date(_now())
    else:
        date_str = format_date(_now())
    date_key = date_str[:10].replace("/", "-")

    rel = yoritoori_rel(folder)
    try:
        if graph_configured():
            raw = read_file("onedrive", rel)
        else:
            raw = (Path.home() / "Library/CloudStorage/OneDrive-個人用" / rel).read_bytes()
        text = raw.decode("utf-8", errors="replace")
    except Exception as e:
        return f"read_fail:{e}"

    if already_in_md(text, name, subject, date_key):
        if mark_read and not dry_run:
            try:
                service.users().messages().modify(
                    userId="me",
                    id=msg_id,
                    body={"removeLabelIds": ["UNREAD"]},
                ).execute()
            except Exception as e:
                print(f"# mark-read skip-existing fail {msg_id}: {e}", file=sys.stderr)
        return "dup"

    if dry_run:
        print(f"# dry-run would append {name} {subject[:50]}", file=sys.stderr)
        return "dry_run"

    def transform(old: str, _block: str) -> str:
        return append_inbound_block(
            old, partner_name=name, date_str=date_str, subject=subject, body=body
        )

    try:
        if graph_configured():
            append_text_graph(rel, "", transform=transform)
        else:
            local = Path.home() / "Library/CloudStorage/OneDrive-個人用" / rel
            new = transform(text, "")
            local.write_text(new, encoding="utf-8")
    except Exception as e:
        return f"write_fail:{e}"

    if mark_read:
        try:
            service.users().messages().modify(
                userId="me",
                id=msg_id,
                body={"removeLabelIds": ["UNREAD"]},
            ).execute()
        except Exception as e:
            print(f"# mark-read fail {msg_id}: {e}", file=sys.stderr)

    print(f"# appended {name} match={match_kind} {subject[:40]}", file=sys.stderr)
    return "appended"


def run(*, dry_run: bool, limit: int, newer_days: int) -> dict[str, int]:
    import yaml
    from gmail_to_yoritoori import PartnerResolver, build_service_for_token  # type: ignore
    from gmail_api_scopes import GMAIL_SCOPES_READ_MODIFY  # type: ignore

    stats = {
        "scanned": 0,
        "appended": 0,
        "dup": 0,
        "no_partner": 0,
        "fail": 0,
        "dry_run": 0,
    }
    with tempfile.TemporaryDirectory(prefix="jarvis_gha_yor_") as td:
        contact = materialize_contact_yaml(Path(td))
        config = yaml.safe_load(contact.read_text(encoding="utf-8")) or {}
        partners = config.get("partners") if isinstance(config, dict) else config
        if not isinstance(partners, list):
            partners = []
        resolver = PartnerResolver(partners, contact, learn_emails=False)
        if not resolver.has_match_config():
            raise SystemExit("連絡先に email/domain 設定がありません")

        token = Path(
            os.environ.get("GMAIL_ADMIN_TOKEN_PATH")
            or (MANUAL / "token_livingsupport.json")
        )
        service, _ = build_service_for_token(
            token, scopes=GMAIL_SCOPES_READ_MODIFY, open_browser=False
        )
        if not service:
            raise SystemExit(f"Gmail service failed: {token}")

        # 未読＋直近パートナー from（漏れ）をまとめて走査
        parts = resolver.gmail_from_query_parts()
        queries = ["is:unread"]
        if parts:
            from_q = " OR ".join(parts[:40])  # Gmail クエリ長対策
            queries.append(f"({from_q}) newer_than:{max(1, newer_days)}d")

        seen: set[str] = set()
        for q in queries:
            result = (
                service.users()
                .messages()
                .list(userId="me", q=q, maxResults=min(100, max(limit, 20)))
                .execute()
            )
            for msg in result.get("messages") or []:
                mid = msg.get("id") or ""
                if not mid or mid in seen:
                    continue
                seen.add(mid)
                if stats["scanned"] >= limit:
                    break
                stats["scanned"] += 1
                try:
                    st = process_one(
                        service, mid, resolver, dry_run=dry_run, mark_read=True
                    )
                except Exception as e:
                    print(f"# process fail {mid}: {e}", file=sys.stderr)
                    stats["fail"] += 1
                    continue
                if st == "appended":
                    stats["appended"] += 1
                elif st == "dup":
                    stats["dup"] += 1
                elif st == "no_partner":
                    stats["no_partner"] += 1
                elif st == "dry_run":
                    stats["dry_run"] += 1
                else:
                    stats["fail"] += 1
                    print(f"# skip {mid}: {st}", file=sys.stderr)
            if stats["scanned"] >= limit:
                break
    return stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true", help="書込・既読を実行（既定は dry-run）")
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--newer-days", type=int, default=3)
    args = ap.parse_args(argv)
    dry = not args.apply or args.dry_run
    if args.apply and args.dry_run:
        dry = True
    stats = run(dry_run=dry, limit=args.limit, newer_days=args.newer_days)
    print(f"📎 partner gmail→md: {stats}")
    return 0 if stats.get("fail", 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
