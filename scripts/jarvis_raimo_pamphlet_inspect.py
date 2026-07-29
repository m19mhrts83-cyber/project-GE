#!/usr/bin/env python3
"""Inspect Raimo AI Studio pamphlet workflow UI (周辺MAP project).

Read-only reconnaissance: logs in with RAIMO_PORTAL_* from .env.jarvis_private,
walks to ライモAIスタジオ → パンフレット作成 → ワークフロー → 周辺マップ, and dumps
each step's fields/buttons so the operating manual can be written from facts.

Secrets stay inside the process (never printed).
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path.home() / "git-repos"
ENV = ROOT / ".env.jarvis_private"
OUT = Path("/tmp/raimo_pamphlet")

PROBE_JS = """()=>{
  const vis = el => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && !!el.offsetParent;
  };
  const txt = el => (el.innerText || el.value || '').trim().slice(0, 120);
  return {
    url: location.href,
    title: document.title,
    h: [...document.querySelectorAll('h1,h2,h3,h4')].filter(vis).map(txt).slice(0, 40),
    buttons: [...document.querySelectorAll('button,a[role=button],[class*=btn]')]
      .filter(vis).map(txt).filter(Boolean).slice(0, 80),
    links: [...document.querySelectorAll('a[href]')].filter(vis)
      .map(a => ({t: txt(a), href: a.getAttribute('href')}))
      .filter(x => x.t).slice(0, 80),
    inputs: [...document.querySelectorAll('input,textarea,select')].filter(vis).map(el => ({
      tag: el.tagName.toLowerCase(),
      type: el.getAttribute('type') || '',
      name: el.getAttribute('name') || '',
      ph: el.getAttribute('placeholder') || '',
      label: (el.closest('label') && el.closest('label').innerText || '').trim().slice(0, 80),
    })).slice(0, 60),
    ck: [...document.querySelectorAll('.ck-content')].length,
    bodySnippet: (document.body.innerText || '').replace(/\\n{3,}/g, '\\n\\n').slice(0, 4000),
  };
}"""


CLICK_JS = """(label)=>{
  const vis = el => { const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && !!el.offsetParent; };
  const cands = [...document.querySelectorAll('button,a,[role=button],div,span,h3,p,li')]
    .filter(vis)
    .filter(el => (el.innerText || '').includes(label))
    .filter(el => el.querySelectorAll('*').length < 25)
    .sort((a, b) => (a.innerText || '').length - (b.innerText || '').length);
  if (!cands.length) return 'not-found';
  let el = cands[0];
  for (let i = 0; i < 4; i++) {
    const r = el.getBoundingClientRect();
    if (r.height > 28 && r.width > 60) break;
    if (el.parentElement) el = el.parentElement;
  }
  el.scrollIntoView({block: 'center'});
  el.click();
  return 'clicked:' + (el.tagName + '.' + (el.className || '')).slice(0, 80);
}"""


def slug(s: str) -> str:
    keep = re.sub(r"[^0-9A-Za-z\u3040-\u30ff\u4e00-\u9fff]+", "_", s).strip("_")
    return keep[:32] or "x"


def load_env() -> None:
    for line in ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def login(page, email: str, password: str) -> None:
    page.goto("https://raimo.buzz/login", wait_until="domcontentloaded", timeout=120000)
    page.wait_for_timeout(2000)
    page.locator('input[type="email"],input[name="email"]').first.fill(email)
    page.locator('input[type="password"],input[name="password"]').first.fill(password)
    page.get_by_role("button", name=re.compile("ログイン")).first.click()
    page.wait_for_timeout(6000)


def snap(page, name: str) -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)
    info = page.evaluate(PROBE_JS)
    (OUT / f"{name}.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n===== {name} =====")
    print("url:", info["url"])
    print("headings:", info["h"][:15])
    print("buttons:", info["buttons"][:30])
    print("inputs:", json.dumps(info["inputs"][:15], ensure_ascii=False))
    studio = [l for l in info["links"] if re.search("スタジオ|studio|パンフ", l["t"] + l["href"], re.I)]
    print("studio-ish links:", json.dumps(studio[:20], ensure_ascii=False))
    return info


def main() -> int:
    load_env()
    email = os.environ.get("RAIMO_PORTAL_EMAIL")
    password = os.environ.get("RAIMO_PORTAL_PASSWORD")
    if not email or not password:
        print("missing RAIMO_PORTAL_* in env")
        return 2
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1500, "height": 1300})
        login(page, email, password)
        snap(page, "01_after_login")
        if "--studio" in sys.argv:
            btn = page.get_by_role("button", name=re.compile("ライモAI ?スタジオ"))
            try:
                with page.context.expect_page(timeout=15000) as pop:
                    btn.first.click()
                page = pop.value
                page.wait_for_load_state("domcontentloaded", timeout=60000)
            except Exception:
                btn.first.click()
            page.wait_for_timeout(7000)
            snap(page, "02_studio_top")
        step = 2
        for token in [a for a in sys.argv[1:] if not a.startswith("--")]:
            step += 1
            if token.startswith("click:"):
                label = token.split(":", 1)[1]
                clicked = page.evaluate(CLICK_JS, label)
                print(f"\nclick {label!r}: {clicked}")
                page.wait_for_timeout(6000)
                snap(page, f"{step:02d}_click_{slug(label)}")
            elif token.startswith("wait:"):
                page.wait_for_timeout(int(token.split(":", 1)[1]))
                step -= 1
            else:
                page.goto(token if token.startswith("http") else f"https://movie.raimo.buzz{token}",
                          wait_until="domcontentloaded", timeout=120000)
                page.wait_for_timeout(5000)
                snap(page, f"{step:02d}_nav_{slug(token)}")
        browser.close()
    print(f"\nartifacts: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
