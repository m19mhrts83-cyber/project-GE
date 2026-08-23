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


def _dismiss_overlays(page: Page) -> None:
    """電卓・ComboBox が次のクリックを奪うので閉じる。"""
    for _ in range(3):
        calc = page.locator('[class*="Calculator-module"], [class*="calculator"]')
        visible = False
        try:
            visible = calc.count() > 0 and calc.first.is_visible()
        except Exception:
            visible = False
        if not visible:
            break
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass
        page.wait_for_timeout(150)
        # 確定っぽいボタンがあれば押す
        for lab in ("確定", "OK", "完了", "="):
            btn = page.locator(
                f'[class*="Calculator"] button:has-text("{lab}"), '
                f'[class*="calculator"] button:has-text("{lab}")'
            )
            try:
                if btn.count() and btn.first.is_visible():
                    btn.first.click(timeout=800)
                    page.wait_for_timeout(150)
                    break
            except Exception:
                pass
    try:
        page.keyboard.press("Escape")
    except Exception:
        pass
    page.wait_for_timeout(100)


def _fill_amount(page: Page, amount: int) -> None:
    """新UI ItemForm の readonly 金額（電卓）を確実に入れる。"""
    loc = page.locator('input[name="amount"]')
    if loc.count() == 0:
        raise RuntimeError("金額欄が見つかりません")
    el = loc.first
    target = str(amount)

    def _norm(s: str) -> str:
        return (s or "").replace(",", "").replace("¥", "").replace("￥", "").strip()

    el.click(timeout=5000)
    page.wait_for_timeout(500)
    # 電卓の結果欄に入る（amount 本体は確定まで 0 のまま）
    page.keyboard.type(target, delay=45)
    page.wait_for_timeout(200)
    page.keyboard.press("Enter")
    page.wait_for_timeout(350)
    got = _norm(el.input_value())
    if got != target:
        # 確定ボタン
        conf = page.locator('[class*="Calculator-module__fixBtn"]')
        if conf.count():
            try:
                conf.first.click(timeout=1500)
                page.wait_for_timeout(300)
            except Exception:
                pass
        got = _norm(el.input_value())
    if got != target:
        raise RuntimeError(f"金額を入力できませんでした（表示={got!r} 期待={target}）")
    # Escape で電卓を閉じる（金額は確定済み）
    try:
        page.keyboard.press("Escape")
    except Exception:
        pass
    page.wait_for_timeout(150)


def _pick_row_category(page: Page, category: str, genre: str) -> bool:
    """1行目のカテゴリ欄（品目行の2列目・nameなし input）を ComboBox 入力。"""
    _dismiss_overlays(page)
    # 品目行: item_name の右隣がカテゴリ
    row_cat = page.locator(
        'input.ItemForm-module__itemInput___2DX3K:not([name]), '
        'input[class*="ItemForm-module__itemInput"]:not([name="item_name"]):not([name="comment"]):not([name="amount"])'
    )
    # より堅牢: 最初の行ブロック内の name 空 text
    if row_cat.count() == 0:
        row_cat = page.locator('input[type="text"][name=""]').first
    else:
        row_cat = row_cat.first
    try:
        if not row_cat.count() and page.locator('input[type="text"][name=""]').count():
            row_cat = page.locator('input[type="text"][name=""]').first
        row_cat.click(force=True, timeout=3000)
        page.wait_for_timeout(200)
        row_cat.fill("")
        row_cat.type(category, delay=35)
        page.wait_for_timeout(500)
        if not _pick_combobox_suggestion(page, category):
            return False
    except Exception:
        return False
    if not genre:
        return True
    page.wait_for_timeout(300)
    # 内訳が別 ComboBox になる場合
    try:
        page.keyboard.type(genre, delay=35)
        page.wait_for_timeout(450)
        return _pick_combobox_suggestion(page, genre)
    except Exception:
        return _pick_category_batch_overwrite(page, category, genre)


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


def _select_native(page: Page, label: str, *, index: int | None = None) -> bool:
    """Zaim のカテゴリ／口座／集計は hidden な <select>。JS で value を入れる。"""
    if not label:
        return False
    found = page.evaluate(
        """([q, idx]) => {
          const norm = (t) => (t || '').replace(/\\s+/g, '');
          const qn = norm(q);
          const selects = [...document.querySelectorAll('select')];
          const list = (idx === null || idx === undefined) ? selects : [selects[idx]].filter(Boolean);
          const tryMatch = (pred) => {
            for (const s of list) {
              for (const o of s.options) {
                const t = (o.text || '').trim();
                if (!pred(t)) continue;
                const desc = Object.getOwnPropertyDescriptor(
                  window.HTMLSelectElement.prototype, 'value'
                );
                if (desc && desc.set) desc.set.call(s, o.value);
                else s.value = o.value;
                s.dispatchEvent(new Event('input', { bubbles: true }));
                s.dispatchEvent(new Event('change', { bubbles: true }));
                return t;
              }
            }
            return null;
          };
          // exact → 空白無視 exact → 一意の部分一致（Bloomo vs bloomo証券 など）
          return (
            tryMatch((t) => t === q || norm(t) === qn) ||
            tryMatch((t) => {
              const tn = norm(t);
              if (!qn || qn.length < 3) return false;
              if (!(tn.includes(qn) || qn.includes(tn))) return false;
              const hits = list.flatMap((s) => [...s.options].map((o) => norm(o.text || '')))
                .filter((x) => x && (x.includes(qn) || qn.includes(x)));
              return new Set(hits).size === 1;
            })
          );
        }""",
        [label, index],
    )
    if found:
        page.wait_for_timeout(200)
        return True
    return False


def _open_select(page: Page, names: list[str]) -> bool:
    for name in names:
        loc = page.locator(
            f'label:has-text("{name}"), [aria-label*="{name}"], '
            f'button:has-text("{name}"), select[name*="{name}"]'
        )
        if loc.count() > 0:
            try:
                loc.first.click(timeout=2000)
                page.wait_for_timeout(400)
                return True
            except Exception:
                pass
        # 新UI: 「カテゴリ」ラベルの右の値（現在の分類名）をクリック
        label = page.get_by_text(name, exact=True)
        if label.count() == 0:
            continue
        try:
            opened = label.first.evaluate(
                """el => {
                  const row = el.closest(
                    '[class*="row"], [class*="Row"], [class*="Field"], [class*="Item"], li, tr'
                  ) || el.parentElement;
                  if (!row) { el.click(); return true; }
                  const value = row.querySelector(
                    'button, [role="button"], [class*="value"], [class*="Value"], select'
                  );
                  (value || row).click();
                  return true;
                }"""
            )
            if opened:
                page.wait_for_timeout(500)
                return True
        except Exception:
            try:
                label.first.click(timeout=2000)
                page.wait_for_timeout(400)
                return True
            except Exception:
                continue
    return False


def _filter_picker(page: Page, query: str) -> None:
    search = page.locator(
        'input[placeholder*="検索"], input[placeholder*="カテゴリ"], input[type="search"], '
        '[role="dialog"] input[type="text"], [class*="Modal"] input, [class*="Search"] input'
    )
    if search.count() == 0:
        return
    try:
        search.first.fill(query)
        page.wait_for_timeout(400)
    except Exception:
        pass


def _pick_combobox_suggestion(page: Page, query: str) -> bool:
    """開いている ComboBox 候補から query を選ぶ。"""
    if not query:
        return False
    # ラベル行（数字サフィックス付き "α.B.C.投資2501" 等も許容）
    cands = page.locator(
        '[class*="ComboBox-module__normalLabel"], '
        '[class*="ComboBox-module__flexWrapper"], '
        '[class*="ComboBox-module__element"]'
    )
    n = min(cands.count(), 80)
    for i in range(n):
        el = cands.nth(i)
        try:
            if not el.is_visible():
                continue
            txt = (el.inner_text() or "").strip().split("\n")[0]
            if not txt:
                continue
            if txt == query or txt.startswith(query):
                el.click(timeout=2000)
                page.wait_for_timeout(250)
                return True
        except Exception:
            continue
    if _pick_by_text(page, query):
        return True
    try:
        page.keyboard.press("ArrowDown")
        page.keyboard.press("Enter")
        page.wait_for_timeout(200)
        return True
    except Exception:
        return False


def _pick_category_batch_overwrite(page: Page, category: str, genre: str) -> bool:
    """新UI: 「全体のカテゴリ」の 全品目一括上書 ComboBox。"""
    _dismiss_overlays(page)
    box = page.locator('input[placeholder="全品目一括上書"]')
    if box.count() == 0:
        return False
    try:
        box.first.click(timeout=3000, force=True)
    except Exception:
        try:
            box.first.focus()
        except Exception:
            return False
    page.wait_for_timeout(200)
    try:
        box.first.fill("")
        box.first.type(category, delay=35)
    except Exception:
        page.keyboard.type(category, delay=35)
    page.wait_for_timeout(500)
    if not _pick_combobox_suggestion(page, category):
        return False
    if not genre:
        return True
    page.wait_for_timeout(300)
    # 内訳: 未分類コンボ or 同じ一括欄の続き
    un = page.get_by_text("未分類", exact=True)
    opened = False
    for i in range(min(un.count(), 6)):
        try:
            if un.nth(i).is_visible():
                un.nth(i).click(timeout=1500)
                opened = True
                break
        except Exception:
            continue
    if not opened:
        # 行内カテゴリ隣や追加 ComboBox
        extras = page.locator('input[class*="ComboBox-module__defaultInput"]')
        for i in range(extras.count()):
            el = extras.nth(i)
            try:
                if not el.is_visible():
                    continue
                ph = el.get_attribute("placeholder") or ""
                if "店" in ph or ph == "全品目一括上書":
                    continue
                el.click(force=True, timeout=1500)
                opened = True
                break
            except Exception:
                continue
    page.wait_for_timeout(200)
    try:
        page.keyboard.type(genre, delay=35)
    except Exception:
        pass
    page.wait_for_timeout(450)
    return _pick_combobox_suggestion(page, genre)


def _pick_category(page: Page, category: str, genre: str) -> None:
    _dismiss_overlays(page)
    if not category:
        return
    if _select_native(page, category) and (not genre or _select_native(page, genre)):
        return
    # 新UI優先: 品目行カテゴリ → 全体一括上書
    if _pick_row_category(page, category, genre):
        return
    if _pick_category_batch_overwrite(page, category, genre):
        return
    _open_select(page, ["カテゴリ", "分類", "category", "カテゴリ▼"])
    for q in (
        category,
        category.split(".")[-1] if "." in category else category,
        "B.C.投資" if "投資" in category else category,
    ):
        _filter_picker(page, q)
        if _pick_by_text(page, category) or _pick_combobox_suggestion(page, category):
            break
    else:
        raise RuntimeError(f"カテゴリが見つかりません: {category}")
    if genre:
        if _select_native(page, genre):
            return
        _open_select(page, ["内訳", "ジャンル", "genre", "未分類"])
        _filter_picker(page, genre)
        if not (
            _pick_by_text(page, genre) or _pick_combobox_suggestion(page, genre)
        ):
            raise RuntimeError(f"内訳が見つかりません: {genre}")


def _pick_account(page: Page, account: str, *, kind: str) -> None:
    _dismiss_overlays(page)
    if _select_native(page, account):
        return
    labels = (
        ["出金元", "口座", "支払元", "出金元"]
        if kind == "payment"
        else ["入金先", "口座", "入金元"]
    )
    _open_select(page, labels)
    # 出金元 ComboBox 入力
    for ph in ("口座を選択", "出金元", "入金先"):
        box = page.locator(f'input[placeholder*="{ph}"]')
        if box.count() == 0:
            continue
        try:
            if box.first.is_visible():
                box.first.click(force=True, timeout=2000)
                box.first.fill("")
                box.first.type(account, delay=30)
                page.wait_for_timeout(450)
                if _pick_combobox_suggestion(page, account):
                    return
        except Exception:
            continue
    if not (
        _pick_by_text(page, account) or _pick_combobox_suggestion(page, account)
    ):
        raise RuntimeError(f"口座が見つかりません: {account}")


def _set_exclude(page: Page, exclude: bool) -> None:
    if not exclude:
        return
    if _select_native(page, "常に含めない"):
        return
    for lab in (
        "常に含めない",
        "この収入を集計に含めない",
        "この支出を集計に含めない",
        "集計に含めない",
        "集計から除外",
    ):
        loc = page.get_by_text(lab, exact=True)
        if loc.count() == 0:
            loc = page.get_by_text(lab, exact=False)
        if loc.count() == 0:
            continue
        try:
            loc.first.click(timeout=2000)
            page.wait_for_timeout(200)
            return
        except Exception:
            continue
    box = page.locator('input[type="checkbox"]')
    if box.count() > 0:
        try:
            if not box.first.is_checked():
                box.first.check()
        except Exception:
            pass


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
    try:
        amt = (page.locator('input[name="amount"]').first.input_value() or "").replace(
            ",", ""
        )
        if amt in ("", "0"):
            raise RuntimeError(f"登録前チェック: 金額が未入力です（{amt!r}）")
    except RuntimeError:
        raise
    except Exception:
        pass
    btn = page.locator('input[type="submit"][value*="入力する"], input[type="submit"][value*="登録"]')
    if btn.count() == 0:
        for text in ("登録", "保存", "完了", "入力する"):
            role_btn = page.get_by_role("button", name=re.compile(text))
            if role_btn.count() > 0:
                btn = role_btn
                break
    if btn.count() == 0:
        raise RuntimeError("登録ボタンが見つかりません")
    btn.first.click(timeout=4000, no_wait_after=True)
    try:
        page.get_by_text("入力しました", exact=False).wait_for(timeout=8000)
    except Exception:
        body = ""
        try:
            body = page.inner_text("body") or ""
        except Exception:
            pass
        if "入力しました" not in body:
            raise RuntimeError("登録ボタンを押したが完了表示がありません")


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
    _dismiss_overlays(page)
    # 金額を先に（日付ピッカーがフォーカスを奪うと電卓入力が 0 のままになる）
    _fill_amount(page, amount)
    _dismiss_overlays(page)
    _pick_category(page, category, genre)
    _dismiss_overlays(page)
    _pick_account(page, account, kind=kind)
    _fill_date(page, day)
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
