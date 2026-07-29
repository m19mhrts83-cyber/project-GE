#!/usr/bin/env python3
"""Register Raimo MyPrompt Step4.1 (通常・2ステップ: 次へ→コード入力→作成する)."""
from __future__ import annotations

import os
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path.home() / "git-repos"
ENV = ROOT / ".env.jarvis_private"
PROMPT_MD = (
    ROOT
    / "215_kamiooya/C1_cursor/1c_神・大家さん倶楽部_AI推進/AI×周辺MAP"
    / "14_Raimoプロンプト_Step4.1画像検証.md"
)
TITLE = "【周辺MAP_Step4.1】画像検証・修正提案"
FOLDER = "AI周辺MAP"


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


SET_DATA_JS = """(body)=>{
  const esc=s=>s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  const html=body.split('\\n').map(l=> l.trim()===''? '<p>&nbsp;</p>' : '<p>'+esc(l)+'</p>').join('');
  const eds=[...document.querySelectorAll('.ck-content')].filter(e=>e.ckeditorInstance);
  const t=eds[0];
  if(!t) return {ok:false};
  t.ckeditorInstance.setData(html);
  return {ok:true, has:t.ckeditorInstance.getData().includes('2枚が必須')};
}"""


def set_private(page) -> bool:
    return page.evaluate("""()=>{
      const card=[...document.querySelectorAll('*')].find(x=>{
        const t=(x.innerText||'').trim();
        return /^自分のみ公開/.test(t) && x.querySelectorAll('*').length<8;
      });
      if(!card) return false;
      let clickable=card;
      for(let i=0;i<3&&clickable.parentElement;i++){
        if(clickable.getBoundingClientRect().height>60) break;
        clickable=clickable.parentElement;
      }
      clickable.click(); return true;
    }""")


def fill_title(page, title: str) -> bool:
    return page.evaluate("""(title)=>{
      const inputs=[...document.querySelectorAll('input[type=text],input:not([type])')];
      for (const el of inputs) {
        const meta=((el.placeholder||'')+(el.name||'')+(el.id||'')).toLowerCase();
        if (/title|タイトル|name|名称|プロンプト名/.test(meta) || el.clientWidth>200) {
          el.focus(); el.value='';
          el.value=title;
          el.dispatchEvent(new Event('input',{bubbles:true}));
          el.dispatchEvent(new Event('change',{bubbles:true}));
          return true;
        }
      }
      return false;
    }""", title)


def find_prompt_url(page) -> str:
    page.goto("https://raimo.buzz/myprompt", wait_until="domcontentloaded")
    page.wait_for_timeout(2500)
    if page.get_by_text(FOLDER).count():
        page.get_by_text(FOLDER).first.click()
        page.wait_for_timeout(1000)
    href = page.evaluate(
        """(t)=>{
          const a=[...document.querySelectorAll('a')].find(x=>(x.textContent||'').includes(t));
          return a?a.href:'';
        }""",
        "Step4.1",
    )
    return href or ""


def main() -> int:
    load_env()
    email = os.environ["RAIMO_PORTAL_EMAIL"]
    password = os.environ["RAIMO_PORTAL_PASSWORD"]
    prompt_body = body()
    print("body_len", len(prompt_body))

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 1100})
        page.goto("https://raimo.buzz/login", wait_until="domcontentloaded", timeout=120000)
        page.wait_for_timeout(1500)
        page.locator('input[type="email"],input[name="email"]').first.fill(email)
        page.locator('input[type="password"],input[name="password"]').first.fill(password)
        page.get_by_role("button", name=re.compile("ログイン")).first.click()
        page.wait_for_timeout(4500)

        existing = find_prompt_url(page)
        if existing:
            print("exists", existing)
            print("PROMPT_URL=" + existing)
            browser.close()
            return 0

        page.get_by_role("button", name=re.compile("プロンプト新規作成")).first.click()
        page.wait_for_timeout(2500)
        page.get_by_text("通常プロンプト", exact=True).first.click()
        page.wait_for_timeout(4000)
        print("step1_url", page.url)

        print("title_filled", fill_title(page, TITLE))
        set_private(page)
        page.wait_for_timeout(400)
        print("setData", page.evaluate(SET_DATA_JS, prompt_body))
        page.screenshot(path="/tmp/raimo_step41_s1.png", full_page=True)

        # Step1 → 次へ
        page.locator('button:has-text("次へ")').first.click()
        page.wait_for_timeout(4000)
        print("step2_url", page.url)
        page.screenshot(path="/tmp/raimo_step41_s2.png", full_page=True)

        # Step2: コード入力 textarea
        ta = page.locator("textarea").first
        if ta.count():
            ta.fill(prompt_body)
            print("filled_textarea", True, "len", len(prompt_body))
        else:
            # contenteditable fallback
            page.evaluate("""(body)=>{
              const el=document.querySelector('[contenteditable=true],textarea');
              if(!el) return false;
              if(el.isContentEditable) el.innerText=body;
              else { el.value=body; el.dispatchEvent(new Event('input',{bubbles:true})); }
              return true;
            }""", prompt_body)
            print("filled_fallback")

        page.wait_for_timeout(800)
        page.screenshot(path="/tmp/raimo_step41_s2b.png", full_page=True)

        page.locator('button:has-text("作成する")').first.click()
        page.wait_for_timeout(6000)
        page.screenshot(path="/tmp/raimo_step41_done.png", full_page=True)
        print("after_create_url", page.url)

        m = re.search(r"/prompt/(\d+)", page.url)
        if m:
            url = "https://raimo.buzz/prompt/" + m.group(1)
            print("PROMPT_URL=" + url)
        else:
            href = find_prompt_url(page)
            print("PROMPT_URL=" + (href or "PENDING_MANUAL"))
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
