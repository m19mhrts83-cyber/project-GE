#!/usr/bin/env python3
"""
オリックス銀行「返済実績表」PDF のダウンロード後処理。

- PDF 本文から **実際に表に載っている最新の月分** を推定し、
  `返済実績表_<グループ>_<開始>〜<終了>.pdf` の **終了月** を実データに合わせて付け直す。
- 照会期間の「至」が翌月まで含まれていても、**表に行が無い月**（例: 4月分が未反映）は
  ファイル名では **3月まで** にそろえる（ユーザ要望）。

前提:
  返済実績表の PDF では、月分と取引日が `2026/032026/03/10` のように連結されて抽出されることが多い。
  そのパターンを優先して解析する。取れない場合は日付 `YYYY/MM/DD` の最大値から月を推定する
  （このとき `作成日` 行を除く）。

使用例:

  cd ~/git-repos/215_kamiooya/C1_cursor/tax_docs_tools
  pip install -r requirements.txt   # 初回のみ

  python3 orix_repayment_pdf_postprocess.py \\
    --input ~/Downloads/NBGA3160....pdf \\
    --dest-dir \"$HOME/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/50_税金,確定申告/knees bee 税理士法人/2.経費,売上資料/2025/10月-2026.4月/00_元ファイル_サイト取得/オリックス銀行_借入\" \\
    --group G1

  # ドライラン
  python3 orix_repayment_pdf_postprocess.py --input ./sample.pdf --dest-dir ./out --group G1 --dry-run
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None  # type: ignore


# 月分 + 取引日が連結: 例 円2026/032026/03/10
_GLUE_ROW = re.compile(
    r"(20\d{2})/(\d{1,2})(20\d{2})/(\d{1,2})/(\d{1,2})"
)
# 対象期間 （自）2025/10/01～ （至）2026/04/30
_PERIOD = re.compile(
    r"[（(]自[）)]\s*(20\d{2})/(\d{1,2})/\d{1,2}\s*[～~〜\-－]\s*(20\d{2})/(\d{1,2})/\d{1,2}"
)
# フォールバック: すべてのスラッシュ日付
_FULL_DATE = re.compile(r"(20\d{2})/(\d{1,2})/(\d{1,2})")


def extract_pdf_text(path: Path) -> str:
    if PdfReader is None:
        raise RuntimeError(
            "pypdf が必要です。tax_docs_tools で pip install -r requirements.txt を実行してください。"
        )
    reader = PdfReader(str(path))
    parts: list[str] = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return "\n".join(parts)


def strip_creation_line(text: str) -> str:
    """作成日の行を除き、誤って最新月に取り込まないようにする。"""
    lines = []
    for line in text.splitlines():
        if "作成日" in line and re.search(r"20\d{2}/\d{1,2}/\d{1,2}", line):
            continue
        lines.append(line)
    return "\n".join(lines)


def latest_month_from_glued_rows(text: str) -> tuple[int, int] | None:
    """(年, 月) の最大。連結パターンから月分（先頭の YYYY/MM）を使う。"""
    best: tuple[int, int] | None = None
    for m in _GLUE_ROW.finditer(text):
        y, mo = int(m.group(1)), int(m.group(2))
        y2, mo2 = int(m.group(3)), int(m.group(4))
        # 同一行では月分と取引日の年月は一致している想定
        if (y, mo) != (y2, mo2):
            continue
        cand = (y, mo)
        if best is None or cand > best:
            best = cand
    return best


def latest_month_from_all_dates(text: str) -> tuple[int, int] | None:
    """連結が取れない PDF 向け。フル日付の最大から月を得る。"""
    t = strip_creation_line(text)
    best: tuple[int, int] | None = None
    for m in _FULL_DATE.finditer(t):
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if mo < 1 or mo > 12 or d < 1 or d > 31:
            continue
        cand = (y, mo)
        if best is None or cand > best:
            best = cand
    return best


def parse_period_start_end(text: str) -> tuple[tuple[int, int], tuple[int, int]] | None:
    m = _PERIOD.search(text.replace("~", "～"))
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2))), (int(m.group(3)), int(m.group(4)))


def format_period_label(start: tuple[int, int], end: tuple[int, int]) -> str:
    sy, sm = start
    ey, em = end
    if sy == ey:
        return f"{sy}.{sm}月〜{em}月"
    return f"{sy}.{sm}月〜{ey}.{em}月"


def build_target_name(group: str, start: tuple[int, int], end: tuple[int, int]) -> str:
    return f"返済実績表_{group}_{format_period_label(start, end)}.pdf"


def resolve_end_month(
    period_end: tuple[int, int],
    latest_data: tuple[int, int] | None,
) -> tuple[int, int]:
    """ファイル名の終了月は **照会「至」** と **表に出ている最新月分** のいずれか**早い**月にそろえる。"""
    if latest_data is None:
        return period_end
    return min(period_end, latest_data)


def process_one(
    src: Path,
    dest_dir: Path,
    group: str,
    dry_run: bool,
    overwrite: bool,
) -> tuple[Path | None, str]:
    text = extract_pdf_text(src)
    period = parse_period_start_end(text)
    if not period:
        return None, "対象期間（自）〜（至）を PDF から読み取れませんでした"

    start_m, period_end_m = period
    latest_glued = latest_month_from_glued_rows(text)
    latest_fb = latest_month_from_all_dates(text)
    latest_data = latest_glued or latest_fb
    if latest_data is None:
        return None, "表から最新の月分を推定できませんでした"

    end_m = resolve_end_month(period_end_m, latest_data)
    new_name = build_target_name(group, start_m, end_m)
    dest = dest_dir / new_name

    if dest.exists() and dest.resolve() != src.resolve() and not overwrite:
        return dest, f"スキップ（既存）: {dest.name}"

    msg = f"{src.name} → {new_name}（実データ最新月: {latest_data[0]}/{latest_data[1]:02d}）"
    if dry_run:
        return dest, msg + " [dry-run]"

    dest_dir.mkdir(parents=True, exist_ok=True)
    if dest.exists() and overwrite:
        dest.unlink()
    shutil.copy2(src, dest)
    return dest, msg


def main() -> int:
    ap = argparse.ArgumentParser(
        description="オリックス返済実績表 PDF を実データの最新月に合わせてリネーム保存する"
    )
    ap.add_argument("--input", type=Path, required=True, help="元の PDF（NBGA… 等）")
    ap.add_argument(
        "--dest-dir",
        type=Path,
        required=True,
        help="保存先ディレクトリ（例: …/00_元ファイル_サイト取得/オリックス銀行_借入）",
    )
    ap.add_argument("--group", default="G1", help="ファイル名のグループ（既定: G1）")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--overwrite",
        action="store_true",
        help="同名があれば上書き（既定はスキップ扱いでエラーにしない）",
    )
    args = ap.parse_args()

    src = args.input.expanduser().resolve()
    if not src.is_file():
        print(f"エラー: ファイルがありません: {src}", file=sys.stderr)
        return 1

    dest_dir = args.dest_dir.expanduser().resolve()

    try:
        dest, info = process_one(src, dest_dir, args.group, args.dry_run, args.overwrite)
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 1

    if dest is None:
        print(f"エラー: {info}", file=sys.stderr)
        return 1

    print(info)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
