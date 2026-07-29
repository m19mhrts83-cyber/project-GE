#!/usr/bin/env python3
"""List Raimo MyPrompts matching Step4.1 and delete duplicates (keep 474298)."""
from __future__ import annotations

import os
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path.home() / "git-repos"
ENV = ROOT / ".env.jarvis_private"
KEEP_ID = "474298"  # Step4.1 紙面仕上げ（正）


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


def login(page, email: str, password: str) -> None:
    page.goto("https://raimo.buzz/login", wait_until="domcontentloaded", timeout=120000)
    page.wait_for_timeout(1800)
    page.locator('input[type="email"],input[name="email"]').first.fill(email)
    page.locator('input[type="password"],input[name="password"]').first.fill(password)
    page.get_by_role("button", name=re.compile("ログイン")).first.click()
    page.wait_for_timeout(5000)


def collect_step41(page) -> list[dict]:
    """Return [{id, title, href}] for prompts whose title mentions Step4.1."""
    urls = [
        "https://raimo.buzz/myprompt",
        "https://raimo.buzz/gpt/myprompt",
        "https://raimo.buzz/prompt",
    ]
    found: dict[str, dict] = {}
    for url in urls:
        page.goto(url, wait_until="domcontentloaded", timeout=120000)
        page.wait_for_timeout(2500)
        # search box if any
        for sel in ['input[placeholder*="検索"]', 'input[type="search"]', 'input[name*="search"]']:
            box = page.locator(sel)
            if box.count():
                try:
                    box.first.fill("Step4.1")
                    page.wait_for_timeout(1500)
                except Exception:
                    pass
                break
        items = page.evaluate(
            """()=>{
          const out=[];
          const links=[...document.querySelectorAll('a[href*="/prompt/"]')];
          for(const a of links){
            const href=a.getAttribute('href')||'';
            const m=href.match(/\\/prompt\\/(\\d+)/);
            if(!m) continue;
            const id=m[1];
            const title=(a.innerText||a.textContent||'').replace(/\\s+/g,' ').trim();
            if(!/Step\\s*4\\.1|ステップ\\s*4\\.1|周辺MAP_Step4\\.1/i.test(title)
               && !/Step\\s*4\\.1|ステップ\\s*4\\.1|周辺MAP_Step4\\.1/i.test(
                    (a.closest('tr,li,div,article,section')||a).innerText||'')) continue;
            // Prefer link text; fallback to card text first line
            let t=title;
            if(!t || t.length<3){
              const card=(a.closest('tr,li,div,article,section')||a);
              t=(card.innerText||'').split('\\n').map(s=>s.trim()).find(s=>/Step\\s*4\\.1|ステップ\\s*4\\.1|周辺MAP_Step4\\.1/i.test(s))||'';
            }
            if(!/4\\.1/.test(t) && !/4\\.1/.test(title)) continue;
            if(!out.find(x=>x.id===id)) out.push({id, title:t||title||('(no title '+id+')'), href:href.startsWith('http')?href:('https://raimo.buzz'+href)});
          }
          // Also scan cards without relying only on link text
          const cards=[...document.querySelectorAll('a,div,li,article')].filter(el=>{
            const t=(el.innerText||'').replace(/\\s+/g,' ');
            return /【?周辺MAP_Step4\\.1|Step4\\.1|ステップ4\\.1/.test(t) && t.length<200;
          });
          for(const el of cards){
            const a=el.closest('a')||el.querySelector('a[href*="/prompt/"]')||el;
            const href=(a.getAttribute&&a.getAttribute('href'))||'';
            const m=String(href).match(/\\/prompt\\/(\\d+)/);
            if(!m) continue;
            const id=m[1];
            const title=(el.innerText||'').split('\\n').map(s=>s.trim()).find(s=>/4\\.1/.test(s))||('prompt '+id);
            if(!out.find(x=>x.id===id)) out.push({id, title, href:href.startsWith('http')?href:('https://raimo.buzz'+href)});
          }
          return out;
        }"""
        )
        for it in items:
            found[it["id"]] = it
        page.screenshot(path=f"/tmp/raimo_myprompt_{url.split('/')[-1]}.png", full_page=True)
    return list(found.values())


def try_delete(page, pid: str) -> str:
    page.goto(f"https://raimo.buzz/prompt/{pid}", wait_until="domcontentloaded", timeout=120000)
    page.wait_for_timeout(2000)
    page.screenshot(path=f"/tmp/raimo_before_del_{pid}.png", full_page=True)
    # edit page sometimes at /gpt/prompt/{id}
    title = page.evaluate(
        """()=>{
      const h=document.querySelector('h1,h2,.title,[class*="title"]');
      return (h&&h.innerText)||document.title||'';
    }"""
    )
    # Look for delete / 削除
    clicked = page.evaluate(
        """()=>{
      const btns=[...document.querySelectorAll('button,a,[role="button"]')];
      const del=btns.find(b=>{
        const t=(b.innerText||b.getAttribute('aria-label')||'').trim();
        return /削除|Delete|ゴミ箱/.test(t);
      });
      if(!del) return '';
      del.scrollIntoView({block:'center'});
      del.click();
      return (del.innerText||'').trim();
    }"""
    )
    page.wait_for_timeout(1500)
    # confirm dialog
    confirmed = page.evaluate(
        """()=>{
      const btns=[...document.querySelectorAll('button,a,[role="button"]')];
      const ok=btns.find(b=>{
        const t=(b.innerText||'').trim();
        return /削除する|削除|はい|OK|確認|実行/.test(t) && !/キャンセル|やめる/.test(t);
      });
      if(!ok) return '';
      ok.click();
      return (ok.innerText||'').trim();
    }"""
    )
    page.wait_for_timeout(3000)
    # alternate edit URL
    if not clicked:
        page.goto(f"https://raimo.buzz/gpt/prompt/{pid}", wait_until="domcontentloaded", timeout=120000)
        page.wait_for_timeout(2000)
        clicked = page.evaluate(
            """()=>{
          const btns=[...document.querySelectorAll('button,a,[role="button"]')];
          const del=btns.find(b=>/削除|Delete|ゴミ箱/.test((b.innerText||b.getAttribute('aria-label')||'').trim()));
          if(!del) return '';
          del.click();
          return (del.innerText||'').trim();
            }"""
        )
        page.wait_for_timeout(1500)
        confirmed = page.evaluate(
            """()=>{
          const btns=[...document.querySelectorAll('button,a,[role="button"]')];
          const ok=btns.find(b=>{
            const t=(b.innerText||'').trim();
            return /削除する|削除|はい|OK|確認|実行/.test(t) && !/キャンセル|やめる/.test(t);
          });
          if(!ok) return '';
          ok.click();
          return (ok.innerText||'').trim();
            }"""
        )
        page.wait_for_timeout(3000)
    page.screenshot(path=f"/tmp/raimo_after_del_{pid}.png", full_page=True)
    return f"title={title!r} click={clicked!r} confirm={confirmed!r} url={page.url}"


def main() -> None:
    load_env()
    email = os.environ.get("RAIMO_PORTAL_EMAIL") or ""
    password = os.environ.get("RAIMO_PORTAL_PASSWORD") or ""
    if not email or not password:
        raise SystemExit("RAIMO_PORTAL_EMAIL/PASSWORD missing")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        login(page, email, password)
        items = collect_step41(page)
        print("FOUND", len(items))
        for it in items:
            mark = "KEEP" if it["id"] == KEEP_ID else "CANDIDATE"
            print(f"  [{mark}] {it['id']}  {it['title'][:80]}  {it['href']}")

        # Also check known IDs
        for pid in ["474298", "474383", "474382"]:
            page.goto(f"https://raimo.buzz/prompt/{pid}", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(1200)
            t = page.evaluate(
                "()=>(document.querySelector('h1,h2')||{}).innerText||document.title||''"
            )
            print(f"CHECK {pid}: {t[:100]!r} url={page.url}")

        to_delete = [it for it in items if it["id"] != KEEP_ID]
        # If list empty, try deleting known duplicate draft 474382 (old Step4.1 draft)
        if not to_delete:
            print("No duplicate titles in list scan; will inspect 474382/474383 titles")
        for it in to_delete:
            print("DELETE", it["id"], it["title"][:60])
            print(" ", try_delete(page, it["id"]))

        # Re-list
        items2 = collect_step41(page)
        print("AFTER", len(items2))
        for it in items2:
            print(f"  {it['id']}  {it['title'][:80]}")

        browser.close()


if __name__ == "__main__":
    main()
