#!/usr/bin/env python3
"""カテエネに中部電力ミライズ契約を紐づけ（お客さま番号）。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_katene_link_contracts.py
  ~/selenium_env/venv/bin/python scripts/jarvis_katene_link_contracts.py --dry-run

SMS OTP: Mac Messages DB から自動取得（jarvis-sms-otp-messages）。
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
OUT_DIR = REPO / ".jarvis_state" / "katene_amp_check"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def load_contracts() -> list[dict]:
    if STATE.is_file():
        data = json.loads(STATE.read_text(encoding="utf-8"))
        return data.get("contracts") or []
    return []


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
            AND (text LIKE '%認証%' OR text LIKE '%ワンタイム%' OR text LIKE '%カテエネ%' OR text LIKE '%中部%')
            ORDER BY message.date DESC LIMIT 10
            """,
            (f"-{max_age_sec} seconds",),
        )
        for (text,) in cur.fetchall():
            if not text:
                continue
            # カテエネ: 【123456】TC IDの認証用コード
            m = re.search(r"【(\d{4,8})】\s*TC ID", text)
            if m:
                return m.group(1)
            m = re.search(r"#(\d{4,8})", text)
            if m and ("chuden" in text.lower() or "カテエネ" in text or "認証" in text):
                return m.group(1)
            m = re.search(r"\b(\d{6})\b", text)
            if m and ("認証" in text or "ワンタイム" in text or "カテエネ" in text):
                return m.group(1)
    except Exception as e:
        print(f"SMS OTP read failed: {e}", file=sys.stderr)
    return None


def run(dry_run: bool) -> int:
    tc_id = os.environ.get("KATENE_TC_ID", "").strip()
    password = os.environ.get("KATENE_PASSWORD", "").strip()
    if not tc_id or not password:
        print("KATENE_TC_ID / KATENE_PASSWORD 未設定", file=sys.stderr)
        return 1

    contracts = load_contracts()
    customer_nos = [c["customer_no"] for c in contracts if c.get("customer_no")]
    if not customer_nos:
        print("契約なし（chuden_miraiz_contracts.json）", file=sys.stderr)
        return 1

    print(f"使用: カテエネ TC ID={tc_id[:3]}… / 契約 {len(customer_nos)}件")
    if dry_run:
        print("DRY-RUN:", customer_nos)
        return 0

    from playwright.sync_api import sync_playwright

    steps: list[dict] = []
    result: dict = {"linked": [], "errors": [], "screenshots": []}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto("https://katene.chuden.jp/", wait_until="domcontentloaded", timeout=60000)
            steps.append({"url": page.url, "title": page.title()})

            # ログイン（モーダル or ヘッダ）
            for sel in [
                "button:has-text('ログイン')",
                "a:has-text('ログイン')",
                ".login-btn",
            ]:
                try:
                    loc = page.locator(sel)
                    if loc.count() > 0:
                        loc.first.click(timeout=8000)
                        page.wait_for_timeout(2000)
                        steps.append({"clicked_login": sel})
                        break
                except Exception:
                    continue

            # TC ID / パスワード（複数iframe対応）
            filled = False
            for frame in [page] + page.frames:
                try:
                    user = frame.locator(
                        "input#loginId, input[name='loginId'], input[name*='tc'], input[type='email'], input[type='text']"
                    )
                    pw = frame.locator("input[type='password']")
                    if user.count() > 0 and pw.count() > 0:
                        user.first.fill(tc_id)
                        pw.first.fill(password)
                        filled = True
                        steps.append({"filled_login_form": frame.url if hasattr(frame, 'url') else 'main'})
                        for sel in ["button:has-text('ログイン')", "button[type='submit']", "input[type='submit']"]:
                            try:
                                frame.locator(sel).first.click(timeout=5000)
                                break
                            except Exception:
                                continue
                        break
                except Exception:
                    continue
            if not filled:
                raise RuntimeError("login form not found")
            page.wait_for_timeout(3000)

            # OTP（MFA SMS）
            if "mfa-sms" in page.url or "認証" in page.title():
                for attempt in range(18):
                    code = sms_otp(max_age_sec=120)
                    if code:
                        for frame in [page] + page.frames:
                            otp_input = frame.locator(
                                "input[name*='code'], input[name*='otp'], input[type='tel'], input[inputmode='numeric']"
                            )
                            if otp_input.count() == 0:
                                continue
                            otp_input.first.fill(code)
                            for sel in [
                                "button:has-text('ログイン')",
                                "button:has-text('認証')",
                                "button:has-text('確認')",
                                "button[type='submit']",
                            ]:
                                try:
                                    frame.locator(sel).first.click(timeout=5000)
                                    break
                                except Exception:
                                    continue
                            break
                        page.wait_for_timeout(5000)
                        if "mfa-sms" not in page.url:
                            break
                    time.sleep(5)
                steps.append({"after_mfa": page.url, "title": page.title()})
            elif page.locator(
                "input[name*='otp'], input[name*='code'], input[placeholder*='認証'], input[type='tel']"
            ).count() > 0:
                for _ in range(12):
                    code = sms_otp()
                    if code:
                        page.locator(
                            "input[name*='otp'], input[name*='code'], input[placeholder*='認証'], input[type='tel']"
                        ).first.fill(code)
                        for sel in ["button:has-text('認証')", "button:has-text('ログイン')", "button[type='submit']"]:
                            try:
                                page.locator(sel).first.click(timeout=3000)
                                break
                            except Exception:
                                continue
                        break
                    time.sleep(5)
                page.wait_for_timeout(4000)

            shot = OUT_DIR / "katene_after_login.png"
            page.screenshot(path=str(shot), full_page=True)
            result["screenshots"].append(str(shot))
            steps.append({"after_login": page.url, "title": page.title()})

            # ご契約情報の登録
            reg_btn = page.get_by_role("button", name=re.compile("ご契約情報"))
            if reg_btn.count() == 0:
                reg_btn = page.locator("a:has-text('ご契約情報'), button:has-text('ご契約情報')")
            if reg_btn.count() > 0:
                reg_btn.first.click(timeout=10000)
                page.wait_for_timeout(3000)
                steps.append({"clicked": "ご契約情報の登録", "url": page.url})

            # 電気・ガス契約を選択
            elec = page.locator("button:has-text('電気・ガスのご契約'), a:has-text('電気・ガスのご契約')")
            if elec.count() > 0:
                elec.first.click(timeout=8000)
                page.wait_for_timeout(2000)
                steps.append({"clicked": "電気・ガスのご契約", "url": page.url})

            contract_meta = {
                "1604325040100": {
                    "label": "キャラメル共用部",
                    "names": [
                        os.environ.get("COMPANY_NAME", ""),
                        os.environ.get("REPRESENTATIVE_NAME", ""),
                        os.environ.get("PERSONAL_NAME", ""),
                    ],
                },
                "1201844057520": {
                    "label": "GrandoleⅠ共用部",
                    "names": [
                        os.environ.get("COMPANY_NAME", ""),
                        os.environ.get("REPRESENTATIVE_NAME", ""),
                    ],
                },
            }

            for cn in customer_nos:
                linked = False
                if cn in page.content():
                    result["linked"].append(cn)
                    continue
                meta = contract_meta.get(cn, {"names": []})
                names = [n.strip() for n in meta.get("names", []) if n and n.strip()]

                for pay_label in ["クレジットカード", "払込票", "口座振替"]:
                    pay = page.locator(f"button:has-text('{pay_label}'), a:has-text('{pay_label}')")
                    if pay.count() == 0:
                        continue
                    try:
                        pay.first.click(timeout=5000)
                        page.wait_for_timeout(2000)
                    except Exception:
                        continue

                    for name in names or [""]:
                        try:
                            cn_inp = page.locator(
                                "input[name*='okyaku'], input[name*='customerNo'], input[placeholder*='お客さま番号']"
                            )
                            if cn_inp.count() > 0:
                                cn_inp.first.fill(cn)
                            name_inp = page.locator(
                                "input[name*='name'], input[placeholder*='お名前'], input[placeholder*='契約者']"
                            )
                            if name and name_inp.count() > 0:
                                name_inp.first.fill(name)
                            for sel in [
                                "button:has-text('次へ')",
                                "button:has-text('確認')",
                                "button:has-text('登録')",
                                "button[type='submit']",
                            ]:
                                try:
                                    page.locator(sel).first.click(timeout=5000)
                                    page.wait_for_timeout(3000)
                                    break
                                except Exception:
                                    continue
                            if cn in page.content() and "エラー" not in page.content():
                                result["linked"].append(cn)
                                linked = True
                                steps.append({"linked": cn, "pay": pay_label, "name_tried": name[:4] + "…" if name else ""})
                                break
                        except Exception as e:
                            result["errors"].append(f"{cn}/{pay_label}: {e}")
                    if linked:
                        break
                    # フォーム選択に戻る
                    page.goto("https://katene.chuden.jp/clubkatene/keiyakuadd/keiyakuSelect.do", wait_until="domcontentloaded")
                    page.wait_for_timeout(1500)
                    if elec.count() > 0:
                        page.locator("button:has-text('電気・ガスのご契約'), a:has-text('電気・ガスのご契約')").first.click(timeout=5000)
                        page.wait_for_timeout(1500)

                if not linked and cn not in result.get("linked", []):
                    result["errors"].append(f"{cn}: 登録未完了（支払方法・契約者名の確認が必要）")

            shot2 = OUT_DIR / "katene_after_link.png"
            page.screenshot(path=str(shot2), full_page=True)
            result["screenshots"].append(str(shot2))

        except Exception as e:
            result["errors"].append(str(e))
            err_shot = OUT_DIR / "katene_error.png"
            try:
                page.screenshot(path=str(err_shot), full_page=True)
                result["screenshots"].append(str(err_shot))
            except Exception:
                pass
        finally:
            browser.close()

    result["steps"] = steps
    result["checked_at"] = datetime.now(timezone.utc).astimezone().isoformat()
    out = OUT_DIR / "link_result.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    # state 更新
    if STATE.is_file():
        data = json.loads(STATE.read_text(encoding="utf-8"))
        linked_set = set(result.get("linked") or [])
        for c in data.get("contracts") or []:
            if c.get("customer_no") in linked_set:
                c["katene_linked"] = True
        data["jarvis_actions_done"] = list(set((data.get("jarvis_actions_done") or []) + ["katene_link_attempt"]))
        data["updated_at"] = result["checked_at"]
        STATE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not result.get("errors") else 2


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    return run(args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
