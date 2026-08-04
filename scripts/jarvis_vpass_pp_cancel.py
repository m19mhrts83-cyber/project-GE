#!/usr/bin/env python3
"""単体プラチナプリファードの Vpass カード退会（Olive INF は触らない）。

  /Users/matsunomasaharu2/selenium_env/venv/bin/python \\
    ~/git-repos/scripts/jarvis_vpass_pp_cancel.py
  # 最終確定まで進める（カード名が PP のみのとき）:
  ... jarvis_vpass_pp_cancel.py --i-confirm-cancel

秘密は .env.jarvis_private の VPASS_* のみ。値は stdout に出さない。
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout, sync_playwright

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from car_loan.chrome_cdp import cdp_ready, start_cdp_chrome  # noqa: E402
from car_loan.env_state import ENV_FILE, load_env  # noqa: E402

CDP_PORT = 9231
PROFILE = Path.home() / ".jarvis_state" / "chrome_vpass_audit"
CANCEL_ENTRY = "https://www.smbc-card.com/memx/card_cancel/index.html"
SHOT_DIR = Path.home() / "git-repos" / ".jarvis_state" / "vpass_pp_cancel"
PP_HINTS = ("プリファード", "PREFERRED", "プラチナプリファード")
INF_HINTS = ("ＩＮＦ", "INF", "INFINITE", "インフィニット", "フレキシブル")


def _shot(page: Page, name: str) -> Path:
    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SHOT_DIR / f"{datetime.now():%Y%m%d_%H%M%S}_{name}.png"
    page.screenshot(path=str(path), full_page=True)
    print(f"📎 screenshot: {path}")
    return path


def _body(page: Page, n: int = 2500) -> str:
    try:
        return page.inner_text("body")[:n]
    except Exception:
        return ""


def _login(page: Page, vpass_id: str, vpass_pw: str) -> None:
    page.goto(CANCEL_ENTRY, wait_until="domcontentloaded", timeout=90000)
    time.sleep(1.5)
    body0 = _body(page, 800)
    has_login_fields = page.locator("input[name='userid']").count() > 0
    if (not has_login_fields) and ("ログアウト" in body0):
        print(f"📎 既にログイン済み: {page.url}")
        return
    if not has_login_fields:
        print(f"📎 ログイン欄なし: {page.url}")
        return
    print("📎 ログインフォーム入力…")
    page.locator("input[name='userid']").first.fill(vpass_id)
    page.locator("input[name='password']").first.fill(vpass_pw)
    # 可視・有効なログインボタンのみ（非表示の確認する等を踏まない）
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
        page.locator("input[name='password']").first.press("Enter")
    page.wait_for_load_state("domcontentloaded", timeout=90000)
    time.sleep(2)


def _click_visible(page: Page, patterns: list[str]) -> bool:
    for pat in patterns:
        loc = page.locator("a,button,input[type='submit']").filter(has_text=re.compile(pat))
        n = loc.count()
        for i in range(n):
            el = loc.nth(i)
            try:
                if not el.is_visible() or not el.is_enabled():
                    continue
                el.click(timeout=5000)
                page.wait_for_load_state("domcontentloaded", timeout=60000)
                time.sleep(1.2)
                print(f"📎 clicked visible ~/{pat}/")
                return True
            except Exception:
                continue
    return False


def _switch_to_pp_via_mypage(page: Page) -> bool:
    """操作中カードをプラチナプリファードへ（select）。"""
    print("📎 マイページ経由で操作中カード切替を試行…")
    page.goto("https://www.smbc-card.com/memx/mypage/index.html", wait_until="domcontentloaded", timeout=60000)
    time.sleep(2)
    if "ログアウト" not in _body(page, 400):
        print("⚠️ マイページ未ログイン")
        return False
    try:
        page.get_by_text("操作中のカードを変更する", exact=False).first.click(timeout=5000)
        time.sleep(1)
    except Exception:
        pass
    sel = page.locator("select").filter(has=page.locator("option", has_text="プラチナプリファード"))
    if sel.count() == 0:
        print("⚠️ PP の select が見つかりません")
        return False
    opts = sel.first.locator("option").all_inner_texts()
    pp = next((o for o in opts if "プラチナプリファード" in o and not _looks_like_inf(o)), None)
    if not pp:
        return False
    sel.first.select_option(label=pp)
    page.wait_for_load_state("domcontentloaded", timeout=60000)
    time.sleep(2)
    print(f"📎 操作中カード → {pp}")
    return True


def _looks_like_pp(text: str) -> bool:
    t = text.replace(" ", "").replace("　", "")
    if any(h in t for h in INF_HINTS) and "プリファード" not in t:
        return False
    return any(h in t for h in PP_HINTS)


def _looks_like_inf(text: str) -> bool:
    t = text.replace(" ", "").replace("　", "")
    return any(h in t for h in INF_HINTS)


def _select_pp_card(page: Page) -> str | None:
    """カード選択 UI があれば PP を選ぶ。選んだラベルを返す。"""
    # select
    sels = page.locator("select")
    for i in range(sels.count()):
        sel = sels.nth(i)
        opts = sel.locator("option").all_inner_texts()
        pp = next((o for o in opts if _looks_like_pp(o) and not _looks_like_inf(o)), None)
        if pp:
            sel.select_option(label=pp)
            print(f"📎 select: {pp[:80]}")
            return pp
    # radio / label
    labels = page.locator("label, li, tr, .card, .Card")
    for i in range(min(labels.count(), 40)):
        t = labels.nth(i).inner_text()
        if _looks_like_pp(t) and not _looks_like_inf(t):
            try:
                labels.nth(i).click(timeout=2000)
                print(f"📎 click label: {t[:80].replace(chr(10), ' ')}")
                return t[:120]
            except Exception:
                continue
    # link containing PP
    for role in ("link", "button"):
        loc = page.get_by_role(role, name=re.compile(r"プリファード|PREFERRED"))
        if loc.count():
            txt = loc.first.inner_text()
            if not _looks_like_inf(txt):
                loc.first.click()
                print(f"📎 click {role}: {txt[:80]}")
                return txt[:120]
    return None


def _click_next(page: Page) -> bool:
    patterns = [
        r"次へ",
        r"進む",
        r"お手続きへ",
        r"退会手続きへ",
        r"解約手続きへ",
        r"内容を確認",
        r"^確認する$",
        r"同意して",
        r"申し込む",
        r"申込む",
        r"退会する",
        r"解約する",
        r"手続きを完了",
        r"完了する",
    ]
    return _click_visible(page, patterns)


def _check_agreements(page: Page) -> None:
    boxes = page.locator("input[type='checkbox']")
    for i in range(boxes.count()):
        box = boxes.nth(i)
        try:
            if not box.is_checked():
                box.check(force=True)
        except Exception:
            pass


def _is_done(text: str) -> bool:
    return any(
        k in text
        for k in (
            "受付完了",
            "お手続きが完了",
            "退会手続きを受け付け",
            "解約手続きを受け付け",
            "受付番号",
            "ありがとうございました",
        )
    )


def _is_confirm_screen(text: str) -> bool:
    return any(k in text for k in ("内容のご確認", "以下の内容で", "最終確認", "よろしいですか"))


def run(confirm: bool, wait_sec: int, port: int) -> int:
    env = load_env(ENV_FILE)
    vpass_id = env.get("VPASS_ID", "")
    vpass_pw = env.get("VPASS_PASSWORD", "")
    if not vpass_id or not vpass_pw:
        print("未設定: VPASS_ID / VPASS_PASSWORD", file=sys.stderr)
        return 1

    start_cdp_chrome(port, PROFILE, CANCEL_ENTRY)

    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        ctx = browser.contexts[0] if browser.contexts else browser.new_context(locale="ja-JP")
        page = ctx.new_page()

        print("📎 Vpass ログイン（退会入口）…")
        _login(page, vpass_id, vpass_pw)
        print(f"📎 URL: {page.url}")
        _shot(page, "after_login")

        body = _body(page)
        if "ワンタイム" in body or "認証コード" in body or "SMS" in body:
            print("⚠️ OTP / SMS 認証が必要です。Chrome で入力してください（最大3分待機）…")
            deadline = time.time() + 180
            while time.time() < deadline:
                body = _body(page)
                if "ワンタイム" not in body and "認証コード" not in body:
                    break
                time.sleep(2)
            _shot(page, "after_otp")

        body = _body(page)
        if "表示されない" in body or ("退会" in body and "ラジオ" not in body and "select" not in page.content().lower()):
            # カード一覧が空 → 操作中カード切替
            if "プリファード" not in body.replace(" ", ""):
                _switch_to_pp_via_mypage(page)
                page.goto(CANCEL_ENTRY, wait_until="domcontentloaded", timeout=90000)
                time.sleep(2)
                _shot(page, "after_card_switch")

        # カード選択
        chosen = _select_pp_card(page)
        if chosen and _looks_like_inf(chosen):
            print("❌ Olive / INF が選ばれました。中止します。", file=sys.stderr)
            return 2

        # 数ステップ進む（最大 8）
        for step in range(8):
            body = _body(page, 4000)
            print(f"---- step {step} url={page.url}")
            print(body[:500].replace("\n", " | "))
            _shot(page, f"step{step}")

            if _is_done(body):
                print("✅ 退会受付完了と判定")
                print(body[:800])
                return 0

            if _looks_like_inf(body) and not _looks_like_pp(body):
                print("❌ 画面が Olive INF のみ。中止。", file=sys.stderr)
                return 2

            # 確認画面で PP 以外なら止める
            if _is_confirm_screen(body) or ("退会" in body and "確認" in body):
                if _looks_like_inf(body) and "プリファード" not in body.replace(" ", ""):
                    print("❌ 確認画面が INF。中止。", file=sys.stderr)
                    return 2
                if not confirm:
                    print("⏸ 最終確認画面です。--i-confirm-cancel で確定できます。")
                    print("   Chrome を開いたまま待機します。")
                    time.sleep(wait_sec)
                    return 0
                _check_agreements(page)
                if not _click_next(page):
                    print("⚠️ 確定ボタンが見つかりません。手動で完了してください。")
                    time.sleep(wait_sec)
                    return 3
                continue

            _check_agreements(page)
            # 毎回 PP 再選択を試みる（多段セレクト）
            _select_pp_card(page)
            if not _click_next(page):
                print("⚠️ 次へボタン無し。手動操作待ち…")
                time.sleep(min(wait_sec, 120))
                body2 = _body(page, 4000)
                if _is_done(body2):
                    print("✅ 手動完了を検知")
                    _shot(page, "done_manual")
                    return 0
                print(f"📎 待機後 URL: {page.url}")
                _shot(page, "stuck")
                return 4

        body = _body(page, 4000)
        _shot(page, "final")
        if _is_done(body):
            print("✅ 完了")
            print(body[:800])
            return 0
        print("⚠️ 自動完了まで到達せず。Chrome を確認してください。")
        print(body[:800])
        time.sleep(wait_sec)
        return 5


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--i-confirm-cancel", action="store_true", help="最終確認で退会を確定する")
    p.add_argument("--port", type=int, default=CDP_PORT)
    p.add_argument("--wait-sec", type=int, default=300)
    args = p.parse_args()
    try:
        return run(args.i_confirm_cancel, args.wait_sec, args.port)
    except (PlaywrightTimeout, TimeoutError, RuntimeError) as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
