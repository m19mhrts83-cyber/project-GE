#!/usr/bin/env python3
"""Re-register 周辺MAP MyPrompts to Raimo (CKEditor 5 + multi-step wizard).

Root cause fixed upstream: nested ``` code fences no longer truncate body
extraction. Raimo editor is CKEditor 5 (setData required) and the save form
requires a valid 公開設定. We set 公開設定=自分のみ公開 (per user decision) so the
共有グループ validation does not block save, then walk 次へ to the save button.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path.home() / "git-repos"
ENV = ROOT / ".env.jarvis_private"
MAP = ROOT / "215_kamiooya/C1_cursor/1c_神・大家さん倶楽部_AI推進/AI×周辺MAP"

TARGETS = {
    "473911": ("01_Raimoプロンプト_Step1基本洗い出し.md", r"## プロンプト本文.*?\n```\n(.*?)```"),
    "473910": ("02_DeepResearchプロンプト_評判店リサーチ.md", r"## Deep Research 用プロンプト本文.*?\n```\n(.*?)```"),
    "473916": ("05_Raimoプロンプト_アドバンス_周辺MAP洗い出し.md", r"## プロンプト本文.*?\n```\n(.*?)```"),
}
MARKER = "P1 | 検索クエリ | 表示名"


def load_env() -> None:
    for line in ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    for a, b in [("RAIMO_PORTAL_EMAIL", "LIMO_PORTAL_EMAIL"),
                 ("RAIMO_PORTAL_PASSWORD", "LIMO_PORTAL_PASSWORD")]:
        if not os.environ.get(a) and os.environ.get(b):
            os.environ[a] = os.environ[b]


def extract_body(md_name: str, pattern: str) -> str:
    text = (MAP / md_name).read_text(encoding="utf-8")
    m = re.search(pattern, text, re.S)
    if not m:
        raise SystemExit(f"no body in {md_name}")
    b = m.group(1).strip()
    if MARKER not in b:
        raise SystemExit(f"marker missing in {md_name}")
    return b


def login(page, email, password):
    page.goto("https://raimo.buzz/login", wait_until="domcontentloaded", timeout=120000)
    page.wait_for_timeout(1800)
    page.locator('input[type="email"],input[name="email"]').first.fill(email)
    page.locator('input[type="password"],input[name="password"]').first.fill(password)
    page.get_by_role("button", name=re.compile("ログイン")).first.click()
    page.wait_for_timeout(5000)


SET_DATA_JS = """(body)=>{
  const esc=s=>s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  const html=body.split('\\n').map(l=> l.trim()===''? '<p>&nbsp;</p>' : '<p>'+esc(l)+'</p>').join('');
  const eds=[...document.querySelectorAll('.ck-content')].filter(e=>e.ckeditorInstance);
  let t=eds.find(e=>{const d=e.ckeditorInstance.getData();return d.includes('前提条件')||d.includes('実行指示')||d.includes('調査対象');})||eds[0];
  if(!t) return {ok:false};
  t.ckeditorInstance.setData(html);
  return {ok:true, mark:t.ckeditorInstance.getData().includes('P1 | 検索クエリ | 表示名')};
}"""

VISIBLE_SAVE_JS = """()=>{
  const b=[...document.querySelectorAll('button')].find(x=>{
    const t=(x.innerText||'').trim();
    if(!['更新する','保存する','作成する'].includes(t)) return false;
    const r=x.getBoundingClientRect(); return r.height>0 && !!x.offsetParent;
  });
  if(b){ b.scrollIntoView({block:'center'}); b.click(); return (b.innerText||'').trim(); }
  return '';
}"""


def set_private(page) -> bool:
    return page.evaluate("""()=>{
      const card=[...document.querySelectorAll('*')].find(x=>{
        const t=(x.innerText||'').trim();
        return /^自分のみ公開/.test(t) && x.querySelectorAll('*').length<6;
      });
      if(!card) return false;
      let clickable=card; for(let i=0;i<3&&clickable.parentElement;i++){ if(clickable.getBoundingClientRect().height>60) break; clickable=clickable.parentElement; }
      clickable.click(); return true;
    }""")


def update_one(page, pid: str, body: str) -> dict:
    page.goto(f"https://raimo.buzz/gpt/prompt/{pid}", wait_until="domcontentloaded", timeout=120000)
    page.wait_for_timeout(3000)
    priv = set_private(page)
    page.wait_for_timeout(800)
    sd = page.evaluate(SET_DATA_JS, body)
    page.wait_for_timeout(600)
    saved = ""
    for _ in range(5):
        saved = page.evaluate(VISIBLE_SAVE_JS)
        if saved:
            break
        nxt = page.locator('button:has-text("次へ")')
        if nxt.count():
            try:
                nxt.first.click(timeout=6000)
            except Exception:
                break
            page.wait_for_timeout(2500)
        else:
            break
    page.wait_for_timeout(4500)
    page.screenshot(path=f"/tmp/raimo_{pid}_final.png", full_page=True)
    return {"private": priv, "setdata": sd, "save": saved, "url": page.url}


def verify_one(page, pid: str) -> bool:
    page.goto(f"https://raimo.buzz/gpt/prompt/{pid}", wait_until="domcontentloaded", timeout=120000)
    page.wait_for_timeout(3500)
    return page.evaluate(
        """()=>{const eds=[...document.querySelectorAll('.ck-content')].filter(e=>e.ckeditorInstance);
        const d=eds.map(e=>e.ckeditorInstance.getData()).join('\\n');
        return d.includes('P1 | 検索クエリ | 表示名');}"""
    )


def main() -> int:
    load_env()
    email = os.environ["RAIMO_PORTAL_EMAIL"]
    password = os.environ["RAIMO_PORTAL_PASSWORD"]
    bodies = {pid: extract_body(name, pat) for pid, (name, pat) in TARGETS.items()}
    results = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 1400})
        login(page, email, password)
        for pid, b in bodies.items():
            r = update_one(page, pid, b)
            print(f"update {pid}: {r}")
            results[pid] = r
        for pid in bodies:
            v = verify_one(page, pid)
            results[pid]["verified"] = v
            print(f"verify {pid}: marker_present={v}")
        browser.close()
    ok = all(r.get("verified") for r in results.values())
    print("ALL_VERIFIED" if ok else "SOME_FAILED")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
