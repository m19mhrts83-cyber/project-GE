#!/usr/bin/env python3
"""証券の保有内訳スナップ（保険配分と同系統）。

正本:
  - SBI インデックス枠: Zaim 証券詳細（財務）
  - Bloomo: マネーフォワード ME（評価額と同系）

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_securities_holdings.py
  ~/selenium_env/venv/bin/python scripts/jarvis_securities_holdings.py --skip-web
  ~/selenium_env/venv/bin/python scripts/jarvis_securities_holdings.py --json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
SNAP_PATH = REPO / ".jarvis_state" / "securities_holdings_snap.json"
FINANCE = REPO / "215_kamiooya" / "C1_cursor" / "finance" / "zaim_budget_sync"

# name \t units \t cost \t nav \t value \t pnl
ZAIM_FUND_RE = re.compile(
    r"^(.+?)\t([\d,]+)\t¥([\d,]+)\t¥([\d,]+)\t¥([\d,]+)\t([+\-−]?¥[\d,]+)$"
)
# MF Bloomo: code \t name \t qty \t ... \t value円 \t ...
MF_ETF_RE = re.compile(
    r"^([A-Z0-9]+)\t(.+?)\t([\d,]+)\t.*?\t([\d,]+)円\t"
)


def load_snap() -> dict[str, Any]:
    if not SNAP_PATH.is_file():
        return {"accounts": {}, "updated_at": None}
    try:
        return json.loads(SNAP_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"accounts": {}, "updated_at": None}


def save_snap(data: dict[str, Any]) -> None:
    SNAP_PATH.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = date.today().isoformat()
    SNAP_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def push_supabase(snap: dict[str, Any]) -> int:
    """securities_holdings へ account_id×as_of で upsert。"""
    sys.path.insert(0, str(REPO / "scripts"))
    from jarvis_trade_common import sb_client

    sb = sb_client()
    n = 0
    for aid, rec in (snap.get("accounts") or {}).items():
        if rec.get("error") and not rec.get("funds"):
            continue
        as_of = rec.get("as_of") or date.today().isoformat()
        funds = rec.get("funds") or []
        sb.table("securities_holdings").upsert(
            {
                "account_id": aid,
                "as_of": as_of,
                "value_jpy": rec.get("value_jpy"),
                "source": rec.get("source"),
                "payload": {"funds": funds, "url": rec.get("url")},
            },
            on_conflict="account_id,as_of",
        ).execute()
        n += 1
    return n


def _yen(s: str) -> int:
    return int(re.sub(r"[^\d]", "", s or "0") or "0")


def parse_zaim_funds(text: str) -> list[dict[str, Any]]:
    funds: list[dict[str, Any]] = []
    for ln in (text or "").splitlines():
        ln = ln.strip()
        m = ZAIM_FUND_RE.match(ln)
        if not m:
            continue
        name = m.group(1).strip()
        if name in ("銘柄", "ファンド名") or name.startswith("銘柄"):
            continue
        value = _yen(m.group(5))
        if value <= 0 and name == "SBI証券口座分":
            continue
        funds.append(
            {
                "name": name,
                "units": _yen(m.group(2)),
                "cost_unit": _yen(m.group(3)),
                "nav": _yen(m.group(4)),
                "value_jpy": value,
                "pnl_jpy": int(
                    re.sub(r"[^\d\-]", "", m.group(6).replace("−", "-").replace("+", ""))
                    or "0"
                ),
            }
        )
    # merge same name (複数口座・NISA分割)
    merged: dict[str, dict[str, Any]] = {}
    for f in funds:
        prev = merged.get(f["name"])
        if not prev:
            merged[f["name"]] = dict(f)
            continue
        prev["units"] += f["units"]
        prev["value_jpy"] += f["value_jpy"]
        prev["pnl_jpy"] += f["pnl_jpy"]
    return sorted(merged.values(), key=lambda x: -x["value_jpy"])


def parse_mf_etfs(text: str) -> list[dict[str, Any]]:
    funds: list[dict[str, Any]] = []
    for ln in (text or "").splitlines():
        ln = ln.strip()
        m = MF_ETF_RE.match(ln)
        if not m:
            continue
        funds.append(
            {
                "code": m.group(1),
                "name": m.group(2).strip(),
                "units": _yen(m.group(3)),
                "value_jpy": _yen(m.group(4)),
            }
        )
    return sorted(funds, key=lambda x: -x["value_jpy"])


def fetch_zaim_sbi() -> dict[str, Any]:
    sys.path.insert(0, str(FINANCE))
    import zaim_budget_apply as zaim  # noqa: WPS433
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser, ctx, _ = zaim.open_browser_context(
            pw,
            headless=False,
            connect_cdp=None,
            storage_state=zaim.STORAGE_STATE,
        )
        page = zaim.get_work_page(ctx)
        zaim.ensure_logged_in(
            page,
            email=zaim.DEFAULT_LOGIN_EMAIL,
            password=zaim.DEFAULT_LOGIN_PASSWORD,
            google_email=zaim.DEFAULT_GOOGLE_EMAIL,
            login_method="email",
            manual=False,
        )
        page.goto("https://zaim.net/home", wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(1500)
        page.locator('text=SBI 証券').first.click(timeout=10_000)
        page.wait_for_timeout(2000)
        body = page.inner_text("body") or ""
        url = page.url
        zaim.save_storage_state(ctx)
        if browser:
            browser.close()
    funds = parse_zaim_funds(body)
    total = sum(f["value_jpy"] for f in funds)
    return {
        "as_of": date.today().isoformat(),
        "source": "zaim",
        "url": url,
        "value_jpy": total,
        "funds": funds,
    }


def fetch_mf_bloomo() -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    profile = Path(
        (os.environ.get("MONEYFORWARD_BROWSER_PROFILE") or "").strip()
        or str(REPO / ".jarvis_state" / "mf_me_browser_profile")
    )
    show = (os.environ.get("MONEYFORWARD_BLOOMO_SHOW_URL") or "").strip()
    ch = (os.environ.get("MONEYFORWARD_BROWSER_CHANNEL") or "chrome").strip().lower()
    launch: dict[str, Any] = {
        "user_data_dir": str(profile),
        "headless": False,
        "viewport": {"width": 1280, "height": 900},
        "locale": "ja-JP",
        "args": ["--disable-blink-features=AutomationControlled"],
    }
    if ch and ch not in ("", "chromium", "none", "0"):
        launch["channel"] = ch
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(**launch)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        if show:
            page.goto(show, wait_until="domcontentloaded", timeout=60_000)
        else:
            page.goto(
                "https://moneyforward.com/accounts",
                wait_until="domcontentloaded",
                timeout=60_000,
            )
            page.wait_for_timeout(1500)
            page.locator('a:has-text("ブルーモ証券")').first.click(timeout=15_000)
        page.wait_for_timeout(1500)
        body = page.inner_text("body") or ""
        url = page.url
        ctx.close()
    funds = parse_mf_etfs(body)
    m = re.search(r"証券口座\s*([\d,]+)\s*円", body) or re.search(
        r"資産総額[：:]\s*([\d,]+)\s*円", body
    )
    total = int(m.group(1).replace(",", "")) if m else sum(f["value_jpy"] for f in funds)
    return {
        "as_of": date.today().isoformat(),
        "source": "moneyforward",
        "url": url,
        "value_jpy": total,
        "funds": funds,
    }


def fund_summary(funds: list[dict[str, Any]] | None, limit: int = 6) -> str:
    if not funds:
        return "—"
    parts = []
    for f in funds[:limit]:
        label = f.get("code") or f.get("name") or "?"
        if f.get("code") and f.get("name"):
            label = f"{f['code']} {f['name']}"
        parts.append(f"{label} {f.get('value_jpy', 0):,}円")
    extra = len(funds) - limit
    if extra > 0:
        parts.append(f"他{extra}件")
    return " / ".join(parts)


def print_view(snap: dict[str, Any]) -> None:
    print("📎 証券内訳（保険配分と同系統）")
    for aid, rec in (snap.get("accounts") or {}).items():
        v = rec.get("value_jpy")
        vtxt = f"{int(v):,}円" if v is not None else "—"
        print(f"- {aid}: {vtxt} ({rec.get('source') or '—'} / {rec.get('as_of') or '—'})")
        print(f"  {fund_summary(rec.get('funds'))}")


def main() -> int:
    ap = argparse.ArgumentParser(description="証券保有内訳スナップ")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--skip-web", action="store_true", help="前回 snap のみ表示")
    ap.add_argument("--sbi-only", action="store_true")
    ap.add_argument("--bloomo-only", action="store_true")
    ap.add_argument(
        "--push-db",
        action="store_true",
        help="Supabase securities_holdings へ upsert",
    )
    ap.add_argument(
        "--no-push-db",
        action="store_true",
        help="DB upsert をしない（ローカル snap のみ）",
    )
    args = ap.parse_args()

    snap = load_snap()
    accounts = dict(snap.get("accounts") or {})

    if not args.skip_web:
        do_sbi = not args.bloomo_only
        do_bloomo = not args.sbi_only
        if do_sbi:
            try:
                accounts["sbi_index"] = fetch_zaim_sbi()
                print(
                    f"# sbi_index holdings: {len(accounts['sbi_index'].get('funds') or [])} "
                    f"total={accounts['sbi_index'].get('value_jpy'):,}",
                    file=sys.stderr,
                )
            except Exception as exc:
                print(f"# sbi_index holdings FAIL: {exc}", file=sys.stderr)
                accounts.setdefault("sbi_index", {})["error"] = str(exc)[:300]
        if do_bloomo:
            try:
                accounts["bloomo"] = fetch_mf_bloomo()
                print(
                    f"# bloomo holdings: {len(accounts['bloomo'].get('funds') or [])} "
                    f"total={accounts['bloomo'].get('value_jpy'):,}",
                    file=sys.stderr,
                )
            except Exception as exc:
                print(f"# bloomo holdings FAIL: {exc}", file=sys.stderr)
                accounts.setdefault("bloomo", {})["error"] = str(exc)[:300]
        snap = {"accounts": accounts}
        save_snap(snap)

    do_push = args.push_db or (not args.no_push_db and not args.skip_web)
    if do_push and not args.no_push_db:
        try:
            n = push_supabase(snap)
            print(f"# securities_holdings supabase upsert={n}", file=sys.stderr)
        except Exception as exc:
            print(f"# securities_holdings supabase FAIL: {exc}", file=sys.stderr)

    if args.json:
        print(json.dumps(snap, ensure_ascii=False))
    else:
        print_view(snap)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
