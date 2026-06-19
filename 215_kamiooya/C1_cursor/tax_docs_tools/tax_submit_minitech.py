#!/usr/bin/env python3
"""
ミニテック送金のご案内 PDF 取得 → MyKomon アップロードを一括実行する。

使い方:
  python tax_submit_minitech.py \
      --months 2025-07,2025-08,2025-09 \
      --materials-root ".../2.経費,売上資料"

内部動作:
  1. 月ごとに期間フォルダ（00_元ファイル_サイト取得/ミニテック/）を確認・作成
  2. ミニテック・オーナーマイページから送金のご案内 PDF を取得
  3. 年度・四半期を月から判定
  4. MyKomon の 02_賃貸収入 にアップロード（--skip-mykomon で省略可）

認証情報: .env.tax_docs に MINITECH / MyKomon の両方を設定する。
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
MYKOMON_CATEGORY_MINITECH = "02_賃貸収入"


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


def _period_folder(month: int) -> str:
    """四半期の期間フォルダ名を返す（OneDrive 側の命名）。"""
    q = (month - 1) // 3
    folders = ["1月-3月", "4月-6月", "7月-9月", "10月-12月"]
    return folders[q]


def _ensure_output_dir(materials_root: Path, year: int, month: int) -> Path:
    """00_元ファイル_サイト取得/ミニテック/ を確認・作成して返す。"""
    period = _period_folder(month)
    out = materials_root / str(year) / period / "00_元ファイル_サイト取得" / "ミニテック"
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
    from minitech_statement import run as minitech_run
    from mykomon_upload import run as mykomon_run

    results: list[dict] = []

    # ミニテックからのPDFダウンロードは1セッションでまとめて行う
    month_tuples = [(m.year, m.month) for m in months]

    # 出力先は四半期ごとにまとまる可能性があるが、全部同じディレクトリを使う
    # 最初の月から出力ディレクトリを決める
    output_dirs: dict[tuple[int, int], Path] = {}
    for m in months:
        out = _ensure_output_dir(materials_root, m.year, m.month)
        output_dirs[(m.year, m.month)] = out

    # 全月まとめて取得（同じ四半期なら同一ディレクトリ）
    unique_dirs = set(output_dirs.values())
    if len(unique_dirs) == 1:
        output_dir = unique_dirs.pop()
    else:
        # 複数ディレクトリの場合、各月のディレクトリにダウンロード
        output_dir = None

    print(f"\n{'='*60}")
    print(f"  ミニテック送金のご案内 → MyKomon 一括提出")
    print(f"  対象: {', '.join(f'{m.year}年{m.month}月' for m in months)}")
    print(f"{'='*60}")

    # ミニテック PDF 取得
    print("\n--- ミニテック PDF 取得 ---")
    if output_dir:
        dl_results = minitech_run(
            months=month_tuples,
            output_dir=output_dir,
            headed=headed,
            dry_run=dry_run,
            pause_on_error=pause_on_error,
        )
    else:
        dl_results = []
        for m in months:
            per_results = minitech_run(
                months=[(m.year, m.month)],
                output_dir=output_dirs[(m.year, m.month)],
                headed=headed,
                dry_run=dry_run,
                pause_on_error=pause_on_error,
            )
            dl_results.extend(per_results)

    # MyKomon アップロード
    for r in dl_results:
        label = f"{r['year']}年{r['month']}月"
        if r["status"] != "ok" or r["path"] is None:
            results.append({
                "month": label,
                "minitech": r["status"],
                "mykomon": "skipped",
            })
            continue

        results.append({
            "month": label,
            "minitech": "OK",
            "mykomon": "pending",
        })

        if skip_mykomon:
            results[-1]["mykomon"] = "skipped"
            continue

        m_date = date(r["year"], r["month"], 1)
        fy = _fiscal_year(m_date)
        year_label = _year_label(fy)
        quarter = _quarter_label(r["month"])

        print(f"\n--- MyKomon アップロード ({label}) ---")
        print(f"  年度: {year_label}, 四半期: {quarter}, 分類: {MYKOMON_CATEGORY_MINITECH}")

        ok = mykomon_run(
            file_path=r["path"],
            year=year_label,
            quarter=quarter,
            category=MYKOMON_CATEGORY_MINITECH,
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
        mt = r["minitech"]
        mk = r["mykomon"]
        print(f"  {r['month']:12s}  ミニテック: {mt:8s}  MyKomon: {mk:8s}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ミニテック送金のご案内 → MyKomon の一括提出ツール",
    )
    parser.add_argument(
        "--months", required=True,
        help="対象月（YYYY-MM のカンマ区切り。例: 2025-07,2025-08,2025-09）",
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
        help="MyKomon アップロードをスキップ（ミニテック PDF 取得のみ）",
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
