#!/usr/bin/env python3
"""KURASHIFT personal tax: Yayoi CSV stub + accountant mail evidence (Gmail).

Default Gmail account: admin (token_livingsupport.json) — Workspace 受信集約。
Override: KURASHIFT_TAX_GMAIL_TOKEN=/path/to/token.json
"""
from __future__ import annotations

import argparse
import base64
import csv
import json
import os
import re
import sys
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
MANUAL = REPO / "215_kamiooya" / "C1_cursor" / "1b_Cursorマニュアル"
OUT_ROOT = Path(
    "/Users/matsunomasaharu2/Library/CloudStorage/OneDrive-個人用/"
    "215_神・大家さん倶楽部/C2_ルーティン作業/27_確定申告_個人/kurashift"
)


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def emit_result(obj: dict) -> None:
    print("KURASHIFT_RESULT:" + json.dumps(obj, ensure_ascii=False))


def year_dir(year: int) -> Path:
    return OUT_ROOT / str(year)


def sb_client() -> Any | None:
    url = os.environ.get("JARVIS_SUPABASE_URL")
    key = os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        return None
    from supabase import create_client

    return create_client(url, key)


TAX_DIR = Path(
    "/Users/matsunomasaharu2/Library/CloudStorage/OneDrive-個人用/"
    "215_神・大家さん倶楽部/50_税金,確定申告"
).expanduser()

# 個人側のざっくり勘定（弥生取り込み用ドラフト。検証で直す）
ZAIM_TO_YAYOI: dict[str, str] = {
    "2C.食費": "消耗品費",
    "3C.水道/光熱": "水道光熱費",
    "4C.通信": "通信費",
    "5C.日用雑貨": "消耗品費",
    "6.1C.エ/交際/被服/趣味": "接待交際費",
    "6.2C 自己投資・寄付": "新聞図書費",
    "7C.医療費": "医療費",
    "8C.交通": "旅費交通費",
    "13.1F.生命保険": "保険料",
    "13.2F.自動車保険": "保険料",
    "17S.帰省・旅行": "旅費交通費",
    "21F.AIリスキリング": "研修費",
}


def parse_yen_cell(raw: str) -> int:
    s = (raw or "").strip().replace(",", "").replace("円", "")
    if not s:
        return 0
    try:
        return int(round(float(s)))
    except ValueError:
        return 0


def find_zaim_summary(year: int) -> Path | None:
    year_dir_path = TAX_DIR / f"{year}年度"
    for p in [
        year_dir_path / f"Zaim_ライフプラン_サマリー_{year}年度.csv",
        year_dir_path / f"Zaim_ライフプラン_サマリー_{year}年度.csv",
    ]:
        if p.is_file():
            return p
    if year_dir_path.is_dir():
        for p in sorted(year_dir_path.glob("Zaim*サマリー*.csv")):
            return p
    return None


def build_csv(year: int, dry_run: bool) -> dict:
    d = year_dir(year)
    path = d / f"yayoi_personal_{year}.csv"
    summary = find_zaim_summary(year)
    rows: list[list[str]] = [
        ["日付", "借方勘定科目", "借方金額", "貸方勘定科目", "貸方金額", "摘要", "スコープ"],
    ]
    mapped = 0
    skipped: list[str] = []

    if summary and summary.is_file():
        with summary.open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for r in reader:
                cat = (r.get("カテゴリ") or "").strip()
                if not cat or cat.startswith("合計"):
                    continue
                # 法人・不動産事業は個人CSVから除外（税理士／別仕訳）
                if cat.startswith("19") or "賃貸" in cat or "マンション" in cat or cat.startswith("A."):
                    skipped.append(cat)
                    continue
                expense = parse_yen_cell(r.get("支出（円）") or r.get("支出") or "0")
                if expense <= 0:
                    continue
                account = ZAIM_TO_YAYOI.get(cat)
                if not account:
                    # 前方一致のゆるいマップ
                    for k, v in ZAIM_TO_YAYOI.items():
                        if k in cat or cat in k:
                            account = v
                            break
                if not account:
                    skipped.append(cat)
                    continue
                rows.append(
                    [
                        f"{year}-12-31",
                        account,
                        str(expense),
                        "事業主借",
                        str(expense),
                        f"Zaim年間 {cat}",
                        "personal",
                    ]
                )
                mapped += 1
    else:
        rows.append(
            [
                f"{year}-01-01",
                "普通預金",
                "0",
                "事業主借",
                "0",
                "Zaimサマリー未検出 — 手動で差し替え",
                "personal",
            ]
        )

    out: dict[str, Any] = {
        "action": "build_csv",
        "fiscal_year": year,
        "path": str(path),
        "scope": "personal",
        "source": str(summary) if summary else None,
        "mapped_rows": mapped,
        "skipped_categories": skipped[:30],
        "note": (
            "個人のみ。19不動産・会社費用は除外。"
            "勘定マップは検証で直すドラフト。弥生本登録は承認後。"
        ),
        "register": False,
    }
    if dry_run:
        out["dry_run"] = True
        print(json.dumps(out, ensure_ascii=False, indent=2))
        emit_result(out)
        return out

    d.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f).writerows(rows)
    out["artifacts"] = [{"kind": "yayoi_csv", "path": str(path)}]

    sb = sb_client()
    if sb:
        title = f"個人申告 {year}"
        existing = (
            sb.table("kurashift_tax_cases")
            .select("id")
            .eq("fiscal_year", year)
            .eq("title", title)
            .limit(1)
            .execute()
            .data
        )
        row = {
            "fiscal_year": year,
            "title": title,
            "status": "csv_ready",
            "scope": "personal",
            "csv_path": str(path),
            "notes": f"mapped={mapped} from Zaim summary; register=false",
            "updated_at": now_iso(),
        }
        if existing:
            sb.table("kurashift_tax_cases").update(row).eq("id", existing[0]["id"]).execute()
        else:
            sb.table("kurashift_tax_cases").insert(row).execute()
        out["tax_case_upserted"] = True

    print(json.dumps(out, ensure_ascii=False, indent=2))
    emit_result(out)
    return out


def resolve_gmail_paths() -> tuple[Path, Path]:
    cred = MANUAL / "credentials.json"
    env_tok = os.environ.get("KURASHIFT_TAX_GMAIL_TOKEN", "").strip()
    if env_tok:
        tok = Path(env_tok).expanduser()
    else:
        # admin 集約を既定。個人申告メールが別箱なら env で切替。
        tok = MANUAL / "token_livingsupport.json"
        if not tok.is_file():
            tok = MANUAL / "token.json"
    if not cred.is_file() or not tok.is_file():
        raise SystemExit(f"Gmail credentials/token がありません: {cred} / {tok}")
    return cred, tok


def gmail_service():
    sys.path.insert(0, str(MANUAL))
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    from gmail_api_scopes import GMAIL_SCOPES_215 as SCOPES

    cred_path, token_path = resolve_gmail_paths()
    creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token_path.write_text(creds.to_json(), encoding="utf-8")
        else:
            raise SystemExit(f"token 無効・再同意が必要: {token_path}")
    return build("gmail", "v1", credentials=creds), token_path


def header_map(headers: list[dict]) -> dict[str, str]:
    return {h.get("name", "").lower(): h.get("value", "") for h in headers or []}


def collect_attachment_parts(payload: dict) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []

    def walk(p: dict) -> None:
        filename = (p.get("filename") or "").strip()
        body = p.get("body") or {}
        if filename and body.get("attachmentId"):
            found.append({"filename": filename, "attachmentId": body["attachmentId"]})
        for child in p.get("parts") or []:
            walk(child)

    walk(payload or {})
    return found


def sanitize_filename(name: str) -> str:
    name = re.sub(r"[\\/:*?\"<>|]+", "_", name).strip() or "attachment.bin"
    return name[:180]


def ensure_tax_case(sb: Any, year: int) -> str | None:
    title = f"個人申告 {year}"
    rows = (
        sb.table("kurashift_tax_cases")
        .select("id")
        .eq("fiscal_year", year)
        .eq("title", title)
        .limit(1)
        .execute()
        .data
    )
    if rows:
        return rows[0]["id"]
    res = (
        sb.table("kurashift_tax_cases")
        .insert(
            {
                "fiscal_year": year,
                "title": title,
                "status": "draft",
                "scope": "personal",
                "notes": "auto from tax mail ingest",
                "updated_at": now_iso(),
            }
        )
        .execute()
    )
    return (res.data or [{}])[0].get("id")


def ingest_mail(year: int, dry_run: bool, limit: int) -> dict:
    """Search admin Gmail for tax-accountant-like mail; save attachments as evidence."""
    query = (
        f"(from:税理士 OR from:公認会計士 OR from:会計事務所 "
        f"OR subject:税理士 OR subject:確定申告 OR subject:決算 OR subject:申告 "
        f"OR subject:源泉 OR subject:控除 OR filename:pdf) "
        f"after:{year}/1/1 before:{year + 1}/4/1"
    )
    store = year_dir(year) / "evidence"
    out: dict[str, Any] = {
        "action": "ingest_mail",
        "fiscal_year": year,
        "scope": "personal",
        "gmail_query": query,
        "store_dir": str(store),
        "account_default": "admin / token_livingsupport.json",
    }

    if dry_run:
        out["dry_run"] = True
        print(json.dumps(out, ensure_ascii=False, indent=2))
        emit_result(out)
        return out

    service, token_path = gmail_service()
    out["token"] = token_path.name
    store.mkdir(parents=True, exist_ok=True)

    listed = (
        service.users()
        .messages()
        .list(userId="me", q=query, maxResults=limit)
        .execute()
    )
    messages = listed.get("messages") or []
    sb = sb_client()
    case_id = ensure_tax_case(sb, year) if sb else None
    saved: list[dict[str, Any]] = []

    for m in messages:
        mid = m["id"]
        full = (
            service.users()
            .messages()
            .get(userId="me", id=mid, format="full")
            .execute()
        )
        headers = header_map((full.get("payload") or {}).get("headers") or [])
        subject = headers.get("subject") or ""
        date_hdr = headers.get("date") or ""
        received_at = None
        try:
            received_at = parsedate_to_datetime(date_hdr).isoformat()
        except Exception:  # noqa: BLE001
            received_at = None

        # skip if already stored
        if sb:
            exists = (
                sb.table("kurashift_tax_evidence")
                .select("id")
                .eq("gmail_message_id", mid)
                .limit(1)
                .execute()
                .data
            )
            if exists:
                continue

        parts = collect_attachment_parts(full.get("payload") or {})
        if not parts:
            # still record a placeholder note file for body-only mail
            note_path = store / f"{mid}_no_attachment.txt"
            note_path.write_text(
                f"subject: {subject}\ndate: {date_hdr}\nid: {mid}\n",
                encoding="utf-8",
            )
            parts = []
            if sb:
                sb.table("kurashift_tax_evidence").insert(
                    {
                        "tax_case_id": case_id,
                        "fiscal_year": year,
                        "source": "gmail",
                        "doc_kind": "mail_note",
                        "subject": subject,
                        "gmail_message_id": mid,
                        "stored_path": str(note_path),
                        "original_filename": note_path.name,
                        "received_at": received_at,
                        "metadata": {"has_attachment": False},
                    }
                ).execute()
            saved.append({"message_id": mid, "subject": subject, "files": [str(note_path)]})
            continue

        files: list[str] = []
        for i, part in enumerate(parts):
            att = (
                service.users()
                .messages()
                .attachments()
                .get(userId="me", messageId=mid, id=part["attachmentId"])
                .execute()
            )
            data = base64.urlsafe_b64decode(att.get("data") or "")
            safe = sanitize_filename(part["filename"])
            if len(parts) > 1:
                dest = store / f"{mid}_{i+1:02d}_{safe}"
            else:
                dest = store / f"{mid}_{safe}"
            dest.write_bytes(data)
            files.append(str(dest))
            if sb:
                sb.table("kurashift_tax_evidence").insert(
                    {
                        "tax_case_id": case_id,
                        "fiscal_year": year,
                        "source": "gmail",
                        "doc_kind": "attachment",
                        "subject": subject,
                        "gmail_message_id": mid,
                        "stored_path": str(dest),
                        "original_filename": part["filename"],
                        "received_at": received_at,
                        "metadata": {"has_attachment": True},
                    }
                ).execute()
        saved.append({"message_id": mid, "subject": subject, "files": files})

    out["messages_scanned"] = len(messages)
    out["saved"] = len(saved)
    out["items"] = saved
    out["artifacts"] = [{"kind": "evidence_dir", "path": str(store)}]
    print(json.dumps(out, ensure_ascii=False, indent=2))
    emit_result(out)
    return out


def export_evidence(year: int, evidence_id: str, dry_run: bool) -> dict:
    import shutil

    export_dir = year_dir(year) / "export"
    out: dict[str, Any] = {
        "action": "export_evidence",
        "fiscal_year": year,
        "evidence_id": evidence_id,
        "export_dir": str(export_dir),
    }
    if dry_run or not evidence_id:
        out["dry_run"] = True
        out["note"] = "evidence_id と DB 行が揃ったらコピーする"
        print(json.dumps(out, ensure_ascii=False, indent=2))
        emit_result(out)
        return out

    sb = sb_client()
    if not sb:
        raise SystemExit("JARVIS_SUPABASE_* required")
    rows = (
        sb.table("kurashift_tax_evidence")
        .select("*")
        .eq("id", evidence_id)
        .limit(1)
        .execute()
        .data
    )
    if not rows:
        raise SystemExit(f"evidence not found: {evidence_id}")
    row = rows[0]
    src = Path(row["stored_path"])
    if not src.exists():
        raise SystemExit(f"file missing: {src}")
    export_dir.mkdir(parents=True, exist_ok=True)
    dest = export_dir / (row.get("original_filename") or src.name)
    shutil.copy2(src, dest)
    out["exported_to"] = str(dest)
    out["artifacts"] = [{"kind": "evidence_export", "path": str(dest)}]
    print(json.dumps(out, ensure_ascii=False, indent=2))
    emit_result(out)
    return out


def ingest_manual_dir(year: int, dry_run: bool) -> dict:
    """OneDrive kurashift/{year}/evidence/inbox の PDF 等を証憑として取り込む。"""
    import shutil

    inbox = year_dir(year) / "evidence" / "inbox"
    store = year_dir(year) / "evidence"
    out: dict[str, Any] = {
        "action": "ingest_manual_dir",
        "fiscal_year": year,
        "inbox": str(inbox),
        "saved": 0,
        "items": [],
    }
    if not inbox.is_dir():
        inbox.mkdir(parents=True, exist_ok=True)
        out["note"] = "inbox を作成しました。PDF を置いて再実行してください。"
        print(json.dumps(out, ensure_ascii=False, indent=2))
        emit_result(out)
        return out

    files = sorted(
        p
        for p in inbox.iterdir()
        if p.is_file() and p.suffix.lower() in {".pdf", ".png", ".jpg", ".jpeg", ".heic"}
    )
    if dry_run:
        out["candidates"] = [p.name for p in files]
        print(json.dumps(out, ensure_ascii=False, indent=2))
        emit_result(out)
        return out

    store.mkdir(parents=True, exist_ok=True)
    sb = sb_client()
    for src in files:
        dest = store / src.name
        if dest.exists():
            dest = store / f"{date.today().isoformat()}_{src.name}"
        shutil.move(str(src), str(dest))
        item = {
            "filename": dest.name,
            "path": str(dest),
        }
        if sb:
            sb.table("kurashift_tax_evidence").insert(
                {
                    "fiscal_year": year,
                    "scope": "personal",
                    "doc_kind": "manual_inbox",
                    "subject": f"手動取込: {dest.name}",
                    "original_filename": src.name,
                    "stored_path": str(dest),
                    "received_at": date.today().isoformat(),
                }
            ).execute()
        out["items"].append(item)
        out["saved"] += 1

    out["artifacts"] = [{"kind": "evidence_dir", "path": str(store)}]
    print(json.dumps(out, ensure_ascii=False, indent=2))
    emit_result(out)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=date.today().year - 1)
    ap.add_argument("--build-csv", action="store_true")
    ap.add_argument("--ingest-mail", action="store_true")
    ap.add_argument("--ingest-manual-dir", action="store_true")
    ap.add_argument("--export-evidence", action="store_true")
    ap.add_argument("--evidence-id", default="")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.build_csv:
        build_csv(args.year, args.dry_run)
    elif args.ingest_mail:
        ingest_mail(args.year, args.dry_run, args.limit)
    elif args.ingest_manual_dir:
        ingest_manual_dir(args.year, args.dry_run)
    elif args.export_evidence:
        export_evidence(args.year, args.evidence_id, args.dry_run)
    else:
        raise SystemExit(
            "specify --build-csv | --ingest-mail | --ingest-manual-dir | --export-evidence"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
