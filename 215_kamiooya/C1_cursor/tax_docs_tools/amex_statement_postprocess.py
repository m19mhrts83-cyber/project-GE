#!/usr/bin/env python3
"""
AMEX 明細ファイルの「ダウンロード後」整理用スクリプト。

- ダウンロードフォルダ等に保存された CSV / PDF を、四半期ごとの税理士提出フォルダへ移動し、
  ファイル名を `AMEX_<年>Q<四半期>_...` 形式にそろえる。
- ログインやサイトからの取得は行わない（手動ダウンロード後の後処理のみ）。

使用例:

  cd ~/git-repos/215_kamiooya/C1_cursor/tax_docs_tools
  python3 amex_statement_postprocess.py \\
    --inbox ~/Downloads \\
    --materials-root \"$HOME/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/50_税金,確定申告/knees bee 税理士法人/2.経費,売上資料\" \\
    --year 2025 --quarter 3 \\
    --since-hours 48

  # ドライラン
  python3 amex_statement_postprocess.py --inbox ~/Downloads --dest \".../2025/7月-9月/07_AMEX明細\" --year 2025 --quarter 3 --dry-run
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

QUARTER_MONTH_LABEL: dict[int, str] = {
    1: "1月-3月",
    2: "4月-6月",
    3: "7月-9月",
    4: "10月-12月",
}


def quarter_month_range_label(q: int) -> str:
    if q not in QUARTER_MONTH_LABEL:
        raise ValueError(f"quarter must be 1-4, got {q}")
    return QUARTER_MONTH_LABEL[q]


def default_dest_folder(materials_root: Path, year: int, quarter: int) -> Path:
    return materials_root / str(year) / quarter_month_range_label(quarter) / "07_AMEX明細"


def is_recent(path: Path, since_hours: float | None) -> bool:
    if since_hours is None:
        return True
    mtime = datetime.fromtimestamp(path.stat().st_mtime)
    return mtime >= datetime.now() - timedelta(hours=since_hours)


def looks_like_amex_candidate(path: Path) -> bool:
    """ファイル名に AMEX 関連っぽい文字列があるか（--amex-only 用。厳密ではない）。"""
    name = path.name.lower()
    # オンライン明細の Excel 既定名が activity.xlsx / activity (1).xlsx の場合がある
    if path.suffix.lower() in (".xlsx", ".xls"):
        stem = path.stem.lower()
        if stem == "activity" or stem.startswith("activity ("):
            return True
    keys = (
        "amex",
        "american",
        "express",
        "アメックス",
        "エキスプレス",
        "アメリカン",
    )
    return any(k.lower() in name for k in keys)


def pick_files(
    inbox: Path,
    since_hours: float | None,
    extensions: Iterable[str],
    amex_only: bool,
) -> list[Path]:
    exts = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in extensions}
    candidates: list[Path] = []
    for p in sorted(inbox.iterdir()):
        if not p.is_file():
            continue
        if p.suffix.lower() not in exts:
            continue
        if not is_recent(p, since_hours):
            continue
        if amex_only and not looks_like_amex_candidate(p):
            continue
        candidates.append(p)
    return candidates


def build_target_name(
    year: int,
    quarter: int,
    kind: str,
    index: int,
    suffix: str,
) -> str:
    base = f"AMEX_{year}Q{quarter}_{kind}"
    if index > 0:
        base = f"{base}_{index + 1}"
    return base + suffix


def classify_kind(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".csv":
        return "利用履歴"
    if ext in (".xlsx", ".xls"):
        return "利用履歴_表計算"
    if ext == ".pdf":
        return "ご利用代金明細書"
    return "明細"


def run_organize(args: argparse.Namespace) -> int:
    inbox: Path = args.inbox.expanduser().resolve()
    if not inbox.is_dir():
        print(f"エラー: インボックスが存在しません: {inbox}", file=sys.stderr)
        return 1

    if args.dest:
        dest = args.dest.expanduser().resolve()
    else:
        root = args.materials_root.expanduser().resolve()
        dest = default_dest_folder(root, args.year, args.quarter)

    dest.mkdir(parents=True, exist_ok=True)

    since: float | None = None if args.all_inbox else args.since_hours

    files = pick_files(
        inbox,
        since,
        args.extensions.split(","),
        amex_only=args.amex_only,
    )
    if not files:
        print(
            f"移動対象がありません（inbox={inbox}, since_hours={since}, amex_only={args.amex_only}）"
        )
        return 0

    # 種類ごとに連番
    counts: dict[str, int] = {}

    print(f"保存先: {dest}")
    for src in files:
        kind = classify_kind(src)
        idx = counts.get(kind, 0)
        counts[kind] = idx + 1
        new_name = build_target_name(
            args.year, args.quarter, kind, idx, src.suffix.lower()
        )
        target = dest / new_name
        if target.exists() and not args.overwrite:
            print(f"スキップ（既存）: {target}")
            continue
        print(f"  {src.name} -> {new_name}")
        if args.dry_run:
            continue
        if target.exists() and args.overwrite:
            target.unlink()
        shutil.move(str(src), str(target))

    if args.dry_run:
        print("（dry-run のため移動していません）")
    return 0


def main() -> None:
    p = argparse.ArgumentParser(
        description="AMEX 明細ファイルを四半期フォルダへ移動・リネームする（ダウンロード後処理）"
    )
    p.add_argument(
        "--inbox",
        type=Path,
        default=Path.home() / "Downloads",
        help="ダウンロード済みファイルがあるフォルダ（既定: ~/Downloads）",
    )
    p.add_argument(
        "--materials-root",
        type=Path,
        help="税理士資料のベース（例: .../2.経費,売上資料）。--dest 未指定時に使用",
    )
    p.add_argument(
        "--dest",
        type=Path,
        help="保存先フォルダをフルパスで指定（指定時は --materials-root / 年 / 四半期は不要）",
    )
    p.add_argument("--year", type=int, required=True, help="例: 2025")
    p.add_argument(
        "--quarter",
        type=int,
        choices=(1, 2, 3, 4),
        required=True,
        help="四半期 1〜4",
    )
    p.add_argument(
        "--since-hours",
        type=float,
        default=72.0,
        help="この時間以内に更新されたファイルのみ（既定: 72）。--all-inbox と併用不可",
    )
    p.add_argument(
        "--all-inbox",
        action="store_true",
        help="更新日時に関わらず、インボックス内の対象拡張子をすべて移動（取り込み過多に注意）",
    )
    p.add_argument(
        "--extensions",
        default="csv,pdf,xlsx,xls",
        help="対象拡張子（カンマ区切り）",
    )
    p.add_argument(
        "--amex-only",
        action="store_true",
        help="ファイル名に AMEX っぽい文字列があるものだけ（既定はオフ＝拡張子に合う最近のファイルすべて）",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="表示のみで移動しない",
    )
    p.add_argument(
        "--overwrite",
        action="store_true",
        help="同名ファイルがあれば上書き（通常はスキップ）",
    )
    args = p.parse_args()

    if not args.dest and not args.materials_root:
        p.error("--dest か --materials-root のどちらかが必要です")

    sys.exit(run_organize(args))


if __name__ == "__main__":
    main()
