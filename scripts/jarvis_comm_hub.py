#!/usr/bin/env python3
"""コミュニケーション台帳（comm hub）— 共通ライブラリ＋CLI（Phase 0）。

設計: Claude Doc「コミュニケーション集約DB 設計案」（2026-11-03 松野さん承認）
migration: apps/jarvis-dashboard/supabase/migrations/20261104_comm_hub.sql

台帳は「書き足すだけ」。失敗しても既存の流れ（triage_items 等）は止めない。

  # 名簿（連絡先一覧.yaml → comm_parties）
  python scripts/jarvis_comm_hub.py sync-parties --dry-run
  python scripts/jarvis_comm_hub.py sync-parties --apply

  # 過去分（26_パートナー社への相談/*/5.やり取り.md → comm_items）
  python scripts/jarvis_comm_hub.py backfill-md --dry-run [--folder 102_ミニテック]
  python scripts/jarvis_comm_hub.py backfill-md --apply

  # 確認（分類で絞る＋日本語キーワード）
  python scripts/jarvis_comm_hub.py search --party partner:102_ミニテック --query エアコン
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

PARTNER_BASE_REL = "215_神・大家さん倶楽部/C2_ルーティン作業/26_パートナー社への相談"
CONTACT_REL = f"{PARTNER_BASE_REL}/000_共通/連絡先一覧.yaml"
REPO_PARTNER_BASE = REPO / "215_kamiooya" / "C2_ルーティン作業" / "26_パートナー社への相談"

# フォルダ番号の百の位（連絡先一覧.yaml の採番ルール）→ comm_parties.kind
KIND_BY_HUNDREDS = {
    "1": "mgmt",
    "2": "repair",
    "3": "insurance",
    "5": "finance",
    "6": "tenant",
    "7": "learning",
    "8": "club",
    "9": "agency",
}

CHUNK = 200
BODY_MAX = 8000


# ------------------------------------------------------------------ parties


def party_id_for_folder(folder: str) -> str:
    return f"partner:{folder.strip()}"


def kind_for_folder(folder: str) -> str:
    m = re.match(r"^\D*(\d)", folder or "")
    return KIND_BY_HUNDREDS.get(m.group(1), "other") if m else "other"


def _as_list(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        return [v.strip()] if v.strip() else []
    if isinstance(v, (list, tuple)):
        return [str(x).strip() for x in v if str(x).strip()]
    return [str(v).strip()]


def party_row(p: dict[str, Any], *, now: str) -> dict[str, Any] | None:
    folder = str(p.get("folder") or "").strip()
    if not folder:
        return None
    chat_ids: dict[str, Any] = {}
    for k in (
        "chatwork_room_id",
        "chatwork_rooms",
        "line_group_chat_mid",
        "line_direct_chat_mid",
        "phones",
    ):
        v = p.get(k)
        if v not in (None, "", [], {}):
            chat_ids[k] = v
    return {
        "party_id": party_id_for_folder(folder),
        "kind": kind_for_folder(folder),
        "name": str(p.get("name") or folder).strip(),
        "partner_folder": folder,
        "emails": [e.lower() for e in _as_list(p.get("emails"))],
        "email_domains": [d.lower() for d in _as_list(p.get("email_domains"))],
        "chat_ids": chat_ids,
        # 2026-11-03 松野さん: 「必ず確認」は今の連絡先一覧すべて
        "must_check": True,
        "source": "contact_yaml",
        "active": True,
        "payload": {
            k: p.get(k)
            for k in ("contact", "line", "to_name_hints")
            if p.get(k) not in (None, "", [])
        },
        "synced_at": now,
    }


def load_contact_partners(path: Path | None = None) -> list[dict[str, Any]]:
    import yaml

    if path is None:
        path = resolve_contact_yaml()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    partners = data.get("partners") if isinstance(data, dict) else None
    return [p for p in (partners or []) if isinstance(p, dict)]


def resolve_contact_yaml() -> Path:
    """OneDrive（Graph → ローカル）→ リポジトリ内コピーの順。"""
    try:
        from jarvis_onedrive_graph import graph_configured, read_file

        if graph_configured():
            tmp = Path(tempfile.mkdtemp(prefix="comm_hub_")) / "連絡先一覧.yaml"
            tmp.write_bytes(read_file("onedrive", CONTACT_REL))
            return tmp
    except Exception as e:  # noqa: BLE001
        print(f"# contact graph skip: {e}", file=sys.stderr)
    local = Path.home() / "Library/CloudStorage/OneDrive-個人用" / CONTACT_REL
    if local.is_file():
        return local
    repo_copy = REPO_PARTNER_BASE / "000_共通" / "連絡先一覧.yaml"
    if repo_copy.is_file():
        return repo_copy
    raise SystemExit("連絡先一覧.yaml が見つかりません")


# ------------------------------------------------------------------ items


def _channel_of(raw: str) -> str:
    from jarvis_night_triage import chat_channel_kind, is_gmail_channel

    kind = chat_channel_kind(raw)
    if kind == "Chatwork":
        return "chatwork"
    if kind == "iMessage":
        return "imessage"
    if kind == "LINE":
        return "line"
    if is_gmail_channel(raw) or "Gmail" in (raw or ""):
        return "gmail"
    return "other"


def parse_occurred_at(s: str) -> datetime | None:
    s = (s or "").strip()
    for fmt, n in (("%Y/%m/%d %H:%M", 16), ("%Y/%m/%d", 10)):
        try:
            return datetime.strptime(s[:n], fmt).replace(tzinfo=JST)
        except ValueError:
            continue
    return None


def md_external_id(entry: dict[str, Any]) -> str:
    raw = "|".join(
        [
            str(entry.get("folder") or ""),
            str(entry.get("received_at") or ""),
            str(entry.get("channel") or ""),
            str(entry.get("subject") or ""),
            str(entry.get("summary") or "")[:80],
        ]
    )
    return "md:" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def item_from_md_entry(
    entry: dict[str, Any],
    *,
    recent_cutoff: datetime | None = None,
) -> dict[str, Any] | None:
    """parse_yoritoori_text の1件 → comm_items 行。日時が読めなければ None。"""
    from jarvis_night_triage import (
        chat_thread_key,
        is_chat_noise,
        is_noise_mail,
    )

    occurred = parse_occurred_at(entry.get("received_at") or "")
    if occurred is None:
        return None
    raw_ch = str(entry.get("channel") or "")
    channel = _channel_of(raw_ch)
    folder = str(entry.get("folder") or "")
    subject = str(entry.get("subject") or "")
    summary = str(entry.get("summary") or "")
    body = str(entry.get("body") or "")[:BODY_MAX]

    outbound = "自分から送信" in raw_ch or raw_ch.strip().startswith("自分から")
    if not outbound and channel == "gmail":
        # 「相手から返信」誤ラベルの自分発信（BCC 等）
        try:
            from jarvis_kurashift_re_inquiry_channel import looks_like_self_outbound_body

            outbound = bool(looks_like_self_outbound_body(body))
        except Exception:  # noqa: BLE001
            pass
    direction = "outbound" if outbound else "inbound"

    if channel == "gmail":
        noise = is_noise_mail(subject, body, summary)
        thread_key = f"{folder}|gmail|{entry.get('subject_norm') or subject}"
    else:
        noise = is_chat_noise(summary, body, subject)
        kind = {"chatwork": "Chatwork", "imessage": "iMessage", "line": "LINE"}.get(channel, channel)
        thread_key = chat_thread_key(folder, raw_ch, kind)

    if direction == "outbound":
        work_status = "done"
    elif recent_cutoff is not None and occurred < recent_cutoff:
        work_status = "done"  # 過去分は対応済み扱い（未返信判定は 111 側が付け直す）
    else:
        work_status = "new"

    name = str(entry.get("partner_name") or folder)
    header = (
        f"{name}｜{folder}｜{channel}｜{'自分→相手' if outbound else '相手→自分'}｜"
        f"{occurred.strftime('%Y-%m-%d %H:%M')}"
    )
    return {
        "channel": channel,
        "account": "",
        "external_id": md_external_id(entry),
        "thread_key": thread_key,
        "occurred_at": occurred.isoformat(),
        "direction": direction,
        "party_id": party_id_for_folder(folder) if folder else None,
        "category": "partner",
        "tags": [],
        "ingest_status": "excluded" if noise else "ready",
        "work_status": work_status,
        "subject": subject[:500] or None,
        "summary": summary[:500] or None,
        "body_text": body or None,
        "context_header": header,
        "source_ref": {
            "source": "yoritoori_md",
            "path": f"{PARTNER_BASE_REL}/{folder}/5.やり取り.md",
            "heading": f"### {entry.get('received_at')}｜{name}｜{raw_ch}｜{summary}"[:400],
            "channel_raw": raw_ch,
        },
        "payload": {},
    }


def read_partner_md(folder: str) -> str | None:
    rel = f"{PARTNER_BASE_REL}/{folder}/5.やり取り.md"
    try:
        from jarvis_onedrive_graph import graph_configured, read_file

        if graph_configured():
            return read_file("onedrive", rel).decode("utf-8", errors="replace")
    except Exception as e:  # noqa: BLE001
        print(f"# md graph skip {folder}: {e}", file=sys.stderr)
    for p in (
        Path.home() / "Library/CloudStorage/OneDrive-個人用" / rel,
        REPO_PARTNER_BASE / folder / "5.やり取り.md",
    ):
        if p.is_file():
            return p.read_text(encoding="utf-8", errors="replace")
    return None


def items_from_md_text(
    text: str,
    folder: str,
    name: str,
    *,
    recent_cutoff: datetime | None = None,
) -> list[dict[str, Any]]:
    from jarvis_night_triage import parse_yoritoori_text

    out: dict[str, dict[str, Any]] = {}
    for e in parse_yoritoori_text(text, folder, name):
        row = item_from_md_entry(e, recent_cutoff=recent_cutoff)
        if row is not None:
            # 同一キーは先勝ち（md は新しい順なので最新の見出しを採用）
            out.setdefault(row["external_id"], row)
    return list(out.values())


# ------------------------------------------------------------------ supabase


def client():
    from supabase import create_client

    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        raise RuntimeError("JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY 未設定")
    return create_client(url, key)


def _chunks(rows: list[dict[str, Any]], n: int = CHUNK) -> Iterable[list[dict[str, Any]]]:
    for i in range(0, len(rows), n):
        yield rows[i : i + n]


def upsert_parties(sb, rows: list[dict[str, Any]]) -> int:
    n = 0
    for chunk in _chunks(rows):
        sb.table("comm_parties").upsert(chunk, on_conflict="party_id").execute()
        n += len(chunk)
    return n


def ensure_parties(sb, party_ids: set[str]) -> None:
    """名簿にない party_id があれば最小行を足す（FK 違反で台帳書込が落ちないように）。"""
    ids = sorted(p for p in party_ids if p)
    if not ids:
        return
    have: set[str] = set()
    for i in range(0, len(ids), 100):
        r = sb.table("comm_parties").select("party_id").in_("party_id", ids[i : i + 100]).execute()
        have |= {str(x["party_id"]) for x in (r.data or [])}
    missing = [p for p in ids if p not in have]
    if missing:
        rows = []
        for pid in missing:
            folder = pid.split(":", 1)[-1]
            rows.append(
                {
                    "party_id": pid,
                    "kind": kind_for_folder(folder),
                    "name": re.sub(r"^\w?\d+_", "", folder) or folder,
                    "partner_folder": folder,
                    "must_check": True,
                    "source": "auto_from_md",
                }
            )
        upsert_parties(sb, rows)


def insert_items(sb, rows: list[dict[str, Any]]) -> dict[str, str]:
    """新規のみ挿入（既存行の work_status 等は触らない）。external_id → id を返す。"""
    if not rows:
        return {}
    ensure_parties(sb, {r.get("party_id") or "" for r in rows})
    for chunk in _chunks(rows):
        sb.table("comm_items").upsert(
            chunk,
            on_conflict="channel,account,external_id",
            ignore_duplicates=True,
        ).execute()
    return lookup_ids(sb, [r["external_id"] for r in rows])


def lookup_ids(sb, external_ids: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    ids = sorted(set(external_ids))
    for i in range(0, len(ids), 100):
        r = (
            sb.table("comm_items")
            .select("id,external_id")
            .in_("external_id", ids[i : i + 100])
            .execute()
        )
        for x in r.data or []:
            out[str(x["external_id"])] = str(x["id"])
    return out


def mark_needs_reply(sb, item_ids: list[str]) -> int:
    """未返信候補になった行だけ new → needs_reply（人が閉じた状態は戻さない）。"""
    n = 0
    ids = sorted(set(i for i in item_ids if i))
    for i in range(0, len(ids), 100):
        r = (
            sb.table("comm_items")
            .update({"work_status": "needs_reply"})
            .in_("id", ids[i : i + 100])
            .eq("work_status", "new")
            .execute()
        )
        n += len(r.data or [])
    return n


def link_items(sb, links: list[dict[str, Any]]) -> int:
    if not links:
        return 0
    for chunk in _chunks(links):
        sb.table("comm_links").upsert(
            chunk, on_conflict="item_id,target_type,target_id", ignore_duplicates=True
        ).execute()
    return len(links)


# ------------------------------------------------------------------ CLI


def cmd_sync_parties(args: argparse.Namespace) -> int:
    now = datetime.now(JST).isoformat()
    path = Path(args.contact) if args.contact else None
    rows = [r for r in (party_row(p, now=now) for p in load_contact_partners(path)) if r]
    print(f"# parties: {len(rows)}", file=sys.stderr)
    for r in rows:
        print(f"  {r['party_id']}\t{r['kind']}\t{r['name']}", file=sys.stderr)
    if not args.apply:
        print("📒 comm parties dry-run")
        return 0
    n = upsert_parties(client(), rows)
    print(f"📒 comm parties upserted={n}")
    return 0


def cmd_backfill_md(args: argparse.Namespace) -> int:
    path = Path(args.contact) if args.contact else None
    partners = load_contact_partners(path)
    if args.folder:
        partners = [p for p in partners if str(p.get("folder") or "") in set(args.folder)]
    cutoff = datetime.now(JST) - timedelta(days=args.recent_days)
    all_rows: list[dict[str, Any]] = []
    for p in partners:
        folder = str(p.get("folder") or "").strip()
        if not folder:
            continue
        text = read_partner_md(folder)
        if not text:
            print(f"# skip {folder}: md なし", file=sys.stderr)
            continue
        rows = items_from_md_text(text, folder, str(p.get("name") or folder), recent_cutoff=cutoff)
        ready = sum(1 for r in rows if r["ingest_status"] == "ready")
        print(f"# {folder}: {len(rows)} 件（ready {ready}）", file=sys.stderr)
        all_rows.extend(rows)
    print(f"# total {len(all_rows)}", file=sys.stderr)
    if not args.apply:
        if all_rows:
            sample = dict(all_rows[0])
            sample["body_text"] = (sample.get("body_text") or "")[:200]
            print(json.dumps(sample, ensure_ascii=False, indent=2))
        print("📒 comm backfill dry-run")
        return 0
    sb = client()
    if not args.skip_parties:
        now = datetime.now(JST).isoformat()
        upsert_parties(sb, [r for r in (party_row(p, now=now) for p in partners) if r])
    ids = insert_items(sb, all_rows)
    print(f"📒 comm backfill rows={len(all_rows)} in_db={len(ids)}")
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    params: dict[str, Any] = {"p_limit": args.limit}
    if args.party:
        params["p_party_ids"] = args.party
    if args.category:
        params["p_categories"] = args.category
    if args.query:
        params["p_query"] = args.query
    if args.since:
        params["p_since"] = args.since
    r = client().rpc("comm_search", params).execute()
    for x in r.data or []:
        print(
            f"{x['occurred_at'][:16]}\t{x['channel']}\t{x['direction']}\t"
            f"{x['party_id']}\t{x['work_status']}\t{(x.get('subject') or '')[:60]}"
        )
    print(f"# {len(r.data or [])} 件", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s1 = sub.add_parser("sync-parties")
    s1.add_argument("--contact", help="連絡先一覧.yaml のパス（省略時は OneDrive→repo）")
    g1 = s1.add_mutually_exclusive_group()
    g1.add_argument("--dry-run", action="store_true")
    g1.add_argument("--apply", action="store_true")
    s1.set_defaults(func=cmd_sync_parties)

    s2 = sub.add_parser("backfill-md")
    s2.add_argument("--contact")
    s2.add_argument("--folder", action="append", help="対象フォルダ（複数可）")
    s2.add_argument("--recent-days", type=int, default=14, help="これより古い受信は done 扱い")
    s2.add_argument("--skip-parties", action="store_true")
    g2 = s2.add_mutually_exclusive_group()
    g2.add_argument("--dry-run", action="store_true")
    g2.add_argument("--apply", action="store_true")
    s2.set_defaults(func=cmd_backfill_md)

    s3 = sub.add_parser("search")
    s3.add_argument("--party", action="append")
    s3.add_argument("--category", action="append")
    s3.add_argument("--query")
    s3.add_argument("--since")
    s3.add_argument("--limit", type=int, default=30)
    s3.set_defaults(func=cmd_search)

    args = ap.parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
