#!/usr/bin/env python3
"""
Zaim 連携設定ページで、指定口座の「連携データを更新」を押す（Phase1）。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  cd 215_kamiooya/C1_cursor/finance/zaim_budget_sync
  python ../../../../scripts/jarvis_zaim_bank_sync_manual.py
  python ../../../../scripts/jarvis_zaim_bank_sync_manual.py --names '★MUFG(アパート経営)' '★三井住友銀行 刈谷'

要: 先に zaim_budget_apply.py --login（セッション切れ時）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[1]
ZAIM_DIR = REPO / "215_kamiooya" / "C1_cursor" / "finance" / "zaim_budget_sync"
sys.path.insert(0, str(ZAIM_DIR))
import zaim_budget_apply as zaim  # noqa: E402

ONLINE = "https://zaim.net/online_accounts"
DEFAULT_NAMES = [
    "★MUFG(アパート経営)",
    "★三井住友銀行 刈谷",
    "住信 SBI ネット銀行",
]


def dismiss(page) -> None:
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)


def update_one(page, name: str) -> dict:
    name_el = page.locator('[class*="accountName"]', has_text=name).first
    if name_el.count() == 0:
        return {"name": name, "ok": False, "reason": "not found"}
    name_el.scroll_into_view_if_needed()
    page.wait_for_timeout(400)
    pulldown = name_el.locator(
        'xpath=following::a[contains(@class,"PulldownMenu")][1]'
    )
    if pulldown.count() == 0:
        return {"name": name, "ok": False, "reason": "no pulldown"}
    pulldown.click()
    page.wait_for_timeout(600)
    clicked = None
    for label in ("連携データを更新", "データを更新する", "データを更新"):
        cand = page.get_by_text(label, exact=False)
        for i in range(cand.count()):
            el = cand.nth(i)
            if el.is_visible():
                el.click()
                clicked = label
                break
        if clicked:
            break
    page.wait_for_timeout(5000)
    dismiss(page)
    return {"name": name, "ok": bool(clicked), "clicked": clicked}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--names", nargs="*", default=DEFAULT_NAMES)
    ap.add_argument("--headed", action="store_true", default=True)
    ap.add_argument("--headless", action="store_true")
    args = ap.parse_args(argv)
    headed = not args.headless

    if not zaim.STORAGE_STATE.is_file():
        print(f"先に login: {zaim.STORAGE_STATE}", file=sys.stderr)
        return 1

    results = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not headed)
        ctx = browser.new_context(storage_state=str(zaim.STORAGE_STATE))
        page = ctx.new_page()
        page.goto(ONLINE, wait_until="networkidle", timeout=90000)
        page.wait_for_timeout(2000)
        dismiss(page)
        if zaim.is_login_page(page) or "kufu.jp/signin" in page.url:
            print("セッション切れ。zaim_budget_apply.py --login を先に。", file=sys.stderr)
            browser.close()
            return 2
        for name in args.names:
            print(f"# update {name}", file=sys.stderr)
            results.append(update_one(page, name))
            if "online_accounts" not in page.url:
                page.goto(ONLINE, wait_until="domcontentloaded")
                page.wait_for_timeout(2000)
                dismiss(page)
        zaim.save_storage_state(ctx)
        browser.close()
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if all(r.get("ok") for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
