#!/usr/bin/env python3
"""Vpass から Olive Infinite の次回お支払い金額・引落日を取得。

既定の「お支払い金額のお知らせ」メールは金額非表示のため、金額把握の本線。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_vpass_payment_fetch.py
  ~/selenium_env/venv/bin/python scripts/jarvis_vpass_payment_fetch.py --json
  ~/selenium_env/venv/bin/python scripts/jarvis_vpass_payment_fetch.py --headed

秘密は .env.jarvis_private の VPASS_ID / VPASS_PASSWORD。値は出さない。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from playwright.sync_api import Page, sync_playwright

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from car_loan.chrome_cdp import start_cdp_chrome  # noqa: E402
from car_loan.env_state import ENV_FILE, load_env  # noqa: E402

JST = ZoneInfo("Asia/Tokyo")
CDP_PORT = 9233
PROFILE = Path.home() / ".jarvis_state" / "chrome_vpass_payment"
SHOT_DIR = Path.home() / "git-repos" / ".jarvis_state" / "vpass_payment_fetch"
LOGIN_URL = "https://www.smbc-card.com/memx/force_login/index.html"
MYPAGE_URL = "https://www.smbc-card.com/memx/mypage/index.html"
# お支払い金額まわり（ログイン後にリンク探索もする）
PAYMENT_HINTS = (
    "お支払金額の確認・変更",
    "お支払い金額の確認・変更",
    "お支払金額の確認",
    "お支払い金額の確認",
    "お支払い金額照会",
    "お支払金額照会",
)
PAYMENT_URL_CANDIDATES = (
    "https://www.smbc-card.com/memx/mypage/index.html",  # Myページに確定額が出る
    "https://www.smbc-card.com/memx/seikyu/index.html",  # お支払金額の確認・変更
)
INF_HINTS = ("Ｏｌｉｖｅ　ＩＮＦ", "Ｏｌｉｖｅ ＩＮＦ", "Olive　INF", "ＩＮＦ", "INF", "インフィニット")


def _shot(page: Page, name: str) -> Path:
    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SHOT_DIR / f"{datetime.now(JST):%Y%m%d_%H%M%S}_{name}.png"
    try:
        page.screenshot(path=str(path), full_page=True)
        print(f"# shot {path.name}", file=sys.stderr)
    except Exception as e:
        print(f"# shot skip: {e}", file=sys.stderr)
    return path


def _body(page: Page, n: int = 8000) -> str:
    try:
        return page.inner_text("body")[:n]
    except Exception:
        return ""


def _login(page: Page, vpass_id: str, vpass_pw: str) -> None:
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=90000)
    time.sleep(1.2)
    body0 = _body(page, 1200)
    if "アクセス集中" in body0 or "つながりにくい" in body0:
        raise RuntimeError("Vpass アクセス集中（しばらく待って再試行）")
    has_login_fields = page.locator("input[name='userid']").count() > 0
    if (not has_login_fields) and ("ログアウト" in body0 or "Myページ" in body0):
        print("# already logged in", file=sys.stderr)
        return
    if not has_login_fields:
        if page.locator("input[type='password']").count() == 0:
            print(f"# no login fields url={page.url}", file=sys.stderr)
            return
    print("# login form…", file=sys.stderr)
    id_box = page.locator("input[name='userid']")
    if id_box.count() == 0:
        id_box = page.locator("input[type='text'], input:not([type])")
    id_box.first.fill(vpass_id)
    page.locator("input[name='password'], input[type='password']").first.fill(vpass_pw)
    clicked = page.evaluate(
        """() => {
          const nodes = [...document.querySelectorAll('input[type=submit],button')];
          const btn = nodes.find(b => {
            const label = (b.value || b.innerText || '').trim();
            if (label !== 'ログイン') return false;
            if (b.disabled) return false;
            const r = b.getBoundingClientRect();
            return r.width > 0 && r.height > 0;
          });
          if (!btn) return false;
          btn.click();
          return true;
        }"""
    )
    if not clicked:
        page.locator("input[type='password']").first.press("Enter")
    page.wait_for_load_state("domcontentloaded", timeout=90000)
    time.sleep(2.5)
    body1 = _body(page, 1200)
    if "アクセス集中" in body1 or "つながりにくい" in body1:
        raise RuntimeError("Vpass アクセス集中（ログイン後）")


def _goto_mypage(page: Page) -> None:
    page.goto(MYPAGE_URL, wait_until="domcontentloaded", timeout=90000)
    time.sleep(1.5)
    body = _body(page, 1500)
    if "アクセス集中" in body or "つながりにくい" in body:
        raise RuntimeError("Vpass アクセス集中（Myページ）")
    if (
        "ログイン" in body
        and "ログアウト" not in body
        and page.locator("input[type='password']").count()
    ):
        raise RuntimeError("Myページ未ログイン（再ログインが必要）")


def _select_olive_inf_if_needed(page: Page) -> None:
    body = _body(page, 3000)
    if "ログインするカードを選択" not in body and "次へ進む" not in body:
        return
    for hint in INF_HINTS:
        loc = page.locator("label,a,button,div,span,option").filter(
            has_text=re.compile(re.escape(hint))
        )
        if loc.count() == 0:
            continue
        try:
            # select option
            if page.locator("select").count():
                sel = page.locator("select").first
                opts = sel.locator("option").all_inner_texts()
                target = next((o for o in opts if hint in o or "ＩＮＦ" in o or "INF" in o), None)
                if target:
                    sel.select_option(label=target)
                    print(f"# select option ~/{hint}/", file=sys.stderr)
                    break
            loc.first.click(timeout=3000)
            print(f"# card click ~/{hint}/", file=sys.stderr)
            break
        except Exception:
            continue
    for pat in (r"次へ進む", r"次へ", r"決定"):
        loc = page.locator("a,button,input[type='submit']").filter(has_text=re.compile(pat))
        for i in range(min(loc.count(), 4)):
            el = loc.nth(i)
            try:
                if el.is_visible():
                    el.click(timeout=4000)
                    page.wait_for_load_state("domcontentloaded", timeout=60000)
                    time.sleep(1.5)
                    print(f"# next ~/{pat}/", file=sys.stderr)
                    return
            except Exception:
                continue


def _open_payment_page(page: Page) -> bool:
    for url in PAYMENT_URL_CANDIDATES:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            time.sleep(1.2)
            body = _body(page, 2000)
            if "アクセス集中" in body:
                continue
            if any(h in body for h in ("お支払い金額", "お支払金額", "今回のお支払い", "引落")):
                print(f"# opened payment url {url}", file=sys.stderr)
                return True
        except Exception:
            continue

    body = _body(page, 4000)
    for hint in PAYMENT_HINTS:
        loc = page.locator("a,button").filter(has_text=re.compile(re.escape(hint)))
        for i in range(min(loc.count(), 5)):
            el = loc.nth(i)
            try:
                if not el.is_visible():
                    continue
                el.click(timeout=5000)
                page.wait_for_load_state("domcontentloaded", timeout=60000)
                time.sleep(1.5)
                print(f"# opened payment via ~/{hint}/", file=sys.stderr)
                return True
            except Exception:
                continue
    for menu in ("明細・支払い", "お支払い", "ご利用明細"):
        loc = page.locator("a,button").filter(has_text=re.compile(re.escape(menu)))
        if loc.count() == 0:
            continue
        try:
            loc.first.click(timeout=4000)
            page.wait_for_load_state("domcontentloaded", timeout=60000)
            time.sleep(1.2)
        except Exception:
            continue
        for hint in PAYMENT_HINTS:
            loc2 = page.locator("a,button").filter(has_text=re.compile(re.escape(hint)))
            if loc2.count() == 0:
                continue
            try:
                loc2.first.click(timeout=4000)
                page.wait_for_load_state("domcontentloaded", timeout=60000)
                time.sleep(1.5)
                print(f"# opened via menu/{menu}→{hint}", file=sys.stderr)
                return True
            except Exception:
                continue
    return False


def _parse_yen(text: str) -> list[int]:
    out: list[int] = []
    for m in re.finditer(r"([0-9]{1,3}(?:,[0-9]{3})+|\d{5,})\s*円", text):
        try:
            out.append(int(m.group(1).replace(",", "")))
        except ValueError:
            pass
    return out


def _parse_due(text: str, today: date | None = None) -> str | None:
    today = today or datetime.now(JST).date()
    # 2026年8月26日 / 2026/08/26 / 8月26日（金）
    m = re.search(r"(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
        except ValueError:
            pass
    m = re.search(r"(20\d{2})[/\-.](\d{1,2})[/\-.](\d{1,2})", text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
        except ValueError:
            pass
    m = re.search(r"(\d{1,2})\s*月\s*(\d{1,2})\s*日", text)
    if m:
        mo, d = int(m.group(1)), int(m.group(2))
        y = today.year
        try:
            due = date(y, mo, d)
            if due < today - __import__("datetime").timedelta(days=7):
                due = date(y + 1, mo, d)
            return due.isoformat()
        except ValueError:
            pass
    return None


def parse_payment_from_text(text: str) -> dict[str, Any]:
    """画面テキストから次回支払額・引落日を推定（Myページ見出しを最優先）。"""
    t = text.replace("\xa0", " ").replace("&nbsp;", " ")
    amount: int | None = None
    due: str | None = None

    # Myページ: 「8月26日お支払い金額 （確定）」「1,596,308円」
    m = re.search(
        r"(\d{1,2})\s*月\s*(\d{1,2})\s*日\s*お支払い金額\s*[（(]?\s*確定\s*[）)]?\s*"
        r"([0-9]{1,3}(?:,[0-9]{3})+)\s*円",
        t,
        re.S,
    )
    if m:
        today = datetime.now(JST).date()
        mo, d = int(m.group(1)), int(m.group(2))
        y = today.year
        try:
            due_d = date(y, mo, d)
            if due_d < today - __import__("datetime").timedelta(days=7):
                due_d = date(y + 1, mo, d)
            due = due_d.isoformat()
        except ValueError:
            due = None
        amount = int(m.group(3).replace(",", ""))

    if amount is None:
        for pat in (
            r"お支払い金額[^0-9]{0,40}?([0-9]{1,3}(?:,[0-9]{3})+)\s*円",
            r"今回のお支払い[^0-9]{0,40}?([0-9]{1,3}(?:,[0-9]{3})+)\s*円",
            r"お支払金額[^0-9]{0,40}?([0-9]{1,3}(?:,[0-9]{3})+)\s*円",
            r"請求金額[^0-9]{0,40}?([0-9]{1,3}(?:,[0-9]{3})+)\s*円",
            r"合計[^0-9]{0,20}?([0-9]{1,3}(?:,[0-9]{3})+)\s*円",
        ):
            mm = re.search(pat, t)
            if mm:
                amount = int(mm.group(1).replace(",", ""))
                break
    if amount is None:
        cands = [a for a in _parse_yen(t) if 10_000 <= a <= 5_000_000]
        if cands:
            amount = max(cands)

    if due is None:
        due_block = t
        for label in ("お支払い日", "引落日", "お引落日", "支払日"):
            idx = t.find(label)
            if idx >= 0:
                due_block = t[idx : idx + 120]
                break
        due = _parse_due(due_block) or _parse_due(t)

    has_inf = any(h in t for h in ("ＩＮＦ", "INF", "インフィニット", "Olive"))
    return {
        "amount_jpy": amount,
        "due_date": due,
        "has_olive_inf_marker": has_inf,
        "source": "vpass_web",
    }


def fetch_olive_payment(*, headed: bool = False, wait_sec: int = 0) -> dict[str, Any]:
    env = load_env(ENV_FILE)
    vpass_id = env.get("VPASS_ID", "")
    vpass_pw = env.get("VPASS_PASSWORD", "")
    if not vpass_id or not vpass_pw:
        return {"ok": False, "error": "VPASS_ID/VPASS_PASSWORD 未設定"}

    start_cdp_chrome(CDP_PORT, PROFILE, LOGIN_URL)
    result: dict[str, Any] = {"ok": False}

    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
        ctx = browser.contexts[0] if browser.contexts else browser.new_context(locale="ja-JP")
        page = ctx.new_page()
        try:
            _login(page, vpass_id, vpass_pw)
            _select_olive_inf_if_needed(page)
            _goto_mypage(page)
            _select_olive_inf_if_needed(page)
            # カード切替後に確定額が載るので Myページを再読込
            page.goto(MYPAGE_URL, wait_until="domcontentloaded", timeout=90000)
            time.sleep(1.5)
            text = _body(page, 12000)
            _shot(page, "after_login")
            parsed = parse_payment_from_text(text)
            opened = parsed.get("amount_jpy") is not None
            if not opened:
                opened = _open_payment_page(page)
                _select_olive_inf_if_needed(page)
                text = _body(page, 12000)
                if "アクセス集中" in text or "つながりにくい" in text:
                    raise RuntimeError("Vpass アクセス集中（支払画面）")
                _shot(page, "payment_page")
                parsed = parse_payment_from_text(text)
            result = {
                "ok": parsed.get("amount_jpy") is not None,
                "card_id": "olive_infinite",
                "url": page.url,
                "opened_payment_nav": opened,
                **parsed,
                "fetched_at": datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S%z"),
            }
            if not result["ok"]:
                result["error"] = "金額を画面から抽出できず"
                result["text_sample"] = text[:800]
        except Exception as e:
            result = {"ok": False, "error": str(e)}
            try:
                _shot(page, "error")
            except Exception:
                pass
        if wait_sec > 0:
            time.sleep(wait_sec)
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="Vpass から Olive INF 支払額を取得")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--headed", action="store_true", help="互換用（CDP Chrome）")
    ap.add_argument("--wait-sec", type=int, default=0)
    args = ap.parse_args()
    out = fetch_olive_payment(headed=args.headed, wait_sec=args.wait_sec)
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print("📎 Vpass支払額取得")
        if out.get("ok"):
            amt = out.get("amount_jpy")
            print(f"- Olive Infinite: {amt:,}円" if isinstance(amt, int) else f"- 金額: {amt}")
            print(f"- 引落日: {out.get('due_date') or '—'}")
            print(f"- source: {out.get('source')}")
        else:
            print(f"- 失敗: {out.get('error')}")
            if out.get("url"):
                print(f"- url: {out.get('url')}")
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
