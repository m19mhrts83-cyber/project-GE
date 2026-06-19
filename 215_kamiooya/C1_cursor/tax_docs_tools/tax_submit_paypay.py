#!/usr/bin/env python3
"""
PayPay銀行 明細 PDF 取得 → MyKomon アップロードを一括実行する。

使い方（月を列挙）:
  python tax_submit_paypay.py \
      --months 2025-06,2026-05 \
      --materials-root ".../2.経費,売上資料"

内部動作:
  1. 月ごとに期間フォルダ（00_元ファイル_サイト取得/PayPay銀行/）を確認・作成
  2. PayPay銀行にログインして明細 PDF を取得
  3. 年度・四半期を月から判定
  4. MyKomon にアップロード（--skip-mykomon で省略可）

認証情報: .env.tax_docs に PayPay / MyKomon の両方を設定する。
"""

from __future__ import annotations

import argparse
import calendar
import os
import sys
from datetime import date
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_ENV_PATH = SCRIPT_DIR / ".env.tax_docs"

FISCAL_YEAR_START_MONTH = 7
"""法人の決算期に合わせた年度の開始月（7月始まり＝6月決算）。"""

MYKOMON_CATEGORY_PAYPAY = "01_預金通帳のコピー"


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
    """決算期に基づく会計年度を返す（7月始まりなら 2025年7月→2026年度）。"""
    if month_date.month >= FISCAL_YEAR_START_MONTH:
        return month_date.year + 1
    return month_date.year


def _quarter_label(month: int) -> str:
    """月から四半期フォルダ名を返す（①1-3月, ②4-6月, ③7-9月, ④10-12月）。"""
    q = (month - 1) // 3
    labels = ["①1-3月", "②4-6月", "③7-9月", "④10-12月"]
    return labels[q]


def _year_label(fiscal_year: int) -> str:
    """MyKomon のフォルダ名形式の年度ラベルを返す。"""
    reiwa = fiscal_year - 2018
    return f"{fiscal_year}年（令和{reiwa}年）"


def _folder_name_for_month(year: int, month: int) -> str:
    """期間フォルダ名を返す（例: "6月"）。"""
    return f"{month}月"


def _output_name_for_month(month: int) -> str:
    """PayPay PDF のファイル名を返す。"""
    return f"PayPay銀行明細_{month}月.pdf"


def _ensure_output_dir(materials_root: Path, year: int, month: int) -> Path:
    """00_元ファイル_サイト取得/PayPay銀行/ を確認・作成して返す。"""
    folder = _folder_name_for_month(year, month)
    out = materials_root / str(year) / folder / "00_元ファイル_サイト取得" / "PayPay銀行"
    out.mkdir(parents=True, exist_ok=True)
    return out


def run_pipeline(
    *,
    months: list[date],
    materials_root: Path,
    headed: bool,
    dry_run: bool,
    skip_mykomon: bool,
    pause_on_error: bool,
) -> None:
    # 遅延 import（PayPay / MyKomon スクリプトが同ディレクトリにある前提）
    from paypay_bank_statement import run as paypay_run
    from mykomon_upload import run as mykomon_run

    results: list[dict] = []

    for m in months:
        label = f"{m.year}年{m.month}月"
        print(f"\n{'='*60}")
        print(f"  {label}")
        print(f"{'='*60}")

        start_date = m
        last_day = calendar.monthrange(m.year, m.month)[1]
        end_date = date(m.year, m.month, last_day)

        output_dir = _ensure_output_dir(materials_root, m.year, m.month)
        output_name = _output_name_for_month(m.month)
        dest = output_dir / output_name

        if dest.exists() and not dry_run:
            print(f"  ⚠ 既にファイルが存在します: {dest}")
            print(f"    スキップします（上書きするには手動で削除してください）。")
            results.append({"month": label, "paypay": "skipped", "mykomon": "skipped"})
            continue

        # PayPay PDF 取得
        print(f"\n--- PayPay銀行 PDF 取得 ({label}) ---")
        pdf_path = paypay_run(
            start_date=start_date,
            end_date=end_date,
            output_dir=output_dir,
            output_name=output_name,
            headed=headed,
            dry_run=dry_run,
            pause_on_error=pause_on_error,
        )

        if dry_run:
            results.append({"month": label, "paypay": "dry-run", "mykomon": "dry-run"})
            continue

        if pdf_path is None:
            print(f"  ❌ PayPay PDF の取得に失敗: {label}")
            results.append({"month": label, "paypay": "FAILED", "mykomon": "skipped"})
            continue

        results.append({"month": label, "paypay": "OK", "mykomon": "pending"})

        # MyKomon アップロード
        if skip_mykomon:
            print(f"  (--skip-mykomon: MyKomon アップロードをスキップ)")
            results[-1]["mykomon"] = "skipped"
            continue

        fy = _fiscal_year(m)
        year_label = _year_label(fy)
        quarter = _quarter_label(m.month)

        print(f"\n--- MyKomon アップロード ({label}) ---")
        print(f"  年度: {year_label}, 四半期: {quarter}, 分類: {MYKOMON_CATEGORY_PAYPAY}")

        ok = mykomon_run(
            file_path=pdf_path,
            year=year_label,
            quarter=quarter,
            category=MYKOMON_CATEGORY_PAYPAY,
            headed=headed,
            dry_run=False,
            pause_on_error=pause_on_error,
        )
        results[-1]["mykomon"] = "OK" if ok else "FAILED"

    # サマリー
    print(f"\n{'='*60}")
    print("  結果サマリー")
    print(f"{'='*60}")
    for r in results:
        pp = r["paypay"]
        mk = r["mykomon"]
        print(f"  {r['month']:12s}  PayPay: {pp:8s}  MyKomon: {mk:8s}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="PayPay銀行 → MyKomon の一括提出ツール",
    )
    parser.add_argument(
        "--months", required=True,
        help="対象月（YYYY-MM のカンマ区切り。例: 2025-06,2026-05）",
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
        help="MyKomon アップロードをスキップ（PayPay PDF 取得のみ）",
    )
    parser.add_argument(
        "--no-pause", action="store_true",
        help="エラー時に page.pause() を呼ばない",
    )
    args = parser.parse_args()

    _load_env_file(Path(args.env_file))

    months: list[date] = []
    for token in args.months.split(","):
        token = token.strip()
        parts = token.split("-")
        if len(parts) != 2:
            print(f"エラー: 月の形式が不正です: {token}（YYYY-MM）", file=sys.stderr)
            sys.exit(1)
        y, m = int(parts[0]), int(parts[1])
        months.append(date(y, m, 1))

    run_pipeline(
        months=months,
        materials_root=Path(args.materials_root),
        headed=not args.headless,
        dry_run=args.dry_run,
        skip_mykomon=args.skip_mykomon,
        pause_on_error=not args.no_pause,
    )


if __name__ == "__main__":
    main()
