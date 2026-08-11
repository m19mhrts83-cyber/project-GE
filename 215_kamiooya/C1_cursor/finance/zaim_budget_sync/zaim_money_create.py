#!/usr/bin/env python3
"""Web版 Zaim に明細を1件登録する（あかつき週次など）。

過去実績（2026-04-15 CSV）:
  payment / α.B.C.投資 / 外国債減収 / あかつき証券 / 集計に含めない

  python zaim_money_create.py --dry-run --kind payment --amount 50944 \\
    --account あかつき証券 --category 'α.B.C.投資' --genre 外国債減収 --exclude
  python zaim_money_create.py --apply --yes --kind payment --amount 100 \\
    --account あかつき証券 --category 'α.B.C.投資' --genre 外国債減収 --exclude
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import Page

import zaim_budget_apply as zaim

SCRIPT_DIR = Path(__file__).resolve().parent
SHOT_DIR = SCRIPT_DIR / "screenshots" / "money_create"
MONEY_URL = "https://zaim.net/money"


def _shot(page: Page, name: str) -> None:
    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(SHOT_DIR / f"{name}.png"), full_page=True)


def _open_new_form(page: Page, kind: str) -> None:
    page.goto(MONEY_URL, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(1500)
    if "login" in page.url or "id.zaim.net" in page.url:
        raise RuntimeError(f"未ログイン: {page.url}")

    opened = False
    for sel in (
        'a[href*="/money/new"]',
        'button:has-text("入力")',
        'a:has-text("入力")',
        'button:has-text("支出を記録")',
        '[aria-label="入力"]',
        "button.plus, a.plus, .money-plus",
    ):
        loc = page.locator(sel)
        if loc.count() == 0:
            continue
        try:
            loc.first.click(timeout=3000)
            page.wait_for_timeout(800)
            opened = True
            break
        except Exception:
            continue
    if not opened:
        page.goto("https://zaim.net/money/new", wait_until="domcontentloaded")
        page.wait_for_timeout(1200)

    tab = "支出" if kind == "payment" else "収入" if kind == "income" else "振替"
    tab_loc = page.get_by_role("tab", name=re.compile(tab))
    if tab_loc.count() == 0:
        tab_loc = page.get_by_text(tab, exact=True)
    if tab_loc.count() > 0:
        try:
            tab_loc.first.click(timeout=3000)
            page.wait_for_timeout(400)
        except Exception:
            pass


def _fill_date(page: Page, day: str) -> None:
    y, m, d = day.split("-")
    for sel in (
        'input[name="date"]',
        'input[type="date"]',
        'input[name*="date"]',
    ):
        loc = page.locator(sel)
        if loc.count() == 0:
            continue
        try:
            loc.first.fill(day)
            return
        except Exception:
            try:
                loc.first.fill(f"{y}/{m}/{d}")
                return
            except Exception:
                continue


def _fill_amount(page: Page, amount: int) -> None:
    loc = page.locator(
        'input[name="amount"], input[name="price"], input[inputmode="numeric"], '
        'input[type="tel"], input[placeholder*="金額"]'
    )
    if loc.count() == 0:
        raise RuntimeError("金額欄が見つかりません")
    loc.first.fill(str(amount))


def _pick_by_text(page: Page, label: str) -> bool:
    if not label:
        return False
    candidates = [
        page.get_by_role("option", name=re.compile(re.escape(label))),
        page.get_by_text(label, exact=True),
        page.get_by_text(label, exact=False),
    ]
    for loc in candidates:
        if loc.count() == 0:
            continue
        try:
            loc.first.click(timeout=2500)
            page.wait_for_timeout(300)
            return True
        except Exception:
            continue
    return False


def _open_select(page: Page, names: list[str]) -> bool:
    for name in names:
        loc = page.locator(
            f'label:has-text("{name}"), [aria-label*="{name}"], '
            f'button:has-text("{name}"), select[name*="{name}"]'
        )
        if loc.count() == 0:
            continue
        try:
            loc.first.click(timeout=2000)
            page.wait_for_timeout(400)
            return True
        except Exception:
            continue
    return False


def _pick_category(page: Page, category: str, genre: str) -> None:
    _open_select(page, ["カテゴリ", "分類", "category"])
    if category and not _pick_by_text(page, category):
        short = category.split(".")[-1] if "." in category else category
        if not _pick_by_text(page, short):
            raise RuntimeError(f"カテゴリが見つかりません: {category}")
    if genre:
        _open_select(page, ["内訳", "ジャンル", "genre"])
        if not _pick_by_text(page, genre):
            raise RuntimeError(f"内訳が見つかりません: {genre}")


def _pick_account(page: Page, account: str, *, kind: str) -> None:
    labels = ["口座", "支払元", "出金元"] if kind == "payment" else ["口座", "入金先", "入金元"]
    _open_select(page, labels)
    if not _pick_by_text(page, account):
        raise RuntimeError(f"口座が見つかりません: {account}")


def _set_exclude(page: Page, exclude: bool) -> None:
    if not exclude:
        return
    for lab in ("集計に含めない", "集計から除外", "この支出を集計に含めない", "この収入を集計に含めない"):
        loc = page.get_by_text(lab, exact=False)
        if loc.count() == 0:
            continue
        box = page.locator(
            f'label:has-text("{lab}") input[type="checkbox"], input[type="checkbox"]'
        )
        try:
            if box.count() > 0 and not box.first.is_checked():
                box.first.check()
                return
            loc.first.click()
            return
        except Exception:
            continue


def _fill_comment(page: Page, comment: str) -> None:
    if not comment:
        return
    loc = page.locator(
        'textarea[name="comment"], input[name="comment"], textarea[placeholder*="メモ"], '
        'input[placeholder*="品目"], input[name="name"]'
    )
    if loc.count() > 0:
        try:
            loc.first.fill(comment[:80])
        except Exception:
            pass


def _submit(page: Page) -> None:
    for text in ("登録", "保存", "完了", "入力する"):
        btn = page.get_by_role("button", name=re.compile(text))
        if btn.count() == 0:
            btn = page.locator(f'input[type="submit"][value*="{text}"]')
        if btn.count() == 0:
            continue
        btn.first.click(timeout=4000)
        page.wait_for_timeout(1500)
        return
    raise RuntimeError("登録ボタンが見つかりません")


def create_money(
    page: Page,
    *,
    kind: str,
    amount: int,
    day: str,
    account: str,
    category: str,
    genre: str,
    comment: str,
    exclude: bool,
) -> None:
    _open_new_form(page, kind)
    _fill_date(page, day)
    _fill_amount(page, amount)
    _pick_category(page, category, genre)
    _pick_account(page, account, kind=kind)
    _set_exclude(page, exclude)
    _fill_comment(page, comment)
    _shot(page, "before_submit")
    _submit(page)
    _shot(page, "after_submit")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Zaim 明細を1件登録")
    ap.add_argument("--kind", choices=["payment", "income"], required=True)
    ap.add_argument("--amount", type=int, required=True)
    ap.add_argument("--date", default="", help="YYYY-MM-DD（省略時は今日）")
    ap.add_argument("--account", required=True)
    ap.add_argument("--category", default="")
    ap.add_argument("--genre", default="")
    ap.add_argument("--comment", default="")
    ap.add_argument("--exclude", action="store_true", help="集計に含めない")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--connect-cdp", default=None)
    ap.add_argument("--login-method", choices=["email", "google"], default="email")
    args = ap.parse_args(argv)

    day = args.date or __import__("datetime").date.today().isoformat()
    print(
        f"# zaim_money_create {args.kind} {day} ¥{args.amount:,} "
        f"acct={args.account} cat={args.category}/{args.genre} exclude={args.exclude}"
    )
    if args.dry_run:
        print("# dry-run: Zaim には書きません")
        return 0
    if not args.apply or not args.yes:
        print("--apply --yes が必要です（先に --dry-run）", file=sys.stderr)
        return 1

    from playwright.sync_api import sync_playwright

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
            email=zaim.DEFAULT_LOGIN_EMAIL,
            password=zaim.DEFAULT_LOGIN_PASSWORD,
            google_email=zaim.DEFAULT_GOOGLE_EMAIL,
            login_method=args.login_method,
            manual=False,
        )
        try:
            create_money(
                page,
                kind=args.kind,
                amount=args.amount,
                day=day,
                account=args.account,
                category=args.category,
                genre=args.genre,
                comment=args.comment,
                exclude=args.exclude,
            )
        except Exception as exc:
            _shot(page, "fail")
            print(f"登録失敗: {exc}", file=sys.stderr)
            zaim.save_storage_state(ctx)
            if browser and not args.connect_cdp:
                browser.close()
            return 1
        zaim.save_storage_state(ctx)
        if browser and not args.connect_cdp:
            browser.close()
    print(f"# ok shots={SHOT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
