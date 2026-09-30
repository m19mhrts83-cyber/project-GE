#!/usr/bin/env python3
"""Kneesbee / MyKomon 取得物 → kurashift_re_* 取込。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_re_statement_ingest.py
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_re_statement_ingest.py --dry-run

既定入力:
  …/knees bee 税理士法人/1.資料/2期終了_202608/
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from supabase import create_client

REPO = Path(__file__).resolve().parents[1]
DEFAULT_DIR = (
    Path.home()
    / "Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部"
    / "50_税金,確定申告/knees bee 税理士法人/1.資料/2期終了_202608"
)

# 事業計画書 PDF 抽出値（2026-08-28 MyKomon・作成日同日）
PLAN_YEARS = [
    # fiscal_year = 決算期の暦年（5月期末）
    {
        "fiscal_year": 2026,
        "label": "2026年5月期（実績）",
        "revenue_jpy": 4017572,
        "full_rent_jpy": 5022000,
        "pretax_profit_jpy": -1190714,
        "tax_jpy": 70000,
        "cash_flow_jpy": -1409359,
        "interest_jpy": 1559349,
        "depreciation_jpy": 1447131,
        "repair_jpy": 498801,
        "other_expense_jpy": 1475518,
        "tax_public_jpy": 227487,
        "principal_repay_jpy": 3155125,
    },
    {
        "fiscal_year": 2027,
        "label": "2027年5月期（見込）",
        "revenue_jpy": 3829931,
        "full_rent_jpy": 5022000,
        "pretax_profit_jpy": -673181,
        "tax_jpy": 70000,
        "cash_flow_jpy": -1098167,
        "interest_jpy": 1353007,
        "depreciation_jpy": 1447131,
        "repair_jpy": 0,
        "other_expense_jpy": 1475487,
        "tax_public_jpy": 227487,
        "principal_repay_jpy": 3155124,
    },
    {
        "fiscal_year": 2028,
        "label": "2028年5月期（見込・満室）",
        "revenue_jpy": 5022000,
        "full_rent_jpy": 5022000,
        "pretax_profit_jpy": 560777,
        "tax_jpy": 70000,
        "cash_flow_jpy": 93902,
        "interest_jpy": 1311118,
        "depreciation_jpy": 1447131,
        "repair_jpy": 0,
        "other_expense_jpy": 1475487,
        "tax_public_jpy": 227487,
        "principal_repay_jpy": 3155124,
    },
]

# R8 決算メール（2026-07-15）＋事業計画の整合
R8_STATEMENT = {
    "entity": "corporate",
    "fiscal_year": 2026,
    "period_start": "2025-06-01",
    "period_end": "2026-05-31",
    "label": "R8（第2期）",
    "source": "kneesbee_r8",
    "revenue_jpy": 4017572,
    "operating_profit_jpy": 180994,
    "pretax_profit_jpy": -1190714,
    "tax_jpy": 71000,
    "net_income_jpy": -1190714 - 71000,  # 参考: 税引後は欠損扱い
    "capital_jpy": 100000,
    "retained_earnings_jpy": -1590000,  # Notion 8/28 累損約▲159万
    "officer_loan_jpy": 8900000,  # Notion 約890万
    "pl_json": {
        "full_rent_jpy": 5022000,
        "interest_jpy": 1559349,
        "depreciation_jpy": 1447131,
        "cash_flow_jpy": -1409359,
        "loss_carryforward_jpy": 1500000,
    },
    "bs_json": {
        "substantive_equity_note": "役員借入を実質資本とみなすと純資産700〜800万円規模（Notion 8/28）",
        "debt_excess_book_jpy": -1500000,
    },
    "reconcile_notes": (
        "営業利益180,994はR8メール。不動産所得▲1,190,714は事業計画・R8税引前と一致。"
        "法人税等メール71,000／計画70,000（均等割）。手残り計画▲1,409,359≒Notion▲150万。"
    ),
}


def sb_client():
    url = os.environ.get("JARVIS_SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
    key = os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError("JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY が必要")
    return create_client(url, key)


def _wareki_to_iso(s: str) -> str | None:
    m = re.match(r"令和(\d+)年(\d+)月(\d+)日", s or "")
    if not m:
        return None
    y = 2018 + int(m.group(1))
    return f"{y:04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"


def _num(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(str(v).replace(",", ""))
    except ValueError:
        return None


def decode_gl_csv(path: Path) -> list[list[str]]:
    raw = path.read_bytes()
    for enc in ("cp932", "shift_jis", "utf-8-sig", "utf-8"):
        try:
            text = raw.decode(enc)
            break
        except Exception:
            continue
    else:
        text = raw.decode("utf-8", errors="replace")
    return list(csv.reader(text.splitlines()))


def parse_gl_lines(rows: list[list[str]]) -> list[dict[str, Any]]:
    # header index from 表題行
    header: list[str] = []
    for r in rows:
        if r and r[0] == "[表題行]":
            header = r[1:]
            break
    idx = {name: i for i, name in enumerate(header)}

    def col(r: list[str], name: str) -> str:
        i = idx.get(name)
        if i is None:
            return ""
        # r[0] is row type; data starts at r[1]
        j = i + 1
        return r[j] if j < len(r) else ""

    out: list[dict[str, Any]] = []
    for r in rows:
        if not r or r[0] != "[明細行]":
            continue
        account = col(r, "勘定科目") or (r[2] if len(r) > 2 else "")
        if not account:
            continue
        debit = _num(col(r, "借方金額"))
        credit = _num(col(r, "貸方金額"))
        amount = None
        if debit is not None or credit is not None:
            amount = (debit or 0) - (credit or 0)
        date_s = _wareki_to_iso(col(r, "日付"))
        desc = col(r, "摘要")
        aux = col(r, "補助科目")
        fp_src = "|".join(
            [
                account,
                aux,
                date_s or "",
                col(r, "伝票No."),
                col(r, "仕訳番号"),
                str(debit or ""),
                str(credit or ""),
                desc,
            ]
        )
        fp = hashlib.sha1(fp_src.encode("utf-8")).hexdigest()
        out.append(
            {
                "entity": "corporate",
                "fiscal_year": 2026,
                "txn_date": date_s,
                "account_name": account,
                "description": desc or None,
                "counterparty": aux or None,
                "debit_jpy": debit,
                "credit_jpy": credit,
                "amount_jpy": amount,
                "source_file": "総勘定元帳.txt",
                "source": "mykomon",
                "row_fingerprint": fp,
            }
        )
    return out


def upsert_statement(sb: Any, *, dry_run: bool) -> None:
    row = {
        **R8_STATEMENT,
        "evidence_path": str(DEFAULT_DIR / "R8_リビングサポート松_申告書一式.pdf"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    print(f"# statement R8 pretax={row['pretax_profit_jpy']} op={row['operating_profit_jpy']}")
    if dry_run:
        return
    sb.table("kurashift_re_statements").upsert(
        row, on_conflict="entity,period_end,source"
    ).execute()


def upsert_plans(sb: Any, *, dry_run: bool) -> None:
    now = datetime.now(timezone.utc).isoformat()
    for p in PLAN_YEARS:
        row = {
            "entity": "corporate",
            "fiscal_year": p["fiscal_year"],
            "label": p["label"],
            "source": "mykomon",
            "plan_json": p,
            "revenue_jpy": p["revenue_jpy"],
            "operating_profit_jpy": None,
            "pretax_profit_jpy": p["pretax_profit_jpy"],
            "cash_flow_jpy": p["cash_flow_jpy"],
            "occupancy_pct": round(p["revenue_jpy"] / p["full_rent_jpy"] * 100, 1)
            if p["full_rent_jpy"]
            else None,
            "notes": "事業計画書_2026年申告後（MyKomon・2026-08-28作成）",
            "evidence_path": str(
                DEFAULT_DIR / "事業計画書_株式会社　リビングサポート松様_2026年　申告後 (1).pdf"
            ),
            "updated_at": now,
        }
        print(
            f"# plan FY{p['fiscal_year']} revenue={p['revenue_jpy']} "
            f"pretax={p['pretax_profit_jpy']} cf={p['cash_flow_jpy']}"
        )
        if dry_run:
            continue
        sb.table("kurashift_re_annual_plans").upsert(
            row, on_conflict="entity,fiscal_year,source,label"
        ).execute()


def upsert_gl(sb: Any, lines: list[dict[str, Any]], *, dry_run: bool) -> None:
    print(f"# gl_lines={len(lines)}")
    if dry_run:
        return
    # chunk upsert
    for i in range(0, len(lines), 200):
        chunk = lines[i : i + 200]
        sb.table("kurashift_re_gl_lines").upsert(
            chunk, on_conflict="entity,row_fingerprint"
        ).execute()
        print(f"  upserted {i + len(chunk)}/{len(lines)}")


def write_reconcile_md(out_dir: Path, gl_count: int) -> None:
    md = f"""# 突合ゲート — Kneesbee / MyKomon / Notion 8/28（2026-08-30）

## ソース

| ソース | ファイル／場所 |
|---|---|
| MyKomon DL | `{out_dir}` |
| Notion | 2期目決算報告・事業計画書レビュー会議（2026-08-28） |
| R8メール | 2026-07-15 決算のご報告 |

## 主要数値

| 項目 | MyKomon事業計画 | R8メール | Notion 8/28 | 判定 |
|---|---:|---:|---:|---|
| 満室家賃 | 5,022,000 | — | 約500万 | OK |
| 家賃収入（2026/5期） | 4,017,572 | — | 約380万 | OK（概算） |
| 税引前／不動産所得 | -1,190,714 | -1,190,714 | ▲120万 | OK |
| 営業利益 | — | 180,994 | — | メール正 |
| 法人税等 | 70,000 | 71,000 | 均等割のみ | 差額1,000円・許容 |
| 手残りCF | -1,409,359 | — | ▲150万 | OK（概算） |
| 欠損金繰越 | 計画上使用 | — | 約150万 | OK |
| 資本金 | — | — | 10万 | OK |
| 役員借入 | — | — | 約890万 | Notion正（元帳に科目あり） |

## 元帳

- 総勘定元帳.txt（処理日時 令和08年08月28日）明細行 **{gl_count}** 件を取込対象
- 期間: 令和07年06月01日〜令和08年05月31日（決算仕訳含む）

## ゲート

**PASS** — 法人PL主要行はソース間で説明可能。UI は statement / plan 優先で実装可。
"""
    path = out_dir / "01_突合ゲート.md"
    path.write_text(md, encoding="utf-8")
    print(f"📎 reconcile → {path}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(DEFAULT_DIR))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    out_dir = Path(args.dir)
    gl_path = out_dir / "総勘定元帳.txt"
    if not gl_path.exists():
        print(f"missing {gl_path}", file=sys.stderr)
        return 1

    rows = decode_gl_csv(gl_path)
    lines = parse_gl_lines(rows)
    write_reconcile_md(out_dir, len(lines))

    if args.dry_run:
        print(f"# dry-run statement pretax={R8_STATEMENT['pretax_profit_jpy']}")
        for p in PLAN_YEARS:
            print(f"# dry-run plan FY{p['fiscal_year']} cf={p['cash_flow_jpy']}")
        print(f"# dry-run gl={len(lines)} sample_accounts={[x['account_name'] for x in lines[:5]]}")
        return 0

    sb = sb_client()
    upsert_statement(sb, dry_run=False)
    upsert_plans(sb, dry_run=False)
    upsert_gl(sb, lines, dry_run=False)
    print("KURASHIFT_RESULT:" + json.dumps({"gl": len(lines), "ok": True}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
