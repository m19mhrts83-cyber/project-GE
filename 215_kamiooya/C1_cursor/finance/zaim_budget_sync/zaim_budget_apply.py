#!/usr/bin/env python3
"""
Numbers 中間 CSV → Web版 Zaim「月ごと・カテゴリ別」予算反映。

使い方:
  # 1) Numbers から CSV 生成
  python numbers_budget_extract.py --year 2026

  # 2) 反映プレビュー
  python zaim_budget_apply.py --csv budget_2026.csv --dry-run

  # 3) 初回ログイン（セッション保存）
  python zaim_budget_apply.py --login

  # 4) 1ヶ月だけ試験反映
  python zaim_budget_apply.py --csv budget_2026.csv --month 2026-01 --apply --yes

  # 5) 年間一括
  python zaim_budget_apply.py --csv budget_2026.csv --year 2026 --apply --yes
"""

from __future__ import annotations

import argparse
import csv
import os
import socket
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CSV = SCRIPT_DIR / "budget_2026.csv"
STORAGE_STATE = SCRIPT_DIR / ".zaim_storage_state.json"
SCREENSHOT_DIR = SCRIPT_DIR / "screenshots"
CHROME_PROFILE_DIR = SCRIPT_DIR / ".zaim-chrome-profile"
ZAIM_HOME = "https://zaim.net/home"
ZAIM_LOGIN = "https://id.zaim.net/"
ZAIM_BUDGET_MONTH_URL = "https://zaim.net/budgets/detail/{ym}"
DEFAULT_CDP_URL = "http://127.0.0.1:9223"
DEFAULT_CDP_PORT = 9223
DEFAULT_GOOGLE_EMAIL = os.environ.get("ZAIM_GOOGLE_EMAIL", "m19m.hrts83@gmail.com")
DEFAULT_LOGIN_EMAIL = os.environ.get("ZAIM_LOGIN_EMAIL", DEFAULT_GOOGLE_EMAIL)
DEFAULT_LOGIN_PASSWORD = os.environ.get("ZAIM_PASSWORD", "")
LOGIN_WAIT_MS = 300_000  # 手動完了待ち（5分）
EMAIL_LOGIN_ATTEMPTS = 2  # 手動検証: 同一資格情報を2回入力する必要あり


def load_budget_csv(csv_path: Path) -> list[dict]:
    rows: list[dict] = []
    with csv_path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append(
                {
                    "year": int(row["year"]),
                    "month": int(row["month"]),
                    "category_key": row["category_key"].strip(),
                    "amount_yen": int(row["amount_yen"]),
                }
            )
    return rows


def filter_rows(rows: list[dict], year: int | None, month: str | None) -> list[dict]:
    if month:
        y, m = map(int, month.split("-"))
        return [r for r in rows if r["year"] == y and r["month"] == m]
    if year:
        return [r for r in rows if r["year"] == year]
    return rows


def group_by_month(rows: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        key = f"{r['year']:04d}-{r['month']:02d}"
        grouped[key].append(r)
    return dict(sorted(grouped.items()))


def print_dry_run(grouped: dict[str, list[dict]]) -> None:
    total = 0
    for ym, items in grouped.items():
        subtotal = sum(i["amount_yen"] for i in items)
        total += subtotal
        print(f"\n=== {ym} ({len(items)} カテゴリ, 合計 {subtotal:,} 円) ===")
        for item in sorted(items, key=lambda x: x["category_key"]):
            print(f"  {item['category_key']:40s} {item['amount_yen']:>10,} 円")
    print(f"\n📊 全体: {len(grouped)} ヶ月, {sum(len(v) for v in grouped.values())} 行, 合計 {total:,} 円")


def is_login_page(page: Page) -> bool:
    url = page.url
    if "id.zaim.net" in url or "user_session" in url or "sign_in" in url:
        return True
    return page.locator('a:has-text("Google でログイン"), a:has-text("利用規約に同意して Google でログイン")').count() > 0


def is_authenticated(page: Page) -> bool:
    url = page.url
    if "id.zaim.net" in url or "user_session" in url or "sign_in" in url:
        return False
    if "accounts.google.com" in url:
        return False
    if "zaim.net/home" in url:
        return True
    if url.rstrip("/") == "https://zaim.net":
        return True
    return page.locator('text="HOME"').count() > 0


def wait_for_authenticated(page: Page, timeout_ms: int = LOGIN_WAIT_MS) -> None:
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        if is_authenticated(page):
            page.wait_for_timeout(1000)
            return
        page.wait_for_timeout(1000)
    page.screenshot(path=str(SCREENSHOT_DIR / "login_timeout.png"), full_page=True)
    raise TimeoutError(f"ログイン完了を待ちましたが HOME に到達しませんでした: {page.url}")


def submit_email_login_once(page: Page, email: str, password: str) -> None:
    email_box = page.locator(
        'input[name="email"], input[type="email"], input[placeholder*="メール"], input[placeholder*="メールアドレス"]'
    ).first
    pass_box = page.locator('input[name="password"], input[type="password"]').first
    email_box.wait_for(state="visible", timeout=15_000)
    email_box.fill("")
    email_box.fill(email)
    pass_box.fill("")
    pass_box.fill(password)
    page.locator('button:has-text("ログイン"), input[type="submit"][value="ログイン"]').first.click()
    page.wait_for_timeout(2500)


def login_with_email_password(page: Page, email: str, password: str) -> None:
    page.goto(ZAIM_LOGIN, wait_until="domcontentloaded")
    page.wait_for_timeout(1500)
    if is_authenticated(page):
        return
    if not password:
        raise RuntimeError("ZAIM_PASSWORD が未設定です (.env.jarvis_private)")

    for attempt in range(1, EMAIL_LOGIN_ATTEMPTS + 1):
        if is_authenticated(page):
            return
        if is_login_page(page) or page.locator('input[type="password"]').count():
            print(f"  メールログイン試行 {attempt}/{EMAIL_LOGIN_ATTEMPTS}...")
            submit_email_login_once(page, email, password)
        else:
            break

    wait_for_authenticated(page)


def wait_for_manual_login(page: Page, email: str) -> None:
    page.goto(ZAIM_LOGIN, wait_until="domcontentloaded")
    print("=" * 60)
    print("  Zaim 手動ログイン")
    print(f"  アカウント: {email}")
    print("  1. メールアドレスとパスワードを入力 → ログイン")
    print("  2. もう一度入力画面が出たら、同じ内容を再入力 → ログイン")
    print("     （2回目の入力は Zaim 側の仕様です）")
    print("  3. HOME が表示されるまで待機します")
    print("=" * 60)
    wait_for_authenticated(page)


def _chrome_executable() -> str:
    return "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def _cdp_port(cdp_url: str) -> int:
    from urllib.parse import urlparse

    parsed = urlparse(cdp_url)
    return parsed.port or DEFAULT_CDP_PORT


def _is_cdp_ready(port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            s.connect(("127.0.0.1", port))
        return True
    except OSError:
        return False


def start_chrome_for_cdp(port: int = DEFAULT_CDP_PORT) -> subprocess.Popen:
    CHROME_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    chrome = _chrome_executable()
    if not Path(chrome).exists():
        raise RuntimeError(f"Chrome が見つかりません: {chrome}")

    if _is_cdp_ready(port):
        print(f"📎 既存の CDP Chrome (port {port}) を利用します")
        return None  # type: ignore[return-value]

    args = [
        chrome,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={CHROME_PROFILE_DIR}",
        "--no-first-run",
        "--no-default-browser-check",
        ZAIM_LOGIN,
    ]
    print(f"📎 Chrome を CDP モードで起動します (port {port})...")
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    for _ in range(40):
        if _is_cdp_ready(port):
            time.sleep(1)
            return proc
        time.sleep(0.5)
    proc.kill()
    raise RuntimeError(f"Chrome が port {port} で起動しませんでした")


def open_browser_context(
    pw,
    *,
    headless: bool,
    connect_cdp: str | None,
    storage_state: Path | None,
) -> tuple[Browser | None, BrowserContext, subprocess.Popen | None]:
    chrome_proc = None
    if connect_cdp:
        port = _cdp_port(connect_cdp)
        chrome_proc = start_chrome_for_cdp(port)
        browser = pw.chromium.connect_over_cdp(connect_cdp)
        ctx = browser.contexts[0] if browser.contexts else browser.new_context(locale="ja-JP")
        return browser, ctx, chrome_proc

    browser = pw.chromium.launch(
        headless=headless,
        channel="chrome",
        args=["--disable-blink-features=AutomationControlled"],
    )
    ctx_kwargs: dict = {"locale": "ja-JP"}
    if storage_state and storage_state.exists():
        ctx_kwargs["storage_state"] = str(storage_state)
    ctx = browser.new_context(**ctx_kwargs)
    return browser, ctx, chrome_proc


def get_work_page(ctx: BrowserContext) -> Page:
    for p in ctx.pages:
        if "zaim.net" in p.url or "id.zaim.net" in p.url:
            return p
    return ctx.new_page()


def start_google_login(page: Page, google_email: str) -> None:
    page.goto(ZAIM_LOGIN, wait_until="domcontentloaded")
    page.wait_for_timeout(1500)
    google_btn = page.locator(
        'a:has-text("Google でログイン"), a:has-text("利用規約に同意して Google でログイン")'
    ).first
    if google_btn.count() and google_btn.is_visible():
        google_btn.click()
        page.wait_for_timeout(2000)
    print("=" * 60)
    print("  Zaim ログイン（Google）")
    print(f"  アカウント: {google_email}")
    print("  ブラウザで Google ログインを完了してください。")
    print("=" * 60)


def ensure_logged_in(
    page: Page,
    email: str = DEFAULT_LOGIN_EMAIL,
    password: str = DEFAULT_LOGIN_PASSWORD,
    google_email: str = DEFAULT_GOOGLE_EMAIL,
    login_method: str = "email",
    manual: bool = False,
) -> None:
    page.goto(ZAIM_HOME, wait_until="domcontentloaded")
    page.wait_for_timeout(1500)
    if is_authenticated(page):
        return

    if manual:
        wait_for_manual_login(page, email)
    elif login_method == "email":
        login_with_email_password(page, email, password)
    else:
        start_google_login(page, google_email)
        wait_for_authenticated(page)


def click_first_visible(page: Page, selectors: list[str], wait_ms: int = 800) -> bool:
    for sel in selectors:
        loc = page.locator(sel).first
        if loc.count() and loc.is_visible():
            loc.click()
            page.wait_for_timeout(wait_ms)
            return True
    return False


def budget_detail_url(year: int, month: int) -> str:
    return ZAIM_BUDGET_MONTH_URL.format(ym=f"{year}{month:02d}")


def open_monthly_budget_page(page: Page, year: int, month: int) -> None:
    page.goto(budget_detail_url(year, month), wait_until="domcontentloaded")
    page.wait_for_timeout(2000)
    page.locator("input.budget-amount").first.wait_for(state="visible", timeout=20_000)


def select_year_month(page: Page, year: int, month: int) -> None:
    open_monthly_budget_page(page, year, month)


def set_category_amount(page: Page, category: str, amount: int) -> bool:
    """カテゴリ行の金額を設定。成功 True / 行なし False。"""
    row = page.locator("tr", has=page.locator(f"text={category}")).first
    if not row.count():
        # 括弧等を含むカテゴリ名向け
        short = category.split(".", 1)[-1] if "." in category else category
        row = page.locator("tr", has=page.locator(f"text={short}")).first
    if not row.count():
        return False

    inp = row.locator("input.budget-amount").first
    if not inp.count():
        return False
    inp.click()
    inp.fill(str(amount))
    return True


def click_update(page: Page) -> None:
    btn = page.locator('button:has-text("更新"), input[type="submit"][value="更新"]').first
    btn.wait_for(state="visible", timeout=10_000)
    btn.click()
    page.wait_for_timeout(2500)


def apply_month(page: Page, ym: str, items: list[dict], screenshot_dir: Path) -> tuple[int, list[str]]:
    year, month = map(int, ym.split("-"))
    open_monthly_budget_page(page, year, month)

    missing: list[str] = []
    updated = 0
    for item in items:
        ok = set_category_amount(page, item["category_key"], item["amount_yen"])
        if ok:
            updated += 1
        else:
            missing.append(item["category_key"])

    if updated:
        click_update(page)
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(screenshot_dir / f"budget_{ym}.png"), full_page=True)
    return updated, missing


def save_storage_state(ctx: BrowserContext) -> None:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    ctx.storage_state(path=str(STORAGE_STATE))
    print(f"✅ セッション保存: {STORAGE_STATE}")


def cmd_login(args: argparse.Namespace) -> int:
    with sync_playwright() as pw:
        browser, ctx, chrome_proc = open_browser_context(
            pw,
            headless=args.headless,
            connect_cdp=args.connect_cdp,
            storage_state=None,
        )
        page = get_work_page(ctx)
        ensure_logged_in(
            page,
            email=args.login_email,
            password=args.login_password,
            google_email=args.google_email,
            login_method=args.login_method,
            manual=args.manual_login,
        )
        save_storage_state(ctx)
        if browser and not args.connect_cdp:
            browser.close()
        elif args.connect_cdp:
            print("📎 CDP Chrome は起動したままです（次の apply でも --connect-cdp を使えます）")
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    rows = load_budget_csv(args.csv)
    rows = filter_rows(rows, args.year, args.month)
    grouped = group_by_month(rows)
    if not grouped:
        print("対象データがありません。", file=sys.stderr)
        return 1

    if args.dry_run:
        print_dry_run(grouped)
        return 0

    if not args.apply:
        print("本番反映には --apply を付けてください。", file=sys.stderr)
        return 1
    if not args.yes:
        print("確認: --yes を付けないと反映しません。", file=sys.stderr)
        return 1
    if not args.connect_cdp and not STORAGE_STATE.exists():
        print(f"先に --login でセッション保存するか、--connect-cdp を使ってください: {STORAGE_STATE}", file=sys.stderr)
        return 1

    with sync_playwright() as pw:
        browser, ctx, _chrome_proc = open_browser_context(
            pw,
            headless=args.headless,
            connect_cdp=args.connect_cdp,
            storage_state=STORAGE_STATE if not args.connect_cdp else None,
        )
        page = get_work_page(ctx)
        ensure_logged_in(
            page,
            email=args.login_email,
            password=args.login_password,
            google_email=args.google_email,
            login_method=args.login_method,
            manual=False,
        )

        for ym, items in grouped.items():
            print(f"▶ {ym} を反映中 ({len(items)} カテゴリ)...")
            updated, missing = apply_month(page, ym, items, SCREENSHOT_DIR)
            print(f"  更新 {updated}/{len(items)}")
            if missing:
                print(f"  ⚠️  UI上に見つからなかったカテゴリ: {', '.join(missing)}")
            time.sleep(1)

        save_storage_state(ctx)
        if browser and not args.connect_cdp:
            browser.close()

    print(f"✅ 完了。スクショ: {SCREENSHOT_DIR}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Zaim 月ごと予算反映")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--year", type=int, default=None)
    parser.add_argument("--month", default=None, help="YYYY-MM")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--login", action="store_true", help="ログインしてセッション保存")
    parser.add_argument("--manual-login", action="store_true", help="手動ログイン待ち（CDP推奨）")
    parser.add_argument("--connect-cdp", default=None, help=f"CDP接続URL（例: {DEFAULT_CDP_URL}）")
    parser.add_argument("--login-method", choices=["email", "google"], default="email")
    parser.add_argument("--login-email", default=DEFAULT_LOGIN_EMAIL)
    parser.add_argument("--login-password", default=DEFAULT_LOGIN_PASSWORD)
    parser.add_argument("--google-email", default=DEFAULT_GOOGLE_EMAIL, help="Google ログイン用メール")
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args(argv)

    if args.login:
        return cmd_login(args)

    if not args.csv.exists():
        print(f"CSV がありません: {args.csv}\n先に numbers_budget_extract.py を実行してください。", file=sys.stderr)
        return 1

    return cmd_apply(args)


if __name__ == "__main__":
    raise SystemExit(main())
