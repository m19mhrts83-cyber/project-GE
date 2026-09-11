#!/usr/bin/env python3
"""
Vポイントサイト（旧Tサイト）履歴取得 — V会員番号＋メールOTP。

流れ:
  1. mypage.tsite.jp → 番号でログイン
  2. メール認証 OTP 送信
  3. estate / m19m Gmail API でコード取得
  4. ポイント履歴をパース → .jarvis_state/vpoint_tsite_history_YYYYMMDD.json

使い方:
  python scripts/jarvis_vpoint_tsite_fetch.py
  python scripts/jarvis_vpoint_tsite_fetch.py --headless
  python scripts/jarvis_vpoint_tsite_fetch.py --skip-otp-wait   # OTP を /tmp から読む試験用
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from playwright.sync_api import Page, sync_playwright

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from car_loan.chrome_cdp import CHROME, cdp_ready, start_cdp_chrome  # noqa: E402
from car_loan.env_state import ENV_FILE, load_env  # noqa: E402

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
STATE = REPO / ".jarvis_state"
SHOT_DIR = STATE / "vpoint_tsite"
CDP_PORT = 9236
PROFILE = Path.home() / ".jarvis_state" / "chrome_vpoint_tsite"
MYPAGE = "https://mypage.tsite.jp/"
LOGIN_CHOICE = "https://tsite.jp/tm/pc/login/STKIp0018001.do"
LOGIN_NUMBER = "https://tsite.jp/tm/pc/login/STKIp0002010.do"
MANUAL = (
    REPO
    / "215_kamiooya"
    / "C1_cursor"
    / "1b_Cursorマニュアル"
)
GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
]


def now_iso() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def _shot(page: Page, name: str) -> None:
    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(JST).strftime("%Y%m%d_%H%M%S")
    path = SHOT_DIR / f"{stamp}_{name}.png"
    try:
        page.screenshot(path=str(path), full_page=True)
        print(f"📎 screenshot: {path}")
    except Exception as e:
        print(f"⚠️ shot {name}: {e}")


def _body(page: Page, n: int = 4000) -> str:
    try:
        return page.inner_text("body")[:n]
    except Exception:
        return ""


def fetch_otp_from_gmail(*, newer_than: str = "1h", max_attempts: int = 14) -> str | None:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    tokens = [
        ("estate", MANUAL / "token_estate.json"),
        ("m19m", MANUAL / "token_m19m.json"),
        ("admin", MANUAL / "token_livingsupport.json"),
    ]
    queries = [
        f'newer_than:{newer_than} (認証コード OR 確認コード OR ワンタイム) (tsite OR Vポイント OR "V POINT" OR CCCMK OR 会員 OR V会員)',
        f"newer_than:{newer_than} subject:(認証コード OR 確認コード)",
        f"newer_than:{newer_than} from:(tsite.jp OR v-points OR vpoint OR cccmk OR ccc)",
    ]

    def body_text(full: dict) -> str:
        parts: list[str] = []

        def walk(p: dict) -> None:
            data = (p.get("body") or {}).get("data")
            if data and str(p.get("mimeType") or "").startswith("text/"):
                parts.append(base64.urlsafe_b64decode(data).decode("utf-8", "replace"))
            for c in p.get("parts") or []:
                walk(c)

        walk(full.get("payload") or {})
        return "\n".join(parts)

    for attempt in range(max_attempts):
        if attempt:
            time.sleep(5)
        for label, tok in tokens:
            if not tok.is_file():
                continue
            creds = Credentials.from_authorized_user_file(str(tok), GMAIL_SCOPES)
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
            svc = build("gmail", "v1", credentials=creds, cache_discovery=False)
            for q in queries:
                resp = (
                    svc.users()
                    .messages()
                    .list(userId="me", q=q, maxResults=8)
                    .execute()
                )
                for m in resp.get("messages") or []:
                    full = (
                        svc.users()
                        .messages()
                        .get(userId="me", id=m["id"], format="full")
                        .execute()
                    )
                    h = {
                        x["name"]: x["value"]
                        for x in (full.get("payload") or {}).get("headers") or []
                    }
                    text = body_text(full) or full.get("snippet") or ""
                    subj = h.get("Subject", "")
                    fr = h.get("From", "")
                    if "すぐチャン" in subj:
                        continue
                    blob = subj + fr + text
                    if not re.search(
                        r"認証|確認|ワンタイム|tsite|Vポイント|V POINT|CCCMK|V会員",
                        blob,
                        re.I,
                    ):
                        continue
                    mcode = re.search(
                        r"(認証コード|確認コード|ワンタイム)[^\d]{0,40}(\d{4,8})", text
                    )
                    code = None
                    if mcode:
                        code = mcode.group(2)
                    else:
                        six = re.findall(r"(?<![0-9])(\d{6})(?![0-9])", text)
                        six = [c for c in six if not c.startswith("202")]
                        if six:
                            code = six[0]
                    if not code or code.startswith("202"):
                        continue
                    print(f"📎 OTP from [{label}] subject={subj[:50]}")
                    return code
        print(f"📎 OTP wait attempt {attempt + 1}/{max_attempts}")
    return None


def parse_history_body(text: str) -> dict[str, Any]:
    """画面テキストから残高と主要付与行を抽出。"""
    balance = None
    m = re.search(r"(?:保有|残高|ポイント)\s*([0-9,]+)\s*pt", text, re.I)
    if m:
        balance = int(m.group(1).replace(",", ""))
    if balance is None:
        m = re.search(r"([0-9,]+)\s*ポイント", text)
        if m:
            balance = int(m.group(1).replace(",", ""))

    entries: list[dict[str, Any]] = []
    # 日付行＋説明＋pt が分かれている SPA を線で拾う
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    date_re = re.compile(r"^(20\d{2})[./年](\d{1,2})[./月](\d{1,2})")
    pt_re = re.compile(r"([+\-]?)\s*([0-9,]+)\s*(?:pt|ポイント)")
    i = 0
    while i < len(lines):
        dm = date_re.match(lines[i])
        if not dm:
            i += 1
            continue
        y, mo, d = int(dm.group(1)), int(dm.group(2)), int(dm.group(3))
        date_s = f"{y:04d}-{mo:02d}-{d:02d}"
        chunk = " ".join(lines[i : i + 6])
        pm = pt_re.search(chunk)
        if not pm:
            i += 1
            continue
        sign = -1 if pm.group(1) == "-" else 1
        pt = sign * int(pm.group(2).replace(",", ""))
        desc = chunk
        for noise in (date_s, pm.group(0)):
            desc = desc.replace(noise, " ")
        desc = re.sub(r"\s+", " ", desc).strip()[:180]
        # 興味ある行だけ key_entries に
        interesting = bool(
            re.search(
                r"積立|投信|ＳＢＩ|SBI|マクド|サイゼ|セブン|Olive|Ｏｌｉｖｅ|特典|カードご利用|マイレージ",
                desc,
            )
        )
        if interesting or abs(pt) >= 50:
            entries.append({"date": date_s, "desc": desc, "pt": pt})
        i += 1

    # 重複除去（date+desc+pt）
    seen: set[str] = set()
    uniq: list[dict[str, Any]] = []
    for e in entries:
        k = f"{e['date']}|{e['desc'][:40]}|{e['pt']}"
        if k in seen:
            continue
        seen.add(k)
        uniq.append(e)

    # 積立特典を優先ソート
    def score(e: dict) -> tuple:
        d = e.get("desc") or ""
        pri = 0
        if "積立" in d or "投信" in d:
            pri = 0
        elif "＋" in d or "特典" in d:
            pri = 1
        else:
            pri = 2
        return (pri, e.get("date") or "", -abs(int(e.get("pt") or 0)))

    uniq.sort(key=score)
    return {"balance_pt": balance, "key_entries": uniq[:80], "raw_line_count": len(lines)}


def _click_text(page: Page, *pats: str, timeout: int = 5000) -> str | None:
    """ボタンが a/button 以外（div[role=button] 等）でも押す。"""
    for pat in pats:
        # Playwright role（最優先）
        try:
            role = page.get_by_role("button", name=re.compile(pat))
            if role.count():
                el = role.first
                if el.is_visible():
                    el.scroll_into_view_if_needed(timeout=3000)
                    el.click(timeout=timeout)
                    time.sleep(1.2)
                    print(f"📎 clicked role=button ~/{pat}/")
                    return pat
        except Exception:
            pass
        loc = page.locator(
            "a,button,input[type='submit'],input[type='button'],[role='button'],div,span"
        ).filter(has_text=re.compile(pat))
        n = min(loc.count(), 8)
        for i in range(n):
            try:
                el = loc.nth(i)
                if not el.is_visible():
                    continue
                # 巨大な親コンテナを誤クリックしない
                box = el.bounding_box()
                if box and (box["height"] > 120 or box["width"] > 800):
                    continue
                el.scroll_into_view_if_needed(timeout=3000)
                el.click(timeout=timeout)
                time.sleep(1.2)
                print(f"📎 clicked ~/{pat}/")
                return pat
            except Exception:
                continue
    return None


def _fill_first_visible(page: Page, value: str, sels: tuple[str, ...]) -> bool:
    for sel in sels:
        loc = page.locator(sel)
        for i in range(min(loc.count(), 4)):
            try:
                el = loc.nth(i)
                if el.is_visible():
                    el.click(timeout=2000)
                    el.fill("")
                    el.fill(value)
                    print(f"📎 filled via {sel}")
                    return True
            except Exception:
                continue
    return False


def _fill_member_id(page: Page, vid: str) -> None:
    """Playwright fill() だと #nextButton が disabled のままになるため、キーボード入力する。"""
    sels = (
        "#registration input",
        "input[name*='member']",
        "input[name*='Member']",
        "input[name*='tcard']",
        "input[type='tel']",
        "input[type='text']",
    )
    el = None
    for sel in sels:
        loc = page.locator(sel)
        if loc.count() == 0:
            continue
        try:
            cand = loc.first
            if cand.is_visible():
                el = cand
                print(f"📎 member input via {sel}")
                break
        except Exception:
            continue
    if el is None:
        raise RuntimeError("V会員番号の入力欄が見つかりません")
    el.click(timeout=4000)
    # 全選択削除 → 1文字ずつ（サイト側バリデーション発火用）
    page.keyboard.press("Meta+A")
    page.keyboard.press("Backspace")
    page.keyboard.type(vid, delay=25)
    page.keyboard.press("Tab")
    time.sleep(0.8)
    # #nextButton 有効化待ち
    for i in range(20):
        enabled = page.evaluate(
            """() => {
              const b = document.querySelector('#nextButton');
              return !!(b && !b.disabled);
            }"""
        )
        if enabled:
            print(f"📎 nextButton enabled (wait={i})")
            return
        time.sleep(0.3)
    raise RuntimeError("#nextButton が有効になりません（番号バリデーション未通過）")


def _click_next_button(page: Page) -> None:
    loc = page.locator("#nextButton")
    if loc.count() and loc.first.is_visible():
        try:
            loc.first.click(timeout=5000)
            print("📎 clicked #nextButton")
            return
        except Exception:
            loc.first.click(force=True, timeout=5000)
            print("📎 force-clicked #nextButton")
            return
    if not _click_text(page, r"^次へ$", r"次へ"):
        raise RuntimeError("『次へ』ボタンをクリックできませんでした")


def _do_email_otp(page: Page) -> None:
    body = _body(page, 2500)
    if not re.search(r"Eメール|メール.*認証|認証コード|ワンタイム|確認コード|本人認証", body):
        if not re.search(r"認証|メール|SMS|電話", body):
            return
    _click_text(
        page,
        r"Eメールで認証する",
        r"Eメールで認証",
        r"メールで認証する",
        r"メールで認証",
        r"メールアドレス",
    )
    time.sleep(0.8)
    # 送信ボタンが別画面の場合
    body2 = _body(page, 2000)
    if re.search(r"認証コードを送信|コードを送信|送信する", body2):
        _click_text(page, r"認証コードを送信", r"コードを送信", r"送信する", r"^送信$")
        time.sleep(2)
    else:
        # 「Eメールで認証する」自体が送信トリガのこともある
        time.sleep(2)
    _shot(page, "otp_sent")

    otp = fetch_otp_from_gmail()
    if not otp:
        raise RuntimeError("Gmail から Tサイト OTP を取得できませんでした")
    print(f"📎 OTP acquired (len={len(otp)})")
    if not _fill_first_visible(
        page,
        otp,
        (
            "input[name*='code']",
            "input[name*='Code']",
            "input[name*='otp']",
            "input[name*='OTP']",
            "input[autocomplete='one-time-code']",
            "input[type='tel']",
            "input[type='text']",
            "input[type='password']",
            "input[type='number']",
        ),
    ):
        page.keyboard.type(otp, delay=20)
        print("📎 typed OTP via keyboard")
    _click_text(page, r"認証する", r"確認する", r"^確認$", r"次へ", r"ログイン")
    # #nextButton がある場合
    if page.locator("#nextButton").count():
        try:
            page.locator("#nextButton").first.click(timeout=3000)
        except Exception:
            pass
    try:
        page.wait_for_load_state("domcontentloaded", timeout=90000)
    except Exception:
        pass
    time.sleep(2)
    _shot(page, "after_otp")


def login_and_scrape(page: Page, vid: str) -> dict[str, Any]:
    page.goto(MYPAGE, wait_until="domcontentloaded", timeout=90000)
    time.sleep(2)
    _shot(page, "mypage")

    body = _body(page, 2500)
    logged_in = bool(
        re.search(r"ポイント履歴|保有ポイント|ログアウト", body)
        and not re.search(r"ようこそVポイント|設定を始める|番号でログイン", body)
    )

    if not logged_in:
        if re.search(r"設定を始める|ようこそVポイント", body):
            _click_text(page, r"設定を始める")
            time.sleep(1.5)
        body = _body(page, 1500)
        if re.search(r"番号でログイン", body):
            _click_text(page, r"番号でログイン")
            time.sleep(1.5)
        body = _body(page, 1200)
        has_input = (
            page.locator("input[type='text'],input[type='tel'],input[type='password']").count()
            > 0
        )
        if not has_input or not re.search(r"番号|会員|カード", body):
            print(f"📎 goto LOGIN_NUMBER (url was {page.url})")
            page.goto(LOGIN_NUMBER, wait_until="domcontentloaded", timeout=90000)
            time.sleep(1.5)

        _fill_member_id(page, vid)
        _shot(page, "after_id")
        _click_next_button(page)
        try:
            page.wait_for_load_state("domcontentloaded", timeout=60000)
        except Exception:
            pass
        time.sleep(2.5)
        _shot(page, "after_submit_id")
        body_after = _body(page, 1500)
        if re.search(r"番号を入力|ご利用中のV会員番号", body_after) and not re.search(
            r"Eメール|メール|認証コード|SMS|電話|本人認証", body_after
        ):
            raise RuntimeError(
                f"『次へ』後も番号入力のまま url={page.url} snip={body_after[:180]!r}"
            )
        _do_email_otp(page)

        body = _body(page, 2000)
        if re.search(r"ようこそVポイント|設定を始める|番号でログイン|番号を入力|本人認証", body):
            raise RuntimeError(
                f"ログイン未完了のままです url={page.url} snip={body[:200]!r}"
            )

    # 履歴タブへ
    for url in (
        "https://mypage.tsite.jp/#point-history-tab/",
        "https://mypage.tsite.jp/",
    ):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=90000)
            time.sleep(3)
        except Exception:
            continue
        for pat in (r"ポイント履歴", r"履歴"):
            loc = page.locator("a,button,div,span").filter(has_text=re.compile(pat))
            if loc.count():
                try:
                    loc.first.click(timeout=3000)
                    time.sleep(2)
                except Exception:
                    pass
        body = _body(page, 8000)
        if re.search(r"ポイント|獲得|利用|積立", body) and len(body) > 200:
            break
    time.sleep(2)
    for _ in range(10):
        page.mouse.wheel(0, 1800)
        time.sleep(0.35)
    time.sleep(1)
    _shot(page, "history")

    dom = page.evaluate(
        r"""() => {
      const body = document.body.innerText || '';
      let balance = null;
      const m1 = body.match(/Vポイント\s*\n\s*([0-9,]+)/);
      const m2 = body.match(/([0-9,]{4,})\s*\n\s*有効期限/);
      const m3 = body.match(/([0-9,]{4,})\s*pt/);
      if (m1) balance = parseInt(m1[1].replace(/,/g,''), 10);
      else if (m2) balance = parseInt(m2[1].replace(/,/g,''), 10);
      else if (m3) balance = parseInt(m3[1].replace(/,/g,''), 10);

      const rows = [];
      const blocks = body.split(/\n(?=20\d{2}\/\d{1,2}\/\d{1,2})/);
      for (const block of blocks) {
        const dm = block.match(/^(20\d{2})\/(\d{1,2})\/(\d{1,2})/);
        if (!dm) continue;
        const lines = block.split('\n').map(s => s.trim()).filter(Boolean);
        if (lines.length < 2) continue;
        let pt = null;
        let descParts = [];
        for (const ln of lines.slice(1)) {
          const pm = ln.match(/^([+\-−]?)\s*([0-9,]+)\s*$/);
          if (pm && pt === null) {
            const sign = (pm[1]||'').includes('-') || (pm[1]||'').includes('−') ? -1 : 1;
            pt = sign * parseInt(pm[2].replace(/,/g,''), 10);
          } else if (!/^(利用日順|反映日順|絞り込み|グラフ|ポイント履歴|有効期限)$/.test(ln)) {
            descParts.push(ln);
          }
        }
        if (pt === null) continue;
        const date = `${dm[1]}-${dm[2].padStart(2,'0')}-${dm[3].padStart(2,'0')}`;
        rows.push({date, desc: descParts.join(' ').slice(0,200), pt});
      }
      const seen = new Set();
      const uniq = [];
      for (const r of rows) {
        const k = r.date+'|'+r.pt+'|'+r.desc.slice(0,40);
        if (seen.has(k)) continue;
        seen.add(k);
        uniq.push(r);
      }
      return {balance_pt: balance, rows: uniq, body};
    }"""
    )
    body = dom.get("body") or _body(page, 12000)
    parsed_fallback = parse_history_body(body)
    rows = dom.get("rows") or []
    interesting: list[dict[str, Any]] = []
    for e in rows:
        d = e.get("desc") or ""
        if re.search(
            r"積立|投信|マクド|サイゼ|Olive|Ｏｌｉｖｅ|プラチナ|特典|カードご利用|マイレージ|給与|ポイント移動",
            d,
        ) or abs(int(e.get("pt") or 0)) >= 100:
            interesting.append({"date": e["date"], "desc": e["desc"], "pt": e["pt"]})
    parsed: dict[str, Any] = {
        "balance_pt": dom.get("balance_pt") or parsed_fallback.get("balance_pt"),
        "key_entries": interesting[:80] or (parsed_fallback.get("key_entries") or []),
        "raw_line_count": len(rows) or parsed_fallback.get("raw_line_count"),
        "page_url": page.url,
        "body_snip": re.sub(r"\d{6,}", "****", body[:2000]),
    }
    return parsed


def run(*, headless: bool) -> dict[str, Any]:
    env = load_env(ENV_FILE)
    vid = (env.get("VPOINT_TSITE_ID") or os.environ.get("VPOINT_TSITE_ID") or "").strip()
    if not vid:
        raise RuntimeError("未設定: VPOINT_TSITE_ID")

    want_headless = headless or os.environ.get("TEIKI_HEADLESS") == "1"
    with sync_playwright() as p:
        if want_headless or not Path(CHROME).exists():
            print("📎 Tサイト: Playwright headless")
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(locale="ja-JP", viewport={"width": 1280, "height": 900})
            page = ctx.new_page()
            try:
                return login_and_scrape(page, vid)
            finally:
                ctx.close()
                browser.close()

        start_cdp_chrome(CDP_PORT, PROFILE, MYPAGE)
        if not cdp_ready(CDP_PORT):
            raise RuntimeError(f"CDP {CDP_PORT} not ready")
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        return login_and_scrape(page, vid)


def save_history(parsed: dict[str, Any]) -> Path:
    day = datetime.now(JST).strftime("%Y%m%d")
    path = STATE / f"vpoint_tsite_history_{day}.json"
    out = {
        "fetched_at": now_iso(),
        "balance_pt": parsed.get("balance_pt"),
        "login": "email_otp_via_VPOINT_TSITE_ID",
        "page_url": parsed.get("page_url"),
        "key_entries": parsed.get("key_entries") or [],
        "raw_line_count": parsed.get("raw_line_count"),
    }
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"✅ wrote {path} entries={len(out['key_entries'])} balance={out.get('balance_pt')}")
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description="Vポイント Tサイト履歴取得")
    ap.add_argument("--headless", action="store_true")
    args = ap.parse_args()
    try:
        parsed = run(headless=args.headless)
    except Exception as e:
        print(f"⚠️ Tサイト取得失敗: {e}", file=sys.stderr)
        return 1
    path = save_history(parsed)
    print(json.dumps({"path": str(path), "balance_pt": parsed.get("balance_pt"), "n": len(parsed.get("key_entries") or [])}, ensure_ascii=False))
    if not parsed.get("key_entries") and not parsed.get("balance_pt"):
        print("⚠️ 履歴・残高をパースできませんでした（スクショ確認）", file=sys.stderr)
        snip = (parsed.get("body_snip") or "")[:800]
        print(snip)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
