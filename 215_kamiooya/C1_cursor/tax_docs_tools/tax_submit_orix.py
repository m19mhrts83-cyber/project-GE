#!/usr/bin/env python3
"""
オリックス銀行 返済実績表 PDF 取得 → リネーム → MyKomon アップロードを一括実行する。

使い方:
  python tax_submit_orix.py \
      --start-month 2025-06 --end-month 2025-06 \
      --group G1 \
      --materials-root ".../2.経費,売上資料"

内部動作:
  1. オリックス銀行にログインして返済実績表 PDF を取得
  2. orix_repayment_pdf_postprocess のロジックでリネーム
  3. 年度・四半期を照会期間から判定
  4. MyKomon の 05_借入金・保険・固定資産税 にアップロード（--skip-mykomon で省略可）

契約選択:
  既定で法人名義（Zinkaku=2）の契約を自動選択する（税理士提出は法人のみ）。
  --contract-index で明示指定した場合のみ個人契約も取得可能。

認証情報: .env.tax_docs に ORIX / MyKomon の両方を設定する。
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_ENV_PATH = SCRIPT_DIR / ".env.tax_docs"

FISCAL_YEAR_START_MONTH = 7
MYKOMON_CATEGORY_ORIX = "05_借入金・保険・固定資産税"


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and value and key not in os.environ:
            os.environ[key] = value


def _fiscal_year(month_date: date) -> int:
    if month_date.month >= FISCAL_YEAR_START_MONTH:
        return month_date.year + 1
    return month_date.year


def _quarter_label(month: int) -> str:
    q = (month - 1) // 3
    labels = ["①1-3月", "②4-6月", "③7-9月", "④10-12月"]
    return labels[q]


def _year_label(fiscal_year: int) -> str:
    reiwa = fiscal_year - 2018
    return f"{fiscal_year}年（令和{reiwa}年）"


def _period_folder(start_month: int, end_month: int, start_year: int, end_year: int) -> str:
    """OneDrive 側の期間フォルダ名を返す。"""
    if start_year == end_year:
        return f"{start_month}月-{end_month}月"
    return f"{start_month}月-{end_year}.{end_month}月"


def _ensure_output_dir(materials_root: Path, year: int, period_folder: str) -> Path:
    """00_元ファイル_サイト取得/オリックス銀行_借入/ を確認・作成して返す。"""
    out = materials_root / str(year) / period_folder / "00_元ファイル_サイト取得" / "オリックス銀行_借入"
    out.mkdir(parents=True, exist_ok=True)
    return out


def run_pipeline(
    *,
    start_year: int,
    start_month: int,
    end_year: int,
    end_month: int,
    contract_index: int | None,
    group: str,
    materials_root: Path,
    headed: bool,
    dry_run: bool,
    skip_mykomon: bool,
    pause_on_error: bool,
) -> None:
    from orix_bank_statement import run as orix_run

    print(f"\n{'='*60}")
    print(f"  オリックス銀行 返済実績表 → MyKomon 一括提出")
    print(f"  照会期間: {start_year}/{start_month:02d} 〜 {end_year}/{end_month:02d}")
    print(f"  グループ: {group}")
    print(f"{'='*60}")

    # 期間フォルダの決定
    period_folder = _period_folder(start_month, end_month, start_year, end_year)
    output_dir = _ensure_output_dir(materials_root, start_year, period_folder)

    # PDF 取得
    print("\n--- オリックス銀行 PDF 取得 ---")
    raw_pdf = orix_run(
        start_year=start_year,
        start_month=start_month,
        end_year=end_year,
        end_month=end_month,
        contract_index=contract_index,
        group=group,
        output_dir=output_dir,
        headed=headed,
        dry_run=dry_run,
        pause_on_error=pause_on_error,
    )

    if dry_run:
        print(f"\n{'='*60}")
        print("  [dry-run] 完了")
        print(f"{'='*60}")
        return

    if raw_pdf is None:
        print(f"\n{'='*60}")
        print("  ❌ PDF 取得失敗")
        print(f"{'='*60}")
        return

    # リネーム（後処理スクリプトのロジックを利用）
    print("\n--- PDF リネーム（後処理） ---")
    try:
        from orix_repayment_pdf_postprocess import process_one
        renamed, info = process_one(
            raw_pdf, output_dir, group, dry_run=False, overwrite=False
        )
        print(f"  {info}")
        final_pdf = renamed if renamed else raw_pdf
    except Exception as e:
        print(f"  ⚠ リネームエラー: {e}")
        print(f"  → 元のファイル名のまま続行: {raw_pdf.name}")
        final_pdf = raw_pdf

    # MyKomon アップロード
    if skip_mykomon:
        print(f"\n  (--skip-mykomon: MyKomon アップロードをスキップ)")
        result_mykomon = "skipped"
    else:
        from mykomon_upload import run as mykomon_run

        # 照会期間の終了月からMyKomonフォルダを判定
        m_date = date(end_year, end_month, 1)
        fy = _fiscal_year(m_date)
        year_label = _year_label(fy)
        quarter = _quarter_label(end_month)

        print(f"\n--- MyKomon アップロード ---")
        print(f"  年度: {year_label}, 四半期: {quarter}, 分類: {MYKOMON_CATEGORY_ORIX}")

        ok = mykomon_run(
            file_path=final_pdf,
            year=year_label,
            quarter=quarter,
            category=MYKOMON_CATEGORY_ORIX,
            headed=headed,
            dry_run=False,
            pause_on_error=pause_on_error,
        )
        result_mykomon = "OK" if ok else "FAILED"

    # サマリー
    print(f"\n{'='*60}")
    print("  結果サマリー")
    print(f"{'='*60}")
    print(f"  期間: {start_year}/{start_month:02d}〜{end_year}/{end_month:02d}")
    print(f"  PDF: {final_pdf.name}")
    print(f"  MyKomon: {result_mykomon}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="オリックス銀行 返済実績表 → MyKomon の一括提出ツール",
    )
    parser.add_argument(
        "--start-month", required=True,
        help="照会開始月（YYYY-MM。例: 2025-06）",
    )
    parser.add_argument(
        "--end-month", required=True,
        help="照会終了月（YYYY-MM。例: 2025-06）",
    )
    parser.add_argument(
        "--contract-index", type=int, default=None,
        help="契約一覧での選択位置（0始まり）。未指定時は法人名義を自動選択",
    )
    parser.add_argument(
        "--group", default="G1",
        help="借入グループ名（既定: G1）",
    )
    parser.add_argument(
        "--materials-root", required=True,
        help="2.経費,売上資料 フォルダのパス",
    )
    parser.add_argument(
        "--env-file", default=str(DEFAULT_ENV_PATH),
        help=f"認証情報 .env ファイル（既定: {DEFAULT_ENV_PATH}）",
    )
    parser.add_argument(
        "--headless", action="store_true",
        help="ヘッドレスモードで実行",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="画面遷移のみ確認",
    )
    parser.add_argument(
        "--skip-mykomon", action="store_true",
        help="MyKomon アップロードをスキップ",
    )
    parser.add_argument(
        "--no-pause", action="store_true",
        help="エラー時に page.pause() を呼ばない",
    )
    args = parser.parse_args()

    _load_env_file(Path(args.env_file))

    sy, sm = args.start_month.split("-")
    ey, em = args.end_month.split("-")

    run_pipeline(
        start_year=int(sy),
        start_month=int(sm),
        end_year=int(ey),
        end_month=int(em),
        contract_index=args.contract_index,
        group=args.group,
        materials_root=Path(args.materials_root),
        headed=not args.headless,
        dry_run=args.dry_run,
        skip_mykomon=args.skip_mykomon,
        pause_on_error=not args.no_pause,
    )


if __name__ == "__main__":
    main()
