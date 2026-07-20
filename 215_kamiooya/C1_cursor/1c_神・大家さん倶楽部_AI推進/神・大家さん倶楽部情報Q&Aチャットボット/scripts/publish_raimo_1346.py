#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Publish local miniApp front+API to Raimo 1346 via save + backend API + deploy."""

from __future__ import annotations

import os
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

CHATBOT = Path(__file__).resolve().parents[1]
OUT = CHATBOT / ".raimo_export_1346"
APP_ID = 1346
BACKEND_ID = 1046


def load_env() -> None:
    roots = [
        Path.home() / "git-repos" / ".env.jarvis_private",
        CHATBOT / "scripts" / ".env",
    ]
    for p in roots:
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    for a, b in [
        ("RAIMO_PORTAL_EMAIL", "LIMO_PORTAL_EMAIL"),
        ("RAIMO_PORTAL_PASSWORD", "LIMO_PORTAL_PASSWORD"),
        ("RAIMO_APP_URL", "LIMO_APP_URL"),
    ]:
        if not os.environ.get(a) and os.environ.get(b):
            os.environ[a] = os.environ[b]


def inject_notify_placeholders(api_yaml: str) -> str:
    """Replace __NOTIFY_*__ in API YAML with values from env (not left as placeholders)."""
    if "__NOTIFY_WEBHOOK_URL__" not in api_yaml and "__NOTIFY_SHARED_SECRET__" not in api_yaml:
        return api_yaml
    url = (os.environ.get("NOTIFY_WEBHOOK_URL") or "").strip()
    secret = (os.environ.get("NOTIFY_SHARED_SECRET") or "").strip()
    if not url or url.startswith("https://script.google.com/macros/s/PASTE"):
        raise SystemExit(
            "NOTIFY_WEBHOOK_URL が未設定です。.env.jarvis_private を確認してください。"
        )
    if not secret:
        raise SystemExit("NOTIFY_SHARED_SECRET が未設定です。")
    out = api_yaml.replace("__NOTIFY_WEBHOOK_URL__", url)
    out = out.replace("__NOTIFY_SHARED_SECRET__", secret)
    print("notify placeholders: injected (webhook+secret)")
    return out


def main() -> int:
    load_env()
    email = os.environ["RAIMO_PORTAL_EMAIL"]
    password = os.environ["RAIMO_PORTAL_PASSWORD"]
    app_url = (os.environ.get("RAIMO_APP_URL") or "").rstrip("/")

    html = (CHATBOT / "index.html").read_text(encoding="utf-8")
    css = (CHATBOT / "style.css").read_text(encoding="utf-8")
    js = (CHATBOT / "app.js").read_text(encoding="utf-8")
    api = (CHATBOT / "WeStudy_API_secret_admin_upgrade.yaml").read_text(encoding="utf-8")
    api = inject_notify_placeholders(api)

    marker = "<!-- RAIMO_KNOWLEDGE_UI_20260720 -->"
    if marker not in html:
        html = html.replace("<!DOCTYPE html>", "<!DOCTYPE html>\n" + marker, 1)
        (CHATBOT / "index.html").write_text(html, encoding="utf-8")

    OUT.mkdir(exist_ok=True)
    base = "https://raimo.buzz"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"{base}/login", wait_until="networkidle", timeout=120000)
        page.fill('input[type="email"], input[placeholder*="company"]', email)
        page.fill('input[type="password"]', password)
        page.click('button:has-text("ログイン")')
        page.wait_for_timeout(5000)

        page.goto(f"{base}/miniApp/{APP_ID}/edit", wait_until="domcontentloaded", timeout=180000)
        page.wait_for_timeout(5000)
        assert "権限がありません" not in page.inner_text("body")

        detail = page.request.get(f"{base}/gpt/api/miniApp/{APP_ID}", timeout=60000)
        assert detail.status == 200, detail.text()[:200]
        title = (detail.json() or {}).get("title") or "神大家さん倶楽部AIチャットボット"

        save = page.request.post(
            f"{base}/gpt/api/miniApp/{APP_ID}/save",
            data={
                "title": title,
                "htmlContent": html,
                "cssContent": css,
                "jsContent": js,
            },
            timeout=120000,
        )
        print("save front", save.status)
        sj = save.json() if save.status == 200 else {}
        print(
            "front markers",
            {
                "html": marker in (sj.get("htmlContent") or ""),
                "js": "buildCitationsFromRelated" in (sj.get("jsContent") or ""),
            },
        )

        # API YAML is stored on miniAppBackend, not miniApp save payload
        api_put = page.request.put(
            f"{base}/gpt/api/miniAppBackend/{BACKEND_ID}/api",
            data={"apiDefinition": api},
            timeout=120000,
        )
        print("save api", api_put.status, api_put.text()[:160].replace("\n", " "))

        deploy = page.request.post(
            f"{base}/gpt/api/miniApp/{APP_ID}/deploy",
            data={},
            timeout=120000,
        )
        print("deploy", deploy.status)

        # confirm backend dsl
        be = page.request.get(f"{base}/gpt/api/miniAppBackend/{BACKEND_ID}", timeout=60000)
        dsl = ""
        if be.status == 200:
            api_list = (be.json().get("miniAppBackend") or {}).get("apiList") or []
            if api_list:
                dsl = api_list[0].get("dslContent") or ""
        print(
            "backend dsl",
            {
                "len": len(dsl),
                "updateKnowledgeSource": "updateKnowledgeSource" in dsl,
                "relatedSources": "relatedSources" in dsl,
            },
        )
        browser.close()

    time.sleep(2)
    if app_url:
        live = urllib.request.urlopen(app_url + "/?t=" + str(int(time.time())), timeout=30).read().decode(
            "utf-8", "replace"
        )
        js_live = urllib.request.urlopen(app_url + "/app.js?t=" + str(int(time.time())), timeout=30).read().decode(
            "utf-8", "replace"
        )
        print(
            "live",
            {
                "marker": marker in live,
                "seminar": "セミナー動画" in live,
                "citations": "buildCitationsFromRelated" in js_live,
                "html_len": len(live),
                "js_len": len(js_live),
            },
        )
    print("DONE publish")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
