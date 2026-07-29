#!/usr/bin/env python3
"""Ensure Google Maps API key exists for a GCP project and save to .env.jarvis_private.

Flow (idempotent):
1. Connect Chrome CDP :9222 (must be logged in as project owner)
2. Link Maps billing if prompted (prefers 請求先アカウント(Amex) / My Billing Account)
3. If API key already listed → show/copy and save
4. Else create API key (select Maps JS / Places / Geocoding / Maps Static) → save
5. Never prints the full key

Prereq — start Chrome once:
  /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome \\
    --remote-debugging-port=9222 --remote-allow-origins='*' \\
    --user-data-dir=/tmp/chrome-jarvis-gcp --no-first-run \\
    'https://console.cloud.google.com/apis/credentials?project=PROJECT&hl=ja'

Then:
  python scripts/jarvis_gcp_maps_api_key_create.py --project serch-property-management-co
  python scripts/jarvis_maps_key_check.py
"""
from __future__ import annotations

import argparse
import asyncio
import re
import sys
from pathlib import Path

from playwright.async_api import async_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / ".env.jarvis_private"
DEFAULT_PROJECT = "serch-property-management-co"
KEY_NAME = "project-GE-shuhen-map"
CDP = "http://127.0.0.1:9222"
BILLING_PREFS = ("請求先アカウント(Amex)", "My Billing Account", "請求先アカウント")


def log(msg: str) -> None:
    print(msg, flush=True)


def save_key(key: str) -> None:
    text = ENV.read_text(encoding="utf-8")
    line = f"GOOGLE_MAPS_API_KEY={key}"
    if re.search(r"^GOOGLE_MAPS_API_KEY=.*$", text, re.M):
        text = re.sub(r"^GOOGLE_MAPS_API_KEY=.*$", line, text, count=1, flags=re.M)
    else:
        text = text.rstrip() + "\n\n" + line + "\n"
    ENV.write_text(text, encoding="utf-8")


async def extract_key(page) -> str | None:
    return await page.evaluate(
        """() => {
          for (const i of document.querySelectorAll('input,textarea')) {
            const v = i.value || '';
            if (v.startsWith('AIza') && v.length > 30) return v;
          }
          const m = (document.body.innerText || '').match(/AIza[0-9A-Za-z_\\-]{30,}/);
          return m ? m[0] : null;
        }"""
    )


async def ensure_billing(page, project: str) -> None:
    url = f"https://console.cloud.google.com/google/maps-apis/credentials?project={project}&hl=ja"
    await page.goto(url, wait_until="domcontentloaded", timeout=120000)
    await page.wait_for_timeout(4000)
    body = await page.inner_text("body")
    if "請求先アカウント" not in body and "アカウントを設定" not in body:
        log("billing: already linked or not prompted")
        return

    opened = await page.evaluate(
        """() => {
          const dlg = document.querySelector('[role=dialog]') || document.body;
          const ms = dlg.querySelector('mat-select, [role=combobox]');
          if (ms) { ms.click(); return 'ok'; }
          return 'no';
        }"""
    )
    log(f"billing dropdown: {opened}")
    await page.wait_for_timeout(1200)

    picked = None
    for name in BILLING_PREFS:
        loc = page.get_by_role("option", name=name)
        if await loc.count() == 0:
            loc = page.get_by_text(name, exact=True)
        if await loc.count():
            await loc.first.click()
            picked = name
            break
    if not picked:
        raise RuntimeError("No billing account option found. Create one in Cloud Billing first.")
    log(f"billing picked: {picked}")
    setup = page.get_by_role("button", name="アカウントを設定")
    await expect(setup).to_be_enabled(timeout=15000)
    await setup.click()
    log("billing linked")
    await page.wait_for_timeout(6000)


async def show_existing_key(page, project: str) -> str | None:
    url = f"https://console.cloud.google.com/apis/credentials?project={project}&hl=ja"
    await page.goto(url, wait_until="domcontentloaded", timeout=120000)
    await page.wait_for_timeout(4000)
    body = await page.inner_text("body")
    if "表示する API キーがありません" in body:
        return None

    # Close leftover panels
    for name in ("キャンセル", "Cancel", "閉じる"):
        btn = page.get_by_role("button", name=name)
        if await btn.count():
            try:
                await btn.first.click(timeout=1500)
                await page.wait_for_timeout(500)
            except Exception:
                pass

    show = page.get_by_role("button", name=re.compile(r"鍵を表示|キーを表示|Show key|表示します"))
    if await show.count() == 0:
        show = page.get_by_text("鍵を表示", exact=False)
    if await show.count():
        await show.first.click()
        await page.wait_for_timeout(2000)
    key = await extract_key(page)
    if key:
        return key
    copy = page.get_by_role("button", name=re.compile(r"コピー|Copy"))
    if await copy.count():
        await copy.first.click()
        await page.wait_for_timeout(400)
        try:
            clip = await page.evaluate("() => navigator.clipboard.readText()")
            if clip and clip.startswith("AIza"):
                return clip
        except Exception:
            pass
    return await extract_key(page)


async def create_new_key(page, project: str) -> str:
    url = f"https://console.cloud.google.com/apis/credentials?project={project}&hl=ja"
    await page.goto(url, wait_until="domcontentloaded", timeout=120000)
    await page.wait_for_timeout(4000)
    await page.get_by_role("button", name=re.compile(r"認証情報を作成")).first.click()
    await page.wait_for_timeout(800)
    await page.get_by_text("シンプル API キーを使用して", exact=False).first.click()
    await expect(page.get_by_text("API キーの作成", exact=False).first).to_be_visible(timeout=30000)
    panel = page.locator(".cdk-overlay-pane, [role=dialog], aside").last
    if await panel.locator("input").count():
        await panel.locator("input").first.fill(KEY_NAME)

    sel = panel.get_by_text("API が選択されていません", exact=False)
    if await sel.count() == 0:
        sel = panel.get_by_text("API の制限の選択", exact=False)
    await sel.first.click()
    await page.wait_for_timeout(1200)
    for api in ("Maps JavaScript API", "Places API", "Geocoding API", "Maps Static API"):
        opt = page.get_by_role("option", name=api)
        if await opt.count() == 0:
            opt = page.get_by_text(api, exact=True)
        if await opt.count():
            await opt.first.click()
            await page.wait_for_timeout(250)
    await page.keyboard.press("Escape")
    await page.wait_for_timeout(400)

    create_btn = panel.get_by_role("button", name=re.compile(r"^作成$|^Create$"))
    if await create_btn.count() == 0:
        create_btn = page.get_by_role("button", name=re.compile(r"^作成$|^Create$"))
    await create_btn.first.click()

    for _ in range(35):
        await page.wait_for_timeout(1000)
        key = await extract_key(page)
        if key:
            return key
    # Fallback: list may have been updated
    key = await show_existing_key(page, project)
    if key:
        return key
    raise RuntimeError("Create clicked but key string not found")


async def main_async(project: str) -> int:
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP)
        ctx = browser.contexts[0]
        page = next((pg for pg in ctx.pages if "cloud.google.com" in pg.url), None)
        if page is None:
            page = await ctx.new_page()
        await page.bring_to_front()

        await ensure_billing(page, project)
        key = await show_existing_key(page, project)
        if not key:
            log("no existing key — creating")
            key = await create_new_key(page, project)
        else:
            log("found existing key — reusing")
        save_key(key)
        log(f"SAVED GOOGLE_MAPS_API_KEY len={len(key)} prefix={key[:6]}…")
        return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default=DEFAULT_PROJECT)
    args = ap.parse_args()
    try:
        return asyncio.run(main_async(args.project))
    except Exception as e:
        log(f"ERROR: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
