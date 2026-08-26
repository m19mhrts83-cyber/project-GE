#!/usr/bin/env python3
"""Grok [Grok修繕候補] メール → 修繕業者 YAML 自動反映。

S4 が matsuno.estate@gmail.com へ送った探索レポートを estate Gmail API で読み、
Markdown 表の候補を kurashift_repair_vendor_list.yaml に merge → Supabase sync。

  cd ~/git-repos
  ~/selenium_env/venv/bin/python scripts/jarvis_grok_repair_mail_apply.py --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_grok_repair_mail_apply.py --apply
  ~/selenium_env/venv/bin/python scripts/jarvis_grok_repair_mail_apply.py --days 90 --apply

使用アカウント: estate / Gmail API（受信）
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

REPO = Path(__file__).resolve().parents[1]
MANUAL = REPO / "215_kamiooya" / "C1_cursor" / "1b_Cursorマニュアル"
STATE_PATH = REPO / ".jarvis_state" / "grok_repair_mail_apply.json"
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]
SUBJECT_PREFIX = "[Grok修繕候補]"
PY = Path("/Users/matsunomasaharu2/selenium_env/venv/bin/python")
SYNC_SCRIPT = REPO / "scripts" / "jarvis_kurashift_repair_vendor_sync.py"

# name | trade | phone | url | sole_score | notes | source
HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "name": ("name", "会社名", "業者名", "氏名", "屋号"),
    "trade": ("trade", "職種"),
    "phone": ("phone", "tel", "電話"),
    "url": ("url", "hp", "サイト"),
    "sole_score": ("sole_score", "sole_proprietor_score", "score"),
    "notes": ("notes", "備考", "メモ"),
    "source": ("source", "出典"),
}

TRADE_MAP: dict[str, str] = {
    "水廻り": "plumbing",
    "水回り": "plumbing",
    "水道": "plumbing",
    "plumbing": "plumbing",
    "電気": "electric",
    "electric": "electric",
    "内装": "interior",
    "interior": "interior",
    "多能工": "multi",
    "便利屋": "multi",
    "multi": "multi",
    "屋根": "roof",
    "roof": "roof",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_state() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        return {"processed_ids": [], "last_run_at": None}
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"processed_ids": [], "last_run_at": None}
        data.setdefault("processed_ids", [])
        return data
    except Exception:
        return {"processed_ids": [], "last_run_at": None}


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
                text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
                text = re.sub(r"</p>", "\n", text, flags=re.I)
                text = re.sub(r"<[^>]+>", " ", text)
                text = re.sub(r"[ \t]+", " ", text)
            texts.append(text)
        for ch in part.get("parts") or []:
            walk(ch)

    walk(payload)
    # prefer plain if both
    plain = [t for t in texts if "|" in t]
    if plain:
        return "\n".join(plain)[:80000]
    return "\n".join(texts)[:80000]


def header_map(headers: list[dict]) -> dict[str, str]:
    out: dict[str, str] = {}
    for h in headers or []:
        out[(h.get("name") or "").lower()] = h.get("value") or ""
    return out


def fetch_repair_messages(svc, *, days: int, max_results: int) -> list[dict[str, Any]]:
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
            }
        )
    return out


def _norm_header_cell(s: str) -> str:
    return re.sub(r"\s+", "", (s or "").strip().lower())


def _map_header(cells: list[str]) -> dict[str, int]:
    idx: dict[str, int] = {}
    for i, raw in enumerate(cells):
        key = _norm_header_cell(raw)
        for field, aliases in HEADER_ALIASES.items():
            if field in idx:
                continue
            for a in aliases:
                if key == _norm_header_cell(a) or _norm_header_cell(a) in key:
                    idx[field] = i
                    break
    return idx


def _split_row(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _is_sep_row(cells: list[str]) -> bool:
    if not cells:
        return False
    return all(re.match(r"^:?-+:?$", c.replace(" ", "")) or c == "" for c in cells)


def normalize_trade(raw: str, fallback: str = "") -> str:
    s = (raw or "").strip()
    if not s:
        s = fallback
    low = s.lower()
    for k, v in TRADE_MAP.items():
        if k.lower() == low or k in s:
            return v
    return s or "multi"


def parse_meta(body: str) -> dict[str, str]:
    meta: dict[str, str] = {}
    for m in re.finditer(
        r"^(area|trade|bot|source|report_id)\s*:\s*(.+)$",
        body,
        re.I | re.M,
    ):
        meta[m.group(1).lower()] = m.group(2).strip()
    # subject fallback later
    return meta


def parse_candidates_from_body(
    body: str,
    *,
    subject: str = "",
    default_area: str = "",
    default_trade: str = "",
) -> list[dict[str, Any]]:
    meta = parse_meta(body)
    area = meta.get("area") or default_area
    trade_fb = normalize_trade(meta.get("trade") or default_trade)

    # subject: [Grok修繕候補] 名古屋市北区 水廻り
    if not area or not trade_fb:
        rest = re.sub(r"^\[Grok修繕候補\]\s*", "", subject or "", flags=re.I).strip()
        parts = rest.split()
        if parts and not area:
            area = parts[0]
        if len(parts) >= 2 and (not meta.get("trade")):
            trade_fb = normalize_trade(parts[1], trade_fb)

    lines = body.splitlines()
    header_i = -1
    colmap: dict[str, int] = {}
    for i, line in enumerate(lines):
        if "|" not in line:
            continue
        cells = _split_row(line)
        if len(cells) < 2:
            continue
        mapped = _map_header(cells)
        if "name" in mapped:
            header_i = i
            colmap = mapped
            break
    if header_i < 0:
        return []

    vendors: list[dict[str, Any]] = []
    for line in lines[header_i + 1 :]:
        if "|" not in line:
            if vendors and line.strip().startswith("##"):
                break
            continue
        cells = _split_row(line)
        if _is_sep_row(cells):
            continue
        if len(cells) <= colmap.get("name", 0):
            continue
        name = cells[colmap["name"]].strip() if "name" in colmap else ""
        if not name or name.lower() in ("name", "…", "...", "—", "-"):
            continue
        if _norm_header_cell(name) in ("name", "会社名", "業者名"):
            continue

        def cell(field: str) -> str:
            j = colmap.get(field)
            if j is None or j >= len(cells):
                return ""
            return cells[j].strip()

        trade = normalize_trade(cell("trade"), trade_fb)
        phone = cell("phone")
        url = cell("url")
        if url and not url.startswith("http") and "." in url:
            url = f"https://{url}"
        notes = cell("notes")
        source = cell("source") or "grok_repair_mail"
        sole = cell("sole_score")
        vendors.append(
            {
                "name": name,
                "trade": trade,
                "area": area,
                "phone": phone,
                "url": url,
                "contact_url": url,
                "sole_proprietor_score": sole,
                "notes": notes,
                "source": source if source.startswith("grok") else f"grok_mail:{source}",
                "status": "discovered",
                "channel": "phone" if phone else "web_form",
                "alive_due_days": 90,
            }
        )
    return vendors


MARK_ALIVE_RE = re.compile(
    r"--mark-alive\s+(?P<id>[^\s]+)\s+--alive-status\s+(?P<status>ok|fail|unknown)"
    r"(?:\s+--alive-method\s+(?P<method>web|phone|both))?"
    r'(?:\s+--note\s+"(?P<note_dq>(?:[^"\\]|\\.)*)"|'
    r"\s+--note\s+(?P<note_sq>\S+))?",
    re.I,
)


def apply_mark_alive_from_text(body: str, *, dry_run: bool) -> dict[str, Any]:
    sys.path.insert(0, str(REPO / "scripts"))
    from jarvis_kurashift_repair_vendor_list import mark_vendor_alive

    applied: list[dict[str, Any]] = []
    errors: list[str] = []
    for m in MARK_ALIVE_RE.finditer(body or ""):
        note = m.group("note_dq") or m.group("note_sq") or ""
        if note:
            note = note.encode("utf-8").decode("unicode_escape") if "\\" in note else note
        out = mark_vendor_alive(
            m.group("id"),
            alive_status=m.group("status").lower(),
            method=(m.group("method") or "phone").lower(),
            note=note,
            dry_run=dry_run,
        )
        if out.get("ok"):
            applied.append({"id": m.group("id"), "status": m.group("status")})
        else:
            errors.append(str(out.get("error") or m.group("id")))
    return {
        "ok": len(errors) == 0,
        "parsed": len(applied) + len(errors),
        "applied": len(applied),
        "errors": errors,
        "dry_run": dry_run,
    }


def maybe_sync(*, dry_run: bool) -> dict[str, Any]:
    if dry_run:
        return {"ok": True, "skipped": "dry_run"}
    if not os.environ.get("JARVIS_SUPABASE_URL") or not os.environ.get(
        "JARVIS_SUPABASE_SERVICE_ROLE_KEY"
    ):
        return {"ok": True, "skipped": "no JARVIS_SUPABASE_*"}
    if not SYNC_SCRIPT.is_file():
        return {"ok": False, "error": "sync script missing"}
    py = str(PY if PY.is_file() else sys.executable)
    r = subprocess.run(
        [py, str(SYNC_SCRIPT), "--apply"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=180,
    )
    return {
        "ok": r.returncode == 0,
        "returncode": r.returncode,
        "stdout": (r.stdout or "")[-500:],
        "stderr": (r.stderr or "")[-300:],
    }


def apply_from_gmail(
    *,
    dry_run: bool,
    days: int,
    reprocess: bool,
    max_results: int,
) -> dict[str, Any]:
    sys.path.insert(0, str(REPO / "scripts"))
    from jarvis_kurashift_repair_vendor_list import ensure_local_yaml, merge_append

    print("使用アカウント: estate / Gmail API（[Grok修繕候補] 受信取込）")
    ensure_local_yaml()

    svc = gmail_service()
    state = load_state()
    processed = set(state.get("processed_ids") or [])
    messages = fetch_repair_messages(svc, days=days, max_results=max_results)

    results: list[dict[str, Any]] = []
    total_parsed = 0
    total_added = 0
    total_alive = 0

    # process oldest first so discovered_at order is natural
    messages_sorted = list(reversed(messages))

    for msg in messages_sorted:
        mid = msg["id"]
        if mid in processed and not reprocess:
            continue
        body = msg.get("body") or ""
        subject = msg.get("subject") or ""
        cands = parse_candidates_from_body(body, subject=subject)
        alive_out = apply_mark_alive_from_text(body, dry_run=dry_run)
        entry: dict[str, Any] = {
            "message_id": mid,
            "subject": subject,
            "parsed_candidates": len(cands),
            "alive_marks": alive_out,
        }
        if cands:
            merged = merge_append(cands, dry_run=dry_run)
            entry["merge"] = merged
            total_parsed += len(cands)
            total_added += int(merged.get("added") or 0)
            entry["ok"] = bool(merged.get("ok"))
        else:
            entry["merge"] = {"ok": True, "skipped": "no table rows"}
            entry["ok"] = True
        total_alive += int(alive_out.get("applied") or 0)
        if alive_out.get("parsed") and not alive_out.get("ok"):
            entry["ok"] = False

        results.append(entry)
        if not dry_run:
            processed.add(mid)

    sync_out: dict[str, Any] = {"ok": True, "skipped": "no changes"}
    if not dry_run and results and (total_added > 0 or total_alive > 0):
        sync_out = maybe_sync(dry_run=False)
    elif not dry_run and results:
        # still mark processed; optional light sync for consistency
        sync_out = maybe_sync(dry_run=False)

    if not dry_run and results:
        state["processed_ids"] = sorted(processed)[-500:]
        save_state(state)

    summary = {
        "ok": all(r.get("ok", True) for r in results) and sync_out.get("ok", True),
        "messages_seen": len(messages),
        "messages_processed": len(results),
        "candidates_parsed": total_parsed,
        "candidates_added": total_added,
        "alive_marks_applied": total_alive,
        "sync": sync_out,
        "dry_run": dry_run,
        "results": results,
    }

    print("📎 Grok修繕候補メール取込")
    print(f"- 対象: 直近{days}日 · subject {SUBJECT_PREFIX}")
    print(f"- 処理: {len(results)}通（一覧{len(messages)}通）")
    print(f"- 候補: 解析 {total_parsed} 件 · 新規追加 {total_added} 件")
    print(f"- mark-alive: {total_alive} 件")
    if dry_run:
        print("- モード: dry-run（YAML 未更新）")
    elif not results:
        print("- 新規メールなし（またはすべて処理済み）")
    print(f"REPAIR_MAIL_APPLY:{json.dumps(summary, ensure_ascii=False)}")
    return summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="YAML に反映＋sync")
    ap.add_argument("--dry-run", action="store_true", help="プレビューのみ")
    ap.add_argument("--days", type=int, default=30, help="検索日数（既定30）")
    ap.add_argument("--max-results", type=int, default=50)
    ap.add_argument(
        "--reprocess",
        action="store_true",
        help="処理済み message_id も再実行",
    )
    args = ap.parse_args()

    if not args.apply and not args.dry_run:
        args.dry_run = True

    out = apply_from_gmail(
        dry_run=not args.apply,
        days=args.days,
        reprocess=args.reprocess,
        max_results=max(1, args.max_results),
    )
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
