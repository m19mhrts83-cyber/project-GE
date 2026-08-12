#!/usr/bin/env python3
"""Zaim（財務）の口座残高から三菱重工持株の評価額を取る。

毎月の買い足しは口数固定では追えないので、連携口座の評価額を正とする。
Yahoo 7011 終値は使わない（トレード監視用の別経路）。

ホーム「現在 の残高」は口座名の次行が ¥377,971 形式。accounts は名称のみ。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_zaim_mhi_balance.py --json
  ~/selenium_env/venv/bin/python scripts/jarvis_zaim_mhi_balance.py --list
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

FINANCE = Path(__file__).resolve().parents[1] / "215_kamiooya" / "C1_cursor" / "finance" / "zaim_budget_sync"
sys.path.insert(0, str(FINANCE))

import zaim_budget_apply as zaim  # noqa: E402

DEFAULT_MATCH = "野村持株WEBサービス,持株,マイ・ターゲット,マイターゲット,野村持株"
ACCOUNT_URLS = (
    "https://zaim.net/home",
    "https://zaim.net/accounts",
)
YEN_LINE_RE = re.compile(r"^[¥￥]\s*(-?[0-9]{1,3}(?:,[0-9]{3})+|-?[0-9]+)$")
YEN_INLINE_RE = re.compile(
    r"(?:[¥￥]\s*(-?[0-9]{1,3}(?:,[0-9]{3})+|-?[0-9]+)|(-?[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)円)"
)
SKIP_NAMES = {
    "現在 の残高",
    "現在の残高",
    "合計：",
    "使った総額",
    "予算の残り",
    "記録数",
    "記録日数",
    "連続記録",
    "内訳",
    "現金",
    "電子マネー",
    "未分類",
    "証券",
    "ポイント",
}


def match_needles(override: str | None = None) -> list[str]:
    raw = (override or os.environ.get("ZAIM_MHI_ACCOUNT_MATCH") or DEFAULT_MATCH).strip()
    return [x.strip() for x in raw.split(",") if x.strip()]


def _is_account_name(name: str) -> bool:
    if not name or len(name) >= 80:
        return False
    if name.startswith("●") or name.startswith("■"):
        return False
    if name.endswith("円") or name.startswith("¥") or name.startswith("￥"):
        return False
    if name in SKIP_NAMES or name.startswith("合計"):
        return False
    return True


def parse_accounts_from_text(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    i = 0
    while i < len(lines):
        name = lines[i]
        yen: int | None = None
        if i + 1 < len(lines):
            m = YEN_LINE_RE.match(lines[i + 1])
            if m:
                yen = int(m.group(1).replace(",", ""))
        if yen is None:
            m2 = YEN_INLINE_RE.search(name)
            if not m2 and i + 1 < len(lines):
                m2 = YEN_INLINE_RE.search(lines[i + 1])
            if m2:
                raw = m2.group(1) or m2.group(2)
                yen = int(raw.replace(",", ""))
        if yen is not None and yen >= 1000 and _is_account_name(name):
            rows.append({"name": name, "value_jpy": yen})
        i += 1
    best: dict[str, dict[str, Any]] = {}
    for r in rows:
        prev = best.get(r["name"])
        if not prev or r["value_jpy"] > prev["value_jpy"]:
            best[r["name"]] = r
    return list(best.values())


def pick_mhi(accounts: list[dict[str, Any]], needles: list[str]) -> dict[str, Any] | None:
    hits = []
    for acc in accounts:
        name = acc["name"]
        if any(n in name for n in needles):
            hits.append(acc)
    if not hits:
        return None
    hits.sort(key=lambda x: x["value_jpy"], reverse=True)
    return hits[0]


def scrape(headless: bool) -> tuple[list[dict[str, Any]], str]:
    from playwright.sync_api import sync_playwright

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
        for url in ACCOUNT_URLS:
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(2500)
            texts.append(page.inner_text("body") or "")
        zaim.save_storage_state(ctx)
        if browser:
            browser.close()
    merged: dict[str, dict[str, Any]] = {}
    for t in texts:
        for acc in parse_accounts_from_text(t):
            prev = merged.get(acc["name"])
            if not prev or acc["value_jpy"] > prev["value_jpy"]:
                merged[acc["name"]] = acc
    return list(merged.values()), texts[0][:2000]


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Zaim 口座残高（既定=持株。--match / ZAIM_*_ACCOUNT_MATCH で他口座可）"
    )
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--list", action="store_true", help="口座名と残高を列挙（突合用）")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument(
        "--match",
        default="",
        help="口座名の部分一致（カンマ区切り）。例: 'SBI 証券'",
    )
    ap.add_argument(
        "--label",
        default="",
        help="エラー文言用ラベル（例: SBIインデックス）",
    )
    args = ap.parse_args()

    needles = match_needles(args.match or None)
    label = (args.label or ("持株" if not args.match else args.match.split(",")[0])).strip()
    try:
        accounts, _ = scrape(headless=not args.headed)
    except Exception as exc:
        err = {"status": "error", "reason": str(exc)[:300]}
        print(json.dumps(err, ensure_ascii=False) if args.json else f"# FAIL {err['reason']}", file=sys.stderr)
        return 1

    if args.list and not args.json:
        print("📎 Zaim 口座（円が読めたもの）")
        for acc in sorted(accounts, key=lambda x: -x["value_jpy"])[:40]:
            print(f"- {acc['name']}: {acc['value_jpy']:,}円")
        print(f"# match needles: {needles}")

    hit = pick_mhi(accounts, needles)
    if not hit:
        payload = {
            "status": "error",
            "reason": f"Zaim口座に{label}が見つかりません needles={needles}",
            "accounts": [a["name"] for a in accounts[:30]],
        }
        print(json.dumps(payload, ensure_ascii=False))
        return 2

    out = {
        "status": "ok",
        "value_jpy": hit["value_jpy"],
        "account": hit["name"],
        "note": f"Zaim {hit['name']} {hit['value_jpy']:,}円",
        "source": "zaim",
    }
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
