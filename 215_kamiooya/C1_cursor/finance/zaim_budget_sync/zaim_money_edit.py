#!/usr/bin/env python3
"""
Web版 Zaim で家計明細の「集計に含める／含めない」を変更する。

既存ログイン: zaim_budget_apply.py の storage / open_browser_context を再利用。

  cd ~/git-repos/215_kamiooya/C1_cursor/finance/zaim_budget_sync
  python zaim_money_edit.py --from-watch --dry-run
  python zaim_money_edit.py --from-watch --apply --yes
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import Page

import zaim_budget_apply as zaim

SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parents[3]  # .../git-repos (finance -> C1 -> 215 -> git-repos)
# SCRIPT_DIR = .../finance/zaim_budget_sync
# parents[0]=finance, [1]=C1_cursor, [2]=215_kamiooya, [3]=git-repos
WATCH_PATH = REPO / ".jarvis_state" / "zaim_quality_watch.json"
MONEY_URL = "https://zaim.net/money"
SCREENSHOT_DIR = SCRIPT_DIR / "screenshots" / "money_edit"

VALUE_MAP = {
    "exclude": "exclude",
    "include": "include",
    "含めない": "exclude",
    "含める": "include",
    "集計に含めない": "exclude",
    "常に集計に含める": "include",
}


def load_actions_from_watch(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    actions = list(data.get("proposed_actions") or [])
    # also samples with action
    for s in data.get("samples") or []:
        a = s.get("action")
        if a and a not in actions:
            actions.append(a)
    # dedupe by date+amount+value+target
    seen: set[tuple] = set()
    out: list[dict[str, Any]] = []
    for a in actions:
        if not a or a.get("action") != "set_aggregate":
            continue
        if a.get("target") == "swap_hint":
            continue
        key = (
            str(a.get("date")),
            round(float(a.get("amount") or 0), 0),
            str(a.get("value")),
            str(a.get("target")),
            str(a.get("shop") or "")[:20],
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(a)
    return out


def print_dry_run(actions: list[dict[str, Any]]) -> None:
    print(f"# dry-run {len(actions)} actions")
    for i, a in enumerate(actions, 1):
        print(
            f"  {i}. {a.get('date')} ¥{float(a.get('amount') or 0):,.0f} "
            f"shop={str(a.get('shop') or '')[:30]} → {a.get('value')} "
            f"(target={a.get('target')}) pay={str(a.get('pay') or '')[:24]}"
        )


def _goto_day(page: Page, day: str) -> None:
    # day: YYYY-MM-DD
    y, m, d = day.split("-")
    url = f"{MONEY_URL}?start_date={day}&end_date={day}"
    page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(1500)
    # fallback: calendar style
    if "login" in page.url or "id.zaim.net" in page.url:
        raise RuntimeError(f"未ログイン: {page.url}")


def _find_and_open_row(page: Page, amount: float, shop: str) -> bool:
    """明細行をクリックして編集を開く。成功で True。"""
    amt_int = int(round(amount))
    # 金額テキストのゆれ
    patterns = [
        f"{amt_int:,}",
        str(amt_int),
        f"-{amt_int:,}",
        f"¥{amt_int:,}",
    ]
    shop_frag = (shop or "").strip()
    if len(shop_frag) > 12:
        shop_frag = shop_frag[:12]

    # list items / table rows
    candidates = page.locator("a, tr, li, div").filter(has_text=re.compile(str(amt_int)))
    n = min(candidates.count(), 40)
    for i in range(n):
        el = candidates.nth(i)
        try:
            text = el.inner_text(timeout=500)
        except Exception:
            continue
        if str(amt_int) not in text.replace(",", ""):
            # allow formatted
            if f"{amt_int:,}" not in text:
                continue
        if shop_frag and shop_frag not in text and shop_frag[:6] not in text:
            # still try if amount unique
            pass
        try:
            el.click(timeout=2000)
            page.wait_for_timeout(800)
            return True
        except Exception:
            continue
    # try link with money edit
    for pat in patterns:
        loc = page.get_by_text(pat, exact=False)
        if loc.count() == 0:
            continue
        try:
            loc.first.click(timeout=2000)
            page.wait_for_timeout(800)
            return True
        except Exception:
            continue
    return False


def _set_aggregate_in_dialog(page: Page, value: str) -> bool:
    """
    編集 UI で集計フラグを設定。
    Zaim は『集計に含めない』チェック／トグルが多い。
    value: include | exclude
    """
    want_exclude = value == "exclude"
    # checkbox labels
    labels = [
        "集計に含めない",
        "集計から除外",
        "合計に含めない",
        "この支出を集計に含めない",
    ]
    for lab in labels:
        loc = page.get_by_text(lab, exact=False)
        if loc.count() == 0:
            continue
        # find associated checkbox
        box = page.locator(
            f'label:has-text("{lab}") input[type="checkbox"], '
            f'input[type="checkbox"][name*="exclude"], '
            f'input[type="checkbox"][id*="exclude"]'
        )
        try:
            if box.count() > 0:
                checked = box.first.is_checked()
                if want_exclude and not checked:
                    box.first.check()
                elif not want_exclude and checked:
                    box.first.uncheck()
                return True
            # click label to toggle
            loc.first.click()
            page.wait_for_timeout(300)
            return True
        except Exception:
            continue

    # select option
    sel = page.locator("select").filter(has_text=re.compile("集計"))
    if sel.count() > 0:
        try:
            if want_exclude:
                sel.first.select_option(label=re.compile("含めない"))
            else:
                sel.first.select_option(label=re.compile("含める"))
            return True
        except Exception:
            pass
    return False


def _save_dialog(page: Page) -> bool:
    for text in ("変更", "保存", "更新", "OK", "完了"):
        btn = page.get_by_role("button", name=re.compile(text))
        if btn.count() > 0:
            try:
                btn.first.click(timeout=3000)
                page.wait_for_timeout(1000)
                return True
            except Exception:
                continue
    inp = page.locator('input[type="submit"]')
    if inp.count() > 0:
        try:
            inp.first.click()
            page.wait_for_timeout(1000)
            return True
        except Exception:
            pass
    return False


def apply_one(page: Page, action: dict[str, Any], *, shot_prefix: str) -> tuple[bool, str]:
    day = str(action.get("date") or "")
    amount = float(action.get("amount") or 0)
    shop = str(action.get("shop") or "")
    raw_val = str(action.get("value") or "exclude")
    value = VALUE_MAP.get(raw_val, raw_val)
    if value not in ("include", "exclude"):
        return False, f"unknown value={raw_val}"

    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        _goto_day(page, day)
    except Exception as e:
        page.screenshot(path=str(SCREENSHOT_DIR / f"{shot_prefix}_nav_fail.png"))
        return False, f"nav: {e}"

    if not _find_and_open_row(page, amount, shop):
        page.screenshot(path=str(SCREENSHOT_DIR / f"{shot_prefix}_row_fail.png"), full_page=True)
        return False, "明細行が見つからない／クリックできない"

    if not _set_aggregate_in_dialog(page, value):
        page.screenshot(path=str(SCREENSHOT_DIR / f"{shot_prefix}_agg_fail.png"), full_page=True)
        return False, "集計設定コントロールが見つからない（UI要調整）"

    if not _save_dialog(page):
        page.screenshot(path=str(SCREENSHOT_DIR / f"{shot_prefix}_save_fail.png"), full_page=True)
        return False, "保存ボタンが見つからない"

    page.screenshot(path=str(SCREENSHOT_DIR / f"{shot_prefix}_ok.png"), full_page=True)
    return True, "ok"


def run_apply(actions: list[dict[str, Any]], args: argparse.Namespace) -> int:
    if not actions:
        print("# no actions", file=sys.stderr)
        return 0
    if args.dry_run:
        print_dry_run(actions)
        return 0
    if not args.apply:
        print("--apply を付けてください（先に --dry-run 推奨）", file=sys.stderr)
        return 1
    if not args.yes:
        print("確認: --yes が必要です", file=sys.stderr)
        return 1
    if not args.connect_cdp and not zaim.STORAGE_STATE.exists():
        print(
            f"先に zaim_budget_apply.py --login: {zaim.STORAGE_STATE}",
            file=sys.stderr,
        )
        return 1

    from playwright.sync_api import sync_playwright

    ok_n = fail_n = 0
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
            email=args.login_email,
            password=args.login_password,
            google_email=args.google_email,
            login_method=args.login_method,
            manual=False,
        )
        limit = args.limit if args.limit and args.limit > 0 else len(actions)
        for i, action in enumerate(actions[:limit]):
            print(f"▶ {i+1}/{limit} {action.get('date')} ¥{action.get('amount')} → {action.get('value')}")
            ok, msg = apply_one(page, action, shot_prefix=f"{i+1:02d}")
            print(f"  {'OK' if ok else 'NG'}: {msg}")
            if ok:
                ok_n += 1
            else:
                fail_n += 1
            time.sleep(0.8)
        zaim.save_storage_state(ctx)
        if browser and not args.connect_cdp:
            browser.close()
    print(f"# done ok={ok_n} fail={fail_n} shots={SCREENSHOT_DIR}")
    return 0 if fail_n == 0 else 2


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Zaim 明細の集計設定を Web で変更")
    ap.add_argument("--from-watch", action="store_true", help="zaim_quality_watch.json の提案を使う")
    ap.add_argument("--watch", type=Path, default=WATCH_PATH)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--limit", type=int, default=5, help="1回の最大件数（安全弁）")
    ap.add_argument("--connect-cdp", default=None)
    ap.add_argument("--login-method", choices=["email", "google"], default="email")
    ap.add_argument("--login-email", default=zaim.DEFAULT_LOGIN_EMAIL)
    ap.add_argument("--login-password", default=zaim.DEFAULT_LOGIN_PASSWORD)
    ap.add_argument("--google-email", default=zaim.DEFAULT_GOOGLE_EMAIL)
    ap.add_argument("--headless", action="store_true")
    # single shot
    ap.add_argument("--date", default=None, help="YYYY-MM-DD")
    ap.add_argument("--amount", type=float, default=None)
    ap.add_argument("--shop", default="")
    ap.add_argument("--value", default="exclude", help="include|exclude")
    args = ap.parse_args(argv)

    actions: list[dict[str, Any]] = []
    if args.from_watch:
        actions = load_actions_from_watch(args.watch)
    elif args.date and args.amount is not None:
        actions = [
            {
                "action": "set_aggregate",
                "date": args.date,
                "amount": args.amount,
                "shop": args.shop,
                "value": args.value,
                "target": "manual",
            }
        ]
    else:
        print("--from-watch か --date/--amount を指定してください", file=sys.stderr)
        return 1

    return run_apply(actions, args)


if __name__ == "__main__":
    raise SystemExit(main())
