#!/usr/bin/env python3
"""Create Raimo MyPrompt C1: click 通常プロンプト then fill title/body/vars."""
from __future__ import annotations

import os
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path.home() / "git-repos"
ENV = ROOT / ".env.jarvis_private"
PROMPT_MD = (
    ROOT
    / "215_kamiooya/C1_cursor/1c_神・大家さん倶楽部_AI推進/AI×周辺MAP/11_Raimoプロンプト_C1下地色味寄せ.md"
)
TITLE = "周辺MAP_C1_下地色味寄せ"


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
        raise SystemExit("no body")
    return m.group(1).strip()


def main() -> int:
    load_env()
    email = os.environ["RAIMO_PORTAL_EMAIL"]
    password = os.environ["RAIMO_PORTAL_PASSWORD"]
    prompt_body = body()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 1000})
        page.goto("https://raimo.buzz/login", wait_until="domcontentloaded", timeout=120000)
        page.locator('input[type="email"]').first.fill(email)
        page.locator('input[type="password"]').first.fill(password)
        page.get_by_role("button", name=re.compile("ログイン")).first.click()
        page.wait_for_timeout(4000)

        page.goto("https://raimo.buzz/myprompt", wait_until="domcontentloaded", timeout=120000)
        page.wait_for_timeout(2500)
        if page.get_by_text("AI周辺MAP").count():
            page.get_by_text("AI周辺MAP").first.click()
            page.wait_for_timeout(800)
        if page.get_by_text(TITLE).count():
            href = page.evaluate(
                """(t)=>{const a=[...document.querySelectorAll('a')].find(x=>(x.textContent||'').includes(t));return a?a.href:'';}""",
                TITLE,
            )
            print("exists", href)
            print("PROMPT_URL=" + (href or "unknown"))
            browser.close()
            return 0

        page.get_by_role("button", name=re.compile("プロンプト新規作成")).first.click()
        page.wait_for_timeout(2500)
        # Choose 通常プロンプト card
        page.get_by_text("通常プロンプト", exact=True).first.click()
        page.wait_for_timeout(4000)
        page.screenshot(path="/tmp/raimo_c1_form.png", full_page=True)
        print("form_url", page.url)

        info = page.evaluate(
            """({title, body}) => {
              const dump = [...document.querySelectorAll('input,textarea,[contenteditable=true]')].map(el => ({
                tag: el.tagName, type: el.type||'', ph: el.placeholder||'', id: el.id||'',
                name: el.name||'', ce: !!el.isContentEditable, w: el.clientWidth, h: el.clientHeight
              }));
              let t=false,b=false;
              for (const el of document.querySelectorAll('input')) {
                const meta=(el.placeholder+el.name+el.id).toLowerCase();
                if (/title|タイトル|name|名称/.test(meta) || el.type==='text') {
                  el.value=title; el.dispatchEvent(new Event('input',{bubbles:true})); t=true; break;
                }
              }
              const areas=[...document.querySelectorAll('textarea,[contenteditable=true]')];
              areas.sort((a,c)=>(c.clientHeight*c.clientWidth)-(a.clientHeight*a.clientWidth));
              if (areas[0]) {
                const el=areas[0];
                if (el.isContentEditable) el.innerText=body; else { el.value=body; el.dispatchEvent(new Event('input',{bubbles:true})); }
                b=true;
              }
              return {t,b,dump:dump.slice(0,20)};
            }""",
            {"title": TITLE, "body": prompt_body},
        )
        print("fill", info)

        # Step1 form uses 次へ → Step2 textarea uses 作成する
        if page.locator('button:has-text("次へ")').count():
            page.locator('button:has-text("次へ")').first.click()
            page.wait_for_timeout(4000)
            print("clicked 次へ", page.url)
            if page.locator("textarea").count():
                page.locator("textarea").first.fill(prompt_body)
                print("filled step2 body")
            if page.locator('button:has-text("作成する")').count():
                page.locator('button:has-text("作成する")').first.click()
                print("clicked 作成する")
                page.wait_for_timeout(5000)
        else:
            for name in ("保存", "登録", "作成", "完了", "公開"):
                btn = page.get_by_role("button", name=re.compile(f"^{name}$|^{name}"))
                if btn.count():
                    btn.first.click()
                    print("clicked", name)
                    page.wait_for_timeout(3000)
                    break
        page.screenshot(path="/tmp/raimo_c1_saved.png", full_page=True)
        print("url", page.url)
        m = re.search(r"/prompt/(\d+)", page.url)
        if m:
            print("PROMPT_URL=https://raimo.buzz/prompt/" + m.group(1))
        else:
            page.goto("https://raimo.buzz/myprompt")
            page.wait_for_timeout(2000)
            if page.get_by_text("AI周辺MAP").count():
                page.get_by_text("AI周辺MAP").first.click()
                page.wait_for_timeout(800)
            href = page.evaluate(
                """(t)=>{const a=[...document.querySelectorAll('a')].find(x=>(x.textContent||'').includes(t));return a?a.href:'';}""",
                TITLE,
            )
            print("PROMPT_URL=" + (href or "PENDING_MANUAL"))
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
