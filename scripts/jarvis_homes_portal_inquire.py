#!/usr/bin/env python3
"""LIFULL HOME'S投資（toushi.homes）資料請求（ログイン壁突破・Mac専用）。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_homes_portal_inquire.py --ids 4660406 --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_homes_portal_inquire.py --ids 4660406,4715985 --apply

秘密は .env.jarvis_private の HOMES_*（空なら PORTAL_LOGIN_*）。値はログに出さない。
手順正本: docs/HOME'S投資_ログイン壁_対応_20260930.md
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
LOGIN_URL = "https://toushi.homes.co.jp/login/"
DETAIL_TMPL = "https://toushi.homes.co.jp/bukkendetail/index/{id}/"
INQUIRE_TMPL = "https://toushi.homes.co.jp/inquire/input/?property_id={id}"


def creds() -> tuple[str, str]:
    email = (
        os.environ.get("HOMES_LOGIN_EMAIL")
        or os.environ.get("PORTAL_LOGIN_EMAIL")
        or ""
    ).strip()
    password = (
        os.environ.get("HOMES_PASSWORD")
        or os.environ.get("PORTAL_LOGIN_PASSWORD")
        or ""
    ).strip()
    if not email or not password:
        raise SystemExit("missing HOMES_/PORTAL_LOGIN credentials in env")
    return email, password


def uncheck_bulk(page, keep_id: str) -> int:
    n = 0
    page.evaluate(
        """(keepId) => {
          for (const cb of document.querySelectorAll('input[type=checkbox]')) {
            const v = cb.value || '';
            const name = cb.name || '';
            if (v === '物件の詳細が知りたい') continue;
            if (name.includes('demand_teikei') && v.includes('詳細')) continue;
            if (/^\\d+$/.test(v) && v !== keepId && cb.checked) {
              cb.checked = false;
            }
            if (/property_id|bukken_id|recommend|matome|relate/i.test(name) && cb.checked) {
              cb.checked = false;
            }
          }
        }""",
        keep_id,
    )
    boxes = page.locator('input[type="checkbox"]')
    for i in range(boxes.count()):
        b = boxes.nth(i)
        try:
            val = b.get_attribute("value") or ""
            if val.isdigit() and val != keep_id and b.is_checked():
                b.uncheck(force=True)
                n += 1
        except Exception:
            pass
    return n


def process_one(page, homes_id: str, *, apply: bool) -> dict:
    item: dict = {
        "id": homes_id,
        "status": "pending",
        "detail_url": DETAIL_TMPL.format(id=homes_id),
        "inquire_url": INQUIRE_TMPL.format(id=homes_id),
        "ask_ids": None,
        "note": "",
        "ts": datetime.now(JST).isoformat(),
    }
    resp = page.goto(item["detail_url"], wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(800)
    title = page.title()
    if (resp and resp.status == 404) or "掲載終了" in title or "NotFound" in title:
        body = page.inner_text("body")[:500]
        if "掲載終了" in title or "掲載終了" in body:
            item["status"] = "listing_ended"
            item["note"] = title[:80]
            return item
        item["note"] = f"detail_status={resp.status if resp else None};{title[:60]}"

    page.goto(item["inquire_url"], wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(1200)
    if "NotFound" in page.title() and "お問合せ" not in page.title():
        item["status"] = "inquire_not_found"
        item["note"] += f"|title={page.title()[:60]}"
        return item

    try:
        page.locator('input[value="物件の詳細が知りたい"]').first.check(force=True)
    except Exception as e:
        item["note"] += f"|check_fail={type(e).__name__}"

    if page.locator("#prg-demand-text").count():
        page.fill(
            "#prg-demand-text",
            "資料請求します。概要・賃料根拠・公図／固評があればご共有ください（買付前提ではありません）。",
        )

    unchecked = uncheck_bulk(page, homes_id)
    item["note"] += f"|unchecked_bulk≈{unchecked}"

    if not apply:
        item["status"] = "dry_run_ready"
        return item

    clicked = False
    for label in ("確認ページへ進む", "確認ページへ", "確認へ進む"):
        btn = page.get_by_role("button", name=re.compile(label))
        if btn.count() == 0:
            btn = page.locator(
                f'button:has-text("{label}"), input[type="submit"][value*="{label}"]'
            )
        if btn.count():
            btn.first.scroll_into_view_if_needed()
            btn.first.click()
            page.wait_for_timeout(2500)
            clicked = True
            item["note"] += f"|click:{label}"
            break
    if not clicked:
        item["status"] = "confirm_button_missing"
        return item

    sent = False
    for label in ("送信する", "この内容で送信", "送信"):
        btn = page.get_by_role("button", name=re.compile(label))
        if btn.count() == 0:
            btn = page.locator(
                f'button:has-text("{label}"), input[type="submit"][value*="{label}"]'
            )
        if btn.count():
            btn.first.click()
            page.wait_for_timeout(3000)
            sent = True
            item["note"] += f"|final:{label}"
            break

    item["complete_url"] = page.url
    m = re.search(r"ask_ids=([^&]+)", page.url)
    if m:
        item["ask_ids"] = m.group(1)
    text = page.inner_text("body")[:2000]
    if "inquire/complete" in page.url or any(
        x in text for x in ("ありがとう", "承りました", "受付完了", "送信完了")
    ):
        item["status"] = "portal_sent"
    elif sent:
        item["status"] = "submitted_unconfirmed"
    else:
        item["status"] = "failed"
    return item


def main() -> int:
    ap = argparse.ArgumentParser(description="HOME'S投資 資料請求（Mac）")
    ap.add_argument("--ids", required=True, help="カンマ区切り homes property_id")
    ap.add_argument("--apply", action="store_true", help="確認→送信まで実行")
    ap.add_argument("--dry-run", action="store_true", help="フォーム到達まで（送信しない）")
    ap.add_argument("--headed", action="store_true", help="ブラウザ表示（既定 headless）")
    ap.add_argument("--json-out", default="", help="結果 JSON パス")
    args = ap.parse_args()
    apply = bool(args.apply) and not args.dry_run
    ids = [x.strip() for x in args.ids.split(",") if x.strip()]
    if not ids:
        raise SystemExit("no ids")

    email, password = creds()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit("playwright not installed") from None

    results: list[dict] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headed, slow_mo=50 if args.headed else 0)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
        page.fill('input[name="login_email"]', email)
        page.fill('input[name="password"]', password)
        page.click(".prg-login")
        page.wait_for_timeout(3000)
        if "mypage" not in page.url and "ログアウト" not in page.content():
            print("LOGIN_FAILED", page.url, file=sys.stderr)
            browser.close()
            return 2
        print(f"login_ok apply={apply}")
        for hid in ids:
            r = process_one(page, hid, apply=apply)
            results.append(r)
            print(
                f"RESULT id={r['id']} status={r['status']} ask_ids={r.get('ask_ids')} note={r.get('note','')[:120]}"
            )
        browser.close()

    out = {
        "ok": all(r["status"] in ("portal_sent", "dry_run_ready", "listing_ended") for r in results),
        "apply": apply,
        "results": results,
        "ts": datetime.now(JST).isoformat(),
    }
    text = json.dumps(out, ensure_ascii=False, indent=2)
    if args.json_out:
        Path(args.json_out).write_text(text, encoding="utf-8")
    print(text)
    return 0 if out["ok"] or not apply else 1


if __name__ == "__main__":
    raise SystemExit(main())
