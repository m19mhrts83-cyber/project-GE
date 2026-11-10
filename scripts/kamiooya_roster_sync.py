#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""神大家Q&A (3) 名簿照合用のハッシュを作り直す（2026-11-10）。

運営の「※削除厳禁※【神大家】目標設定・合格状況」シート（gid=929377200）を
estate アカウント（閲覧が許可されているのはこのアカウントだけ）で読み、
会員番号と「会員番号＋姓名」のハッシュだけを Supabase の qa_roster_hashes に全件入れ替える。
名前・番号の平文は Supabase にも画面にもログにも出さない。

照合のルール（正規化・ハッシュ）は apps/kamiooya-qa-web/lib/rosterMatch.ts と同じ。
tests/rosterMatch.test.mjs が両方の結果が一致することを確かめている。

例（Mac）:
  ~/selenium_env/venv/bin/python scripts/kamiooya_roster_sync.py --dry-run   # 件数だけ表示
  ~/selenium_env/venv/bin/python scripts/kamiooya_roster_sync.py             # 入れ替え
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
import unicodedata
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SPREADSHEET_ID = "1igYsbKqff0u0VzukUQ-Dv2p1dHQwE1yhK1dhJBJFpFU"
SHEET_GID = 929377200
HEADER_ROW = 2  # 1行目は説明、2行目が見出し、3行目は講座名、4行目から会員


def normalize_member_no(v: object) -> str:
    s = re.sub(r"[\s\-ー－_]", "", unicodedata.normalize("NFKC", str(v or ""))).lower()
    return re.sub(r"^0+(?=\d)", "", s) if s.isdigit() else s


def normalize_name(v: object) -> str:
    return re.sub(r"[\s・･.]", "", unicodedata.normalize("NFKC", str(v or ""))).lower()


def roster_hash(kind: str, member_no: object, name: object = "") -> str:
    value = normalize_member_no(member_no) if kind == "no" else normalize_member_no(member_no) + "|" + normalize_name(name)
    return hashlib.sha256(("qa-roster-v1\0" + kind + "\0" + value).encode("utf-8")).hexdigest()


def hashes_from_rows(rows: list[list[str]]) -> set[tuple[str, str]]:
    """見出し行（会員番号・姓・名）を探して列を決め、会員の行からハッシュを作る。"""
    head = [str(x).strip() for x in (rows[HEADER_ROW - 1] if len(rows) >= HEADER_ROW else [])]
    try:
        i_no, i_last = head.index("会員番号"), head.index("姓")
    except ValueError:
        raise SystemExit("見出し（会員番号・姓）が見つかりません。シートの形が変わった可能性があります")
    i_first = head.index("名") if "名" in head else None
    out: set[tuple[str, str]] = set()
    for r in rows[HEADER_ROW + 1:]:
        cell = lambda i: (r[i] if i is not None and i < len(r) else "")
        no, name = normalize_member_no(cell(i_no)), normalize_name(str(cell(i_last)) + str(cell(i_first)))
        if not no or not re.search(r"\d", no):
            continue
        out.add(("no", roster_hash("no", no)))
        if name:
            out.add(("no_name", roster_hash("no_name", no, name)))
    return out


def read_sheet() -> list[list[str]]:
    sys.path.insert(0, str(REPO / "215_kamiooya" / "C1_cursor" / "westudy_common"))
    from google_workspace_auth import load_credentials  # estate アカウント
    from googleapiclient.discovery import build

    svc = build("sheets", "v4", credentials=load_credentials(), cache_discovery=False)
    meta = svc.spreadsheets().get(spreadsheetId=SPREADSHEET_ID, fields="sheets.properties(sheetId,title)").execute()
    title = next((s["properties"]["title"] for s in meta["sheets"] if s["properties"]["sheetId"] == SHEET_GID), None)
    if title is None:
        raise SystemExit("照合用のシート（gid=929377200）が見つかりません")
    rng = "'" + title.replace("'", "''") + "'!A1:C"
    return svc.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range=rng).execute().get("values", [])


def replace_sql(hashes: set[tuple[str, str]], members: int) -> str:
    values = ",".join(f"('{k}','{h}')" for k, h in sorted(hashes))
    return (
        "begin;"
        "delete from public.qa_roster_hashes;"
        + (f"insert into public.qa_roster_hashes(kind,hash) values {values};" if values else "")
        + f"insert into public.qa_roster_meta(id,row_count,synced_at) values (1,{int(members)},now())"
        " on conflict (id) do update set row_count=excluded.row_count, synced_at=excluded.synced_at;"
        "commit;"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    hashes = hashes_from_rows(read_sheet())
    members = sum(1 for k, _ in hashes if k == "no")
    print(f"名簿: 会員番号 {members} 件 / 番号＋姓名 {sum(1 for k, _ in hashes if k == 'no_name')} 件")
    if members == 0:
        raise SystemExit("名簿が0件のため入れ替えません")
    if a.dry_run:
        return 0
    sys.path.insert(0, str(REPO / "scripts"))
    import kamiooya_qa_release as rel  # 同じ秘密情報ファイルと Management API を使う

    rel.load_env()
    rel.mgmt_query(replace_sql(hashes, members))
    print("qa_roster_hashes を入れ替えました")
    return 0


if __name__ == "__main__":
    sys.exit(main())
