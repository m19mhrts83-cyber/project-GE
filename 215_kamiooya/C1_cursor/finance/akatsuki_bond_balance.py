#!/usr/bin/env python3
"""
あかつき証券のマイページから債券残高合計を取得する。

前提:
- Playwright が利用可能な Python 環境で実行する
- 認証情報は .env.akatsuki などのローカルファイルで管理する
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_LOGIN_URL = "https://akatsuki-sec.starmf.jp/web/rmfCmnCauSysLgiInitAction.do"
DEFAULT_ENV_PATH = SCRIPT_DIR / ".env.akatsuki"
DEFAULT_STORAGE_STATE = SCRIPT_DIR / ".akatsuki_storage_state.json"
DEFAULT_DEBUG_DIR = SCRIPT_DIR / "debug"

BOND_KEYWORDS = ("債券", "外国債", "国内債", "公社債")
AMOUNT_HEADER_KEYWORDS = ("評価額", "時価", "残高", "現在額", "金額", "取得金額")
AMOUNT_HEADER_EXCLUDE = ("利率", "償還", "単価", "数量", "額面", "クーポン", "利回り")


@dataclass
class BalanceResult:
    total_jpy: int
    amount_rows: list[int]
    source_url: str
    parser_mode: str
    category: str = ""
    pl_jpy: int = 0


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and value and key not in os.environ:
            os.environ[key] = value


def _parse_yen_int(text: str) -> list[int]:
    out: list[int] = []
    for match in re.finditer(r"[-+]?\d[\d,]{2,}(?:\.\d+)?", text):
        raw = match.group(0).replace(",", "")
        try:
            value = int(float(raw))
        except ValueError:
            continue
        if value > 0:
            out.append(value)
    return out


def _text_has_any(text: str, words: tuple[str, ...]) -> bool:
    return any(word in text for word in words)


def _guess_amount_column(headers: list[str]) -> int | None:
    for idx, header in enumerate(headers):
        if _text_has_any(header, AMOUNT_HEADER_KEYWORDS) and not _text_has_any(
            header, AMOUNT_HEADER_EXCLUDE
        ):
            return idx
    return None


def _extract_amounts_from_tables(tables: list[dict[str, Any]]) -> tuple[list[int], str]:
    matched_amounts: list[int] = []
    mode = "row-max-fallback"
    for table in tables:
        headers = [str(x).strip() for x in table.get("headers", [])]
        rows = [[str(c).strip() for c in row] for row in table.get("rows", [])]
        if not rows:
            continue

        amount_col = _guess_amount_column(headers) if headers else None
        if amount_col is not None:
            mode = "header-column"

        for row in rows:
            row_text = " ".join(row)
            if not _text_has_any(row_text, BOND_KEYWORDS):
                continue

            nums: list[int] = []
            if amount_col is not None and amount_col < len(row):
                nums = _parse_yen_int(row[amount_col])
            if not nums:
                nums = _parse_yen_int(row_text)
                nums = [n for n in nums if n >= 10000]
            if nums:
                matched_amounts.append(max(nums))

    if matched_amounts:
        return matched_amounts, mode

    flat_blocks: list[str] = []
    for table in tables:
        for row in table.get("rows", []):
            text = " ".join(str(c).strip() for c in row)
            if _text_has_any(text, BOND_KEYWORDS):
                flat_blocks.append(text)
    for text in flat_blocks:
        nums = [n for n in _parse_yen_int(text) if n >= 10000]
        if nums:
            matched_amounts.append(max(nums))
    return matched_amounts, mode


def _extract_table_snapshot(page) -> list[dict[str, Any]]:
    return page.evaluate(
        """
() => {
  const tables = Array.from(document.querySelectorAll("table"));
  return tables.map((table) => {
    const headerCells = Array.from(table.querySelectorAll("th"));
    const headers = headerCells.map((h) => (h.innerText || "").trim()).filter(Boolean);
    const rows = Array.from(table.querySelectorAll("tr")).map((tr) =>
      Array.from(tr.querySelectorAll("th,td")).map((cell) => (cell.innerText || "").replace(/\\s+/g, " ").trim())
    ).filter((r) => r.length > 0);
    return { headers, rows };
  });
}
"""
    )


def _extract_holdings_summary_rows(page) -> list[dict[str, str]]:
    """
    「預り資産（保有資産評価合計）」のテーブルを想定して行データを抜く。
    返り値: [{category, eval, pl}, ...]
    """
    return page.evaluate(
        """
() => {
  const out = [];
  const tables = Array.from(document.querySelectorAll("table"));
  for (const table of tables) {
    const allText = (table.innerText || "");
    if (!allText.includes("商品分類") || !allText.includes("評価額")) continue;
    const rows = Array.from(table.querySelectorAll("tr"));
    for (const tr of rows) {
      const cells = Array.from(tr.querySelectorAll("th,td")).map(c => (c.innerText||"").replace(/\\s+/g," ").trim());
      if (cells.length < 2) continue;
      // 期待: [商品分類, 評価額, 評価損益] だが崩れる場合もある
      const category = cells[0] || "";
      const evalv = cells[1] || "";
      const plv = cells[2] || "";
      if (!category) continue;
      // 合計行なども含めて返す（判定はPython側）
      out.push({category, eval: evalv, pl: plv});
    }
  }
  return out;
}
"""
    )


def _parse_yen_signed(text: str) -> int | None:
    """
    ' +148,113円' / '- 1,234円' / '0円' などを int に。
    """
    s = (text or "").strip()
    if not s:
        return None
    sign = -1 if s.startswith("-") else 1
    nums = _parse_yen_int(s)
    if not nums:
        # 0円, -- など
        if "0" in s:
            return 0
        return None
    return sign * nums[0]


def _pick_eval_and_pl(rows: list[dict[str, str]], target_category: str) -> tuple[int | None, int | None, str]:
    """
    rows から target_category を含む行を優先して (評価額, 評価損益, category) を返す。
    見つからなければ合計行を探す。
    """
    needle = (target_category or "").strip()
    candidates = rows
    if needle:
        candidates = [r for r in rows if needle in (r.get("category") or "")]
    if not candidates:
        candidates = [r for r in rows if "合計" in (r.get("category") or "")]
    for r in candidates:
        ev = _parse_yen_signed(r.get("eval") or "")
        pl = _parse_yen_signed(r.get("pl") or "")
        if ev is not None:
            return ev, (pl if pl is not None else 0), (r.get("category") or "")
    return None, None, ""

def _click_bond_navigation(page) -> bool:
    nav_selector = os.environ.get("AKATSUKI_BOND_NAV_SELECTOR", "").strip()
    if nav_selector:
        if page.locator(nav_selector).count() > 0:
            page.locator(nav_selector).first.click()
            return True

    link_text = os.environ.get("AKATSUKI_BOND_LINK_TEXT", "債券").strip()
    candidates = [
        f"a:has-text('{link_text}')",
        f"button:has-text('{link_text}')",
        f"[role='link']:has-text('{link_text}')",
    ]
    for sel in candidates:
        loc = page.locator(sel)
        if loc.count() > 0:
            loc.first.click()
            return True
    return False


def fetch_bond_balance(
    *,
    headless: bool,
    timeout_ms: int,
    save_debug: bool,
    allow_bond_nav_skip: bool,
    env_file: Path,
) -> BalanceResult:
    _load_env_file(env_file)

    branch_code = os.environ.get("AKATSUKI_BRANCH_CODE", "").strip()
    account_no = os.environ.get("AKATSUKI_ACCOUNT_NUMBER", "").strip()
    login_pass = os.environ.get("AKATSUKI_LOGIN_PASSWORD", "").strip()
    login_url = os.environ.get("AKATSUKI_LOGIN_URL", DEFAULT_LOGIN_URL).strip()
    bond_page_url = os.environ.get("AKATSUKI_BOND_PAGE_URL", "").strip()
    target_category = os.environ.get("AKATSUKI_TARGET_CATEGORY", "外国債券").strip()

    missing = [k for k, v in {
        "AKATSUKI_BRANCH_CODE": branch_code,
        "AKATSUKI_ACCOUNT_NUMBER": account_no,
        "AKATSUKI_LOGIN_PASSWORD": login_pass,
    }.items() if not v]
    if missing:
        raise RuntimeError(f"必須環境変数が不足しています: {', '.join(missing)}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            locale="ja-JP",
            storage_state=str(DEFAULT_STORAGE_STATE) if DEFAULT_STORAGE_STATE.exists() else None,
        )
        page = context.new_page()
        page.set_default_timeout(timeout_ms)
        page.goto(login_url, wait_until="domcontentloaded")

        page.locator("#branchNo").fill(branch_code)
        page.locator("#accountNo").fill(account_no)
        page.locator("#passwd1").fill(login_pass)
        page.locator("button[type='submit'][name='_ActionID']").click()
        page.wait_for_load_state("networkidle")

        if bond_page_url:
            target = bond_page_url
            if not re.match(r"^https?://", target):
                target = urljoin(page.url, target)
            page.goto(target, wait_until="domcontentloaded")
            page.wait_for_load_state("networkidle")
        elif not allow_bond_nav_skip:
            moved = _click_bond_navigation(page)
            if moved:
                page.wait_for_load_state("networkidle")

        # まず「預り資産」形式のテーブルを狙って抽出（外国債券の評価額など）
        summary_rows = _extract_holdings_summary_rows(page)
        ev, pl, picked_cat = _pick_eval_and_pl(summary_rows, target_category)
        if ev is not None:
            amounts = [ev]
            mode = f"holdings-summary:{picked_cat or target_category}"
            total = ev
        else:
            tables = _extract_table_snapshot(page)
            amounts, mode = _extract_amounts_from_tables(tables)
            total = sum(amounts)

        if save_debug:
            DEFAULT_DEBUG_DIR.mkdir(parents=True, exist_ok=True)
            html_path = DEFAULT_DEBUG_DIR / "akatsuki_last_page.html"
            png_path = DEFAULT_DEBUG_DIR / "akatsuki_last_page.png"
            html_path.write_text(page.content(), encoding="utf-8")
            page.screenshot(path=str(png_path), full_page=True)

        context.storage_state(path=str(DEFAULT_STORAGE_STATE))
        source_url = page.url
        browser.close()

    if not amounts:
        raise RuntimeError(
            "債券金額を抽出できませんでした。AKATSUKI_BOND_PAGE_URL / AKATSUKI_BOND_NAV_SELECTOR / "
            "AKATSUKI_BOND_LINK_TEXT を見直し、debug/akatsuki_last_page.html を確認してください。"
        )

    return BalanceResult(
        total_jpy=total,
        amount_rows=amounts,
        source_url=source_url,
        parser_mode=mode,
        category=picked_cat if 'picked_cat' in locals() else "",
        pl_jpy=pl if (pl is not None) else 0,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="あかつき証券の債券残高合計を取得")
    parser.add_argument("--headless", action="store_true", help="ヘッドレスで実行する")
    parser.add_argument("--timeout-ms", type=int, default=45000, help="Playwright タイムアウト（ms）")
    parser.add_argument(
        "--env-file",
        default=str(DEFAULT_ENV_PATH),
        help="環境変数ファイル（既定: finance/.env.akatsuki）",
    )
    parser.add_argument("--save-debug", action="store_true", help="最終ページのHTML/PNGを保存する")
    parser.add_argument(
        "--allow-bond-nav-skip",
        action="store_true",
        help="ログイン後の債券ページ遷移をスキップ（既に対象ページに遷移する場合）",
    )
    parser.add_argument("--json", action="store_true", help="JSONで結果を出力する")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        result = fetch_bond_balance(
            headless=args.headless,
            timeout_ms=args.timeout_ms,
            save_debug=args.save_debug,
            allow_bond_nav_skip=args.allow_bond_nav_skip,
            env_file=Path(args.env_file).expanduser(),
        )
    except PlaywrightTimeoutError as exc:
        print(f"タイムアウト: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"取得失敗: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(
            json.dumps(
                {
                    "total_jpy": result.total_jpy,
                    "amount_rows": result.amount_rows,
                    "source_url": result.source_url,
                    "parser_mode": result.parser_mode,
                },
                ensure_ascii=False,
            )
        )
    else:
        print(f"債券残高合計: {result.total_jpy:,}円")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
