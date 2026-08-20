#!/usr/bin/env python3
"""PayPay銀行（法人）→ 他行振込アシスト。

教訓（2026-08-20）:
  - 「自動化できない」ではない。明細取得用ログインはあるが振込フローが未整備だった。
  - ログインは一度蹴られる／上書きログインが出ることがある → 同じPWで再入力する。
  - CDP Chrome が落ちると操作不能になる → 専用プロファイル＋ポート固定。

既定: 確認画面まで進めて停止（最終実行は --execute かつユーザー承認後）。

秘密（.env.jarvis_private）:
  PAYPAY_STORE_NO / PAYPAY_ACCOUNT_NO / PAYPAY_PASSWORD
  PERSONAL_BANK_* （SMBC刈谷宛の既定）

例:
  python scripts/jarvis_paypay_bank_transfer.py --preview
  python scripts/jarvis_paypay_bank_transfer.py --go --amount 258690
  python scripts/jarvis_paypay_bank_transfer.py --go --amount 258690 --execute
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, sync_playwright

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "215_kamiooya/C1_cursor/tax_docs_tools"))

from car_loan.chrome_cdp import cdp_ready, start_cdp_chrome  # noqa: E402
from car_loan.env_state import load_env  # noqa: E402

import paypay_bank_statement as pp  # noqa: E402

CDP_PORT = 9242
PROFILE = Path.home() / ".jarvis_state" / "chrome_paypay_xfer"
START_URL = "https://www.paypay-bank.co.jp/"
STATE_PATH = Path.home() / "git-repos" / ".jarvis_state" / "paypay_bank_transfer.json"


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def _require_creds() -> tuple[str, str, str]:
    store = _env("PAYPAY_STORE_NO")
    acct = _env("PAYPAY_ACCOUNT_NO")
    pw = _env("PAYPAY_PASSWORD")
    if not store or not acct or not pw:
        raise SystemExit(
            "PAYPAY_STORE_NO / PAYPAY_ACCOUNT_NO / PAYPAY_PASSWORD が未設定です。"
            " .env.jarvis_private に追記後『保存した』と一声ください。"
        )
    return store, acct, pw


def _body(page: Page, n: int = 6000) -> str:
    try:
        return page.inner_text("body")[:n]
    except Exception:
        return ""


def _is_logged_in(page: Page) -> bool:
    """IB 内（NBCW 等）。広報サイトの「振り込み」案内は除外。"""
    url = (page.url or "").lower()
    if "paypay-bank.co.jp/business" in url and "login" not in url:
        return False
    if any(x in url for x in ("nbcw", "login.paypay-bank", "japannetbank")):
        t = _body(page, 2500)
        return any(
            k in t
            for k in ("普通預金残高", "Welcome Page", "前回ログイン", "ビジネス営業部")
        )
    t = _body(page, 2500)
    return "普通預金残高" in t and ("ログアウト" in t or "取引明細" in t)


def _needs_relogin(page: Page) -> bool:
    t = _body(page, 3000)
    markers = (
        "上書きログイン",
        "ログイン中です",
        "再度ログイン",
        "セッション",
        "お取り扱いいたしておりません",
        "ログインしてください",
    )
    if any(m in t for m in markers):
        return True
    # ログインフォームがまた出ている
    try:
        if page.locator('input[type="password"]').count() and (
            page.get_by_label("店番号").count()
            or page.locator('input[name="Tenant"]').count()
            or "店番号" in t
        ):
            if not _is_logged_in(page):
                return True
    except Exception:
        pass
    return False


def _pick_home(ctx) -> Page:
    for pg in ctx.pages:
        try:
            if _is_logged_in(pg):
                return pg
        except Exception:
            continue
    return ctx.pages[-1]


def login_with_retry(page: Page, store: str, acct: str, pw: str, *, max_attempts: int = 3) -> Page:
    """蹴られ／上書きログインを含む再入力リトライ。"""
    pp._navigate_to_login_page(page)
    lp = pp._login_page(page)
    last_url = ""
    for attempt in range(1, max_attempts + 1):
        print(f"  ログイン試行 {attempt}/{max_attempts}")
        pp._fill_login_form(page, store, acct, pw)
        pp._click_login_button(lp)
        time.sleep(2.5)
        # ポップアップ／同一タブのどちらも見る
        ctx = page.context
        candidate = _pick_home(ctx)
        # 上書きログインは同一 lp 上に出ることが多い
        if pp._is_overwrite_login_page(lp) or _needs_relogin(lp):
            print("  → 蹴られ／上書きログイン検出。同じパスワードで再入力します")
            pp._fill_login_form(page, store, acct, pw)
            pp._click_login_button(lp)
            time.sleep(3)
            candidate = _pick_home(ctx)
        if _is_logged_in(candidate):
            page._paypay_active_page = candidate  # type: ignore[attr-defined]
            print(f"  ログイン成功: {candidate.url}")
            bal = re.search(r"([\d,]+)円", _body(candidate, 800))
            if bal:
                print(f"  残高表示付近: {bal.group(1)}円（画面冒頭の数値）")
            return candidate
        last_url = candidate.url
        print(f"  未ログイン継続 url={last_url}")
        # ログインページへ戻す
        try:
            pp._navigate_to_login_page(page)
            lp = pp._login_page(page)
        except Exception:
            pass
    raise RuntimeError(f"PayPay銀行ログインに失敗しました（最終URL: {last_url}）")


def open_transfer_menu(page: Page) -> Page:
    """ホームから振り込みへ。"""
    if "振込" in _body(page, 400) and (
        "受取人" in _body(page) or "金融機関" in _body(page) or "振込金額" in _body(page)
    ):
        return page
    clicked = page.evaluate(
        """() => {
      const links = [...document.querySelectorAll('a')].filter(a => {
        const t = (a.textContent || '').trim();
        return t === '振り込み' && a.offsetParent;
      });
      if (!links.length) return null;
      // 左メニューや明細・振込ブロックを優先
      const prefer = links.find(a => {
        const href = a.getAttribute('href') || '';
        return /Transfer|Furikomi|NBCW|振込/i.test(href);
      }) || links[0];
      prefer.click();
      return prefer.getAttribute('href') || 'clicked';
    }"""
    )
    if not clicked:
        raise RuntimeError("「振り込み」リンクが見つかりません")
    print(f"  振り込みクリック: {clicked}")
    time.sleep(3)
    ctx = page.context
    for pg in ctx.pages:
        t = _body(pg, 1200)
        if any(k in t for k in ("振込金額", "受取人", "金融機関", "振込先", "新規振込")):
            return pg
    return _pick_home(ctx)


def fill_smbc_transfer(
    page: Page,
    *,
    amount: int,
    branch_code: str,
    account: str,
    account_type: str = "普通",
) -> None:
    """可能な範囲で SMBC 宛を埋める（UI差分は探索的）。"""
    body0 = _body(page, 1500)
    print("  --- 振込画面冒頭 ---")
    print("  " + body0[:500].replace("\n", " | "))

    # 新規振込／他行 など
    for label in ("新規に振り込む", "新規振込", "他の金融機関", "金融機関を指定", "振込先を入力"):
        loc = page.get_by_text(label, exact=False)
        if loc.count() and loc.first.is_visible():
            try:
                loc.first.click(timeout=2000)
                time.sleep(1.5)
                print(f"  クリック: {label}")
                break
            except Exception:
                pass

    # 金額
    filled_amt = False
    for sel in (
        'input[name*="Amount" i]',
        'input[id*="Amount" i]',
        'input[name*="Kingaku" i]',
        'input[type="tel"]',
        'input[type="text"]',
    ):
        locs = page.locator(sel)
        for i in range(min(locs.count(), 8)):
            el = locs.nth(i)
            if not el.is_visible():
                continue
            name = (el.get_attribute("name") or "") + (el.get_attribute("id") or "")
            if re.search(r"search|query|memo|name|支店|口座", name, re.I):
                continue
            try:
                el.fill(str(amount))
                print(f"  金額入力 via {sel} / {name or '(no name)'}")
                filled_amt = True
                break
            except Exception:
                continue
        if filled_amt:
            break
    if not filled_amt:
        page.evaluate(
            """(amt) => {
              const labs = [...document.querySelectorAll('*')].filter(
                e => (e.textContent || '').trim() === '振込金額' || (e.textContent || '').trim() === '金額'
              );
              for (const lab of labs) {
                const root = lab.closest('tr,div,section,form,li') || lab.parentElement;
                const inp = root && root.querySelector('input:not([type=hidden])');
                if (inp) {
                  inp.focus();
                  inp.value = String(amt);
                  inp.dispatchEvent(new Event('input', { bubbles: true }));
                  return true;
                }
              }
              return false;
            }""",
            amount,
        )
        print("  金額: JSフォールバック")

    # 銀行: 三井住友
    for label in ("三井住友銀行", "三井住友"):
        try:
            page.get_by_text(label, exact=False).first.click(timeout=2000)
            print(f"  銀行選択: {label}")
            time.sleep(1)
            break
        except Exception:
            continue
    else:
        # 金融機関コード 0009
        page.evaluate(
            """() => {
              const inps = [...document.querySelectorAll('input:not([type=hidden])')].filter(i => i.offsetParent);
              for (const inp of inps) {
                const ph = (inp.placeholder || '') + (inp.name || '') + (inp.id || '');
                if (/金融|銀行|Bank|Fncl/i.test(ph)) {
                  inp.value = '三井住友銀行';
                  inp.dispatchEvent(new Event('input', { bubbles: true }));
                  return true;
                }
              }
              return false;
            }"""
        )

    # 支店
    br_ok = page.evaluate(
        """(br) => {
          const inps = [...document.querySelectorAll('input:not([type=hidden])')].filter(i => i.offsetParent);
          for (const inp of inps) {
            const ph = (inp.placeholder || '') + (inp.name || '') + (inp.id || '');
            if (/支店|Branch|Brnch/i.test(ph)) {
              inp.focus();
              inp.value = String(br);
              inp.dispatchEvent(new Event('input', { bubbles: true }));
              return 'field:' + ph.slice(0, 40);
            }
          }
          const labs = [...document.querySelectorAll('*')].filter(e => /^支店/.test((e.textContent || '').trim()));
          for (const lab of labs) {
            const root = lab.closest('tr,div,section,form') || lab.parentElement;
            const inp = root && root.querySelector('input:not([type=hidden])');
            if (inp) {
              inp.value = String(br);
              inp.dispatchEvent(new Event('input', { bubbles: true }));
              return 'label';
            }
          }
          return null;
        }""",
        branch_code,
    )
    print(f"  支店: {br_ok}")
    time.sleep(0.8)
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")
    page.evaluate(
        """() => {
          const a = [...document.querySelectorAll('a,li,div')].find(n =>
            (n.textContent || '').includes('刈谷') && (n.textContent || '').includes('486') && n.offsetParent
          );
          if (a) a.click();
        }"""
    )

    # 口座種類
    try:
        page.get_by_text(account_type, exact=True).first.click(timeout=1500)
    except Exception:
        pass

    # 口座番号
    ac_ok = page.evaluate(
        """(acct) => {
          const inps = [...document.querySelectorAll('input:not([type=hidden])')].filter(i => i.offsetParent);
          for (const inp of inps) {
            const ph = (inp.placeholder || '') + (inp.name || '') + (inp.id || '');
            if (/口座番号|Acct|Account|kouza/i.test(ph)) {
              inp.focus();
              inp.value = String(acct);
              inp.dispatchEvent(new Event('input', { bubbles: true }));
              return 'field';
            }
          }
          const labs = [...document.querySelectorAll('*')].filter(e => (e.textContent || '').trim() === '口座番号');
          for (const lab of labs) {
            const root = lab.closest('tr,div,section,form') || lab.parentElement;
            const inp = root && root.querySelector('input:not([type=hidden])');
            if (inp) {
              inp.value = String(acct);
              inp.dispatchEvent(new Event('input', { bubbles: true }));
              return 'label';
            }
          }
          return null;
        }""",
        account,
    )
    print(f"  口座番号: {ac_ok} ****{account[-4:]}")

    # 次へ／確認
    for label in ("次へ", "確認する", "確認画面へ", "入力内容を確認"):
        clicked = page.evaluate(
            """(lab) => {
              const b = [...document.querySelectorAll('a,button,input')].find(n => {
                const t = (n.value || n.textContent || '').trim();
                return t === lab && n.offsetParent && !n.disabled;
              });
              if (!b) return false;
              b.scrollIntoView({ block: 'center' });
              b.click();
              return true;
            }""",
            label,
        )
        if clicked:
            print(f"  クリック: {label}")
            time.sleep(3)
            break


def save_state(data: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    cur: dict[str, Any] = {}
    if STATE_PATH.is_file():
        try:
            cur = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            cur = {}
    cur.update(data)
    cur["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    for banned in ("password", "otp", "PAYPAY_PASSWORD"):
        cur.pop(banned, None)
    STATE_PATH.write_text(json.dumps(cur, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    load_env(REPO / ".env.jarvis_private")
    p = argparse.ArgumentParser(description="PayPay銀行法人→他行振込アシスト")
    p.add_argument("--preview", action="store_true")
    p.add_argument("--go", action="store_true", help="ブラウザ起動・ログイン・入力まで")
    p.add_argument(
        "--execute",
        action="store_true",
        help="確認画面の実行ボタンも押す（対外送信前確認後のみ）",
    )
    p.add_argument("--amount", type=int, default=258_690)
    p.add_argument("--cdp-port", type=int, default=CDP_PORT)
    p.add_argument("--keep-browser", action="store_true", default=True)
    args = p.parse_args()
    if not args.preview and not args.go:
        p.error("--preview または --go が必要です")

    amount = args.amount
    branch = _env("PERSONAL_BANK_BRANCH_CODE") or "486"
    dest_acct = _env("PERSONAL_BANK_ACCOUNT")
    if not dest_acct:
        raise SystemExit("PERSONAL_BANK_ACCOUNT が未設定です")

    print("=== PayPay銀行 → SMBC刈谷 ===")
    print(f"金額: {amount:,}円")
    print(f"先: 三井住友 刈谷({branch}) ****{dest_acct[-4:]}")
    print("最終実行: " + ("する（--execute）" if args.execute else "しない（確認画面で停止）"))

    if args.preview:
        print("Preview のみ終了。次: --go")
        return

    store, acct, pw = _require_creds()
    port = args.cdp_port
    if not cdp_ready(port):
        start_cdp_chrome(port=port, profile_dir=PROFILE, start_url=START_URL)
        time.sleep(2)
    if not cdp_ready(port):
        raise SystemExit(f"CDP Chrome が起動しませんでした (port {port})")

    with sync_playwright() as pw_api:
        browser = pw_api.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        ctx = browser.contexts[0]
        page = ctx.pages[-1] if ctx.pages else ctx.new_page()
        home = login_with_retry(page, store, acct, pw)
        xfer = open_transfer_menu(home)
        fill_smbc_transfer(
            xfer,
            amount=amount,
            branch_code=branch,
            account=dest_acct,
        )
        body = _body(xfer, 2000)
        print("  --- 現在画面 ---")
        print("  " + body[:900].replace("\n", " | "))
        save_state(
            {
                "status": "at_confirm" if ("確認" in body or "振込金額" in body) else "filled_or_partial",
                "amount_jpy": amount,
                "dest_last4": dest_acct[-4:],
                "branch": branch,
                "execute_requested": bool(args.execute),
                "note": "最終実行はユーザー確認後。Chromeプロファイル chrome_paypay_xfer を維持",
            }
        )
        if args.execute:
            print(
                "⚠ --execute 指定あり。対外送信前確認ルールのため、"
                "チャットで『確定して』と明示されるまで実行ボタンは押しません。"
            )
            print("  確認画面の内容をユーザーに提示し、承認後に --resume-execute 等で続行してください。")
        else:
            print("✅ 入力まで完了（または確認画面）。最終実行はユーザー承認後。")
        print(f"state: {STATE_PATH}")


if __name__ == "__main__":
    main()
