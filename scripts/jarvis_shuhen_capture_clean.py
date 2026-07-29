#!/usr/bin/env python3
"""Capture clean-base screenshots from local shuhen-map.html via Playwright.

Saves pinless / with-pins PNGs into AI×周辺MAP/試走出力 (git-repos + OneDrive).
Uses GOOGLE_MAPS_API_KEY from .env.jarvis_private (never printed).
"""
from __future__ import annotations

import asyncio
import http.server
import socketserver
import threading
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / ".env.jarvis_private"
OUT_DIRS = [
    ROOT
    / "215_kamiooya"
    / "C1_cursor"
    / "1c_神・大家さん倶楽部_AI推進"
    / "AI×周辺MAP"
    / "試走出力",
    Path.home()
    / "Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部"
    / "C1_cursor/1c_神・大家さん倶楽部_AI推進/AI×周辺MAP/試走出力",
]
PORT = 8765


def load_key() -> str:
    for line in ENV.read_text(encoding="utf-8").splitlines():
        if line.startswith("GOOGLE_MAPS_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("GOOGLE_MAPS_API_KEY missing")


def start_server() -> socketserver.TCPServer:
    handler = http.server.SimpleHTTPRequestHandler
    # silence logs
    class Quiet(handler):
        def log_message(self, *args):  # noqa: ANN002
            return

    httpd = socketserver.TCPServer(("127.0.0.1", PORT), Quiet)
    httpd.allow_reuse_address = True
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd


async def capture() -> None:
    key = load_key()
    httpd = start_server()
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 1400, "height": 900})
            await page.goto(f"http://127.0.0.1:{PORT}/shuhen-map.html", wait_until="domcontentloaded")
            await page.fill("#apiKeyInput", key)
            await page.evaluate(
                """(k) => { localStorage.setItem('googleMapsApiKey', k); localStorage.setItem('shuhenCleanStyle','1'); }""",
                key,
            )
            await page.click("#presetButton")
            await page.click("#pinButton")
            await page.wait_for_selector("#resultsSection", state="visible", timeout=120000)
            await page.wait_for_function(
                "() => typeof map !== 'undefined' && map && map.getZoom && map.getZoom() >= 13",
                timeout=120000,
            )
            await page.wait_for_timeout(2500)

            if not await page.is_checked("#cleanStyleToggle"):
                await page.check("#cleanStyleToggle")
            await page.click("#applyStyleButton")
            await page.wait_for_timeout(1200)

            # map-only → resize 後に bounds を締め直す
            await page.click("#mapOnlyButton")
            await page.wait_for_timeout(800)
            await page.evaluate(
                """() => {
                  const bar = document.getElementById('mapOnlyBar');
                  if (bar) bar.style.display = 'none';
                  if (!map || !markers || !markers.length) return;
                  const b = new google.maps.LatLngBounds();
                  markers.forEach((m) => { if (m.getPosition) b.extend(m.getPosition()); });
                  map.fitBounds(b, 72);
                  google.maps.event.addListenerOnce(map, 'idle', () => {
                    const z = map.getZoom();
                    if (z < 14) map.setZoom(14);
                    if (z > 16) map.setZoom(16);
                  });
                }"""
            )
            await page.wait_for_timeout(3500)
            map_el = page.locator("#map")

            for d in OUT_DIRS:
                d.mkdir(parents=True, exist_ok=True)
                path = d / "基準_骨格図_Grandole_クリーン.png"
                await map_el.screenshot(path=str(path))
                print(f"wrote {path} ({path.stat().st_size})")

            # ピン隠し（下地）
            await page.evaluate(
                """() => {
                  const t = document.getElementById('hidePinsToggle');
                  if (t) { t.checked = true; }
                  if (typeof applyMapDisplayOptions === 'function') applyMapDisplayOptions();
                  const bar = document.getElementById('mapOnlyBar');
                  if (bar) bar.style.display = 'none';
                }"""
            )
            await page.wait_for_timeout(2000)

            for d in OUT_DIRS:
                path = d / "基準_下地_Grandole_クリーン.png"
                await map_el.screenshot(path=str(path))
                print(f"wrote {path} ({path.stat().st_size})")

            await browser.close()
    finally:
        httpd.shutdown()


if __name__ == "__main__":
    # serve from repo root where shuhen-map.html lives
    import os

    os.chdir(ROOT)
    asyncio.run(capture())
