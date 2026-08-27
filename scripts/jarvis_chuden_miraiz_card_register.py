#!/usr/bin/env python3
"""中部電力ミライズ — クレジットカード支払 Web申込（共用部・1契約ずつ）。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_chuden_miraiz_card_register.py --contract caramel_common
  ~/selenium_env/venv/bin/python scripts/jarvis_chuden_miraiz_card_register.py --contract caramel_common --submit --headed

SMS OTP: Mac Messages DB。3DS: Gmail Vpass。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
STATE = REPO / ".jarvis_state" / "chuden_miraiz_contracts.json"
OUT = REPO / ".jarvis_state" / "chuden_miraiz_card"
OUT.mkdir(parents=True, exist_ok=True)

FORM_URL = "https://katene.jp/kp/shiharaihoho/shiharaihohoInput.do"


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def load_state() -> dict:
    return json.loads(STATE.read_text(encoding="utf-8"))


def contract_by_id(state: dict, cid: str) -> dict | None:
    for c in state.get("contracts") or []:
        if c.get("id") == cid:
            return c
    return None


def split_person_name(full: str) -> tuple[str, str]:
    full = (full or "").strip()
    m = re.match(r"^(松野|株式会社)(.+)$", full)
    if m:
        return m.group(1), m.group(2)
    if len(full) >= 2:
        return full[:2], full[2:]
    return full, ""


def split_kana_name(full: str) -> tuple[str, str]:
    full = re.sub(r"\s+", "", full or "")
    if full.startswith("マツノ"):
        return "マツノ", full[3:]
    if full.startswith("カブシキガイシャ"):
        return "カブシキガイシャ", full[len("カブシキガイシャ") :]
    return full[: min(4, len(full))], full[min(4, len(full)) :]


def split_customer_no(cn: str) -> list[str]:
    d = re.sub(r"\D", "", cn)
    if len(d) != 13:
        return [d]
    return [d[0:3], d[3:7], d[7:9], d[9:11], d[11:12], d[12:13]]


def sms_otp(max_age_sec: int = 300) -> str | None:
    db = Path.home() / "Library/Messages/chat.db"
    if not db.is_file():
        return None
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT text FROM message
            WHERE text IS NOT NULL
            AND datetime(message.date/1000000000 + strftime('%s','2001-01-01'), 'unixepoch', 'localtime')
                >= datetime('now', 'localtime', ?)
            AND (text LIKE '%認証%' OR text LIKE '%ワンタイム%' OR text LIKE '%中部%' OR text LIKE '%カテエネ%')
            ORDER BY message.date DESC LIMIT 15
            """,
            (f"-{max_age_sec} seconds",),
        )
        for (text,) in cur.fetchall():
            if not text:
                continue
            for pat in [r"【(\d{4,8})】", r"#(\d{4,8})", r"\b(\d{6})\b"]:
                m = re.search(pat, text)
                if m and ("認証" in text or "ワンタイム" in text or "中部" in text or "カテエネ" in text):
                    return m.group(1)
    except Exception as e:
        print(f"SMS OTP read failed: {e}", file=sys.stderr)
    return None


def gmail_vpass_otp() -> str | None:
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        manual = REPO / "215_kamiooya" / "C1_cursor" / "1b_Cursorマニュアル"
        scopes = [
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.modify",
        ]
        path = manual / "token_estate.json"
        creds = Credentials.from_authorized_user_file(str(path), scopes)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        svc = build("gmail", "v1", credentials=creds, cache_discovery=False)
        q = "from:payment.vpass.ne.jp newer_than:1d 認証コード"
        res = svc.users().messages().list(userId="me", q=q, maxResults=3).execute()
        for mid in [m["id"] for m in res.get("messages", [])]:
            msg = svc.users().messages().get(userId="me", id=mid, format="full").execute()
            body = ""
            for part in msg.get("payload", {}).get("parts") or []:
                if part.get("body", {}).get("data"):
                    import base64

                    body += base64.urlsafe_b64decode(part["body"]["data"] + "==").decode("utf-8", "ignore")
            if not body and msg.get("payload", {}).get("body", {}).get("data"):
                import base64

                body = base64.urlsafe_b64decode(msg["payload"]["body"]["data"] + "==").decode("utf-8", "ignore")
            m = re.search(r"認証コード[：:]\s*(\d{6})", body)
            if m:
                return m.group(1)
            m = re.search(r"\b(\d{6})\b", body)
            if m and "7887" in body:
                return m.group(1)
    except Exception as e:
        print(f"Gmail OTP: {e}", file=sys.stderr)
    return None


def unlock_form(page) -> None:
    """同意チェック後も disabled が残る step UI 向け。"""
    page.locator("label[for='riyoKiyakuFlg']").click()
    page.wait_for_timeout(800)
    page.evaluate(
        """() => {
        const cb = document.querySelector('#riyoKiyakuFlg');
        if (cb && !cb.checked) { cb.checked = true; cb.dispatchEvent(new Event('change', {bubbles:true})); }
        document.querySelectorAll('input, select, textarea, button').forEach(el => {
          el.disabled = false;
          el.classList?.remove('disabled');
          el.removeAttribute('aria-disabled');
        });
      }"""
    )
    page.wait_for_timeout(300)


def fill_postal_and_search(page, zip3_id: str, zip4_id: str, btn_id: str, zip3: str, zip4: str) -> None:
    page.locator(f"#{zip3_id}").fill(zip3)
    page.locator(f"#{zip4_id}").fill(zip4)
    page.locator(f"#{btn_id}").click()
    page.wait_for_timeout(2500)


def fill_customer_fields(page, cn: str) -> None:
    parts = split_customer_no(cn)
    names = ["keiyakuKid1", "keiyakuKid2", "keiyakuKid3", "keiyakuKid4", "keiyakuKid5", "keiyakuKid6"]
    for name, val in zip(names, parts):
        page.locator(f'input[name="{name}"]').fill(val)


def register_contract(
    contract: dict,
    *,
    dry_run: bool,
    submit: bool,
    headless: bool,
) -> dict:
    from playwright.sync_api import sync_playwright

    result: dict = {"contract_id": contract["id"], "steps": [], "errors": [], "screenshots": []}
    cid = contract["id"]

    if contract.get("status", "").startswith("cancelled"):
        result["status"] = "skipped_cancelled"
        result["note"] = contract.get("cancel_reason", "cancelled")
        return result

    is_corp = cid == "grandole_i_common"

    billing_postal = os.environ.get("CHUDEN_MIRAIZ_BILLING_POSTAL") or os.environ.get("HOME_POSTAL_CODE", "")
    billing_banti = os.environ.get("HOME_ADDRESS_BANTI", "３４２番地２５")
    notify_email = os.environ.get("CHUDEN_MIRAIZ_NOTIFY_EMAIL", "matsuno.estate@gmail.com")
    phone = re.sub(r"\D", "", os.environ.get("PERSONAL_PHONE", ""))
    applicant_name = os.environ.get("PERSONAL_NAME", "松野真治")
    applicant_kana = (
        os.environ.get("PERSONAL_NAME_KANA_FAMILY", "マツノ")
        + os.environ.get("PERSONAL_NAME_KANA_GIVEN", "マサハル")
    )

    holder = contract.get("contract_holder", applicant_name)
    holder_kana = contract.get("contract_holder_kana", applicant_kana)
    holder_last, holder_first = split_person_name(holder)
    holder_kana_last, holder_kana_first = split_kana_name(holder_kana)
    app_last, app_first = split_person_name(applicant_name)
    app_kana_last, app_kana_first = split_kana_name(applicant_kana)

    card_no = os.environ.get("OLIVE_FLEXIBLE_PAY_CREDIT_NUMBER_WEB") or re.sub(
        r"\D", "", os.environ.get("OLIVE_FLEXIBLE_PAY_CREDIT_NUMBER", "")
    )
    card_exp = os.environ.get("OLIVE_FLEXIBLE_PAY_CREDIT_EXPIRY", "")
    card_cvc = os.environ.get("OLIVE_FLEXIBLE_PAY_CREDIT_CVC", "")
    card_holder = os.environ.get("OLIVE_FLEXIBLE_PAY_CREDIT_HOLDER", "")

    supply = contract.get("supply_location") or {}
    supply_postal = re.sub(r"\D", "", supply.get("postal_code", ""))
    supply_banti = "４１８"
    supply_build = supply.get("facility_name") or ""
    if "418" in (supply.get("address_bill") or supply.get("address") or ""):
        supply_banti = "４１８"

    print(f"契約: {contract.get('property')} / {contract.get('customer_no')} / {'法人' if is_corp else '個人'}")

    if dry_run:
        result["dry_run"] = {
            "supply_postal": supply_postal,
            "supply_banti": supply_banti,
            "billing_postal": billing_postal,
            "notify_email": notify_email,
            "card_last4": card_no[-4:] if card_no else None,
        }
        return result

    if not card_no or not card_exp or not card_cvc:
        result["errors"].append("カード env 未設定")
        return result

    zip3_supply, zip4_supply = supply_postal[:3], supply_postal[3:7]
    zip3_bill, zip4_bill = re.sub(r"\D", "", billing_postal)[:3], re.sub(r"\D", "", billing_postal)[3:7]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page(viewport={"width": 1280, "height": 2400})
        try:
            page.goto(FORM_URL, wait_until="networkidle", timeout=90000)
            result["steps"].append({"url": page.url, "title": page.title()})

            unlock_form(page)

            if is_corp:
                page.locator("#meigi1").check(force=True)
                page.fill("#keiyakukaisyaLastName", "株式会社")
                page.fill("#keiyakukaisyaFirstName", holder.replace("株式会社", ""))
                page.fill("#keiyakukaisyaLastNameKana", "カブシキガイシャ")
                page.fill("#keiyakukaisyaFirstNameKana", holder_kana.replace("カブシキガイシャ", ""))
            else:
                page.locator("#meigi0").check(force=True)
                page.fill("#keiyakuLastName", holder_last)
                page.fill("#keiyakuFirstName", holder_first)
                page.fill("#keiyakuLastNameKana", holder_kana_last)
                page.fill("#keiyakuFirstNameKana", holder_kana_first)

            fill_postal_and_search(
                page, "keiyakuAddrYubin3", "keiyakuAddrYubin4", "keiyakuAddrYubinBtn", zip3_supply, zip4_supply
            )
            page.fill("#keiyakuAddrBanti", supply_banti)
            if supply_build:
                page.fill("#keiyakuAddrBuild", supply_build)

            fill_customer_fields(page, contract.get("customer_no", ""))

            # 請求先 = 自宅（使用場所と同じチェックを外す）
            if page.locator("#rad_place").is_checked():
                page.locator("#rad_place").uncheck(force=True)
            page.wait_for_timeout(500)
            page.evaluate(
                """() => {
                ['paymentPostCd3','paymentPostCd4','paymentSiteAddrBanti','paymentSiteAddrBuild','paymentName',
                 'paymentDenwa1','paymentDenwa2','paymentDenwa3'].forEach(id => {
                  const el = document.getElementById(id) || document.querySelector(`[name="${id}"]`);
                  if (el) { el.disabled = false; el.classList.remove('disabled'); }
                });
                document.querySelectorAll('select[name^="paymentSiteAddr"]').forEach(el => {
                  el.disabled = false; el.classList.remove('disabled');
                });
              }"""
            )
            fill_postal_and_search(
                page,
                "paymentSiteAddrYubin3",
                "paymentSiteAddrYubin4",
                "paymentSiteAddrYubinBtn",
                zip3_bill,
                zip4_bill,
            )
            page.fill("#paymentSiteAddrBanti", billing_banti)
            page.fill("#paymentName", applicant_name)

            page.locator("#kbdtn1").check(force=True)
            page.fill('input[name="paymentDenwa1"]', phone[:3])
            page.fill('input[name="paymentDenwa2"]', phone[3:7])
            page.fill('input[name="paymentDenwa3"]', phone[7:11])

            page.locator("#rad_relation0").check(force=True)
            page.fill('input[name="mosikomisyaLastName"]', app_last)
            page.fill('input[name="mosikomisyaFirstName"]', app_first)
            page.fill('input[name="mosikomisyaLastNameKana"]', app_kana_last)
            page.fill('input[name="mosikomisyaFirstNameKana"]', app_kana_first)

            page.locator("#kbmskmtn1").check(force=True)
            page.fill("#mosikomiDenwa1", phone[:3])
            page.fill("#mosikomiDenwa2", phone[3:7])
            page.fill("#mosikomiDenwa3", phone[7:11])

            page.fill("#email", notify_email)
            page.fill("#mailAddressAgain", notify_email)

            shot2 = OUT / f"{cid}_02_before_next.png"
            page.screenshot(path=str(shot2), full_page=True)
            result["screenshots"].append(str(shot2))

            if not submit:
                result["status"] = "preview_stopped"
                result["note"] = "--submit なしのため確認画面手前で停止"
                browser.close()
                return result

            page.locator("#gtm_main_0001").click()
            page.wait_for_timeout(4000)
            result["steps"].append({"url": page.url, "title": page.title()})

            shot3 = OUT / f"{cid}_03_after_next.png"
            page.screenshot(path=str(shot3), full_page=True)
            result["screenshots"].append(str(shot3))

            for frame in [page] + page.frames:
                try:
                    mapping = [
                        ("input[name*='cardNo'], input[name*='cardno'], input[autocomplete='cc-number']", card_no),
                        ("input[name*='month'], input[placeholder*='月'], select[name*='month']", card_exp.split("/")[0] if "/" in card_exp else card_exp[:2]),
                        ("input[name*='year'], input[placeholder*='年'], select[name*='year']", card_exp.split("/")[1][-2:] if "/" in card_exp else card_exp[-2:]),
                        ("input[name*='security'], input[name*='cvc'], input[autocomplete='cc-csc']", card_cvc),
                        ("input[name*='holder'], input[name*='name']", card_holder),
                    ]
                    for sel, val in mapping:
                        loc = frame.locator(sel)
                        if loc.count() and val:
                            loc.first.fill(val)
                except Exception:
                    continue

            page.wait_for_timeout(2000)
            for text in ["送信", "確認", "次へ", "登録"]:
                try:
                    page.locator(f"button:has-text('{text}'), input[type='submit'][value*='{text}']").first.click(timeout=3000)
                    page.wait_for_timeout(1500)
                except Exception:
                    pass

            time.sleep(10)
            otp = sms_otp(180)
            if otp:
                result["sms_otp_used"] = True
                for loc in page.locator("input[name*='auth'], input[name*='otp'], input[placeholder*='認証']").all():
                    try:
                        loc.fill(otp)
                        break
                    except Exception:
                        continue
                for text in ["確認", "送信"]:
                    try:
                        page.locator(f"button:has-text('{text}')").first.click(timeout=3000)
                    except Exception:
                        pass

            time.sleep(8)
            vpass = gmail_vpass_otp()
            if vpass:
                result["vpass_otp_used"] = True
                for loc in page.locator("input[name*='otp'], input[name*='password'], input[type='tel']").all():
                    try:
                        loc.fill(vpass)
                        break
                    except Exception:
                        continue
                for text in ["送信", "確認"]:
                    try:
                        page.locator(f"button:has-text('{text}')").first.click(timeout=3000)
                    except Exception:
                        pass

            page.wait_for_timeout(5000)
            shot4 = OUT / f"{cid}_04_done.png"
            page.screenshot(path=str(shot4), full_page=True)
            result["screenshots"].append(str(shot4))
            content = page.content()
            result["final_url"] = page.url
            result["status"] = "submitted_attempt"
            if page.url != FORM_URL and ("完了" in content or "受付" in content or "お申込みを受け付け" in content):
                result["status"] = "completed"
            elif "入力内容に不備" in content or page.url == FORM_URL:
                result["status"] = "validation_failed"
                result["note"] = "同一URLのまま／入力不備。AjaxUikJusyo.js 404で郵便番号検索不可の可能性"

        except Exception as e:
            result["errors"].append(str(e))
            err = OUT / f"{cid}_error.png"
            try:
                page.screenshot(path=str(err), full_page=True)
                result["screenshots"].append(str(err))
            except Exception:
                pass
        finally:
            browser.close()

    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--contract", choices=["caramel_common", "grandole_i_common", "all"], default="caramel_common")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--submit", action="store_true", help="最終送信まで実行")
    ap.add_argument("--headed", action="store_true", help="ブラウザ表示")
    args = ap.parse_args()

    state = load_state()
    ids = ["caramel_common", "grandole_i_common"] if args.contract == "all" else [args.contract]
    results = []
    for cid in ids:
        c = contract_by_id(state, cid)
        if not c:
            print(f"unknown contract: {cid}", file=sys.stderr)
            return 1
        r = register_contract(c, dry_run=args.dry_run, submit=args.submit, headless=not args.headed)
        results.append(r)
        print(json.dumps(r, ensure_ascii=False, indent=2))

    out = OUT / "register_results.json"
    out.write_text(json.dumps({"at": now_iso(), "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")

    for r in results:
        if r.get("status") == "completed":
            c = contract_by_id(state, r["contract_id"])
            if c:
                c["status"] = "card_registered_web"
                c["card_registered_at"] = now_iso()
    state["updated_at"] = now_iso()
    state["jarvis_actions_done"] = list(
        set((state.get("jarvis_actions_done") or []) + ["card_register_attempt"])
    )
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    return 0 if all(not r.get("errors") for r in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
