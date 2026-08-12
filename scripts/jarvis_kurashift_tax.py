#!/usr/bin/env python3
"""KURASHIFT personal tax helpers (Yayoi CSV scaffold + evidence).

Corporate returns are out of scope (tax accountant). Personal only.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
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


def build_csv(year: int, dry_run: bool) -> dict:
    """Write a minimal Yayoi-oriented CSV stub for personal books.

    Real mapping from finance categories comes in a later phase.
    """
    d = year_dir(year)
    path = d / f"yayoi_personal_{year}_stub.csv"
    rows = [
        ["日付", "借方勘定科目", "借方金額", "貸方勘定科目", "貸方金額", "摘要", "スコープ"],
        [
            f"{year}-01-01",
            "普通預金",
            "0",
            "事業主借",
            "0",
            "KURASHIFT stub — replace with real postings",
            "personal",
        ],
    ]
    out: dict[str, Any] = {
        "action": "build_csv",
        "fiscal_year": year,
        "path": str(path),
        "scope": "personal",
        "note": "個人のみ。法人は対象外。本番仕訳マッピングは次フェーズ。",
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

    url = os.environ.get("JARVIS_SUPABASE_URL")
    key = os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY")
    if url and key:
        from supabase import create_client

        sb = create_client(url, key)
        title = f"個人申告 {year}"
        existing = (
            sb.table("kurashift_tax_cases")
            .select("id")
            .eq("fiscal_year", year)
            .eq("title", title)
            .maybe_single()
            .execute()
        )
        row = {
            "fiscal_year": year,
            "title": title,
            "status": "csv_ready",
            "scope": "personal",
            "csv_path": str(path),
            "notes": "stub CSV from jarvis_kurashift_tax.py",
            "updated_at": now_iso(),
        }
        if existing.data:
            sb.table("kurashift_tax_cases").update(row).eq("id", existing.data["id"]).execute()
        else:
            sb.table("kurashift_tax_cases").insert(row).execute()
        out["tax_case_upserted"] = True

    print(json.dumps(out, ensure_ascii=False, indent=2))
    emit_result(out)
    return out


def ingest_mail(year: int, dry_run: bool) -> dict:
    """Scaffold: search admin Gmail for tax-accountant-like mail and list hits.

    Full attachment save → kurashift_tax_evidence in next iteration.
    """
    out: dict[str, Any] = {
        "action": "ingest_mail",
        "fiscal_year": year,
        "scope": "personal",
        "note": "税理士メール＋添付の本取込は次フェーズ。ここではクエリと保存先を固定。",
        "gmail_query_hint": f"subject:(確定申告 OR 決算 OR 申告) after:{year}/1/1",
        "store_dir": str(year_dir(year) / "evidence"),
    }
    if dry_run:
        out["dry_run"] = True
    else:
        (year_dir(year) / "evidence").mkdir(parents=True, exist_ok=True)
        out["evidence_dir_ready"] = True
    print(json.dumps(out, ensure_ascii=False, indent=2))
    emit_result(out)
    return out


def export_evidence(year: int, evidence_id: str, dry_run: bool) -> dict:
    """Re-export a stored evidence file to an export folder (証憑再出力)."""
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

    url = os.environ.get("JARVIS_SUPABASE_URL")
    key = os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_* required")
    from supabase import create_client

    sb = create_client(url, key)
    row = (
        sb.table("kurashift_tax_evidence")
        .select("*")
        .eq("id", evidence_id)
        .maybe_single()
        .execute()
        .data
    )
    if not row:
        raise SystemExit(f"evidence not found: {evidence_id}")
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=date.today().year - 1)
    ap.add_argument("--build-csv", action="store_true")
    ap.add_argument("--ingest-mail", action="store_true")
    ap.add_argument("--export-evidence", action="store_true")
    ap.add_argument("--evidence-id", default="")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.build_csv:
        build_csv(args.year, args.dry_run)
    elif args.ingest_mail:
        ingest_mail(args.year, args.dry_run)
    elif args.export_evidence:
        export_evidence(args.year, args.evidence_id, args.dry_run)
    else:
        raise SystemExit("specify --build-csv | --ingest-mail | --export-evidence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
