#!/usr/bin/env python3
"""
Jarvis: LEAF くらさぽ送金明細 — パートナー確認用の定常取得。

ルール（送金は毎月20日想定）:
  - 今日が 21日以降 → 当月を必須
  - 今日が 20日以前 → 前月を必須
  - 必須月の1つ前が Stock に無ければ補完対象
  - Stock に LEAF_送金明細書_{YYYY}年{M}月.pdf があればブラウザ起動せずスキップ

使い方:
  python scripts/jarvis_leaf_kurasapo_partner_fetch.py
  python scripts/jarvis_leaf_kurasapo_partner_fetch.py --dry-run
  python scripts/jarvis_leaf_kurasapo_partner_fetch.py --force-months 2026-06,2026-07
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
TAX_TOOLS = REPO / "215_kamiooya" / "C1_cursor" / "tax_docs_tools"
LEAF_SCRIPT = TAX_TOOLS / "leaf_kurasapo_statement.py"
DEFAULT_PY = Path.home() / "selenium_env" / "venv" / "bin" / "python"
ONEDRIVE_PARTNER = (
    Path.home()
    / "Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部"
    / "C2_ルーティン作業/26_パートナー社への相談"
)
LEAF_FOLDER = "104_LEAF"
STOCK_NAME = "1.受信添付(Stock)"
PDF_RE = re.compile(r"^LEAF_送金明細書_(\d{4})年(\d{1,2})月\.pdf$")


def partner_base() -> Path:
    import os

    env = (os.environ.get("YORITOORI_BASE_PATH") or "").strip()
    if env:
        p = Path(env).expanduser().resolve()
        if p.is_dir():
            return p
    if ONEDRIVE_PARTNER.is_dir():
        return ONEDRIVE_PARTNER.resolve()
    return (REPO / "215_kamiooya" / "C2_ルーティン作業" / "26_パートナー社への相談").resolve()


def leaf_stock_dir() -> Path:
    return partner_base() / LEAF_FOLDER / STOCK_NAME


def ym_label(ym: tuple[int, int]) -> str:
    return f"{ym[0]}年{ym[1]}月"


def ym_key(ym: tuple[int, int]) -> str:
    return f"{ym[0]:04d}-{ym[1]:02d}"


def parse_ym(token: str) -> tuple[int, int]:
    y, m = token.strip().split("-")
    return int(y), int(m)


def prev_month(ym: tuple[int, int]) -> tuple[int, int]:
    y, m = ym
    if m == 1:
        return y - 1, 12
    return y, m - 1


def required_months(today: date) -> list[tuple[int, int]]:
    """必須月 + Stock 欠け時の前月補完候補を返す（重複なし・古い順）。"""
    if today.day >= 21:
        primary = (today.year, today.month)
    else:
        primary = prev_month((today.year, today.month))
    candidates = [primary, prev_month(primary)]
    # 重複排除しつつ古い順
    seen: set[tuple[int, int]] = set()
    out: list[tuple[int, int]] = []
    for ym in sorted(candidates):
        if ym not in seen:
            seen.add(ym)
            out.append(ym)
    return out


def scan_stock_months(stock: Path) -> dict[tuple[int, int], Path]:
    found: dict[tuple[int, int], Path] = {}
    if not stock.is_dir():
        return found
    for pdf in stock.rglob("LEAF_送金明細書_*.pdf"):
        m = PDF_RE.match(pdf.name)
        if not m:
            continue
        ym = (int(m.group(1)), int(m.group(2)))
        # 同一月が複数ある場合は最初の1つで足りる
        found.setdefault(ym, pdf)
    return found


def output_dir_for_today(today: date) -> Path:
    stock = leaf_stock_dir()
    day = stock / today.isoformat()
    day.mkdir(parents=True, exist_ok=True)
    return day


def print_report(
    *,
    today: date,
    needed: list[tuple[int, int]],
    present: list[tuple[int, int]],
    missing: list[tuple[int, int]],
    fetched: list[str],
    skipped_browser: bool,
    errors: list[str],
    dest: Path | None,
) -> None:
    print("📎 LEAFくらさぽ送金明細")
    print(f"- 判定日: {today.isoformat()}（21日以降=当月必須 / 以前=前月必須）")
    print(f"- 対象月: {', '.join(ym_key(m) for m in needed) or '—'}")
    if present:
        print(f"- Stock 既存: {', '.join(ym_key(m) for m in present)}")
    if skipped_browser:
        print("- 結果: スキップ（未取得月なし・ブラウザ起動なし）")
        return
    if dest:
        print(f"- 保存先: {dest}")
    if fetched:
        print(f"- 取得: {', '.join(fetched)}")
    if missing and not fetched:
        print(f"- 未取得のまま: {', '.join(ym_key(m) for m in missing)}")
    if errors:
        for e in errors:
            print(f"- ⚠ {e}")
    elif fetched and not errors:
        print("- 判定: OK")


def run_leaf_download(
    *,
    months: list[tuple[int, int]],
    output_dir: Path,
    python_bin: Path,
    dry_run: bool,
) -> tuple[int, str, str]:
    months_arg = ",".join(ym_key(m) for m in months)
    cmd = [
        str(python_bin),
        str(LEAF_SCRIPT),
        "--months",
        months_arg,
        "--output-dir",
        str(output_dir),
        "--headless",
        "--no-pause",
    ]
    if dry_run:
        cmd.append("--dry-run")
    proc = subprocess.run(
        cmd,
        cwd=str(TAX_TOOLS),
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="LEAF くらさぽ送金明細をパートナー受信添付へ（未取得月のみ）",
    )
    parser.add_argument(
        "--force-months",
        help="対象月を強制（YYYY-MM カンマ区切り。Stock 判定を無視して欠け月だけ取得）",
    )
    parser.add_argument(
        "--all-missing",
        action="store_true",
        help="--force-months 指定時、Stock にあっても再取得を試みる（同名スキップは leaf 側）",
    )
    parser.add_argument("--dry-run", action="store_true", help="一覧のみ（DL なし）")
    parser.add_argument(
        "--python",
        default=str(DEFAULT_PY),
        help="Playwright 入り Python（既定: selenium_env）",
    )
    parser.add_argument(
        "--as-of",
        help="判定日を上書き（YYYY-MM-DD。テスト用）",
    )
    args = parser.parse_args()

    if args.as_of:
        today = date.fromisoformat(args.as_of)
    else:
        today = datetime.now(JST).date()

    stock = leaf_stock_dir()
    on_disk = scan_stock_months(stock)

    if args.force_months:
        needed = [parse_ym(t) for t in args.force_months.split(",") if t.strip()]
        if args.all_missing:
            missing = needed
        else:
            missing = [ym for ym in needed if ym not in on_disk]
    else:
        needed = required_months(today)
        # 必須の primary は常に対象。前月は欠けているときだけ
        if today.day >= 21:
            primary = (today.year, today.month)
        else:
            primary = prev_month((today.year, today.month))
        missing = []
        if primary not in on_disk:
            missing.append(primary)
        prev = prev_month(primary)
        if prev not in on_disk:
            missing.append(prev)
        # needed 表示用は primary + prev（欠け判定に使った集合）
        needed = sorted({primary, prev})

    present = [ym for ym in needed if ym in on_disk]
    missing = sorted(set(missing))

    if not missing:
        print_report(
            today=today,
            needed=needed,
            present=present,
            missing=[],
            fetched=[],
            skipped_browser=True,
            errors=[],
            dest=None,
        )
        return 0

    if not LEAF_SCRIPT.is_file():
        print_report(
            today=today,
            needed=needed,
            present=present,
            missing=missing,
            fetched=[],
            skipped_browser=False,
            errors=[f"スクリプト不在: {LEAF_SCRIPT}"],
            dest=None,
        )
        return 0

    dest = output_dir_for_today(today)
    py = Path(args.python)
    if not py.is_file():
        print_report(
            today=today,
            needed=needed,
            present=present,
            missing=missing,
            fetched=[],
            skipped_browser=False,
            errors=[f"Python 不在: {py}"],
            dest=dest,
        )
        return 0

    print(
        f"[leaf_kurasapo] 未取得月を取得します: {', '.join(ym_key(m) for m in missing)}",
        file=sys.stderr,
    )
    code, out, err = run_leaf_download(
        months=missing,
        output_dir=dest,
        python_bin=py,
        dry_run=args.dry_run,
    )
    if out.strip():
        print(out.rstrip())
    if err.strip():
        print(err.rstrip(), file=sys.stderr)

    # 再スキャンで取得結果を判定
    on_disk_after = scan_stock_months(stock)
    fetched = [
        ym_key(ym)
        for ym in missing
        if ym in on_disk_after and (args.dry_run or on_disk_after[ym].exists())
    ]
    # dry-run ではファイルが増えないので stdout の ok を見る
    if args.dry_run:
        fetched = [ym_key(ym) for ym in missing]

    still_missing = [ym for ym in missing if ym not in on_disk_after]
    errors: list[str] = []
    failed_line = ""
    for line in (out + "\n" + err).splitlines():
        if line.startswith("# leaf_kurasapo_failed_months:"):
            failed_line = line.split(":", 1)[1].strip()
            break
    if failed_line:
        errors.append(f"PDF失敗: {failed_line}")
    elif code != 0 and still_missing:
        errors.append(
            f"取得失敗（exit={code}）: {', '.join(ym_key(m) for m in still_missing)}"
        )
    elif still_missing and not args.dry_run:
        errors.append(f"未取得のまま: {', '.join(ym_key(m) for m in still_missing)}")

    print_report(
        today=today,
        needed=needed,
        present=present,
        missing=missing,
        fetched=fetched,
        skipped_browser=False,
        errors=errors,
        dest=dest,
    )
    # パートナー確認は止めない
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
