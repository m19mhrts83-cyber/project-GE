#!/usr/bin/env python3
"""
ポータルワン（サイサン／エネワン）から電気の月次使用量・料金を取得する。

要: .env.jarvis_private の PORTALONE_USER / PORTALONE_PASSWORD
  python scripts/jarvis_energy_portalone_fetch.py --dry-run
  python scripts/jarvis_energy_portalone_fetch.py  # → .jarvis_state/energy_portalone.json
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


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


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
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page()
        try:
            page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
            # ログイン欄はサイト改修で変わりうるので広めに探す
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
                # 最初の text/email
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

            body = page.inner_text("body")
            if "ログイン" in body and ("パスワード" in body or "会員" in body) and "ご請求" not in body:
                notes.append("login_may_have_failed")
                browser.close()
                return {
                    "ok": False,
                    "error": "login_failed",
                    "notes": notes,
                    "url": page.url,
                    "months": {},
                }

            # 画面テキストから「YYYY年M月」「N kWh」「N 円」をゆるく拾う
            # ポータルワンのグラフ／一覧は改修されやすいので、取れない月は空のまま
            for m in re.finditer(
                r"(20\d{2})\s*年\s*(\d{1,2})\s*月[^\n]{0,80}?(\d[\d,]*)\s*kWh",
                body,
                re.I,
            ):
                ym = f"{m.group(1)}-{int(m.group(2)):02d}"
                kwh = float(m.group(3).replace(",", ""))
                months.setdefault(ym, {})["buy_kwh"] = kwh
                months[ym]["source"] = "portalone_text"

            for m in re.finditer(
                r"(20\d{2})\s*年\s*(\d{1,2})\s*月[^\n]{0,80}?(\d[\d,]*)\s*円",
                body,
            ):
                ym = f"{m.group(1)}-{int(m.group(2)):02d}"
                yen = float(m.group(3).replace(",", ""))
                # 電気らしき金額帯のみ（ガス合算を避けるため上限緩め）
                if 500 <= yen <= 80000:
                    months.setdefault(ym, {})["buy_yen"] = yen
                    months[ym]["source"] = months[ym].get("source") or "portalone_text"

            notes.append(f"parsed_months={len(months)}")
            notes.append(f"url={page.url}")
            snippet = re.sub(r"\s+", " ", body)[:500]
        finally:
            browser.close()

    return {
        "ok": True,
        "fetched_at": datetime.now(JST).isoformat(timespec="seconds"),
        "months": months,
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
    print(f"# wrote {OUT} ok={result.get('ok')} months={len(result.get('months') or {})}", file=sys.stderr)
    if result.get("error") == "missing_credentials":
        print(result.get("hint") or "", file=sys.stderr)
        return 2
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
