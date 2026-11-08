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
  python scripts/jarvis_comm_hub.py dedupe --dry-run   # 二重記載の整理（--apply で削除）
  python scripts/jarvis_comm_hub.py link-pending --dry-run   # /partner の未返信を台帳へつなぐ（--apply）
  python scripts/jarvis_comm_hub.py search --party partner:P102_ミニテック --query エアコン
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


def dedupe_key(row: dict[str, Any]) -> tuple[str, str, str, str, str]:
    """同じ送受信が md に2回書かれた分（「自分から送信」と誤ラベルの「相手から返信」等）を同一視する鍵。"""
    body = re.sub(r"\s+", "", str(row.get("body_text") or ""))[:300]
    occurred = str(row.get("occurred_at") or "")
    try:  # DB は UTC、取込側は +09:00。同じ瞬間なら同じ文字列にそろえる
        occurred = datetime.fromisoformat(occurred).astimezone(ZoneInfo("UTC")).isoformat()
    except ValueError:
        pass
    return (
        str(row.get("party_id") or ""),
        str(row.get("channel") or ""),
        occurred,
        str(row.get("direction") or ""),
        body or str(row.get("subject") or ""),
    )


def items_from_md_text(
    text: str,
    folder: str,
    name: str,
    *,
    recent_cutoff: datetime | None = None,
) -> list[dict[str, Any]]:
    from jarvis_night_triage import parse_yoritoori_text

    out: dict[str, dict[str, Any]] = {}
    seen: set[tuple[str, str, str, str, str]] = set()
    for e in parse_yoritoori_text(text, folder, name):
        row = item_from_md_entry(e, recent_cutoff=recent_cutoff)
        if row is None:
            continue
        # 同一キーは先勝ち（md は新しい順なので最新の見出しを採用）
        if row["external_id"] in out:
            continue
        # 同じ日時・向き・本文の二重記載は1行にまとめる
        dk = dedupe_key(row)
        if dk in seen:
            continue
        seen.add(dk)
        out[row["external_id"]] = row
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


def existing_by_dedupe_key(sb, since_iso: str) -> dict[tuple[str, str, str, str, str], str]:
    """since 以降の md 由来の既存行 → {dedupe_key: id}（同一キーは古い行を採用）。"""
    out: dict[tuple[str, str, str, str, str], str] = {}
    start = 0
    while True:
        r = (
            sb.table("comm_items")
            .select("id,party_id,channel,occurred_at,direction,body_text,subject,created_at,source_ref")
            .gte("occurred_at", since_iso)
            .order("id")
            .range(start, start + 999)
            .execute()
        )
        batch = r.data or []
        for x in sorted(batch, key=lambda y: (str(y.get("created_at") or ""), str(y["id"]))):
            if (x.get("source_ref") or {}).get("source") not in ("yoritoori_md", "triage_item"):
                continue
            out.setdefault(dedupe_key(x), str(x["id"]))
        if len(batch) < 1000:
            break
        start += 1000
    return out


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


def _triage_entry(t: dict[str, Any]) -> dict[str, Any]:
    """triage_items 行 → item_from_md_entry に渡せる形。"""
    return {
        "folder": t.get("folder") or "",
        "received_at": t.get("received_at") or "",
        "channel": t.get("channel") or "Gmail",
        "subject": t.get("subject") or "",
        "summary": t.get("summary") or "",
        "body": t.get("original_body") or "",
        "partner_name": t.get("partner") or t.get("folder") or "",
    }


def link_pending(sb, *, apply: bool) -> dict[str, int]:
    """台帳とつながっていない未返信（/partner の pending）を台帳へつなぐ。

    1. 同じ鍵（dedupe_key）の行 → 2. 同じ相手・チャネル・日時の受信が1行だけ → 3. 無ければ新規
    （external_id = triage:<id>）。つないだ行は needs_reply にする（md 取込で過去分扱いの done も戻す）。
    """
    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        r = (
            sb.table("triage_items")
            .select("id,folder,partner,channel,received_at,subject,summary,original_body,status,comm_item_id")
            .eq("lane", "partner")
            .eq("status", "pending")
            .is_("comm_item_id", "null")
            .range(start, start + 499)
            .execute()
        )
        batch = r.data or []
        rows.extend(batch)
        if len(batch) < 500:
            break
        start += 500
    stats = {"pending_unlinked": len(rows), "matched": 0, "created": 0, "skipped": 0}
    if not rows:
        return stats

    cands: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for t in rows:
        item = item_from_md_entry(_triage_entry(t))
        if item is None or not item.get("party_id"):
            stats["skipped"] += 1
            continue
        item["direction"] = "inbound"  # pending = 相手からの未返信
        cands.append((t, item))
    if not cands:
        return stats

    since = min(
        datetime.fromisoformat(i["occurred_at"]).astimezone(ZoneInfo("UTC")) for _t, i in cands
    ).isoformat()
    by_key = existing_by_dedupe_key(sb, since)
    by_slot: dict[tuple[str, str, str], list[str]] = {}
    for (party, ch, occ, direction, _b), iid in by_key.items():
        if direction == "inbound":
            by_slot.setdefault((party, ch, occ), []).append(iid)

    link_rows: list[tuple[str, str]] = []  # (triage_id, item_id)
    new_items: list[tuple[str, dict[str, Any]]] = []
    for t, item in cands:
        dk = dedupe_key(item)
        iid = by_key.get(dk)
        if not iid:
            slot = by_slot.get(dk[:3]) or []
            iid = slot[0] if len(slot) == 1 else None
        if iid:
            link_rows.append((str(t["id"]), iid))
            stats["matched"] += 1
            continue
        new = dict(item)
        new["external_id"] = f"triage:{t['id']}"
        new["work_status"] = "needs_reply"
        new["source_ref"] = {**(item.get("source_ref") or {}), "source": "triage_item", "triage_id": t["id"]}
        new_items.append((str(t["id"]), new))
        stats["created"] += 1

    if not apply:
        return stats

    if new_items:
        ids = insert_items(sb, [x for _tid, x in new_items])
        for tid, x in new_items:
            if x["external_id"] in ids:
                link_rows.append((tid, ids[x["external_id"]]))
    item_ids = sorted({iid for _tid, iid in link_rows})
    for i in range(0, len(item_ids), 100):
        (
            sb.table("comm_items")
            .update({"work_status": "needs_reply"})
            .in_("id", item_ids[i : i + 100])
            .in_("work_status", ["new", "done"])
            .execute()
        )
    for tid, iid in link_rows:
        sb.table("triage_items").update({"comm_item_id": iid}).eq("id", tid).execute()
    link_items(sb, [{"item_id": iid, "target_type": "triage_item", "target_id": tid} for tid, iid in link_rows])
    return stats


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


def find_duplicate_ids(rows: list[dict[str, Any]]) -> list[str]:
    """dedupe_key が同じ行のうち、最初の1行（created_at, id 順）を残して他の id を返す。"""
    keep: dict[tuple[str, str, str, str, str], str] = {}
    drop: list[str] = []
    for r in sorted(rows, key=lambda x: (str(x.get("created_at") or ""), str(x.get("id") or ""))):
        k = dedupe_key(r)
        if k in keep:
            drop.append(str(r["id"]))
        else:
            keep[k] = str(r["id"])
    return drop


def cmd_dedupe(args: argparse.Namespace) -> int:
    sb = client()
    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        r = (
            sb.table("comm_items")
            .select("id,party_id,channel,occurred_at,direction,body_text,subject,created_at,source_ref")
            .eq("category", "partner")
            .eq("account", "")
            .order("id")
            .range(start, start + 999)
            .execute()
        )
        batch = r.data or []
        rows.extend(batch)
        if len(batch) < 1000:
            break
        start += 1000
    # md 由来だけを対象にする（他経路の行は触らない）
    rows = [x for x in rows if (x.get("source_ref") or {}).get("source") == "yoritoori_md"]
    drop = find_duplicate_ids(rows)
    print(f"# md 由来 {len(rows)} 件 / 重複 {len(drop)} 件", file=sys.stderr)
    if not args.apply:
        print("📒 comm dedupe dry-run")
        return 0
    n = 0
    for i in range(0, len(drop), 100):
        sb.table("comm_items").delete().in_("id", drop[i : i + 100]).execute()
        n += len(drop[i : i + 100])
    print(f"📒 comm dedupe deleted={n}")
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


def recent_context(
    folder: str,
    subject: str = "",
    *,
    limit: int = 3,
    since_days: int = 365,
    sb=None,
) -> list[str]:
    """返信下書きの参考用に、同じ相手の過去のやり取りを台帳から引く（211 用・soft-fail）。

    件名に近い過去分（キーワード一致）を先に、足りなければ直近を足す。失敗時は空リスト。
    """
    if (os.environ.get("JARVIS_COMM_HUB") or "").strip() == "0":
        return []
    try:
        sb = sb or client()
        since = (datetime.now(JST) - timedelta(days=since_days)).isoformat()
        base = {
            "p_party_ids": [party_id_for_folder(folder)],
            "p_since": since,
            "p_limit": limit,
        }
        rows: list[dict[str, Any]] = []
        q = re.sub(r"^(re|fw|fwd)\s*:\s*", "", (subject or "").strip(), flags=re.I)
        q = re.sub(r"[【】\[\]()（）「」]", " ", q).strip()
        if len(q) >= 2:
            rows = sb.rpc("comm_search", {**base, "p_query": q[:60]}).execute().data or []
        if len(rows) < limit:
            seen = {r["id"] for r in rows}
            recent = sb.rpc("comm_search", {**base, "p_limit": limit}).execute().data or []
            rows += [r for r in recent if r["id"] not in seen][: limit - len(rows)]
        out = []
        for r in rows[:limit]:
            who = "自分" if r.get("direction") == "outbound" else "相手"
            text = (r.get("subject") or r.get("summary") or "").strip().replace("\n", " ")
            out.append(f"{str(r['occurred_at'])[:10]} {who} {text[:50]}")
        return out
    except Exception as e:  # noqa: BLE001
        print(f"# comm hub context soft-fail: {e}", file=sys.stderr)
        return []


def cmd_link_pending(args: argparse.Namespace) -> int:
    stats = link_pending(client(), apply=bool(args.apply))
    mode = "apply" if args.apply else "dry-run"
    print(
        f"📒 comm link-pending {mode} pending_unlinked={stats['pending_unlinked']} "
        f"matched={stats['matched']} created={stats['created']} skipped={stats['skipped']}"
    )
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

    s4 = sub.add_parser("dedupe", help="md 由来の二重記載（同日時・同向き・同本文）を1行にまとめる")
    g4 = s4.add_mutually_exclusive_group()
    g4.add_argument("--dry-run", action="store_true")
    g4.add_argument("--apply", action="store_true")
    s4.set_defaults(func=cmd_dedupe)

    s5 = sub.add_parser("link-pending", help="台帳とつながっていない /partner の未返信を台帳へつなぐ")
    g5 = s5.add_mutually_exclusive_group()
    g5.add_argument("--dry-run", action="store_true")
    g5.add_argument("--apply", action="store_true")
    s5.set_defaults(func=cmd_link_pending)

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
