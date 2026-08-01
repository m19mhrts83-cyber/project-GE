#!/usr/bin/env python3
"""
ポータルワン（サイサン／エネワン）から電気の月次使用量・料金を取得する。

要: .env.jarvis_private の PORTALONE_USER / PORTALONE_PASSWORD
  python scripts/jarvis_energy_portalone_fetch.py --dry-run
  python scripts/jarvis_energy_portalone_fetch.py  # → .jarvis_state/energy_portalone.json

明細一覧: /page-drkdetails.php （ログイン後）
月ラベルはポータルの請求月表示（例: 2026年07月 = 7月請求分）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
OUT = REPO / ".jarvis_state" / "energy_portalone.json"
LOGIN_URL = "https://app.members-portalone.net/"
DETAILS_PATH = "/page-drkdetails.php"


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def _prev_ym(ym: str) -> str:
    y, m = map(int, ym.split("-")[:2])
    if m == 1:
        return f"{y - 1:04d}-12"
    return f"{y:04d}-{m - 1:02d}"


def _parse_kwh_list(text: str) -> dict[str, dict[str, Any]]:
    """明細一覧の『YYYY年M月 N kWh』は請求月表示 → 利用月は前月キーで保存（Zaimの「N月分」と揃える）。"""
    months: dict[str, dict[str, Any]] = {}
    for m in re.finditer(
        r"(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d[\d,]*)\s*kWh",
        text,
        re.I,
    ):
        billing_ym = f"{m.group(1)}-{int(m.group(2)):02d}"
        usage_ym = _prev_ym(billing_ym)
        kwh = float(m.group(3).replace(",", ""))
        months[usage_ym] = {
            "buy_kwh": kwh,
            "billing_ym": billing_ym,
            "source": "portalone_drkdetails",
            "label_kind": "usage_month_approx_from_billing",
        }
    return months


def _parse_home_electric(text: str) -> dict[str, Any]:
    """トップの最新請求ブロックから電気円・使用期間を拾う。"""
    out: dict[str, Any] = {}
    bill = re.search(r"(20\d{2})/(\d{1,2})/(\d{1,2})請求分", text)
    if bill:
        out["bill_date"] = f"{bill.group(1)}-{int(bill.group(2)):02d}-{int(bill.group(3)):02d}"
        out["bill_ym"] = f"{bill.group(1)}-{int(bill.group(2)):02d}"
        out["usage_ym_approx"] = _prev_ym(out["bill_ym"])
    elec = re.search(
        r"電気\s*([\d,]+)\s*円.*?ご使用期間\s*(\d{1,2})月(\d{1,2})日\s*[～~−-]\s*(\d{1,2})月(\d{1,2})日",
        text,
        re.S,
    )
    if elec:
        out["buy_yen"] = float(elec.group(1).replace(",", ""))
        out["usage_period"] = (
            f"{int(elec.group(2)):02d}-{int(elec.group(3)):02d}"
            f"〜{int(elec.group(4)):02d}-{int(elec.group(5)):02d}"
        )
    return out


def fetch_months(*, headless: bool = True) -> dict[str, Any]:
    user = _env("PORTALONE_USER") or _env("SAISAN_USER")
    password = _env("PORTALONE_PASSWORD") or _env("SAISAN_PASSWORD")
    if not user or not password:
        return {
            "ok": False,
            "error": "missing_credentials",
            "hint": ".env.jarvis_private に PORTALONE_USER / PORTALONE_PASSWORD を追記して『保存した』",
            "months": {},
        }

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"ok": False, "error": "playwright_not_installed", "months": {}}

    months: dict[str, dict[str, Any]] = {}
    notes: list[str] = []
    snippet = ""
    home_meta: dict[str, Any] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page()
        try:
            page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
            for sel in (
                'input[name="loginId"]',
                'input[name="userId"]',
                'input[type="email"]',
                'input[name="mail"]',
                "#loginId",
            ):
                if page.locator(sel).count():
                    page.fill(sel, user)
                    break
            else:
                page.locator('input[type="text"], input[type="email"]').first.fill(user)

            for sel in ('input[name="password"]', 'input[type="password"]', "#password"):
                if page.locator(sel).count():
                    page.fill(sel, password)
                    break
            else:
                page.locator('input[type="password"]').first.fill(password)

            for sel in ('button[type="submit"]', 'input[type="submit"]', "text=ログイン"):
                if page.locator(sel).count():
                    page.locator(sel).first.click()
                    break
            page.wait_for_timeout(4000)

            home = page.inner_text("body")
            if "ご請求" not in home and "ログアウト" not in home:
                notes.append("login_may_have_failed")
                return {
                    "ok": False,
                    "error": "login_failed",
                    "notes": notes,
                    "url": page.url,
                    "months": {},
                }

            home_meta = _parse_home_electric(home)
            notes.append(f"home_url={page.url}")

            # 電気料金明細一覧へ（相対パス or 文言クリック）
            details_url = page.url.split("/")[0:3]
            base = f"{details_url[0]}//{details_url[2]}"
            try:
                page.goto(base + DETAILS_PATH, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(2500)
            except Exception as e:
                notes.append(f"goto_details_fail:{e}")
                if page.get_by_text("電気料金明細一覧").count():
                    page.get_by_text("電気料金明細一覧").first.click()
                    page.wait_for_timeout(3000)

            detail = page.inner_text("body")
            months = _parse_kwh_list(detail)
            notes.append(f"details_url={page.url}")
            notes.append(f"parsed_months={len(months)}")

            # トップの最新電気円を利用月キーへ（請求月の前月）
            uym = home_meta.get("usage_ym_approx")
            if uym and home_meta.get("buy_yen") is not None:
                months.setdefault(uym, {})
                # Zaim の円がある月は Zaim 優先（collect 側）。ここでは補助として残す
                months[uym]["buy_yen_portalone"] = home_meta["buy_yen"]
                months[uym]["usage_period"] = home_meta.get("usage_period")
                months[uym]["bill_date"] = home_meta.get("bill_date")
                months[uym]["billing_ym"] = home_meta.get("bill_ym")
                if months[uym].get("buy_kwh") is None and "source" not in months[uym]:
                    months[uym]["source"] = "portalone_home"

            snippet = re.sub(r"\s+", " ", detail)[:500]
        finally:
            browser.close()

    return {
        "ok": True,
        "fetched_at": datetime.now(JST).isoformat(timespec="seconds"),
        "months": months,
        "home": home_meta,
        "notes": notes,
        "snippet": snippet,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args(argv)
    result = fetch_months(headless=not args.headed)
    if args.dry_run:
        print(json.dumps({k: result[k] for k in result if k != "snippet"}, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") or result.get("error") == "missing_credentials" else 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"# wrote {OUT} ok={result.get('ok')} months={len(result.get('months') or {})}",
        file=sys.stderr,
    )
    if result.get("error") == "missing_credentials":
        print(result.get("hint") or "", file=sys.stderr)
        return 2
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
