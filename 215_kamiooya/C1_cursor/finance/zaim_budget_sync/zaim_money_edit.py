#!/usr/bin/env python3
"""
Web版 Zaim で家計明細の集計設定／費目を変更する。

既存ログイン: zaim_budget_apply.py の storage / open_browser_context を再利用。
費目変更は zaim_money_create のカテゴリ選択 UI を流用。

  cd ~/git-repos/215_kamiooya/C1_cursor/finance/zaim_budget_sync
  python zaim_money_edit.py --from-watch --dry-run
  python zaim_money_edit.py --from-watch --apply --yes

行の特定は zaim_row_match.select_row（金額完全一致＋出金元＋お店でちょうど1件）。0件・複数件は何もしない。
保存後は日別を再読み込みし、同じ明細IDの行の集計アイコンが変わったかで成功判定する（2026-11-24 画面診断に基づく）。
重複除外の専用ツール: scripts/jarvis_zaim_dup_exclude.py
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from playwright.sync_api import Page

import zaim_budget_apply as zaim
import zaim_money_create as zcreate
import zaim_row_match as zmatch

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
        if not a:
            continue
        kind = a.get("action")
        if kind not in ("set_aggregate", "set_category"):
            continue
        if a.get("target") == "swap_hint":
            continue
        if kind == "set_category" and not str(a.get("value") or a.get("suggest") or "").strip():
            continue
        key = (
            str(kind),
            str(a.get("date")),
            round(float(a.get("amount") or 0), 0),
            str(a.get("value") or a.get("suggest") or ""),
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
        kind = a.get("action") or "set_aggregate"
        dest = a.get("value") or a.get("suggest") or ""
        print(
            f"  {i}. [{kind}] {a.get('date')} ¥{float(a.get('amount') or 0):,.0f} "
            f"shop={str(a.get('shop') or '')[:30]} → {dest} "
            f"(target={a.get('target')}) pay={str(a.get('pay') or '')[:24]}"
        )


ROWS_SEL = "div[class*='SearchResult-module__body']"
MODAL_SEL = ".modal.in"
# 日別／期間表示は最大31行で切れる（2026-11-24 診断）。30行以上なら検索フォームで絞る
LIST_CAP_GUARD = 30
WAIT_ROWS_MS = 20_000
WAIT_MODAL_MS = 15_000

ROWS_JS = r"""
() => {
  const g = (r, k) => r.querySelector(`[class*='SearchResult-module__${k}']`);
  const t = (e) => (e ? (e.textContent || '').trim() : '');
  return [...document.querySelectorAll("div[class*='SearchResult-module__body']")].map((r, i) => {
    const calc = g(r, 'calc') ? g(r, 'calc').querySelector('i') : null;
    const edit = g(r, 'edit') ? g(r, 'edit').querySelector('i') : null;
    const acct = g(r, 'fromAccount') ? g(r, 'fromAccount').querySelector('img') : null;
    return {
      index: i,
      price: t(g(r, 'price')),
      calc: t(calc),
      calc_title: calc ? (calc.getAttribute('title') || '') : '',
      acct: acct ? (acct.getAttribute('alt') || '') : '',
      place: t(g(r, 'place')),
      name: t(g(r, 'name')),
      comment: t(g(r, 'comment')),
      category: t(g(r, 'category')),
      edit_url: edit ? (edit.getAttribute('data-url') || '') : '',
    };
  });
}
"""

MODAL_JS = r"""
() => {
  const m = document.querySelector('.modal.in');
  if (!m) return {open: false};
  const c = m.querySelector('.modal-body.content');
  const s = m.querySelector('.modal-body.spinner');
  return {
    open: true,
    spinner_visible: s ? getComputedStyle(s).display !== 'none' : false,
    content_children: c ? c.children.length : 0,
    form_actions: [...m.querySelectorAll('form')].map((f) => f.getAttribute('action') || ''),
  };
}
"""


class EditError(RuntimeError):
    """画面操作の失敗（何も保存していない／確認できなかった）。"""


def _goto_day(page: Page, day: str) -> None:
    """日別一覧を開き、行（body）が1件以上出るまで待つ。0行は失敗（固定待ちはしない）。"""
    url = f"{MONEY_URL}?start_date={day}&end_date={day}"
    page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    if "login" in page.url or "id.zaim.net" in page.url or "kufu.jp" in page.url:
        raise EditError(f"未ログイン: {page.url}")
    try:
        page.wait_for_function(
            "(sel) => document.querySelectorAll(sel).length > 0",
            arg=ROWS_SEL,
            timeout=WAIT_ROWS_MS,
        )
    except Exception as e:
        raise EditError(zmatch.R_NO_ROWS) from e


def read_rows(page: Page) -> list[dict[str, Any]]:
    return page.evaluate(ROWS_JS)


def _narrow_by_form(page: Page, amount: int, agg_value: str | None) -> None:
    """検索フォームの「金額 下限=上限」（＋集計設定）で絞る。多数日用。"""
    before = page.locator(ROWS_SEL).count()
    opener = page.get_by_text("オプションを表示する")
    if opener.count() > 0:
        opener.first.click()
        page.wait_for_timeout(300)
    form = page.locator("[class*='MoneySearchForm-module__moneySearchForm']")
    amts = form.locator("input[placeholder='指定しない']")
    if amts.count() < 2:
        raise EditError("検索フォームの金額欄が見つからない")
    amts.nth(0).fill(str(amount))
    amts.nth(1).fill(str(amount))
    if agg_value is not None:
        agg = form.locator("select").filter(has=page.locator("option[value='6']")).first
        agg.select_option(agg_value)
    form.get_by_text("この条件で絞り込む").first.click()
    # 再検索の反映待ち: 件数が変わって6回(約1秒)安定したら確定（上限6秒）
    prev, stable = before, 0
    for _ in range(40):
        page.wait_for_timeout(150)
        n = page.locator(ROWS_SEL).count()
        if n != before:
            stable = stable + 1 if n == prev else 0
            if stable >= 6:
                break
        prev = n
    n = page.locator(ROWS_SEL).count()
    if n == 0:
        raise EditError(zmatch.R_NO_ROWS)
    if n == before and before >= LIST_CAP_GUARD:
        raise EditError("検索フォームの絞り込みが反映されない")


def rows_for_day(
    page: Page, day: str, amount: int, *, agg_value: str | None = None
) -> list[dict[str, Any]]:
    """日別ページを（再）読み込みして行を返す。30行以上ならフォームで絞る。"""
    _goto_day(page, day)
    rows = read_rows(page)
    if len(rows) >= LIST_CAP_GUARD:
        _narrow_by_form(page, amount, agg_value)
        rows = read_rows(page)
    return rows


def _expected_calc(action: dict[str, Any]) -> str | None:
    """この変更の前提になる集計アイコン。集計除外は『含める(緑)』の行だけが対象。"""
    if str(action.get("action") or "set_aggregate") != "set_aggregate":
        return None
    value = VALUE_MAP.get(str(action.get("value") or "exclude"), str(action.get("value")))
    if value == "exclude":
        return zmatch.CALC_INCLUDE
    if value == "include":
        return zmatch.CALC_EXCLUDE
    return None


def locate_target(page: Page, action: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    """action の行を日別一覧で『ちょうど1件』に特定する。絞れなければ (None, 理由)。"""
    day = str(action.get("date") or "")
    amount = int(round(float(action.get("amount") or 0)))
    expect_calc = _expected_calc(action)
    agg_filter = "10" if expect_calc == zmatch.CALC_INCLUDE else None
    try:
        rows = rows_for_day(page, day, amount, agg_value=agg_filter)
    except EditError as e:
        return None, str(e)
    return zmatch.select_row(
        rows,
        amount=amount,
        pay=str(action.get("pay") or ""),
        shop=str(action.get("shop") or ""),
        expect_calc=expect_calc,
        described=action.get("described"),
        group_size=action.get("group_size", 1),
    )


def _modal_snapshot(page: Page) -> dict[str, Any]:
    return page.evaluate(MODAL_JS)


def open_edit_modal(page: Page, zaim_id: str) -> None:
    """行の edit セルの i[data-url=/money/{ID}/edit] を直接押し、その明細のモーダルが整うまで待つ。"""
    icon = page.locator(
        f"[class*='SearchResult-module__edit'] i[data-url='/money/{zaim_id}/edit']"
    )
    if icon.count() != 1:
        raise EditError(zmatch.R_ID_NOT_FOUND)
    icon.first.click(timeout=5000)
    waited = 0
    while waited < WAIT_MODAL_MS:
        if zmatch.modal_ready(_modal_snapshot(page), zaim_id):
            return
        page.wait_for_timeout(150)
        waited += 150
    close_modal(page)
    raise EditError("編集モーダルが開かない（読み込み待ち切れ）")


def close_modal(page: Page) -> None:
    """保存せずに閉じる。"""
    try:
        btn = page.locator(f"{MODAL_SEL} .close")
        if btn.count() > 0 and btn.first.is_visible():
            btn.first.click(timeout=2000)
        else:
            page.keyboard.press("Escape")
        page.wait_for_timeout(500)
    except Exception:
        pass


def _agg_select(page: Page):
    return page.locator(f"{MODAL_SEL} select").filter(
        has=page.locator("option", has_text="常に含めない")
    )


def read_modal_agg(page: Page) -> str | None:
    sel = _agg_select(page)
    if sel.count() != 1:
        return None
    return sel.first.input_value()


def _set_aggregate_in_dialog(page: Page, value: str) -> bool:
    """モーダルの集計 select（10=標準／6=月ごと・年ごと／3=年ごと／0=含めない）。value: include|exclude。"""
    sel = _agg_select(page)
    if sel.count() != 1:
        return False
    want = "0" if value == "exclude" else "10"
    sel.first.select_option(value=want)
    page.wait_for_timeout(200)
    return sel.first.input_value() == want


def _save_dialog(page: Page) -> bool:
    """モーダル内の『更新する』（input[type=submit]）を押し、モーダルが閉じるまで待つ。"""
    btn = page.locator(f"{MODAL_SEL} input[type='submit'][value='更新する']")
    if btn.count() != 1:
        return False
    btn.first.click(timeout=5000)
    waited = 0
    while waited < WAIT_MODAL_MS:
        if page.locator(MODAL_SEL).count() == 0:
            return True
        page.wait_for_timeout(200)
        waited += 200
    return False  # 閉じない＝入力エラー等。保存は確認できていない


def _set_category_in_dialog(page: Page, category: str, genre: str) -> bool:
    try:
        zcreate._pick_category(page, category, genre)
        return True
    except Exception:
        return False


def verify_by_id(
    page: Page, day: str, amount: int, zaim_id: str, expected_calc: str
) -> tuple[bool, str]:
    """日別ページを再読み込みし、同じ明細IDの行の集計アイコンが期待どおりかで成功判定する。"""
    try:
        rows = rows_for_day(page, day, amount)
    except EditError as e:
        return False, str(e)
    return zmatch.verify_calc(rows, zaim_id, expected_calc)


def change_aggregate_by_id(
    page: Page,
    *,
    day: str,
    amount: int,
    zaim_id: str,
    value: str,
    expect_prev_value: str,
    shot_prefix: str = "",
) -> dict[str, Any]:
    """
    明細IDを指して集計設定を変える（日別一覧が開いていて、その行が見える前提で呼ぶ）。
    value: include|exclude。expect_prev_value: 変更前に画面の select が示すはずの値（10 or 0 など）。
    戻り値: {ok, message, zaim_id, prev_agg, verified}
    """
    out: dict[str, Any] = {
        "ok": False,
        "message": "",
        "zaim_id": zaim_id,
        "prev_agg": None,
        "verified": False,
    }
    try:
        open_edit_modal(page, zaim_id)
    except EditError as e:
        out["message"] = str(e)
        return out
    prev = read_modal_agg(page)
    out["prev_agg"] = prev
    if prev != expect_prev_value:
        close_modal(page)
        out["message"] = f"変更前の集計設定が想定と違う（{prev}）— 変更せず中止"
        return out
    if not _set_aggregate_in_dialog(page, value):
        close_modal(page)
        out["message"] = "集計設定コントロールが見つからない（UI要調整）"
        return out
    if not _save_dialog(page):
        _shot(page, f"{shot_prefix}_save_fail")
        close_modal(page)
        out["message"] = "保存（更新する）が完了しない"
        return out
    want_calc = zmatch.CALC_EXCLUDE if value == "exclude" else zmatch.CALC_INCLUDE
    ok, why = verify_by_id(page, day, amount, zaim_id, want_calc)
    out["verified"] = ok
    out["ok"] = ok
    out["message"] = "ok" if ok else f"保存後の確認で反映を確認できない: {why}"
    return out


def _shot(page: Page, name: str) -> None:
    try:
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(SCREENSHOT_DIR / f"{name}.png"), full_page=True)
    except Exception:
        pass


def apply_one_ex(page: Page, action: dict[str, Any], *, shot_prefix: str) -> dict[str, Any]:
    """1件を特定→変更→再読み込みで確認。ちょうど1件に絞れなければ何もしない。"""
    day = str(action.get("date") or "")
    amount = int(round(float(action.get("amount") or 0)))
    kind = str(action.get("action") or "set_aggregate")
    res: dict[str, Any] = {"ok": False, "message": "", "zaim_id": None, "prev_agg": None, "verified": False}

    row, why = locate_target(page, action)
    if row is None:
        _shot(page, f"{shot_prefix}_row_fail")
        res["message"] = f"行を1件に絞れない: {why}"
        return res
    zaim_id = zmatch.edit_id_from_url(row.get("edit_url")) or ""
    res["zaim_id"] = zaim_id
    if action.get("dry_run_only"):
        res["message"] = "dry-run: 特定のみ"
        res["prev_agg"] = zmatch.agg_value_from_title(row.get("calc_title"))
        res["ok"] = True
        return res

    if kind == "set_category":
        category = str(action.get("value") or action.get("suggest") or "").strip()
        genre = str(action.get("genre") or action.get("suggest_genre") or "").strip()
        if not category or category == "review":
            res["message"] = "category empty"
            return res
        before_cat = row.get("category") or ""
        try:
            open_edit_modal(page, zaim_id)
        except EditError as e:
            res["message"] = str(e)
            return res
        if not _set_category_in_dialog(page, category, genre):
            _shot(page, f"{shot_prefix}_cat_fail")
            close_modal(page)
            res["message"] = f"費目コントロールが見つからない: {category}"
            return res
        if not _save_dialog(page):
            _shot(page, f"{shot_prefix}_save_fail")
            close_modal(page)
            res["message"] = "保存（更新する）が完了しない"
            return res
        try:
            rows = rows_for_day(page, day, amount)
        except EditError as e:
            res["message"] = f"保存後の確認で行を読めない: {e}"
            return res
        after = zmatch.find_by_id(rows, zaim_id)
        if after is None:
            res["message"] = f"保存後の確認: {zmatch.R_ID_NOT_FOUND}"
            return res
        if zmatch.nf(after.get("category")) == zmatch.nf(before_cat):
            res["message"] = "保存後の確認で費目が変わっていない"
            return res
        res.update(ok=True, verified=True, message="ok")
        return res

    raw_val = str(action.get("value") or "exclude")
    value = VALUE_MAP.get(raw_val, raw_val)
    if value not in ("include", "exclude"):
        res["message"] = f"unknown value={raw_val}"
        return res
    expect_prev = "10" if value == "exclude" else "0"
    return change_aggregate_by_id(
        page,
        day=day,
        amount=amount,
        zaim_id=zaim_id,
        value=value,
        expect_prev_value=expect_prev,
        shot_prefix=shot_prefix,
    )


def apply_one(page: Page, action: dict[str, Any], *, shot_prefix: str) -> tuple[bool, str]:
    """互換 API（zaim_money_create などが使用）。"""
    r = apply_one_ex(page, action, shot_prefix=shot_prefix)
    return bool(r["ok"]), str(r["message"])


@contextmanager
def web_session(
    *,
    headless: bool = True,
    connect_cdp: str | None = None,
    login_method: str = "email",
    login_email: str = zaim.DEFAULT_LOGIN_EMAIL,
    login_password: str = zaim.DEFAULT_LOGIN_PASSWORD,
    google_email: str = zaim.DEFAULT_GOOGLE_EMAIL,
) -> Iterator[Page]:
    """既存のログイン流儀（storage state → 失効ならメール+パスワード）で Zaim を開く。"""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser, ctx, _ = zaim.open_browser_context(
            pw,
            headless=headless,
            connect_cdp=connect_cdp,
            storage_state=zaim.STORAGE_STATE if not connect_cdp else None,
        )
        try:
            page = zaim.get_work_page(ctx)
            zaim.ensure_logged_in(
                page,
                email=login_email,
                password=login_password,
                google_email=google_email,
                login_method=login_method,
                manual=False,
            )
            yield page
        finally:
            try:
                zaim.save_storage_state(ctx)
            except Exception:
                pass
            if browser and not connect_cdp:
                browser.close()


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

    ok_n = fail_n = 0
    results: list[dict[str, Any]] = []
    with web_session(
        headless=args.headless,
        connect_cdp=args.connect_cdp,
        login_method=args.login_method,
        login_email=args.login_email,
        login_password=args.login_password,
        google_email=args.google_email,
    ) as page:
        limit = args.limit if args.limit and args.limit > 0 else len(actions)
        for i, action in enumerate(actions[:limit]):
            dest = action.get("value") or action.get("suggest") or ""
            print(
                f"▶ {i+1}/{limit} [{action.get('action')}] "
                f"{action.get('date')} ¥{action.get('amount')} → {dest}"
            )
            r = apply_one_ex(page, action, shot_prefix=f"{i+1:02d}")
            ok, msg = bool(r["ok"]), str(r["message"])
            print(f"  {'OK' if ok else 'NG'}: {msg}")
            results.append(
                {
                    **action,
                    "ok": ok,
                    "message": msg,
                    "zaim_id": r.get("zaim_id"),
                    "prev_agg": r.get("prev_agg"),
                    "verified": r.get("verified"),
                }
            )
            if ok:
                ok_n += 1
            else:
                fail_n += 1
            time.sleep(0.8)
    out_path = REPO / ".jarvis_state" / "zaim_money_apply_last.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {"ok_n": ok_n, "fail_n": fail_n, "results": results},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"# done ok={ok_n} fail={fail_n} shots={SCREENSHOT_DIR}")
    return 0 if fail_n == 0 else 2


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Zaim 明細の集計設定／費目を Web で変更")
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
