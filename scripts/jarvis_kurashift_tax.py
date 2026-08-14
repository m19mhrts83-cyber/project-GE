#!/usr/bin/env python3
"""KURASHIFT tax: personal Yayoi CSV + corporate accountant mail (Gmail).

Personal: Zaim summary → CSV draft（税理士メール取込はしない）。
Corporate: Knees bee（大野さん）PDF, yearly.
Default Gmail: admin (token_livingsupport.json).
Override: KURASHIFT_TAX_GMAIL_TOKEN=/path/to/token.json
"""
from __future__ import annotations

import argparse
import base64
import csv
import json
import mimetypes
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
TAX_DIR = Path(
    "/Users/matsunomasaharu2/Library/CloudStorage/OneDrive-個人用/"
    "215_神・大家さん倶楽部/50_税金,確定申告"
).expanduser()
STORAGE_BUCKET = "kurashift-tax"


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def emit_result(obj: dict) -> None:
    print("KURASHIFT_RESULT:" + json.dumps(obj, ensure_ascii=False))


def guess_mime(name: str) -> str:
    guessed, _ = mimetypes.guess_type(name)
    return guessed or "application/octet-stream"


def storage_key(scope: str, year: int, evidence_id: str, filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if not re.match(r"^\.[a-z0-9]{1,8}$", ext or ""):
        ext = ""
    return f"{scope}/{year}/{evidence_id}{ext}"


def upload_evidence_bytes(sb: Any, key: str, data: bytes, mime: str) -> str | None:
    try:
        sb.storage.from_(STORAGE_BUCKET).upload(
            key,
            data,
            file_options={"content-type": mime, "upsert": "true"},
        )
        return key
    except Exception as e:  # noqa: BLE001
        print(f"# storage upload skip {key}: {e}", flush=True)
        return None


def insert_evidence_row(sb: Any, row: dict, file_path: Path | None, blob: bytes | None) -> str | None:
    """DB 行を作り、可能なら Storage にも上げてプレビューできるようにする。"""
    ins = sb.table("kurashift_tax_evidence").insert(row).execute()
    eid = ((ins.data or [{}])[0] or {}).get("id")
    if not eid:
        return None
    data = blob
    if data is None and file_path and file_path.exists():
        data = file_path.read_bytes()
    name = row.get("original_filename") or (file_path.name if file_path else "file")
    if data is not None:
        key = storage_key(str(row.get("scope") or "personal"), int(row["fiscal_year"]), eid, str(name))
        uploaded = upload_evidence_bytes(sb, key, data, guess_mime(str(name)))
        if uploaded:
            sb.table("kurashift_tax_evidence").update({"storage_path": uploaded}).eq("id", eid).execute()
    return eid


def sync_storage(dry_run: bool) -> dict:
    """既存の stored_path を Storage に上げてプレビュー可能にする。"""
    sb = sb_client()
    if not sb:
        raise SystemExit("JARVIS_SUPABASE_* required")
    rows = (
        sb.table("kurashift_tax_evidence")
        .select("id, fiscal_year, scope, stored_path, original_filename, storage_path")
        .execute()
        .data
        or []
    )
    out: dict[str, Any] = {"action": "sync_storage", "checked": len(rows), "uploaded": 0, "skipped": 0, "missing": []}
    for row in rows:
        if row.get("storage_path"):
            out["skipped"] += 1
            continue
        src = Path(row.get("stored_path") or "")
        if not src.exists():
            out["missing"].append(str(src))
            continue
        if dry_run:
            out["uploaded"] += 1
            continue
        key = storage_key(
            str(row.get("scope") or "personal"),
            int(row["fiscal_year"]),
            str(row["id"]),
            str(row.get("original_filename") or src.name),
        )
        uploaded = upload_evidence_bytes(sb, key, src.read_bytes(), guess_mime(src.name))
        if uploaded:
            sb.table("kurashift_tax_evidence").update({"storage_path": uploaded}).eq("id", row["id"]).execute()
            out["uploaded"] += 1
    print(json.dumps(out, ensure_ascii=False, indent=2))
    emit_result(out)
    return out


def year_dir(year: int, scope: str = "personal") -> Path:
    if scope == "corporate":
        return TAX_DIR / "knees bee 税理士法人" / "kurashift" / str(year)
    return OUT_ROOT / str(year)


def default_year(scope: str = "personal") -> int:
    today = date.today()
    if scope == "corporate":
        return today.year if today.month <= 8 else today.year + 1
    return today.year - 1 if today.month <= 3 else today.year


def sb_client() -> Any | None:
    url = os.environ.get("JARVIS_SUPABASE_URL")
    key = os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        return None
    from supabase import create_client

    return create_client(url, key)


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


def ensure_tax_case(sb: Any, year: int, scope: str = "personal") -> str | None:
    title = f"個人確定申告 {year}" if scope == "personal" else f"法人確定申告 {year}年5月期"
    rows = (
        sb.table("kurashift_tax_cases")
        .select("id")
        .eq("fiscal_year", year)
        .eq("scope", scope)
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
                "scope": scope,
                "notes": "auto from tax mail ingest",
                "updated_at": now_iso(),
            }
        )
        .execute()
    )
    return (res.data or [{}])[0].get("id")


def mail_query(year: int, scope: str) -> str:
    """法人: year = N年5月期。決算報告メールは概ね同年5〜12月に届く。

    旧クエリ before:{year}/10/1 だと遅延便を落とす。2025窓で0件だったのは、
    実際の大野さん決算報告が 2026-07（2026年5月期）だったため。
    """
    if scope == "corporate":
        return (
            "(from:t.ohno@knees-bee.jp OR from:knees-bee.jp) "
            "(filename:pdf OR subject:決算 OR subject:申告書 OR subject:法人税) "
            f"after:{year}/5/1 before:{year + 1}/1/1"
        )
    return (
        f"(from:税理士 OR from:公認会計士 OR from:会計事務所 "
        f"OR subject:税理士 OR subject:確定申告 OR subject:決算 OR subject:申告 "
        f"OR subject:源泉 OR subject:控除 OR filename:pdf) "
        f"after:{year}/1/1 before:{year + 1}/4/1"
    )


def ingest_mail(year: int, dry_run: bool, limit: int, scope: str = "personal") -> dict:
    """法人のみ。Knees bee 大野さんPDFを Gmail から取り込む。個人は対象外。"""
    if scope != "corporate":
        out = {
            "ok": False,
            "action": "ingest_mail",
            "fiscal_year": year,
            "scope": scope,
            "error": "個人の税理士メール取込は廃止。法人（corporate）のみ。",
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        emit_result(out)
        return out
    query = mail_query(year, scope)
    store = year_dir(year, scope) / "evidence"
    out: dict[str, Any] = {
        "action": "ingest_mail",
        "fiscal_year": year,
        "scope": scope,
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
    case_id = ensure_tax_case(sb, year, scope) if sb else None
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
            if scope == "corporate":
                continue
            # still record a placeholder note file for body-only mail
            note_path = store / f"{mid}_no_attachment.txt"
            note_path.write_text(
                f"subject: {subject}\ndate: {date_hdr}\nid: {mid}\n",
                encoding="utf-8",
            )
            if sb:
                insert_evidence_row(
                    sb,
                    {
                        "tax_case_id": case_id,
                        "fiscal_year": year,
                        "scope": scope,
                        "source": "gmail",
                        "doc_kind": "mail_note",
                        "subject": subject,
                        "gmail_message_id": mid,
                        "stored_path": str(note_path),
                        "original_filename": note_path.name,
                        "received_at": received_at,
                        "metadata": {"has_attachment": False},
                    },
                    note_path,
                    None,
                )
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
                insert_evidence_row(
                    sb,
                    {
                        "tax_case_id": case_id,
                        "fiscal_year": year,
                        "scope": scope,
                        "source": "gmail",
                        "doc_kind": "attachment",
                        "subject": subject,
                        "gmail_message_id": mid,
                        "stored_path": str(dest),
                        "original_filename": part["filename"],
                        "received_at": received_at,
                        "metadata": {"has_attachment": True},
                    },
                    dest,
                    data,
                )
        saved.append({"message_id": mid, "subject": subject, "files": files})

    out["messages_scanned"] = len(messages)
    out["saved"] = len(saved)
    out["items"] = saved
    out["artifacts"] = [{"kind": "evidence_dir", "path": str(store)}]
    if not messages:
        out["hint"] = (
            f"0件です。法人は year=N年5月期（例: 2026）。"
            f"決算報告メールは {year}/5〜{year}/12 想定。"
            "前年窓で探すと届いていないことが多い。"
        )
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
            insert_evidence_row(
                sb,
                {
                    "fiscal_year": year,
                    "scope": "personal",
                    "doc_kind": "manual_inbox",
                    "subject": f"手動取込: {dest.name}",
                    "original_filename": src.name,
                    "stored_path": str(dest),
                    "received_at": date.today().isoformat(),
                },
                dest,
                None,
            )
        out["items"].append(item)
        out["saved"] += 1

    out["artifacts"] = [{"kind": "evidence_dir", "path": str(store)}]
    print(json.dumps(out, ensure_ascii=False, indent=2))
    emit_result(out)
    return out


def upsert_metrics(args: argparse.Namespace) -> dict:
    """申告結果KPIを kurashift_tax_year_metrics へ upsert。"""
    sb = sb_client()
    if sb is None:
        raise SystemExit("JARVIS_SUPABASE_* 未設定")

    year = args.year if args.year is not None else default_year(args.scope)
    row: dict[str, Any] = {
        "scope": args.scope,
        "fiscal_year": int(year),
        "filing_status": args.filing_status or "filed",
        "filed_on": (args.filed_on or "").strip() or None,
        "note": (args.note or "").strip() or None,
        "source": "jarvis",
    }
    if (args.metrics_json or "").strip():
        extra = json.loads(args.metrics_json)
        if not isinstance(extra, dict):
            raise SystemExit("--metrics-json はオブジェクトである必要があります")
        row.update(extra)
        row["scope"] = args.scope
        row["fiscal_year"] = int(year)
        row.setdefault("source", "jarvis")

    if args.scope == "personal":
        if args.taxable_income is not None:
            row["taxable_income_jpy"] = args.taxable_income
        if args.income_tax is not None:
            row["income_tax_jpy"] = args.income_tax
        if args.refund_or_pay:
            row["refund_or_pay"] = args.refund_or_pay
    else:
        if args.revenue is not None:
            row["revenue_jpy"] = args.revenue
        if args.ordinary_income is not None:
            row["ordinary_income_jpy"] = args.ordinary_income
        if args.corporate_tax is not None:
            row["corporate_tax_jpy"] = args.corporate_tax
        if args.tax_payable is not None:
            row["tax_payable_jpy"] = args.tax_payable

    out = {"ok": True, "dry_run": bool(args.dry_run), "row": row}
    if args.dry_run:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return out

    sb.table("kurashift_tax_year_metrics").upsert(
        row, on_conflict="scope,fiscal_year"
    ).execute()
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return out


def _catalog_path(args: argparse.Namespace) -> Path:
    raw = (args.catalog or "").strip()
    path = Path(raw).expanduser() if raw else REPO / "config" / "kurashift_tax_year_metrics.yaml"
    if not path.is_file():
        raise SystemExit(f"catalog が見つかりません: {path}")
    return path


def _find_re_statement(pdf: Path) -> Path | None:
    """同ディレクトリの収支内訳書（不動産）を1件探す。"""
    parent = pdf.parent
    if not parent.is_dir():
        return None
    hits = sorted(
        p
        for p in parent.iterdir()
        if p.is_file()
        and p.suffix.lower() == ".pdf"
        and "収支内訳" in p.name
        and ("不動産" in p.name or "不動産所得" in p.name)
    )
    if hits:
        return hits[0]
    # ゆるめ: 収支内訳書のみ
    hits2 = sorted(
        p
        for p in parent.iterdir()
        if p.is_file() and p.suffix.lower() == ".pdf" and "収支内訳" in p.name
    )
    return hits2[0] if hits2 else None


def _evidence_already(sb: Any, *, scope: str, year: int, stored_path: str, filename: str) -> bool:
    by_path = (
        sb.table("kurashift_tax_evidence")
        .select("id")
        .eq("stored_path", stored_path)
        .limit(1)
        .execute()
        .data
    )
    if by_path:
        return True
    by_name = (
        sb.table("kurashift_tax_evidence")
        .select("id")
        .eq("scope", scope)
        .eq("fiscal_year", year)
        .eq("original_filename", filename)
        .limit(1)
        .execute()
        .data
    )
    return bool(by_name)


def ingest_filed_returns(args: argparse.Namespace) -> dict:
    """KPIカタログの source_pdf（＋収支内訳書）を証憑化し Storage へ上げる。"""
    try:
        import yaml
    except ImportError as e:
        raise SystemExit(f"PyYAML が必要です: {e}") from e

    path = _catalog_path(args)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    year_filter = args.year
    want_scopes = ("personal", "corporate")

    candidates: list[dict[str, Any]] = []
    for scope in want_scopes:
        for item in data.get(scope) or []:
            if not isinstance(item, dict):
                continue
            year = int(item["fiscal_year"])
            if year_filter is not None and year != int(year_filter):
                continue
            payload = item.get("payload") or {}
            rel = (payload.get("source_pdf") or "").strip()
            if not rel:
                continue
            pdf = (TAX_DIR / rel).resolve()
            label = f"{year}年分 確定申告書" if scope == "personal" else f"{year}年5月期 申告書"
            candidates.append(
                {
                    "scope": scope,
                    "fiscal_year": year,
                    "doc_kind": "filed_return",
                    "subject": label,
                    "path": pdf,
                    "rel": rel,
                }
            )
            if scope == "personal":
                re_pdf = _find_re_statement(pdf)
                if re_pdf is not None:
                    try:
                        rel_re = str(re_pdf.relative_to(TAX_DIR))
                    except ValueError:
                        rel_re = re_pdf.name
                    candidates.append(
                        {
                            "scope": scope,
                            "fiscal_year": year,
                            "doc_kind": "re_statement",
                            "subject": f"{year}年分 収支内訳書（不動産）",
                            "path": re_pdf,
                            "rel": rel_re,
                        }
                    )

    out: dict[str, Any] = {
        "action": "ingest_filed_returns",
        "catalog": str(path),
        "dry_run": bool(args.dry_run),
        "candidates": len(candidates),
        "inserted": 0,
        "skipped": 0,
        "missing": [],
        "items": [],
    }

    if args.dry_run:
        for c in candidates:
            exists = c["path"].is_file()
            out["items"].append(
                {
                    "scope": c["scope"],
                    "year": c["fiscal_year"],
                    "doc_kind": c["doc_kind"],
                    "path": str(c["path"]),
                    "exists": exists,
                }
            )
            if not exists:
                out["missing"].append(str(c["path"]))
        print(json.dumps(out, ensure_ascii=False, indent=2))
        emit_result(out)
        return out

    sb = sb_client()
    if sb is None:
        raise SystemExit("JARVIS_SUPABASE_* 未設定")

    for c in candidates:
        pdf: Path = c["path"]
        if not pdf.is_file():
            out["missing"].append(str(pdf))
            continue
        if _evidence_already(
            sb,
            scope=c["scope"],
            year=c["fiscal_year"],
            stored_path=str(pdf),
            filename=pdf.name,
        ):
            out["skipped"] += 1
            out["items"].append(
                {
                    "scope": c["scope"],
                    "year": c["fiscal_year"],
                    "doc_kind": c["doc_kind"],
                    "status": "skipped_dup",
                    "file": pdf.name,
                }
            )
            continue
        eid = insert_evidence_row(
            sb,
            {
                "fiscal_year": c["fiscal_year"],
                "scope": c["scope"],
                "source": "upload",
                "doc_kind": c["doc_kind"],
                "subject": c["subject"],
                "original_filename": pdf.name,
                "stored_path": str(pdf),
                "received_at": date.today().isoformat(),
                "metadata": {
                    "catalog_rel": c["rel"],
                    "ingest": "filed_returns",
                },
            },
            pdf,
            None,
        )
        out["inserted"] += 1
        out["items"].append(
            {
                "scope": c["scope"],
                "year": c["fiscal_year"],
                "doc_kind": c["doc_kind"],
                "status": "inserted",
                "id": eid,
                "file": pdf.name,
            }
        )

    print(json.dumps(out, ensure_ascii=False, indent=2))
    emit_result(out)
    return out


def import_metrics_catalog(args: argparse.Namespace) -> dict:
    """config/kurashift_tax_year_metrics.yaml から一括 upsert。"""
    try:
        import yaml
    except ImportError as e:
        raise SystemExit(f"PyYAML が必要です: {e}") from e

    path = _catalog_path(args)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    rows_out: list[dict[str, Any]] = []
    for scope in ("personal", "corporate"):
        for item in data.get(scope) or []:
            if not isinstance(item, dict):
                continue
            year = int(item["fiscal_year"])
            row: dict[str, Any] = {
                "scope": scope,
                "fiscal_year": year,
                "filing_status": item.get("filing_status") or "filed",
                "filed_on": item.get("filed_on") or None,
                "note": item.get("note") or None,
                "source": "import",
                "payload": item.get("payload") or {},
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            if scope == "personal":
                row["taxable_income_jpy"] = item.get("taxable_income_jpy")
                row["income_tax_jpy"] = item.get("income_tax_jpy")
                row["refund_or_pay"] = item.get("refund_or_pay")
            else:
                row["revenue_jpy"] = item.get("revenue_jpy")
                row["ordinary_income_jpy"] = item.get("ordinary_income_jpy")
                row["corporate_tax_jpy"] = item.get("corporate_tax_jpy")
                row["tax_payable_jpy"] = item.get("tax_payable_jpy")
            rows_out.append(row)

    out = {
        "ok": True,
        "dry_run": bool(args.dry_run),
        "catalog": str(path),
        "count": len(rows_out),
        "rows": rows_out,
    }
    if args.dry_run:
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        return out

    sb = sb_client()
    if sb is None:
        raise SystemExit("JARVIS_SUPABASE_* 未設定")
    for row in rows_out:
        sb.table("kurashift_tax_year_metrics").upsert(
            row, on_conflict="scope,fiscal_year"
        ).execute()
    print(json.dumps({k: out[k] for k in ("ok", "dry_run", "catalog", "count")}, ensure_ascii=False, indent=2))
    for row in rows_out:
        print(
            f"  {row['scope']} {row['fiscal_year']}: "
            f"taxable/ord={row.get('taxable_income_jpy') if row.get('taxable_income_jpy') is not None else row.get('ordinary_income_jpy')} "
            f"re={((row.get('payload') or {}).get('re_income_jpy'))}"
        )
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", choices=["personal", "corporate"], default="personal")
    ap.add_argument("--year", type=int, default=None)
    ap.add_argument("--build-csv", action="store_true")
    ap.add_argument("--ingest-mail", action="store_true")
    ap.add_argument("--ingest-manual-dir", action="store_true")
    ap.add_argument(
        "--ingest-filed-returns",
        action="store_true",
        help="KPIカタログの提出PDF（＋収支内訳書）を証憑化しプレビュー用Storageへ",
    )
    ap.add_argument("--export-evidence", action="store_true")
    ap.add_argument("--sync-storage", action="store_true", help="既存証憑をプレビュー用 Storage へ上げる")
    ap.add_argument("--upsert-metrics", action="store_true", help="申告結果KPIを kurashift_tax_year_metrics へ登録")
    ap.add_argument(
        "--import-metrics-catalog",
        action="store_true",
        help="config/kurashift_tax_year_metrics.yaml からKPI一括登録",
    )
    ap.add_argument("--catalog", default="", help="metrics/filed カタログYAMLパス")
    ap.add_argument("--taxable-income", type=float, default=None)
    ap.add_argument("--income-tax", type=float, default=None)
    ap.add_argument("--refund-or-pay", choices=["refund", "pay", "zero"], default=None)
    ap.add_argument("--revenue", type=float, default=None)
    ap.add_argument("--ordinary-income", type=float, default=None)
    ap.add_argument("--corporate-tax", type=float, default=None)
    ap.add_argument("--tax-payable", type=float, default=None)
    ap.add_argument("--filing-status", choices=["draft", "filed", "amended", "unknown"], default="filed")
    ap.add_argument("--filed-on", default="")
    ap.add_argument("--note", default="")
    ap.add_argument("--metrics-json", default="", help="KPIをJSONで渡す（フラグより優先）")
    ap.add_argument("--evidence-id", default="")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    year = args.year if args.year is not None else default_year(args.scope)

    if args.build_csv:
        if args.scope == "corporate":
            raise SystemExit("法人は弥生CSV対象外。--ingest-mail --scope corporate を使う")
        build_csv(year, args.dry_run)
    elif args.ingest_mail:
        ingest_mail(year, args.dry_run, args.limit, args.scope)
    elif args.ingest_manual_dir:
        ingest_manual_dir(year, args.dry_run)
    elif args.ingest_filed_returns:
        ingest_filed_returns(args)
    elif args.export_evidence:
        export_evidence(year, args.evidence_id, args.dry_run)
    elif args.sync_storage:
        sync_storage(args.dry_run)
    elif args.import_metrics_catalog:
        import_metrics_catalog(args)
    elif args.upsert_metrics:
        upsert_metrics(args)
    else:
        raise SystemExit(
            "specify --build-csv | --ingest-mail | --ingest-manual-dir | "
            "--ingest-filed-returns | --export-evidence | --sync-storage | "
            "--upsert-metrics | --import-metrics-catalog"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
