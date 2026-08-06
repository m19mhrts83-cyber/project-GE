#!/usr/bin/env python3
"""
パートナーやり取りから空室／入居を検知し property_units / events を更新。

高確度パターンのみ自動適用。曖昧な候補は sync_meta.occupancy_mail_pending に残す。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  python scripts/jarvis_property_occupancy_from_mail.py
  python scripts/jarvis_property_occupancy_from_mail.py --push
  python scripts/jarvis_property_occupancy_from_mail.py --days 60 --push
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
OUT_PATH = REPO / ".jarvis_state" / "property_occupancy_mail.json"
STATE_PATH = REPO / ".jarvis_state" / "property_occupancy_mail_seen.json"

ONEDRIVE_PARTNERS = Path(
    "~/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部"
    "/C2_ルーティン作業/26_パートナー社への相談"
).expanduser()

PARTNER_FOLDERS = [
    "102_ミニテック",
    "104_LEAF",
    "103_Tcell",
    "101_ホームプランナー",
]

PROPERTY_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    # II を先に（I に誤マッチしない）
    (
        re.compile(
            r"Grandole\s*志賀本通\s*(?:II|Ⅱ|2|２)|志賀本通\s*(?:II|Ⅱ)|Grandole志賀本通II",
            re.I,
        ),
        "grandole-ii",
        "Grandole志賀本通II",
    ),
    (
        re.compile(
            r"Grandole\s*志賀本通\s*[IⅠ1１](?![IⅠ2２])|志賀本通\s*[IⅠ](?![IⅠ])|Grandole志賀本通I(?!I)",
            re.I,
        ),
        "grandole-i",
        "Grandole志賀本通I",
    ),
]


ROOM_RE = re.compile(r"(?<!\d)([12]0[1235])\s*号\s*室")
# High confidence
VACANT_STRONG = re.compile(
    r"(退去|解約|空室に|空室と|空室が|空室出|退去予告|退去届|退去連絡)"
)
OCCUPIED_STRONG = re.compile(
    r"(入居決定|入居が決ま|契約を締結|満室とな|満室になり|入居者様と賃貸借契約)"
)
# 退去後の精算・折衝フォロー（件名に古い「退去」が残る）は空室イベントにしない
SETTLEMENT_FOLLOWUP = re.compile(
    r"(精算確定|退去者との折衝|退去精算|原状回復.*完了|クリーニング.*完了)"
)
VACANT_INTENT = re.compile(r"(退去予告|退去届|空室にな|募集を開始|募集開始|空室が出)")
# Ambiguous
VACANT_WEAK = re.compile(r"空室|募集|内覧")
OCCUPIED_WEAK = re.compile(r"入居|申込|審査")

HEADING_RE = re.compile(
    r"^###\s+(\d{4})[/-](\d{1,2})[/-](\d{1,2})",
)


def sb_client():
    from supabase import create_client

    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_* 未設定")
    return create_client(url, key)


def load_seen() -> set[str]:
    if not STATE_PATH.is_file():
        return set()
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return set(data.get("seen") or [])
    except Exception:
        return set()


def save_seen(seen: set[str]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    # keep last 2000
    items = sorted(seen)[-2000:]
    STATE_PATH.write_text(
        json.dumps(
            {"seen": items, "updated": datetime.now(tz=JST).isoformat()},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def detect_property(text: str) -> tuple[str, str] | None:
    for pat, pid, name in PROPERTY_PATTERNS:
        if pat.search(text):
            return pid, name
    return None


def parse_md_blocks(path: Path, since: date) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8", errors="replace")
    blocks: list[dict[str, Any]] = []
    current_date: date | None = None
    buf: list[str] = []
    subject = ""

    def flush() -> None:
        nonlocal buf, subject, current_date
        if current_date and current_date >= since and buf:
            body = "\n".join(buf)
            blocks.append(
                {
                    "date": current_date.isoformat(),
                    "subject": subject,
                    "body": body,
                }
            )
        buf = []
        subject = ""

    for line in text.splitlines():
        hm = HEADING_RE.match(line.strip())
        if hm:
            flush()
            y, m, d = int(hm.group(1)), int(hm.group(2)), int(hm.group(3))
            try:
                current_date = date(y, m, d)
            except ValueError:
                current_date = None
            continue
        if line.startswith("**件名**") or line.startswith("**件名**:"):
            subject = re.sub(r"^\*\*件名\*\*\s*:?\s*", "", line).strip()
        buf.append(line)
    flush()
    return blocks


def classify_event(subject: str, body: str) -> tuple[str | None, str]:
    """returns (event_type|None, confidence strong|weak|none)"""
    blob = f"{subject}\n{body}"
    if OCCUPIED_STRONG.search(blob):
        return "occupied", "strong"
    # 精算フォロー等は件名の「退去」だけで vacant にしない
    if SETTLEMENT_FOLLOWUP.search(blob) and not VACANT_INTENT.search(blob):
        return None, "weak"
    if VACANT_STRONG.search(blob):
        return "vacant", "strong"
    # both weak → ambiguous
    has_o = bool(OCCUPIED_WEAK.search(blob))
    has_v = bool(VACANT_WEAK.search(blob))
    if has_o and not has_v:
        return "occupied", "weak"
    if has_v and not has_o:
        return "vacant", "weak"
    if has_o or has_v:
        return None, "weak"
    return None, "none"


def scan(days: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    since = date.today() - timedelta(days=days)
    seen = load_seen()
    applied: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []

    for folder in PARTNER_FOLDERS:
        md = ONEDRIVE_PARTNERS / folder / "5.やり取り.md"
        for block in parse_md_blocks(md, since):
            blob = f"{block['subject']}\n{block['body']}"
            prop = detect_property(blob)
            rooms = list(dict.fromkeys(ROOM_RE.findall(blob)))
            event_type, conf = classify_event(block["subject"], block["body"])
            if not rooms or not prop:
                continue
            if conf == "none":
                continue
            pid, pname = prop
            for room in rooms:
                key = f"{block['date']}|{pid}|{room}|{event_type or 'amb'}|{block['subject'][:80]}"
                if key in seen:
                    continue
                item = {
                    "key": key,
                    "occurred_on": block["date"],
                    "event_type": event_type,
                    "property_id": pid,
                    "property_name": pname,
                    "room": room,
                    "source": "mail",
                    "ref": block["subject"][:200] or folder,
                    "note": f"{folder} conf={conf}",
                    "confidence": conf,
                    "partner_folder": folder,
                }
                if conf == "strong" and event_type in ("vacant", "occupied"):
                    applied.append(item)
                else:
                    pending.append(item)
    return applied, pending


def apply_push(applied: list[dict[str, Any]], pending: list[dict[str, Any]]) -> None:
    sb = sb_client()
    now = datetime.now(tz=JST).isoformat()
    seen = load_seen()

    # 号室ごとに発生日が最も新しい strong イベントだけ採用（過去の空室を再適用しない）
    latest: dict[str, dict[str, Any]] = {}
    for item in sorted(applied, key=lambda x: x["occurred_on"]):
        uid = f"{item['property_id']}-{item['room']}"
        latest[uid] = item

    for uid, item in latest.items():
        status = item["event_type"]
        existing = (
            sb.table("property_units").select("*").eq("id", uid).limit(1).execute()
        )
        rows = existing.data or []
        if rows:
            row = rows[0]
            if row.get("status") == status:
                seen.add(item["key"])
                continue
            sb.table("property_units").update(
                {
                    "status": status,
                    "source": "mail",
                    "note": item.get("ref"),
                    "updated_at": now,
                    "payload": {
                        **(row.get("payload") or {}),
                        "last_mail_ref": item.get("ref"),
                        "last_mail_on": item.get("occurred_on"),
                    },
                }
            ).eq("id", uid).execute()
        else:
            sb.table("property_units").upsert(
                {
                    "id": uid,
                    "property_id": item["property_id"],
                    "property_name": item["property_name"],
                    "room": item["room"],
                    "status": status,
                    "source": "mail",
                    "note": item.get("ref"),
                    "payload": {
                        "short": "II" if item["property_id"].endswith("ii") else "I",
                        "last_mail_on": item.get("occurred_on"),
                    },
                    "updated_at": now,
                }
            ).execute()

        sb.table("property_occupancy_events").insert(
            {
                "occurred_on": item["occurred_on"],
                "event_type": status,
                "property_id": item["property_id"],
                "property_name": item["property_name"],
                "room": item["room"],
                "source": "mail",
                "ref": item.get("ref"),
                "note": item.get("note"),
                "payload": {"confidence": "strong"},
            }
        ).execute()
        seen.add(item["key"])

    # 同じスキャンで触っていない applied キーも seen に（再処理防止）
    for item in applied:
        seen.add(item["key"])

    # refresh summary from units
    units = (sb.table("property_units").select("*").execute().data) or []
    total = len(units)
    occupied = sum(1 for u in units if u.get("status") == "occupied")
    vacant_labels = []
    by: dict[str, Any] = {}
    for u in units:
        pid = u["property_id"]
        b = by.setdefault(
            pid,
            {
                "property_id": pid,
                "property_name": u["property_name"],
                "total": 0,
                "occupied": 0,
                "vacant": 0,
                "vacant_rooms": [],
            },
        )
        b["total"] += 1
        short = (u.get("payload") or {}).get("short") or pid
        if u.get("status") == "vacant":
            b["vacant"] += 1
            b["vacant_rooms"].append(u["room"])
            vacant_labels.append(f"{short}-{u['room']}")
        else:
            b["occupied"] += 1
    summary = {
        "total": total,
        "occupied": occupied,
        "vacant": total - occupied,
        "rate_pct": round(100.0 * occupied / total, 1) if total else 0.0,
        "vacant_labels": vacant_labels,
        "by_property": [
            {**b, "rate_pct": round(100.0 * b["occupied"] / (b["total"] or 1), 1)}
            for b in by.values()
        ],
    }
    sb.table("sync_meta").upsert(
        {"key": "occupancy_summary", "value": json.dumps(summary, ensure_ascii=False), "updated_at": now}
    ).execute()
    sb.table("sync_meta").upsert(
        {
            "key": "occupancy_mail_pending",
            "value": json.dumps(pending[:40], ensure_ascii=False),
            "updated_at": now,
        }
    ).execute()
    if pending:
        # soft watch-style hint in sync_meta only (no auto watch_status spam)
        sb.table("sync_meta").upsert(
            {
                "key": "occupancy_mail_pending_count",
                "value": str(len(pending)),
                "updated_at": now,
            }
        ).execute()

    # pending は seen に入れない（再スキャンで残る）。applied のみ記録
    save_seen(seen)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=45)
    ap.add_argument("--push", action="store_true")
    args = ap.parse_args(argv)

    applied, pending = scan(args.days)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(
            {
                "updated": datetime.now(tz=JST).isoformat(),
                "applied": applied,
                "pending": pending,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"# applied={len(applied)} pending={len(pending)} → {OUT_PATH}")

    if args.push:
        apply_push(applied, pending)
        print("# pushed mail occupancy updates")

    print(
        json.dumps(
            {"applied": len(applied), "pending": len(pending)},
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
