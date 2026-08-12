#!/usr/bin/env python3
"""KURASHIFT: ライフプラン .numbers 時点版 + Zaim 財務履歴を Supabase へ取込。

読み替え: ユーザーの「.json（ドットナンバー）」→「.numbers（ドットナンバーズ）」

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_history_ingest.py --finance
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_history_ingest.py --lifeplan --extract
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_history_ingest.py --all --extract
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_history_ingest.py --finance --dry-run
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[1]
LIFEPLAN_DIR = Path(
    "/Users/matsunomasaharu2/Library/Mobile Documents/"
    "com~apple~Numbers/Documents/Life Plan"
)
TAX_DIR = Path(
    "/Users/matsunomasaharu2/Library/CloudStorage/OneDrive-個人用/"
    "215_神・大家さん倶楽部/50_税金,確定申告"
)
PLAYBOOK = REPO / "config" / "trade_theme_playbook.yaml"
ZAIM_SYNC = REPO / "215_kamiooya" / "C1_cursor" / "finance" / "zaim_budget_sync"
MAP_PATH = REPO / "config" / "finance_entity_map.yaml"
STATE = REPO / ".jarvis_state" / "kurashift_history"
PY = Path("/Users/matsunomasaharu2/selenium_env/venv/bin/python")

BUDGET_SHEET = "シングルインカム年収手取"
BUDGET_TABLE = "表1.月別予算設定"
CANONICAL_KEY = "260621"

sys.path.insert(0, str(ZAIM_SYNC))
from column_utils import month_cols_for_year  # noqa: E402
from numbers_budget_extract import (  # noqa: E402
    extract_raw_table,
    load_mapping,
    rows_to_budget_records,
)


def jst_now() -> datetime:
    return datetime.now(timezone.utc).astimezone()


def sb_client() -> Any:
    url = os.environ.get("JARVIS_SUPABASE_URL")
    key = os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY が必要です")
    from supabase import create_client

    return create_client(url, key)


def playbook() -> dict:
    return yaml.safe_load(PLAYBOOK.read_text(encoding="utf-8")) or {}


def file_checksum(path: Path, limit: int = 2_000_000) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        remaining = limit
        while remaining > 0:
            chunk = f.read(min(65536, remaining))
            if not chunk:
                break
            h.update(chunk)
            remaining -= len(chunk)
    h.update(str(path.stat().st_size).encode())
    return h.hexdigest()[:40]


def parse_as_of_from_name(name: str) -> date | None:
    """ファイル名から時点日を推定。YYMMDD / YYYYMMDD / _YYMMDD。"""
    stem = Path(name).stem
    m = re.search(r"(?<!\d)(20\d{2})(\d{2})(\d{2})(?!\d)", stem)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return date(y, mo, d)
        except ValueError:
            pass
    m = re.search(r"(?<!\d)(\d{2})(\d{2})(\d{2})(?!\d)", stem)
    if m:
        yy, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        y = 2000 + yy if yy < 80 else 1900 + yy
        try:
            return date(y, mo, d)
        except ValueError:
            pass
    return None


def version_key_from_path(path: Path) -> str:
    stem = path.stem
    m = re.search(r"(?<!\d)(\d{6}|\d{8})(?!\d)", stem)
    if m:
        return m.group(1)
    # 日本語サフィックスのみの旧名
    safe = re.sub(r"[^\w\-]+", "_", stem, flags=re.UNICODE).strip("_")
    return safe[:48] or path.name[:48]


def discover_numbers_files() -> list[Path]:
    files = list(LIFEPLAN_DIR.glob("*.numbers"))
    old = LIFEPLAN_DIR / "old"
    if old.is_dir():
        files.extend(old.glob("*.numbers"))
    usable: list[Path] = []
    for p in files:
        if not p.exists():
            continue
        try:
            # 空パッケージ（数百バイト）はスキップ
            if p.stat().st_size < 1024:
                print(f"# skip tiny numbers: {p.name} ({p.stat().st_size}B)", flush=True)
                continue
        except OSError:
            continue
        usable.append(p)
    return sorted(set(usable), key=lambda p: (parse_as_of_from_name(p.name) or date.min, p.name))


def yen_num(raw: str | None) -> float:
    try:
        return float(str(raw or "0").replace(",", "").replace("円", "") or 0)
    except ValueError:
        return 0.0


def classify_abg(category: str) -> str:
    c = (category or "").strip()
    if c.startswith("α") or "α." in c[:4]:
        return "alpha"
    if c.startswith("β") or "β." in c[:4]:
        return "beta"
    if c.startswith("γ") or "γ." in c[:4]:
        return "gamma"
    if c.startswith("δ") or c.startswith("19") or "不動産" in c:
        return "delta_re"
    if re.match(r"^0\.", c):
        return "income"
    return "other"


# ----- finance -----


def load_entity_map() -> dict[str, Any]:
    return yaml.safe_load(MAP_PATH.read_text(encoding="utf-8")) or {}


def classify_txn(row: dict[str, str], cfg: dict[str, Any]) -> tuple[str, str]:
    """jarvis_finance_metrics.classify_row と同じ趣旨。"""
    method = (row.get("方法") or "").strip()
    if method in (cfg.get("exclude_methods") or []):
        return "skip", "transfer"
    agg = (row.get("集計の設定") or "").strip()
    if agg in (cfg.get("exclude_aggregation_labels") or ["集計に含めない"]):
        return "skip", "aggregation_exclude"
    cat = (row.get("カテゴリ") or "").strip()
    pay = (row.get("支払元") or "").strip()
    dep = (row.get("入金先") or "").strip()

    def match_rule(text: str, rules: list) -> dict | None:
        for r in rules or []:
            m = str(r.get("match") or "")
            if m and m in (text or ""):
                return r
        return None

    cr = match_rule(cat, cfg.get("category_rules") or [])
    if cr:
        return str(cr.get("entity") or "personal"), str(cr.get("kind") or "other")
    ar = match_rule(pay, cfg.get("account_rules") or []) or match_rule(
        dep, cfg.get("account_rules") or []
    )
    entity = str((ar or {}).get("entity") or "personal")
    defaults = cfg.get("defaults") or {}
    kind = (
        str(defaults.get("income_kind") or "other_income")
        if method == "income"
        else str(defaults.get("expense_kind") or "other_expense")
    )
    if "修繕" in cat or "修繕" in (row.get("品目") or "") or "修繕" in (row.get("メモ") or ""):
        kind = "repair"
    if "家賃" in cat and method == "income":
        kind = "rent_income"
    return entity, kind


def upsert_chunks(sb: Any, table: str, rows: list[dict], on_conflict: str, size: int = 200) -> int:
    n = 0
    for i in range(0, len(rows), size):
        chunk = rows[i : i + size]
        sb.table(table).upsert(chunk, on_conflict=on_conflict).execute()
        n += len(chunk)
    return n


def ingest_zaim_raw(sb: Any, year: int, path: Path, *, dry_run: bool, push_metrics: bool) -> dict:
    cfg = load_entity_map()
    source_key = f"zaim_raw_{year}"
    st = path.stat()
    checksum = file_checksum(path)
    rows_out: list[dict] = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader, start=1):
            entity, kind = classify_txn(row, cfg)
            d_raw = (row.get("日付") or "").strip()
            txn_date = None
            if len(d_raw) >= 10:
                try:
                    txn_date = datetime.strptime(d_raw[:10], "%Y-%m-%d").date().isoformat()
                except ValueError:
                    txn_date = None
            rows_out.append(
                {
                    "fiscal_year": year,
                    "row_index": idx,
                    "txn_date": txn_date,
                    "method": (row.get("方法") or "").strip() or None,
                    "category": (row.get("カテゴリ") or "").strip() or None,
                    "subcategory": (row.get("カテゴリの内訳") or "").strip() or None,
                    "description": (row.get("品目") or "").strip() or None,
                    "memo": (row.get("メモ") or "").strip() or None,
                    "from_account": (row.get("支払元") or "").strip() or None,
                    "to_account": (row.get("入金先") or "").strip() or None,
                    "income_jpy": yen_num(row.get("収入")),
                    "expense_jpy": yen_num(row.get("支出")),
                    "balance_jpy": yen_num(row.get("残高")) if row.get("残高") not in (None, "") else None,
                    "currency": (row.get("通貨") or "").strip() or None,
                    "aggregation": (row.get("集計の設定") or "").strip() or None,
                    "entity": entity,
                    "kind": kind,
                }
            )

    meta = {
        "source_key": source_key,
        "fiscal_year": year,
        "kind": "zaim_raw",
        "source_path": str(path),
        "row_count": len(rows_out),
        "checksum": checksum,
        "file_mtime": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
        "metadata": {"bytes": st.st_size},
    }
    out = {"year": year, "path": str(path), "rows": len(rows_out), "dry_run": dry_run}
    if dry_run:
        return out

    src = (
        sb.table("kurashift_finance_sources")
        .upsert(meta, on_conflict="source_key")
        .execute()
        .data
    )
    source_id = src[0]["id"]
    # 再取込時は当該ソースの明細を差し替え
    sb.table("kurashift_finance_transactions").delete().eq("source_id", source_id).execute()
    for r in rows_out:
        r["source_id"] = source_id
    # insert in chunks (no upsert needed after delete)
    n = 0
    for i in range(0, len(rows_out), 250):
        chunk = rows_out[i : i + 250]
        sb.table("kurashift_finance_transactions").insert(chunk).execute()
        n += len(chunk)
    out["inserted"] = n
    out["source_id"] = source_id

    if push_metrics:
        # 既存メトリクスへ月次集計も載せる
        cmd = [
            str(PY),
            str(REPO / "scripts" / "jarvis_finance_metrics.py"),
            "--year",
            str(year),
            "--push",
        ]
        proc = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True)
        out["metrics_push_rc"] = proc.returncode
        out["metrics_push_stderr"] = (proc.stderr or "")[-400:]
    return out


def ingest_zaim_summary(sb: Any, year: int, path: Path, *, dry_run: bool) -> dict:
    source_key = f"zaim_summary_{year}"
    st = path.stat()
    cats: list[dict] = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cat = (row.get("カテゴリ") or "").strip()
            if not cat:
                continue
            income = yen_num(row.get("収入（円）") or row.get("収入"))
            expense = yen_num(row.get("支出（円）") or row.get("支出"))
            net = yen_num(row.get("収支（収入－支出）（円）") or row.get("収支"))
            if net == 0 and (income or expense):
                net = income - expense
            cats.append(
                {
                    "fiscal_year": year,
                    "category": cat,
                    "income_jpy": income,
                    "expense_jpy": expense,
                    "net_jpy": net,
                    "abg": classify_abg(cat),
                }
            )
    out = {"year": year, "path": str(path), "categories": len(cats), "dry_run": dry_run}
    if dry_run:
        return out
    meta = {
        "source_key": source_key,
        "fiscal_year": year,
        "kind": "zaim_lifeplan_summary",
        "source_path": str(path),
        "row_count": len(cats),
        "checksum": file_checksum(path),
        "file_mtime": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
        "metadata": {},
    }
    src = (
        sb.table("kurashift_finance_sources")
        .upsert(meta, on_conflict="source_key")
        .execute()
        .data
    )
    source_id = src[0]["id"]
    sb.table("kurashift_finance_category_year").delete().eq("source_id", source_id).execute()
    for c in cats:
        c["source_id"] = source_id
    for i in range(0, len(cats), 100):
        sb.table("kurashift_finance_category_year").insert(cats[i : i + 100]).execute()
    out["source_id"] = source_id
    return out


def find_summary_csv(year: int) -> Path | None:
    year_dir = TAX_DIR / f"{year}年度"
    for p in [
        year_dir / f"Zaim_ライフプラン_サマリー_{year}年度.csv",
        year_dir / f"Zaim_ライフプラン_サマリー_{year}年度.csv",
    ]:
        if p.is_file():
            return p
    if year_dir.is_dir():
        for p in sorted(year_dir.glob("Zaim*サマリー*.csv")):
            return p
    return None


def run_finance(*, dry_run: bool, push_metrics: bool) -> dict:
    sb = None if dry_run else sb_client()
    results = []
    years = []
    for year_dir in sorted(TAX_DIR.glob("*年度")):
        m = re.match(r"^(\d{4})年度$", year_dir.name)
        if not m:
            continue
        years.append(int(m.group(1)))
    for year in years:
        raw = TAX_DIR / f"{year}年度" / f"Zaim.{year}年度.csv"
        if raw.is_file():
            if dry_run:
                results.append({"year": year, "raw_rows": sum(1 for _ in raw.open(encoding="utf-8-sig")) - 1})
            else:
                results.append(ingest_zaim_raw(sb, year, raw, dry_run=False, push_metrics=push_metrics))
                print(f"# finance raw {year}: {results[-1].get('inserted', results[-1].get('rows'))} rows", flush=True)
        summary = find_summary_csv(year)
        if summary:
            if dry_run:
                results.append({"year": year, "summary": str(summary)})
            else:
                results.append(ingest_zaim_summary(sb, year, summary, dry_run=False))
                print(f"# finance summary {year}: {results[-1].get('categories')} cats", flush=True)
    if not dry_run and sb:
        sb.table("sync_meta").upsert(
            {
                "key": "kurashift_finance_history_ingested_at",
                "value": jst_now().isoformat(timespec="seconds"),
                "updated_at": jst_now().isoformat(timespec="seconds"),
            },
            on_conflict="key",
        ).execute()
    return {"ok": True, "years": years, "results": results}


# ----- lifeplan -----


def applescript_list_sheets(path: Path) -> list[str]:
    script = f'''
set docPath to POSIX file "{path}"
tell application "Numbers"
    open docPath
    delay 0.8
    set theDoc to front document
    set names to name of every sheet of theDoc
    close theDoc saving no
    set AppleScript's text item delimiters to "||"
    return names as text
end tell
'''
    proc = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=180)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "list sheets failed")
    return [x for x in proc.stdout.strip().split("||") if x]


SEP = "\u241f"  # unit separator proxy（セル内の | や改行と衝突しにくい）


def applescript_list_tables(path: Path, sheet: str) -> list[str]:
    script = f'''
set docPath to POSIX file "{path}"
tell application "Numbers"
    open docPath
    delay 0.8
    set theDoc to front document
    try
        set theSheet to sheet "{sheet}" of theDoc
        set names to name of every table of theSheet
    on error errMsg
        close theDoc saving no
        return "ERR|" & errMsg
    end try
    close theDoc saving no
    set AppleScript's text item delimiters to "||"
    return names as text
end tell
'''
    proc = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=180)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "list tables failed")
    out = proc.stdout.strip()
    if out.startswith("ERR|"):
        raise RuntimeError(out[4:])
    return [x for x in out.split("||") if x]


def applescript_dump_table(
    path: Path, sheet: str, table: str, *, max_cols: int = 90, max_rows: int = 250
) -> dict:
    """任意シート／表の生グリッド。区切りは SEP（セル内 | 対策）。"""
    script = f'''
set docPath to POSIX file "{path}"
set sep to "{SEP}"
tell application "Numbers"
    open docPath
    delay 1.0
    set theDoc to front document
    try
        set theSheet to sheet "{sheet}" of theDoc
        set theTable to table "{table}" of theSheet
    on error errMsg
        close theDoc saving no
        return "ERR|" & errMsg
    end try
    set rowCount to row count of theTable
    set colCount to column count of theTable
    if colCount > {max_cols} then set colCount to {max_cols}
    if rowCount > {max_rows} then set rowCount to {max_rows}
    set out to "META" & sep & rowCount & sep & colCount & linefeed
    repeat with r from 1 to rowCount
        set rowLine to (r as text)
        repeat with c from 1 to colCount
            try
                set v to value of cell r of column c of theTable
                if v is missing value then
                    set t to ""
                else
                    set t to v as text
                end if
            on error
                set t to ""
            end try
            set t to my replaceText(t, sep, "/")
            set t to my replaceText(t, linefeed, " ")
            set rowLine to rowLine & sep & t
        end repeat
        set out to out & rowLine & linefeed
    end repeat
    close theDoc saving no
    return out
end tell

on replaceText(theText, searchString, replacementString)
    set AppleScript's text item delimiters to searchString
    set theItems to every text item of theText
    set AppleScript's text item delimiters to replacementString
    set theText to theItems as string
    set AppleScript's text item delimiters to ""
    return theText
end replaceText
'''
    proc = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "dump failed")
    text = proc.stdout.strip()
    if text.startswith("ERR|"):
        raise RuntimeError(text[4:])
    lines = [ln for ln in text.splitlines() if ln]
    if not lines or not lines[0].startswith("META" + SEP):
        raise RuntimeError("unexpected dump output")
    meta = lines[0].split(SEP)
    rc, cc = int(meta[1]), int(meta[2])
    grid = []
    for ln in lines[1:]:
        parts = ln.split(SEP)
        try:
            rnum = int(parts[0])
        except ValueError:
            continue
        grid.append({"r": rnum, "cells": parts[1:]})
    return {"row_count": rc, "col_count": cc, "grid": grid}


def dump_legacy_sheets(sb: Any, version: dict, *, per_sheet: int = 3) -> int:
    """表名が現行と違う旧版向け。各シートの先頭表を生保存。"""
    path = Path(version["source_path"])
    sheets = list(version.get("sheet_names") or [])
    if not sheets:
        return 0
    dumped = 0
    for sheet in sheets:
        try:
            tables = applescript_list_tables(path, sheet)
        except Exception:
            continue
        for table in tables[:per_sheet]:
            try:
                dump = applescript_dump_table(path, sheet, table)
                sb.table("kurashift_lifeplan_sheet_dumps").upsert(
                    {
                        "version_id": version["id"],
                        "sheet_name": sheet,
                        "table_name": table,
                        "row_count": dump["row_count"],
                        "col_count": dump["col_count"],
                        "payload": {"grid": dump["grid"], "source": "legacy_table_dump"},
                    },
                    on_conflict="version_id,sheet_name,table_name",
                ).execute()
                dumped += 1
            except Exception as e:
                print(f"# dump skip {version.get('version_key')} {sheet}/{table}: {e}", flush=True)
    return dumped

def register_versions(sb: Any, files: list[Path], *, dry_run: bool) -> list[dict]:
    canonical = Path((playbook().get("numbers") or {}).get("canonical_path") or "")
    out = []
    for path in files:
        as_of = parse_as_of_from_name(path.name) or date.fromtimestamp(path.stat().st_mtime)
        key = version_key_from_path(path)
        # 衝突回避
        if any(x["version_key"] == key for x in out):
            key = f"{key}_{path.parent.name}"
        st = path.stat()
        row = {
            "version_key": key,
            "as_of": as_of.isoformat(),
            "source_path": str(path),
            "source_filename": path.name,
            "label": path.stem,
            "is_canonical": path.resolve() == canonical.resolve() if canonical.exists() else key == CANONICAL_KEY,
            "file_mtime": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
            "file_size_bytes": st.st_size,
            "extract_status": "pending",
            "updated_at": jst_now().isoformat(timespec="seconds"),
        }
        out.append(row)
    if dry_run:
        return out
    upsert_chunks(sb, "kurashift_lifeplan_versions", out, on_conflict="version_key", size=50)
    return out


def extract_structured_budget(sb: Any, version: dict, years: list[int]) -> dict:
    path = Path(version["source_path"])
    version_id = version["id"]
    exact, skip_patterns = load_mapping(ZAIM_SYNC / "budget_category_map.yaml")
    all_recs: list[dict] = []
    errors: list[str] = []
    for year in years:
        try:
            month_cols = month_cols_for_year(year)
            raw = extract_raw_table(path, BUDGET_SHEET, BUDGET_TABLE, month_cols)
            records, _unmapped = rows_to_budget_records(raw, year, exact, skip_patterns)
            for rec in records:
                all_recs.append(
                    {
                        "version_id": version_id,
                        "plan_year": year,
                        "month": rec["month"],
                        "numbers_category": rec["numbers_category"],
                        "category_key": rec.get("category_key"),
                        "amount_yen": rec["amount_yen"],
                        "series": "plan",
                    }
                )
        except Exception as e:
            errors.append(f"{year}:{e}")
    # 差し替え
    sb.table("kurashift_lifeplan_budget_rows").delete().eq("version_id", version_id).execute()
    for i in range(0, len(all_recs), 200):
        sb.table("kurashift_lifeplan_budget_rows").insert(all_recs[i : i + 200]).execute()
    return {"budget_rows": len(all_recs), "errors": errors}


def extract_one_version(sb: Any, version: dict, *, dump_sheet: bool, structured_years: list[int] | None) -> dict:
    path = Path(version["source_path"])
    notes: list[str] = []
    sheet_names: list[str] = []
    status = "ok"
    result: dict[str, Any] = {"version_key": version["version_key"]}

    try:
        sheet_names = applescript_list_sheets(path)
        result["sheets"] = sheet_names
    except Exception as e:
        notes.append(f"sheets:{e}")
        status = "failed"
        result["error"] = str(e)

    years = structured_years
    if years is None:
        as_of = date.fromisoformat(version["as_of"])
        # 正本は広め、旧版は前後2年
        if version.get("is_canonical"):
            years = list(range(max(2018, as_of.year - 4), as_of.year + 3))
        else:
            years = list(range(max(2018, as_of.year - 1), as_of.year + 2))

    if status != "failed":
        try:
            ex = extract_structured_budget(sb, version, years)
            result.update(ex)
            if ex["errors"] and ex["budget_rows"] == 0:
                status = "partial"
                notes.extend(ex["errors"][:3])
            elif ex["errors"]:
                status = "partial"
                notes.append(f"partial_years:{len(ex['errors'])}")
        except Exception as e:
            notes.append(f"structured:{e}")
            status = "partial"

    # 現行表名で取れない／明示 dump 時 → シート内の表を生保存
    need_legacy = dump_sheet or not result.get("budget_rows")
    if status != "failed" and need_legacy:
        try:
            n_dump = dump_legacy_sheets(sb, {**version, "sheet_names": sheet_names or version.get("sheet_names")})
            result["sheet_dumps"] = n_dump
            if n_dump and not result.get("budget_rows"):
                status = "ok"
            elif n_dump and status == "partial":
                notes.append(f"legacy_dumps:{n_dump}")
        except Exception as e:
            notes.append(f"legacy_dump:{e}")

    sb.table("kurashift_lifeplan_versions").update(
        {
            "extract_status": status,
            "extract_notes": "; ".join(notes)[:2000] if notes else None,
            "sheet_names": sheet_names,
            "updated_at": jst_now().isoformat(timespec="seconds"),
            "metadata": {
                "budget_rows": result.get("budget_rows"),
                "sheet_dumps": result.get("sheet_dumps"),
                "structured_years": years,
            },
        }
    ).eq("id", version["id"]).execute()
    # 参照用に plan_snapshots へ要約も1件
    if result.get("budget_rows"):
        sb.table("kurashift_plan_snapshots").insert(
            {
                "label": f"numbers_{version['version_key']}",
                "fiscal_year": date.fromisoformat(version["as_of"]).year,
                "snapshot_at": version["as_of"],
                "metrics": {
                    "kind": "lifeplan_version",
                    "version_key": version["version_key"],
                    "budget_rows": result.get("budget_rows"),
                    "sheets": sheet_names[:20],
                    "source_path": version["source_path"],
                },
                "notes": f"history ingest from {version['source_filename']}",
            }
        ).execute()

    result["extract_status"] = status
    result["notes"] = notes
    return result


def run_lifeplan(*, dry_run: bool, extract: bool, dump_sheet: bool) -> dict:
    files = discover_numbers_files()
    print(f"# discovered {len(files)} .numbers under {LIFEPLAN_DIR}", flush=True)
    if dry_run:
        preview = []
        for p in files:
            preview.append(
                {
                    "file": p.name,
                    "as_of": (parse_as_of_from_name(p.name) or date.fromtimestamp(p.stat().st_mtime)).isoformat(),
                    "key": version_key_from_path(p),
                    "bytes": p.stat().st_size,
                }
            )
        return {"ok": True, "dry_run": True, "files": preview}

    sb = sb_client()
    register_versions(sb, files, dry_run=False)
    vers = (
        sb.table("kurashift_lifeplan_versions")
        .select("*")
        .order("as_of")
        .execute()
        .data
        or []
    )
    extracts = []
    if extract:
        for v in vers:
            print(f"# extracting {v['version_key']} ({v['source_filename']}) …", flush=True)
            try:
                extracts.append(
                    extract_one_version(sb, v, dump_sheet=dump_sheet, structured_years=None)
                )
            except Exception as e:
                extracts.append({"version_key": v["version_key"], "error": str(e)})
                sb.table("kurashift_lifeplan_versions").update(
                    {
                        "extract_status": "failed",
                        "extract_notes": str(e)[:2000],
                        "updated_at": jst_now().isoformat(timespec="seconds"),
                    }
                ).eq("id", v["id"]).execute()
            print(f"#   → {extracts[-1].get('extract_status') or extracts[-1].get('error')} "
                  f"budget_rows={extracts[-1].get('budget_rows')}", flush=True)

    sb.table("sync_meta").upsert(
        {
            "key": "kurashift_lifeplan_history_ingested_at",
            "value": jst_now().isoformat(timespec="seconds"),
            "updated_at": jst_now().isoformat(timespec="seconds"),
        },
        on_conflict="key",
    ).execute()
    return {
        "ok": True,
        "versions": len(vers),
        "extracts": extracts,
        "registered": [v["version_key"] for v in vers],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="KURASHIFT history → Supabase")
    ap.add_argument("--finance", action="store_true", help="Zaim 年度CSVを取込")
    ap.add_argument("--lifeplan", action="store_true", help="Life Plan .numbers を登録")
    ap.add_argument("--all", action="store_true", help="finance + lifeplan")
    ap.add_argument("--extract", action="store_true", help="Numbers から予算を抽出（AppleScript）")
    ap.add_argument("--dump-sheet", action="store_true", help="月別予算表の生グリッドも保存")
    ap.add_argument("--no-metrics-push", action="store_true", help="metrics テーブルへの月次pushを省略")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    if not (args.finance or args.lifeplan or args.all):
        ap.error("--finance / --lifeplan / --all のいずれかを指定")

    STATE.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {"at": jst_now().isoformat(timespec="seconds")}

    if args.all or args.finance:
        print("# === finance ===", flush=True)
        report["finance"] = run_finance(
            dry_run=args.dry_run, push_metrics=not args.no_metrics_push and not args.dry_run
        )
    if args.all or args.lifeplan:
        print("# === lifeplan ===", flush=True)
        report["lifeplan"] = run_lifeplan(
            dry_run=args.dry_run,
            extract=args.extract and not args.dry_run,
            dump_sheet=args.dump_sheet,
        )

    out_path = STATE / f"ingest_{jst_now().strftime('%Y%m%d_%H%M%S')}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"# wrote {out_path}", flush=True)
    print(json.dumps({k: (v if k != "finance" else {"years": v.get("years"), "n": len(v.get("results") or [])})
                      if isinstance(v, dict) else v
                      for k, v in report.items()}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
