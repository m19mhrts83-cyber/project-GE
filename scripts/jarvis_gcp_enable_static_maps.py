#!/usr/bin/env python3
"""Enable Maps Static API on serch-property-management-co via Chrome CDP :9222.

Does not print API keys. Idempotent: if already enabled, reports and exits 0.
"""
from __future__ import annotations

import asyncio
import sys

from playwright.async_api import async_playwright

PROJECT = "serch-property-management-co"
CDP = "http://127.0.0.1:9222"
URL = (
    f"https://console.cloud.google.com/apis/library/static-maps-backend.googleapis.com"
    f"?project={PROJECT}&hl=ja"
)


def log(msg: str) -> None:
    print(msg, flush=True)


async def run() -> int:
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP)
        context = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(URL, wait_until="domcontentloaded", timeout=120000)
        await page.wait_for_timeout(5000)

        body = await page.inner_text("body")
        log(f"title={await page.title()}")
        # Already enabled?
        if "API を管理" in body or "Manage" in body and "Disable API" in body:
            log("status: already_enabled (manage UI visible)")
            return 0
        if "無効にする" in body and ("有効" in body or "有効化済み" in body):
            # Japanese: enabled pages often show 無効にする
            if "有効にする" not in body[:2000] or body.count("無効にする") > 0:
                # Heuristic: if disable button exists, API is on
                pass

        # Click enable
        clicked = False
        for label in ("有効にする", "ENABLE", "Enable"):
            btn = page.get_by_role("button", name=label)
            if await btn.count():
                await btn.first.click()
                clicked = True
                log(f"clicked: {label}")
                break
        if not clicked:
            # try text locator
            loc = page.locator("button:has-text('有効にする')")
            if await loc.count():
                await loc.first.click()
                clicked = True
                log("clicked: 有効にする (locator)")
        await page.wait_for_timeout(6000)
        body2 = await page.inner_text("body")
        # Success signals
        if any(s in body2 for s in ("API が有効", "API enabled", "無効にする", "API を管理", "Manage")):
            log("status: enabled_ok")
            return 0
        if "有効にする" in body2 and "無効にする" not in body2:
            log("status: enable_button_still_visible — may need login or billing")
            # dump short snippet without secrets
            snippet = body2.replace("\n", " ")[:400]
            log(f"body_snippet: {snippet}")
            return 2
        log("status: unknown — check console UI")
        log(body2.replace("\n", " ")[:400])
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
