#!/usr/bin/env python3
"""Update Raimo MyPrompt C2 (474298) body from 13_Raimoプロンプト_C2紙面仕上げ.md."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path.home() / "git-repos"
ENV = ROOT / ".env.jarvis_private"
PROMPT_MD = (
    ROOT
    / "215_kamiooya/C1_cursor/1c_神・大家さん倶楽部_AI推進/AI×周辺MAP/13_Raimoプロンプト_C2紙面仕上げ.md"
)
PROMPT_URL = "https://raimo.buzz/prompt/474298"
TITLE = "周辺MAP_C2_紙面仕上げ"
EDIT_URL_CANDIDATES = [
    "https://raimo.buzz/prompt/474298/edit",
    "https://raimo.buzz/myprompt/474298/edit",
]


def load_env() -> None:
    for line in ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    for a, b in [
        ("RAIMO_PORTAL_EMAIL", "LIMO_PORTAL_EMAIL"),
        ("RAIMO_PORTAL_PASSWORD", "LIMO_PORTAL_PASSWORD"),
    ]:
        if not os.environ.get(a) and os.environ.get(b):
            os.environ[a] = os.environ[b]


def body() -> str:
    text = PROMPT_MD.read_text(encoding="utf-8")
    m = re.search(r"## プロンプト本文.*?\n```\n(.*?)```", text, re.S)
    if not m:
        raise SystemExit("no body in md")
    return m.group(1).strip()


def login(page, email: str, password: str) -> None:
    page.goto("https://raimo.buzz/login", wait_until="domcontentloaded", timeout=120000)
    page.wait_for_timeout(1500)
    email_box = page.locator('input[name="email"]').first
    if not email_box.count():
        email_box = page.locator('input[type="email"], input[placeholder*="@"]').first
    email_box.fill(email)
    page.locator('input[name="password"], input[type="password"]').first.fill(password)
    page.get_by_role("button", name=re.compile("ログイン")).first.click()
    page.wait_for_timeout(5000)


def fill_largest_textarea(page, text: str) -> bool:
    return page.evaluate(
        """(body) => {
          const areas=[...document.querySelectorAll('textarea,[contenteditable=true]')];
          areas.sort((a,c)=>(c.clientHeight*c.clientWidth)-(a.clientHeight*a.clientWidth));
          if (!areas[0]) return false;
          const el=areas[0];
          if (el.isContentEditable) { el.focus(); el.innerText=body; }
          else { el.focus(); el.value=body; }
          el.dispatchEvent(new Event('input',{bubbles:true}));
          el.dispatchEvent(new Event('change',{bubbles:true}));
          return true;
        }""",
        text,
    )


def click_save(page) -> str:
    for name in ("保存", "更新", "登録", "作成する", "完了"):
        btn = page.get_by_role("button", name=re.compile(name))
        if btn.count():
            btn.first.click()
            page.wait_for_timeout(3500)
            return name
    # fallback: any button containing 保存
    if page.locator("button:has-text('保存')").count():
        page.locator("button:has-text('保存')").first.click()
        page.wait_for_timeout(3500)
        return "保存(fallback)"
    return ""


def ensure_variables(page) -> None:
    """Best-effort: open variable UI and add missing names if controls exist."""
    wanted = ["物件名", "Access帯", "各ピン文言", "エリア一言", "タッチの強さ", "動線"]
    page.evaluate(
        """(wanted) => {
          const txt = document.body.innerText || '';
          return wanted.map(w => ({w, present: txt.includes('{'+w+'}') || txt.includes(w)}));
        }""",
        wanted,
    )


def main() -> int:
    load_env()
    email = os.environ["RAIMO_PORTAL_EMAIL"]
    password = os.environ["RAIMO_PORTAL_PASSWORD"]
    prompt_body = body()
    print("body_chars", len(prompt_body))

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 1100})
        login(page, email, password)

        # Open prompt page and find edit
        page.goto(PROMPT_URL, wait_until="domcontentloaded", timeout=120000)
        page.wait_for_timeout(2500)
        page.screenshot(path="/tmp/raimo_c2_before.png", full_page=True)
        print("opened", page.url)

        edited = False
        # Try explicit edit buttons
        for label in ("編集", "プロンプトを編集", "修正"):
            loc = page.get_by_role("button", name=re.compile(label))
            if loc.count():
                loc.first.click()
                page.wait_for_timeout(3000)
                print("clicked", label, page.url)
                edited = True
                break
            loc2 = page.get_by_role("link", name=re.compile(label))
            if loc2.count():
                loc2.first.click()
                page.wait_for_timeout(3000)
                print("clicked link", label, page.url)
                edited = True
                break

        if not edited:
            for u in EDIT_URL_CANDIDATES:
                page.goto(u, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(2000)
                if page.locator("textarea").count() or page.locator("[contenteditable=true]").count():
                    print("edit_url_ok", page.url)
                    edited = True
                    break

        if not edited:
            # From myprompt list → open title → edit
            page.goto("https://raimo.buzz/myprompt", wait_until="domcontentloaded", timeout=120000)
            page.wait_for_timeout(2500)
            if page.get_by_text("AI周辺MAP").count():
                page.get_by_text("AI周辺MAP").first.click()
                page.wait_for_timeout(1000)
            if page.get_by_text(TITLE).count():
                page.get_by_text(TITLE).first.click()
                page.wait_for_timeout(2500)
                print("opened from list", page.url)
                for label in ("編集", "プロンプトを編集", "修正"):
                    if page.get_by_role("button", name=re.compile(label)).count():
                        page.get_by_role("button", name=re.compile(label)).first.click()
                        page.wait_for_timeout(3000)
                        edited = True
                        print("clicked", label)
                        break

        page.screenshot(path="/tmp/raimo_c2_edit.png", full_page=True)
        print("edit_page", page.url)

        ok = fill_largest_textarea(page, prompt_body)
        print("filled_body", ok)
        if not ok:
            page.screenshot(path="/tmp/raimo_c2_nofill.png", full_page=True)
            print("FAIL: no textarea")
            browser.close()
            return 1

        # If multi-step wizard
        if page.locator('button:has-text("次へ")').count():
            page.locator('button:has-text("次へ")').first.click()
            page.wait_for_timeout(3000)
            fill_largest_textarea(page, prompt_body)
            print("step2 filled")

        ensure_variables(page)
        saved = click_save(page)
        print("save", saved or "NONE")
        page.wait_for_timeout(2000)
        page.screenshot(path="/tmp/raimo_c2_after.png", full_page=True)
        print("final_url", page.url)
        print("PROMPT_URL=" + PROMPT_URL)
        browser.close()
        return 0 if ok and saved else 2


if __name__ == "__main__":
    raise SystemExit(main())
