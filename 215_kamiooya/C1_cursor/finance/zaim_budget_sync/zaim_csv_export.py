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
import time
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

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


# 折りたたみのトグルは h3[href] 以外（a / data-bs-target）のことがある
_DOWNLOAD_TOGGLES = (
    'h3[href="#collapseDownload"]',
    'a[href="#collapseDownload"]',
    '[data-bs-target="#collapseDownload"]',
    'h3.title:has-text("記録データをダウンロード")',
)


def _safe_url(url: str) -> str:
    parts = urlsplit(url or "")
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _snapshot(page) -> tuple[str, str]:
    url = page.url or ""
    try:
        title = page.title() or ""
    except Exception:
        title = ""
    return url, title


def _download_ui_present(page) -> bool:
    if page.locator("#collapseDownload").count():
        return True
    if page.locator('input[value="この条件でダウンロード"]').count():
        return True
    for sel in _DOWNLOAD_TOGGLES:
        if page.locator(sel).count():
            return True
    return False


def _page_is_auth_wall(page) -> bool:
    url, title = _snapshot(page)
    if zaim.is_auth_wall_url(url):
        return True
    if "ログイン" in title or "くふうアカウント" in title:
        return True
    password = page.locator('input[type="password"]')
    try:
        return bool(password.count() and password.first.is_visible())
    except Exception:
        return False


def _page_is_blocked(page) -> bool:
    _, title = _snapshot(page)
    return "could not be satisfied" in title or "Request blocked" in title


def _goto_money_page(page) -> None:
    page.goto(ZAIM_FILE_IO_URL, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(1500)


def _wait_download_or_wall(page, timeout_ms: int = 20_000) -> str:
    """ui / wall / blocked / missing"""
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        if _download_ui_present(page):
            return "ui"
        if _page_is_blocked(page):
            return "blocked"
        if _page_is_auth_wall(page):
            return "wall"
        page.wait_for_timeout(500)
    if _download_ui_present(page):
        return "ui"
    if _page_is_blocked(page):
        return "blocked"
    if _page_is_auth_wall(page):
        return "wall"
    return "missing"


def _open_download_panel(page) -> None:
    collapse = page.locator("#collapseDownload")
    if collapse.count() and collapse.is_visible():
        return
    for sel in _DOWNLOAD_TOGGLES:
        loc = page.locator(sel).first
        try:
            if loc.count() and loc.is_visible():
                loc.click()
                page.wait_for_timeout(800)
                return
        except Exception:
            continue
    page.locator('h3[href="#collapseDownload"], a[href="#collapseDownload"]').first.click(
        timeout=10_000
    )
    page.wait_for_timeout(800)


def _fail_screenshot(page, name: str) -> None:
    try:
        zaim.SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(zaim.SCREENSHOT_DIR / name), full_page=True)
    except Exception:
        pass


def _force_email_login(page) -> None:
    """zaim.net の URL だけ残って content 側が切れているとき、ログインをやり直す。"""
    print("  ファイル入出力が認証壁のため、メールログインをやり直します")
    try:
        page.context.clear_cookies()
    except Exception as e:
        print(f"  cookie clear skipped: {e}")
    zaim.login_with_email_password(page, zaim.DEFAULT_LOGIN_EMAIL, zaim.DEFAULT_LOGIN_PASSWORD)


def export_csv(page, start: date, end: date, encoding: str, *, login_method: str = "email") -> Path:
    _goto_money_page(page)
    state = _wait_download_or_wall(page)
    if state == "blocked":
        url, title = _snapshot(page)
        print(f"  ダウンロードページがブロック url={_safe_url(url)} title={title!r} → reload")
        page.reload(wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(1500)
        state = _wait_download_or_wall(page, timeout_ms=15_000)
    if state == "wall" and login_method == "email":
        url, title = _snapshot(page)
        print(f"  ダウンロードUIなし url={_safe_url(url)} title={title!r}")
        _force_email_login(page)
        _goto_money_page(page)
        state = _wait_download_or_wall(page)
    elif state == "missing":
        url, title = _snapshot(page)
        print(f"  ダウンロードUI待ち url={_safe_url(url)} title={title!r} → reload")
        page.reload(wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(1500)
        state = _wait_download_or_wall(page, timeout_ms=15_000)
        if state == "wall" and login_method == "email":
            _force_email_login(page)
            _goto_money_page(page)
            state = _wait_download_or_wall(page)

    if state != "ui":
        url, title = _snapshot(page)
        _fail_screenshot(page, "csv_export_no_download_ui.png")
        raise RuntimeError(
            "ZaimのダウンロードUIが見つかりません "
            f"url={_safe_url(url)} title={title!r}"
        )

    _open_download_panel(page)

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


def _goto_with_retries(page, url: str, *, retries: int = 2) -> None:
    """ERR_NETWORK_CHANGED / timeout 向けの軽い再試行。"""
    last_err: Exception | None = None
    for attempt in range(max(1, retries + 1)):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            return
        except Exception as e:  # noqa: BLE001 — Playwright 系をまとめて再試行
            last_err = e
            msg = str(e)
            retryable = any(
                k in msg
                for k in (
                    "ERR_NETWORK_CHANGED",
                    "net::ERR_",
                    "Timeout",
                    "NS_ERROR_NET",
                )
            )
            if not retryable or attempt >= retries:
                raise
            page.wait_for_timeout(1500 * (attempt + 1))
    if last_err:
        raise last_err


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Zaim 家計簿 CSV エクスポート")
    parser.add_argument("--year", type=int, default=2026, help="対象年（1/1 起点）")
    parser.add_argument("--end-date", default=None, help="終了日 YYYY-MM-DD（省略時は年末）")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--encoding", default="utf8", choices=["utf8", "sjis"])
    parser.add_argument("--connect-cdp", default=None)
    parser.add_argument("--login-method", choices=["email", "google"], default="email")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument(
        "--retries",
        type=int,
        default=1,
        help="ネットワーク一時障害時の goto 再試行回数（既定1）",
    )
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
        # ensure_logged_in 前に HOME へ再試行付きで到達
        try:
            _goto_with_retries(page, zaim.ZAIM_HOME, retries=args.retries)
        except Exception as e:
            print(f"# goto home failed: {e}", file=sys.stderr)
            if browser and not args.connect_cdp:
                browser.close()
            return 1
        zaim.ensure_logged_in(
            page,
            login_method=args.login_method,
        )
        print(f"▶ CSV ダウンロード: {start} 〜 {end} ({args.encoding})")
        tmp = export_csv(page, start, end, args.encoding, login_method=args.login_method)
        shutil.copy2(tmp, dest)
        zaim.save_storage_state(ctx)
        if browser and not args.connect_cdp:
            browser.close()

    # OneDrive 直後の読取 deadlock 回避（短い再試行）
    text = ""
    for attempt in range(4):
        try:
            text = dest.read_text(encoding="utf-8", errors="replace")
            break
        except OSError as e:
            if getattr(e, "errno", None) != 11 or attempt >= 3:
                raise
            import time

            time.sleep(1.5 * (attempt + 1))
    lines = text.count("\n")
    print(f"✅ 保存: {dest}")
    print(f"   行数: {lines:,}（ヘッダ含む）")
    if lines > 1:
        print(f"   先頭データ行: {text.splitlines()[1][:80]}...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
