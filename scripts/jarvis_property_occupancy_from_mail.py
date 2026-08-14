#!/usr/bin/env python3
"""
パートナーやり取り＋空室対策メール履歴から空室／入居を検知し
property_units / events / memo_log を更新。

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

CAMPAIGN_MAIL_DIR = Path(
    "~/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部"
    "/C2_ルーティン作業/24_空室対策メール履歴"
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
# High confidence — 成約・空室
VACANT_STRONG = re.compile(
    r"(退去|解約|空室に|空室と|空室が|空室出|退去予告|退去届|退去連絡|"
    r"再募集|募集を改めて再開|募集再開|募集開始のお願い|入居キャンセル)"
)
OCCUPIED_STRONG = re.compile(
    r"(入居決定|入居が決ま|決まりました|契約を締結|賃貸借契約を締結|"
    r"満室とな|満室になり|入居者様と賃貸借契約|募集終了|入居確定)"
)
# Ambiguous
VACANT_WEAK = re.compile(r"空室|募集|内覧")
OCCUPIED_WEAK = re.compile(r"入居|申込|審査")

HEADING_RE = re.compile(
    r"^###\s+(\d{4})[/-](\d{1,2})[/-](\d{1,2})",
)
FILENAME_DATE_RE = re.compile(r"^(\d{2})(\d{2})(\d{2})_")
ROOM_WITH_BLDG_RE = re.compile(
    r"(?:【\s*Grandole志賀本通\s*(II|Ⅱ|I|Ⅰ)\s*】|"
    r"Grandole志賀本通\s*(II|Ⅱ|I|Ⅰ)|"
    r"(?<![A-Za-z])(II|Ⅱ|I|Ⅰ)\s*)"
    r"[^\n]{0,12}?"
    r"(?<!\d)([12]0[1235])\s*号\s*室",
    re.I,
)
RENT_LINE_RE = re.compile(r"・?\s*家賃[：:]\s*([\d,]+)\s*円")
MGMT_LINE_RE = re.compile(r"・?\s*管理費[：:]\s*([\d,]+)\s*円")
YEAR1_CAMPAIGN_RE = re.compile(
    r"1年間\s*[−\-－▲△]\s*([\d,]+)\s*円\s*[（(]\s*([\d,]+)\s*円|"
    r"キャンペーン価格[^\n]{0,40}?[（(]\s*([\d,]+)\s*円|"
    r"1年目[^\d]{0,12}([\d,]+)\s*円"
)
YEAR2_RE = re.compile(r"2年目以降[：:］\]]?\s*[^\d]{0,12}([\d,]+)\s*円")
BRACKET_PROP_ROOM_RE = re.compile(
    r"【\s*Grandole志賀本通\s*(II|Ⅱ|I|Ⅰ)[^\】]*】\s*([12]0[1235])\s*号\s*室",
    re.I,
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


def _bldg_token_to_prop(token: str) -> tuple[str, str] | None:
    t = (token or "").strip().upper().replace("Ⅱ", "II").replace("Ⅰ", "I")
    if t in ("II", "2", "２"):
        return "grandole-ii", "Grandole志賀本通II"
    if t in ("I", "1", "１"):
        return "grandole-i", "Grandole志賀本通I"
    return None


def parse_yen(raw: str | None) -> float | None:
    if not raw:
        return None
    try:
        return float(str(raw).replace(",", ""))
    except ValueError:
        return None


def extract_rent_terms(text: str) -> dict[str, Any]:
    """募集条件ブロックから家賃・管理費・1年目/2年目を拾う。"""
    out: dict[str, Any] = {}
    m = RENT_LINE_RE.search(text)
    if m:
        out["rent_year2"] = parse_yen(m.group(1))
    m = MGMT_LINE_RE.search(text)
    if m:
        out["management_fee"] = parse_yen(m.group(1))
    m = YEAR2_RE.search(text)
    if m:
        out["rent_year2"] = parse_yen(m.group(1)) or out.get("rent_year2")
    m = YEAR1_CAMPAIGN_RE.search(text)
    if m:
        # g1=discount, g2=year1 from 1年間 -X円（Y円）
        # g3=year1 from キャンペーン価格…（Y円）
        # g4=year1 from 1年目…Y円
        if m.group(2):
            out["rent_year1"] = parse_yen(m.group(2))
            disc = parse_yen(m.group(1))
            if disc is not None:
                out["discount_yen"] = disc
        elif m.group(3):
            out["rent_year1"] = parse_yen(m.group(3))
        elif m.group(4):
            out["rent_year1"] = parse_yen(m.group(4))
    ry2 = out.get("rent_year2")
    ry1 = out.get("rent_year1")
    mgmt = out.get("management_fee")
    if ry2 is not None and ry1 is not None and out.get("discount_yen") is None:
        out["discount_yen"] = float(ry2) - float(ry1)
    if ry2 is not None:
        out["total_year2"] = float(ry2) + (float(mgmt) if mgmt is not None else 0.0)
    if ry1 is not None:
        out["total_year1"] = float(ry1) + (float(mgmt) if mgmt is not None else 0.0)
    return out


def extract_room_property_pairs(text: str) -> list[tuple[str, str, str]]:
    """(property_id, property_name, room) を件名・本文から抽出。"""
    pairs: list[tuple[str, str, str]] = []
    seen: set[str] = set()

    for m in BRACKET_PROP_ROOM_RE.finditer(text):
        prop = _bldg_token_to_prop(m.group(1))
        if not prop:
            continue
        room = m.group(2)
        key = f"{prop[0]}-{room}"
        if key not in seen:
            seen.add(key)
            pairs.append((prop[0], prop[1], room))

    for m in ROOM_WITH_BLDG_RE.finditer(text):
        token = m.group(1) or m.group(2) or m.group(3) or ""
        prop = _bldg_token_to_prop(token)
        if not prop:
            continue
        room = m.group(4)
        key = f"{prop[0]}-{room}"
        if key not in seen:
            seen.add(key)
            pairs.append((prop[0], prop[1], room))

    if pairs:
        return pairs

    prop = detect_property(text)
    rooms = list(dict.fromkeys(ROOM_RE.findall(text)))
    if prop and rooms:
        for room in rooms:
            pairs.append((prop[0], prop[1], room))
    return pairs


def classify_event(subject: str, body: str) -> tuple[str | None, str]:
    """returns (event_type|None, confidence strong|weak|none)"""
    blob = f"{subject}\n{body}"
    if re.search(r"入居キャンセル|再募集|募集再開|募集を改めて再開", blob):
        if VACANT_STRONG.search(blob) or "募集" in blob:
            return "vacant", "strong"
    if OCCUPIED_STRONG.search(blob):
        return "occupied", "strong"
    if VACANT_STRONG.search(blob):
        return "vacant", "strong"
    has_o = bool(OCCUPIED_WEAK.search(blob))
    has_v = bool(VACANT_WEAK.search(blob))
    if has_o and not has_v:
        return "occupied", "weak"
    if has_v and not has_o:
        return "vacant", "weak"
    if has_o or has_v:
        return None, "weak"
    return None, "none"


def _room_context(blob: str, property_id: str, room: str) -> str:
    """号室周辺の文脈を切り出し（複数号室メールの誤分類防止）。"""
    short = "II" if property_id.endswith("ii") else "I"
    lines = blob.splitlines()
    subject = lines[0] if lines else ""
    subject_bits: list[str] = []
    for part in re.split(r"[／/]", subject):
        if room in part:
            subject_bits.append(part.strip())
    if not subject_bits and room in subject and subject.count("号室") <= 1:
        subject_bits.append(subject)

    snippets: list[str] = list(subject_bits)
    patterns = [
        rf".{{0,100}}{re.escape(room)}\s*号\s*室.{{0,160}}",
        rf".{{0,60}}{short}\s*{re.escape(room)}.{{0,100}}",
    ]
    body = "\n".join(lines[1:]) if len(lines) > 1 else ""
    for pat in patterns:
        for m in re.finditer(pat, body, flags=re.S):
            snippets.append(m.group(0))
    if not snippets:
        return blob
    return "\n".join(snippets[:8])


def classify_event_for_room(
    subject: str,
    body: str,
    property_id: str,
    room: str,
) -> tuple[str | None, str]:
    """号室単位の分類。混在件名（成約＋募集再開）に対応。"""
    blob = f"{subject}\n{body}"
    local = _room_context(blob, property_id, room)
    # ローカルに強いシグナルがあればそれを優先
    local_has_occ = bool(OCCUPIED_STRONG.search(local))
    local_has_vac = bool(
        VACANT_STRONG.search(local)
        or re.search(r"入居募集|募集のお願い|募集再開|再募集", local)
    )
    if local_has_occ and not local_has_vac:
        return "occupied", "strong"
    if local_has_vac and not local_has_occ:
        return "vacant", "strong"
    if local_has_occ and local_has_vac:
        # 同じ断片に両方あるときは「入居決定／決まり」を優先、なければ募集
        if re.search(r"入居決定|決まりました|入居確定|募集終了|契約を締結", local):
            if not re.search(r"募集再開|再募集|入居募集のお願い", local):
                return "occupied", "strong"
        if re.search(r"募集再開|再募集|入居募集|募集のお願い", local):
            return "vacant", "strong"
        return "occupied", "strong"
    return classify_event(subject, body)


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


def parse_campaign_mail_file(path: Path, since: date) -> dict[str, Any] | None:
    """24_空室対策メール履歴 の 1ファイル＝1通（1行目＝件名）。"""
    if path.suffix.lower() != ".md" or path.name.startswith("."):
        return None
    if path.name in ("test.md", "Cursorチャット文例_メール送信.md"):
        return None
    if "Works" in path.name:
        return None
    fm = FILENAME_DATE_RE.match(path.name)
    if not fm:
        return None
    yy, mm, dd = int(fm.group(1)), int(fm.group(2)), int(fm.group(3))
    year = 2000 + yy
    try:
        occurred = date(year, mm, dd)
    except ValueError:
        return None
    if occurred < since:
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    subject = (lines[0] if lines else path.stem).strip()
    body = "\n".join(lines[1:]).strip() if len(lines) > 1 else text
    return {
        "date": occurred.isoformat(),
        "subject": subject,
        "body": body,
        "ref": path.name,
        "source_kind": "campaign_mail",
    }


def _append_memo_log(
    payload: dict[str, Any],
    *,
    text: str,
    at: str,
    source: str = "mail",
) -> dict[str, Any]:
    log = list(payload.get("memo_log") or [])
    if not isinstance(log, list):
        log = []
    clean = (text or "").strip()[:400]
    if not clean:
        return payload
    for item in log:
        if (
            isinstance(item, dict)
            and str(item.get("source")) == source
            and str(item.get("text") or "").strip() == clean
        ):
            return payload
    log.append({"at": at, "text": clean, "source": source})
    payload["memo_log"] = log[-80:]
    return payload


def scan(days: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    since = date.today() - timedelta(days=days)
    seen = load_seen()
    applied: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []

    # 1) パートナーやり取り
    for folder in PARTNER_FOLDERS:
        md = ONEDRIVE_PARTNERS / folder / "5.やり取り.md"
        for block in parse_md_blocks(md, since):
            blob = f"{block['subject']}\n{block['body']}"
            pairs = extract_room_property_pairs(blob)
            if not pairs:
                continue
            terms = extract_rent_terms(blob)
            for pid, pname, room in pairs:
                event_type, conf = classify_event_for_room(
                    block["subject"], block["body"], pid, room
                )
                if conf == "none":
                    continue
                key = (
                    f"{block['date']}|{pid}|{room}|"
                    f"{event_type or 'amb'}|{block['subject'][:80]}"
                )
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
                    "terms": terms,
                    "memo_text": (
                        f"{block['date']} {block['subject'][:120]}".strip()
                    ),
                }
                if conf == "strong" and event_type in ("vacant", "occupied"):
                    applied.append(item)
                else:
                    pending.append(item)

    # 2) 空室対策メール履歴（成約・再募集・条件変更）
    if CAMPAIGN_MAIL_DIR.is_dir():
        for path in sorted(CAMPAIGN_MAIL_DIR.glob("*.md")):
            block = parse_campaign_mail_file(path, since)
            if not block:
                continue
            blob = f"{block['subject']}\n{block['body']}"
            pairs = extract_room_property_pairs(blob)
            if not pairs:
                continue
            terms = extract_rent_terms(blob)
            for pid, pname, room in pairs:
                event_type, conf = classify_event_for_room(
                    block["subject"], block["body"], pid, room
                )
                terms_only = (
                    event_type is None
                    and conf in ("weak", "none")
                    and bool(terms.get("rent_year2") or terms.get("rent_year1"))
                )
                if conf == "none" and not terms_only:
                    continue
                et = event_type
                c = conf
                if terms_only:
                    et = None
                    c = "strong"
                key = (
                    f"campaign|{block['date']}|{pid}|{room}|"
                    f"{et or 'terms'}|{block['ref']}"
                )
                if key in seen:
                    continue
                item = {
                    "key": key,
                    "occurred_on": block["date"],
                    "event_type": et,
                    "property_id": pid,
                    "property_name": pname,
                    "room": room,
                    "source": "campaign_mail",
                    "ref": block["subject"][:200] or block["ref"],
                    "note": f"24_空室対策メール履歴/{block['ref']} conf={c}",
                    "confidence": c,
                    "partner_folder": "24_空室対策メール履歴",
                    "terms": terms,
                    "memo_text": (
                        f"{block['date']} {block['subject'][:160]}".strip()
                    ),
                    "terms_only": terms_only,
                }
                if c == "strong" and (et in ("vacant", "occupied") or terms_only):
                    applied.append(item)
                else:
                    pending.append(item)

    return applied, pending


def apply_push(applied: list[dict[str, Any]], pending: list[dict[str, Any]]) -> None:
    sb = sb_client()
    now = datetime.now(tz=JST).isoformat()
    seen = load_seen()

    latest: dict[str, dict[str, Any]] = {}
    latest_terms: dict[str, dict[str, Any]] = {}
    for item in sorted(applied, key=lambda x: x["occurred_on"]):
        uid = f"{item['property_id']}-{item['room']}"
        if item.get("terms_only") or item.get("event_type") is None:
            if item.get("terms"):
                latest_terms[uid] = item
            continue
        latest[uid] = item
        if item.get("terms"):
            latest_terms[uid] = item

    touched = set(latest) | set(latest_terms)
    for uid in touched:
        item = latest.get(uid) or latest_terms.get(uid)
        if not item:
            continue
        status = item.get("event_type")
        terms = (latest_terms.get(uid) or item).get("terms") or {}
        memo_src = latest.get(uid) or latest_terms.get(uid) or item
        existing = (
            sb.table("property_units").select("*").eq("id", uid).limit(1).execute()
        )
        rows = existing.data or []
        short = "II" if item["property_id"].endswith("ii") else "I"
        if item["property_id"] == "caramel":
            short = "C"

        if rows:
            row = rows[0]
            payload = dict(row.get("payload") or {})
            payload["last_mail_ref"] = memo_src.get("ref")
            payload["last_mail_on"] = memo_src.get("occurred_on")
            if terms.get("management_fee") is not None:
                payload["management_fee"] = terms["management_fee"]
                payload["mgmt_fee"] = terms["management_fee"]
            for k in (
                "rent_year1",
                "rent_year2",
                "total_year1",
                "total_year2",
                "discount_yen",
            ):
                if terms.get(k) is not None:
                    payload[k] = terms[k]
            if (
                terms.get("rent_year2") is not None
                and terms.get("management_fee") is not None
            ):
                payload["total_rent"] = float(terms["rent_year2"]) + float(
                    terms["management_fee"]
                )
            elif terms.get("total_year2") is not None:
                payload["total_rent"] = terms["total_year2"]

            payload = _append_memo_log(
                payload,
                text=str(memo_src.get("memo_text") or memo_src.get("ref") or ""),
                at=now,
                source="mail",
            )
            update: dict[str, Any] = {
                "source": item.get("source") or "mail",
                "note": str(memo_src.get("memo_text") or memo_src.get("ref") or "")[
                    :500
                ],
                "updated_at": now,
                "payload": payload,
            }
            if status in ("vacant", "occupied") and row.get("status") != status:
                update["status"] = status
            if terms.get("rent_year2") is not None:
                if status == "occupied" and terms.get("rent_year1") is not None:
                    update["rent"] = terms["rent_year1"]
                else:
                    update["rent"] = terms.get("rent_year1") or terms["rent_year2"]
            elif terms.get("rent_year1") is not None:
                update["rent"] = terms["rent_year1"]

            sb.table("property_units").update(update).eq("id", uid).execute()
        else:
            payload = {
                "short": short,
                "last_mail_on": item.get("occurred_on"),
                "last_mail_ref": item.get("ref"),
            }
            for k, v in terms.items():
                if v is not None:
                    payload[k] = v
            if terms.get("management_fee") is not None:
                payload["mgmt_fee"] = terms["management_fee"]
            payload = _append_memo_log(
                payload,
                text=str(memo_src.get("memo_text") or item.get("ref") or ""),
                at=now,
                source="mail",
            )
            rent = terms.get("rent_year1") or terms.get("rent_year2")
            sb.table("property_units").upsert(
                {
                    "id": uid,
                    "property_id": item["property_id"],
                    "property_name": item["property_name"],
                    "room": item["room"],
                    "status": status or "occupied",
                    "rent": rent,
                    "source": item.get("source") or "mail",
                    "note": str(memo_src.get("memo_text") or item.get("ref") or "")[
                        :500
                    ],
                    "payload": payload,
                    "updated_at": now,
                }
            ).execute()

        if status in ("vacant", "occupied"):
            sb.table("property_occupancy_events").insert(
                {
                    "occurred_on": item["occurred_on"],
                    "event_type": status,
                    "property_id": item["property_id"],
                    "property_name": item["property_name"],
                    "room": item["room"],
                    "source": item.get("source") or "mail",
                    "ref": item.get("ref"),
                    "note": item.get("note"),
                    "payload": {
                        "confidence": "strong",
                        "terms": terms or None,
                    },
                }
            ).execute()
        seen.add(item["key"])
        if memo_src.get("key"):
            seen.add(memo_src["key"])

    for item in applied:
        seen.add(item["key"])

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
        {
            "key": "occupancy_summary",
            "value": json.dumps(summary, ensure_ascii=False),
            "updated_at": now,
        }
    ).execute()
    sb.table("sync_meta").upsert(
        {
            "key": "occupancy_mail_pending",
            "value": json.dumps(pending[:40], ensure_ascii=False),
            "updated_at": now,
        }
    ).execute()
    if pending:
        sb.table("sync_meta").upsert(
            {
                "key": "occupancy_mail_pending_count",
                "value": str(len(pending)),
                "updated_at": now,
            }
        ).execute()

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
    for a in applied[:12]:
        print(
            f"  - {a['occurred_on']} {a['property_id']}-{a['room']} "
            f"{a.get('event_type') or 'terms'} {a.get('ref','')[:60]}"
        )

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
