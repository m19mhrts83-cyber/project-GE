#!/usr/bin/env python3
"""
Web版 Zaim から家計簿 CSV をダウンロードし、年度フォルダへ保存する。

例:
  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  python zaim_csv_export.py --year 2026 --end-date 2026-06-28
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import date
from pathlib import Path

from playwright.sync_api import sync_playwright

import zaim_budget_apply as zaim

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = Path(
    "~/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/50_税金,確定申告"
).expanduser()
ZAIM_FILE_IO_URL = "https://content.zaim.net/home/money"
DOWNLOAD_DIR = SCRIPT_DIR / "downloads"


def year_range(year: int, end_date: date | None) -> tuple[date, date]:
    start = date(year, 1, 1)
    end = end_date or date(year, 12, 31)
    if end < start:
        raise ValueError(f"終了日 {end} が開始日 {start} より前です")
    return start, end


def output_path(output_dir: Path, year: int) -> Path:
    year_dir = output_dir / f"{year}年度"
    year_dir.mkdir(parents=True, exist_ok=True)
    return year_dir / f"Zaim.{year}年度.csv"


def select_date(page, prefix: str, d: date) -> None:
    page.locator(f'select[name="{prefix}_year"]').select_option(str(d.year))
    page.locator(f'select[name="{prefix}_month"]').select_option(f"{d.month:02d}")
    page.locator(f'select[name="{prefix}_day"]').select_option(f"{d.day:02d}")


def export_csv(page, start: date, end: date, encoding: str) -> Path:
    page.goto(ZAIM_FILE_IO_URL, wait_until="networkidle")
    page.wait_for_timeout(1500)

    collapse = page.locator("#collapseDownload")
    if not collapse.is_visible():
        page.locator('h3[href="#collapseDownload"]').click()
        page.wait_for_timeout(800)

    select_date(page, "start", start)
    select_date(page, "end", end)
    page.locator('select[name="charset"]').select_option(encoding)

    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    zaim.SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

    submit = page.locator(
        '#collapseDownload form.download-money input[value="この条件でダウンロード"]'
    )
    submit.wait_for(state="visible", timeout=10_000)

    with page.expect_download(timeout=180_000) as dl_info:
        submit.click()

    download = dl_info.value
    tmp = DOWNLOAD_DIR / (download.suggested_filename or "zaim_export.csv")
    download.save_as(str(tmp))
    return tmp


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Zaim 家計簿 CSV エクスポート")
    parser.add_argument("--year", type=int, default=2026, help="対象年（1/1 起点）")
    parser.add_argument("--end-date", default=None, help="終了日 YYYY-MM-DD（省略時は年末）")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--encoding", default="utf8", choices=["utf8", "sjis"])
    parser.add_argument("--connect-cdp", default=None)
    parser.add_argument("--login-method", choices=["email", "google"], default="email")
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args(argv)

    end_d = date.fromisoformat(args.end_date) if args.end_date else None
    start, end = year_range(args.year, end_d)
    dest = output_path(args.output_dir, args.year)

    if not args.connect_cdp and not zaim.STORAGE_STATE.exists():
        print(f"先に zaim_budget_apply.py --login を実行してください: {zaim.STORAGE_STATE}", file=sys.stderr)
        return 1

    with sync_playwright() as pw:
        browser, ctx, _ = zaim.open_browser_context(
            pw,
            headless=args.headless,
            connect_cdp=args.connect_cdp,
            storage_state=zaim.STORAGE_STATE if not args.connect_cdp else None,
        )
        page = zaim.get_work_page(ctx)
        zaim.ensure_logged_in(
            page,
            login_method=args.login_method,
        )
        print(f"▶ CSV ダウンロード: {start} 〜 {end} ({args.encoding})")
        tmp = export_csv(page, start, end, args.encoding)
        shutil.copy2(tmp, dest)
        zaim.save_storage_state(ctx)
        if browser and not args.connect_cdp:
            browser.close()

    text = dest.read_text(encoding="utf-8", errors="replace")
    lines = text.count("\n")
    print(f"✅ 保存: {dest}")
    print(f"   行数: {lines:,}（ヘッダ含む）")
    if lines > 1:
        print(f"   先頭データ行: {text.splitlines()[1][:80]}...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
