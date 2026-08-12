#!/usr/bin/env python3
"""流動性・週次家計サマリーを Zaim から取り、Supabase に積む。

  - liquidity_snapshots: 銀行／現金／電子マネー残高
  - cashflow_week_summaries: その週の収入・支出・クレジット支出（要約）

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_liquidity_weekly.py --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_liquidity_weekly.py --json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from jarvis_trade_common import REPO, sb_client, today_jst

FINANCE = REPO / "215_kamiooya" / "C1_cursor" / "finance" / "zaim_budget_sync"
sys.path.insert(0, str(FINANCE))
sys.path.insert(0, str(REPO / "scripts"))

import jarvis_zaim_mhi_balance as zaim_acc  # noqa: E402
import zaim_budget_apply as zaim  # noqa: E402

YEN_INLINE = re.compile(
    r"(?:[¥￥]\s*(-?[0-9]{1,3}(?:,[0-9]{3})+|-?[0-9]+)|(-?[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)円)"
)


def week_start(d: date | None = None) -> date:
    d = d or today_jst()
    return d - timedelta(days=d.weekday())


def week_end(d: date | None = None) -> date:
    return week_start(d) + timedelta(days=6)


def _parse_yen_near(label: str, text: str) -> int | None:
    """ラベル直後〜同一行／次行の円額を拾う。"""
    for ln in (text or "").splitlines():
        if label not in ln:
            continue
        m = YEN_INLINE.search(ln)
        if m:
            raw = m.group(1) or m.group(2)
            return int(raw.replace(",", ""))
    # 次行パターン
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    for i, ln in enumerate(lines):
        if label in ln and i + 1 < len(lines):
            m = YEN_INLINE.search(lines[i + 1])
            if m:
                raw = m.group(1) or m.group(2)
                return int(raw.replace(",", ""))
    return None


def match_balances(
    zaim_accounts: list[dict[str, Any]],
    liquidity_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    used_zaim: set[str] = set()
    for liq in liquidity_rows:
        if not liq.get("active", True):
            continue
        needle = (liq.get("zaim_match") or liq.get("name") or "").strip()
        if not needle:
            continue
        best: dict[str, Any] | None = None
        for za in zaim_accounts:
            name = za["name"]
            if name in used_zaim:
                continue
            if needle in name:
                if best is None or za["value_jpy"] > best["value_jpy"]:
                    best = za
        if best:
            used_zaim.add(best["name"])
            hits.append(
                {
                    "account_id": liq["id"],
                    "name": liq["name"],
                    "zaim_name": best["name"],
                    "balance_jpy": int(best["value_jpy"]),
                    "kind": liq["kind"],
                }
            )
    return hits


def scrape_zaim(*, headless: bool) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
    """口座一覧 + 週次収支テキストを1セッションで取得。"""
    from playwright.sync_api import sync_playwright

    ws = week_start()
    we = min(week_end(), today_jst())
    with sync_playwright() as pw:
        browser, ctx, _ = zaim.open_browser_context(
            pw,
            headless=headless,
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
        texts: list[str] = []
        for url in ("https://zaim.net/home", "https://zaim.net/accounts"):
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(2000)
            texts.append(page.inner_text("body") or "")

        # 期間一覧（週）
        list_urls = [
            f"https://zaim.net/list?start_date={ws.isoformat()}&end_date={we.isoformat()}",
            f"https://zaim.net/money?start_date={ws.isoformat()}&end_date={we.isoformat()}",
            "https://zaim.net/list",
        ]
        cashflow_text = ""
        for url in list_urls:
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                page.wait_for_timeout(2500)
                cashflow_text = page.inner_text("body") or ""
                if any(k in cashflow_text for k in ("収入", "支出", "支払", "入金")):
                    break
            except Exception:
                continue

        zaim.save_storage_state(ctx)
        if browser:
            browser.close()

    merged: dict[str, dict[str, Any]] = {}
    for t in texts:
        for acc in zaim_acc.parse_accounts_from_text(t):
            prev = merged.get(acc["name"])
            if not prev or acc["value_jpy"] > prev["value_jpy"]:
                merged[acc["name"]] = acc

    income = _parse_yen_near("収入", cashflow_text)
    expense = _parse_yen_near("支出", cashflow_text)
    if expense is None:
        expense = _parse_yen_near("支払総額", cashflow_text) or _parse_yen_near(
            "使った総額", cashflow_text
        )
    # クレジット: 「カード」ラベル付近、または支出の内クレジット言及
    credit = _parse_yen_near("クレジットカード", cashflow_text)
    if credit is None:
        credit = _parse_yen_near("カード", cashflow_text)

    note_parts = [f"week {ws.isoformat()}〜{we.isoformat()}"]
    if income is None and expense is None:
        note_parts.append("収支ラベル未検出（残高のみ）")
    if credit is None:
        note_parts.append("クレジット支出は未検出")

    cashflow = {
        "week_start": ws.isoformat(),
        "income_jpy": income,
        "expense_jpy": expense,
        "credit_spend_jpy": credit,
        "note": "; ".join(note_parts),
        "source": "zaim",
    }
    return list(merged.values()), cashflow, texts[0][:500]


def upsert_liquidity(sb: Any, hits: list[dict[str, Any]], as_of: str) -> int:
    n = 0
    for h in hits:
        sb.table("liquidity_snapshots").upsert(
            {
                "account_id": h["account_id"],
                "as_of": as_of,
                "balance_jpy": h["balance_jpy"],
                "source": "zaim",
                "note": f"Zaim {h['zaim_name']}",
            },
            on_conflict="account_id,as_of",
        ).execute()
        n += 1
    return n


def upsert_cashflow(sb: Any, cashflow: dict[str, Any]) -> None:
    sb.table("cashflow_week_summaries").upsert(
        {
            "week_start": cashflow["week_start"],
            "income_jpy": cashflow.get("income_jpy"),
            "expense_jpy": cashflow.get("expense_jpy"),
            "credit_spend_jpy": cashflow.get("credit_spend_jpy"),
            "note": cashflow.get("note"),
            "source": cashflow.get("source") or "zaim",
            "updated_at": today_jst().isoformat() + "T00:00:00+09:00",
        },
        on_conflict="week_start",
    ).execute()


def main() -> int:
    ap = argparse.ArgumentParser(description="流動性・週次家計 → Supabase")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()

    sb = None if args.dry_run else sb_client()
    as_of = today_jst().isoformat()

    liq_rows: list[dict[str, Any]] = []
    if sb is not None:
        liq_rows = (
            sb.table("liquidity_accounts")
            .select("id, name, kind, zaim_match, active, sort_order")
            .eq("active", True)
            .order("sort_order")
            .execute()
            .data
            or []
        )
    else:
        # dry-run 用の最小シード
        liq_rows = [
            {
                "id": "smbc_kariya",
                "name": "三井住友銀行 刈谷",
                "kind": "bank",
                "zaim_match": "三井住友銀行 刈谷",
                "active": True,
            },
            {
                "id": "wallet",
                "name": "お財布",
                "kind": "cash",
                "zaim_match": "お財布",
                "active": True,
            },
        ]

    try:
        zaim_accounts, cashflow, _ = scrape_zaim(headless=not args.headed)
    except Exception as exc:
        err = {"status": "error", "reason": str(exc)[:400]}
        print(json.dumps(err, ensure_ascii=False) if args.json else f"# FAIL {err['reason']}")
        return 1

    hits = match_balances(zaim_accounts, liq_rows)
    # カードは残高0でもヒットしなければスキップ（支出は cashflow 側）
    bank_hits = [h for h in hits if h["kind"] in ("bank", "cash", "emoney")]

    out = {
        "status": "ok",
        "as_of": as_of,
        "matched": len(bank_hits),
        "balances": bank_hits,
        "cashflow": cashflow,
        "dry_run": args.dry_run,
    }

    if not args.dry_run and sb is not None:
        n = upsert_liquidity(sb, bank_hits, as_of)
        upsert_cashflow(sb, cashflow)
        out["upserted_balances"] = n
        print(
            f"# liquidity: upserted={n} cashflow "
            f"in={cashflow.get('income_jpy')} out={cashflow.get('expense_jpy')} "
            f"credit={cashflow.get('credit_spend_jpy')}",
            file=sys.stderr,
        )

    if args.json:
        print(json.dumps(out, ensure_ascii=False))
    else:
        print("📎 流動性週次")
        for h in bank_hits[:15]:
            print(f"- {h['name']}: {h['balance_jpy']:,}円 ← {h['zaim_name']}")
        cf = cashflow
        print(
            f"- 週次収支 ({cf['week_start']}): "
            f"収入 {cf.get('income_jpy') if cf.get('income_jpy') is not None else '—'} / "
            f"支出 {cf.get('expense_jpy') if cf.get('expense_jpy') is not None else '—'} / "
            f"クレカ {cf.get('credit_spend_jpy') if cf.get('credit_spend_jpy') is not None else '—'}"
        )
        if cf.get("note"):
            print(f"  note: {cf['note']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
