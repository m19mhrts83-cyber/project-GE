#!/usr/bin/env python3
"""
ライフプラン自動化 Step2:
オリックス銀行（投資用不動産ローン・住宅ローン）のお客さま専用ページにログインし、
「契約内容照会（一覧）」から各契約番号を開き、契約ごとの借入残高を取得する。

優先は契約照会詳細ページからの抽出。取れない場合は一覧の借入残高へフォールバック（既定）。
（旧）返済実績表照会のみから一覧表を読むモードは ORIX_LOAN_USE_REPAYMENT_LIST_ONLY=1 で利用可。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_ENV_PATH = SCRIPT_DIR / ".env.lifeplan"
DEFAULT_DEBUG_DIR = SCRIPT_DIR / "debug"


@dataclass
class OrixLoanBalanceItem:
    contract_no: str
    borrow_date: str
    balance_jpy: int
    balance_text: str
    # detail-selector / detail-table-pair / fallback-list-balance など
    extraction_mode: str = ""


@dataclass
class OrixLoanBalanceResult:
    items: list[OrixLoanBalanceItem]
    source_url: str
    parser_mode: str


@dataclass
class _ContractLinkRow:
    href: str
    contract_no: str
    borrow_date: str
    list_balance_text: str
    click_only: bool = False


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


def _parse_yen_int(text: str) -> int | None:
    m = re.search(r"([+-]?\d[\d,]*)", (text or "").replace("\u3000", " "))
    if not m:
        return None
    raw = m.group(1).replace(",", "")
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _wait_page_ready(page, timeout_ms: int) -> None:
    page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
    try:
        page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 10000))
    except Exception:
        pass


def _resolve_otp_code(otp_code_from_env: str, otp_code_override: str | None) -> str:
    code = (otp_code_override or otp_code_from_env or "").strip()
    if code:
        return code
    if not sys.stdin.isatty():
        return ""
    return input("オリックス確認コードを入力してください: ").strip()


def _is_orix_session_error_page(page) -> bool:
    """直リンク等で ERR0010 / エラーコード10 になる場合がある。"""
    try:
        title = page.title() or ""
    except Exception:
        title = ""
    if "ERR0010" in title:
        return True
    try:
        html = page.content() or ""
    except Exception:
        return False
    return "エラーコード：10" in html or "エラーコード:10" in html


def _click_by_selector_or_text(page, *, selector: str, text: str, timeout_ms: int) -> bool:
    if selector:
        loc = page.locator(selector)
        if loc.count() > 0 and loc.first.is_visible():
            loc.first.click()
            _wait_page_ready(page, timeout_ms)
            return True
    if text:
        for q in (
            f"button:has-text('{text}')",
            f"a:has-text('{text}')",
            f"[role='button']:has-text('{text}')",
            f"text={text}",
        ):
            loc = page.locator(q)
            if loc.count() > 0 and loc.first.is_visible():
                loc.first.click()
                _wait_page_ready(page, timeout_ms)
                return True
    return False


def _frames_ordered(page):
    """メインフレーム優先。オリックスはフレーム分割のため全フレームを走査する。"""
    mf = page.main_frame
    return [mf] + [f for f in page.frames if f != mf]


def _click_by_selector_or_text_any_frame(page, *, selector: str, text: str, timeout_ms: int) -> bool:
    for fr in _frames_ordered(page):
        if selector:
            try:
                loc = fr.locator(selector)
                if loc.count() > 0 and loc.first.is_visible():
                    loc.first.click(timeout=timeout_ms)
                    _wait_page_ready(page, timeout_ms)
                    return True
            except Exception:
                pass
        if text:
            for q in (
                f"button:has-text('{text}')",
                f"a:has-text('{text}')",
                f"[role='button']:has-text('{text}')",
            ):
                try:
                    loc = fr.locator(q)
                    if loc.count() > 0 and loc.first.is_visible():
                        loc.first.click(timeout=timeout_ms)
                        _wait_page_ready(page, timeout_ms)
                        return True
                except Exception:
                    pass
    return False


def _collect_contract_link_rows(root) -> list[_ContractLinkRow]:
    """
    「契約内容照会（一覧）」テーブルから、契約番号リンク付きの行だけを拾う（合計行は除外）。
    """
    raw = root.evaluate(
        """
() => {
  const out = [];
  const norm = (s) => (s || "").replace(/\\s+/g, " ").trim();
  const tables = Array.from(document.querySelectorAll("table"));
  for (const table of tables) {
    const txt = norm(table.innerText || "");
    if (!txt.includes("契約番号") || !txt.includes("借入残高")) continue;
    const rows = Array.from(table.querySelectorAll("tr"));
    let contractIdx = -1;
    let dateIdx = -1;
    let balanceIdx = -1;
    for (const tr of rows) {
      const cells = Array.from(tr.querySelectorAll("th,td"));
      const cellTexts = cells.map((c) => norm(c.innerText));
      if (!cellTexts.length) continue;
      if (contractIdx < 0 && cellTexts.some((c) => c.includes("契約番号"))) {
        contractIdx = cellTexts.findIndex((c) => c.includes("契約番号"));
        dateIdx = cellTexts.findIndex((c) => c.includes("借入日"));
        let bi = cellTexts.findIndex((c) => c === "借入残高" || (c.includes("借入残高") && !c.includes("合計")));
        if (bi < 0) bi = cellTexts.findIndex((c) => c.includes("借入残高"));
        balanceIdx = bi;
        continue;
      }
      if (contractIdx < 0 || balanceIdx < 0) continue;
      if (cells.length <= Math.max(contractIdx, balanceIdx)) continue;
      const rowNorm = norm(tr.innerText || "");
      if (rowNorm.includes("借入残高合計")) continue;
      const ccell = cells[contractIdx];
      const alink = ccell.querySelector("a");
      if (!alink) continue;
      const hrefRaw = (alink.getAttribute("href") || "").trim();
      const lowered = hrefRaw.toLowerCase();
      const clickOnly = !hrefRaw || hrefRaw === "#" || lowered.startsWith("javascript:");
      const href = clickOnly ? "" : hrefRaw;
      let contractNo = norm(alink.textContent || "");
      if (!contractNo) contractNo = norm(ccell.innerText || "");
      if (!contractNo || contractNo.includes("合計")) continue;
      if (!/^\\d{3}-\\d+-\\d+$/.test(contractNo.replace(/\\s/g, ""))) continue;
      const borrowDate = dateIdx >= 0 && cells.length > dateIdx ? norm(cells[dateIdx].innerText) : "";
      const balanceText = cells.length > balanceIdx ? norm(cells[balanceIdx].innerText) : "";
      if (balanceText.includes("合計") || borrowDate.includes("合計")) continue;
      out.push({
        href,
        click_only: clickOnly,
        contract_no: contractNo,
        borrow_date: borrowDate,
        list_balance_text: balanceText
      });
    }
  }
  return out;
}
"""
    )
    out: list[_ContractLinkRow] = []
    for r in raw or []:
        if not isinstance(r, dict):
            continue
        href = (r.get("href") or "").strip()
        click_only = bool(r.get("click_only"))
        contract_no = (r.get("contract_no") or "").strip()
        if not contract_no:
            continue
        if not click_only and not href:
            continue
        out.append(
            _ContractLinkRow(
                href=href,
                contract_no=contract_no,
                borrow_date=(r.get("borrow_date") or "").strip(),
                list_balance_text=(r.get("list_balance_text") or "").strip(),
                click_only=click_only,
            )
        )
    return out


def _collect_contract_link_rows_any_frame(page) -> list[_ContractLinkRow]:
    merged: list[_ContractLinkRow] = []
    seen: set[str] = set()
    for fr in _frames_ordered(page):
        try:
            rows = _collect_contract_link_rows(fr)
        except Exception:
            rows = []
        for r in rows:
            if r.contract_no in seen:
                continue
            seen.add(r.contract_no)
            merged.append(r)
    return merged


_JS_CLICK_CONTRACT_LINK_IN_TABLE = """
(cn) => {
  const norm = (s) => (s || "")
    .replace(/[\\u2010-\\u2015\\u2212\\uff0d]/g, "-")
    .replace(/\\s+/g, " ")
    .trim();
  const want = norm(cn);
  const compact = (s) => s.replace(/\\s/g, "");
  const wc = compact(want);
  for (const a of Array.from(document.querySelectorAll("table a"))) {
    const t = norm(a.textContent || "");
    if (t === want || compact(t) === wc) {
      a.click();
      return true;
    }
  }
  return false;
}
"""

_JS_CLICK_CONTRACT_LIST_ROW_BY_INDEX = """
(idx) => {
  const wantIdx = Number(idx);
  if (Number.isNaN(wantIdx) || wantIdx < 0) return false;
  const norm = (s) => (s || "").replace(/\\s+/g, " ").trim();
  const tables = Array.from(document.querySelectorAll("table"));
  for (const table of tables) {
    const ttxt = norm(table.innerText || "");
    if (!ttxt.includes("契約番号") || !ttxt.includes("借入残高")) continue;
    const rows = Array.from(table.querySelectorAll("tr"));
    let contractIdx = -1;
    let dateIdx = -1;
    let balanceIdx = -1;
    let n = 0;
    for (const tr of rows) {
      const cells = Array.from(tr.querySelectorAll("th,td"));
      const cellTexts = cells.map((c) => norm(c.innerText));
      if (!cellTexts.length) continue;
      if (contractIdx < 0 && cellTexts.some((c) => c.includes("契約番号"))) {
        contractIdx = cellTexts.findIndex((c) => c.includes("契約番号"));
        dateIdx = cellTexts.findIndex((c) => c.includes("借入日"));
        let bi = cellTexts.findIndex((c) => c === "借入残高" || (c.includes("借入残高") && !c.includes("合計")));
        if (bi < 0) bi = cellTexts.findIndex((c) => c.includes("借入残高"));
        balanceIdx = bi;
        continue;
      }
      if (contractIdx < 0 || balanceIdx < 0) continue;
      if (cells.length <= Math.max(contractIdx, balanceIdx)) continue;
      const rowNorm = norm(tr.innerText || "");
      if (rowNorm.includes("借入残高合計")) continue;
      const ccell = cells[contractIdx];
      const alink = ccell.querySelector("a");
      if (!alink) continue;
      let contractNo = norm(alink.textContent || "");
      if (!contractNo) contractNo = norm(ccell.innerText || "");
      if (!contractNo || contractNo.includes("合計")) continue;
      if (!/^\\d{3}-\\d+-\\d+$/.test(contractNo.replace(/\\s/g, ""))) continue;
      const borrowDate = dateIdx >= 0 && cells.length > dateIdx ? norm(cells[dateIdx].innerText) : "";
      const balanceText = cells.length > balanceIdx ? norm(cells[balanceIdx].innerText) : "";
      if (balanceText.includes("合計") || borrowDate.includes("合計")) continue;
      if (n === wantIdx) {
        alink.click();
        return true;
      }
      n += 1;
    }
  }
  return false;
}
"""


def _click_contract_row_by_index_any_frame(page, row_index: int, timeout_ms: int) -> bool:
    """契約内容照会一覧の N 件目（0始まり）の契約番号リンクをクリック。収集ロジックと同一の行の除外規則。"""
    if row_index < 0:
        return False
    for fr in _frames_ordered(page):
        try:
            if fr.evaluate(_JS_CLICK_CONTRACT_LIST_ROW_BY_INDEX, row_index):
                return True
        except Exception:
            continue
    return False


def _click_contract_link_in_any_frame(page, cn: str, timeout_ms: int) -> bool:
    """契約一覧テーブル内の契約番号リンクをいずれかのフレームでクリック。"""
    cn = cn.strip()
    for fr in _frames_ordered(page):
        try:
            if fr.evaluate(_JS_CLICK_CONTRACT_LINK_IN_TABLE, cn):
                return True
        except Exception:
            continue
    for fr in _frames_ordered(page):
        try:
            link = fr.get_by_role("link", name=cn, exact=True)
            if link.count() > 0:
                el = link.first
                el.scroll_into_view_if_needed()
                el.click(timeout=min(timeout_ms, 30000))
                return True
        except Exception:
            continue
    return False


def _js_go_menu_101_if_available(page) -> bool:
    """メガメニューが畳まれていても、グローバルの goMenu があれば一覧へ遷移できる。"""
    for fr in _frames_ordered(page):
        try:
            ok = fr.evaluate(
                """
() => {
  try {
    if (typeof goMenu === "function") {
      goMenu("101");
      return true;
    }
  } catch (e) {}
  return false;
}
"""
            )
            if ok:
                return True
        except Exception:
            continue
    return False


def _js_go_keiyaku_if_available(page) -> bool:
    for fr in _frames_ordered(page):
        try:
            ok = fr.evaluate(
                """
() => {
  try {
    if (typeof goKeiyaku === "function") {
      goKeiyaku();
      return true;
    }
  } catch (e) {}
  return false;
}
"""
            )
            if ok:
                return True
        except Exception:
            continue
    return False


def _reload_orix_contract_inquiry_list(page, timeout_ms: int) -> None:
    """
    契約内容照会（一覧）を開き直す。
    明細・詳細から戻るときは goMenu('101') を優先（goKeiyaku が先だと別画面に飛ぶことがある）。
    トップでは goKeiyaku() も試す。
    契約照会詳細にも「契約番号」があるため、一覧に戻れたかはテーブル行の有無で判定する。
    """
    selectors = (
        'a[href*="goMenu(\'101\')"]',
        "a[href*='goMenu'][href*='101']",
        '#l_main a[href*="goKeiyaku"]',
        'a[href="javascript:goKeiyaku();"]',
        'ul.m_links a[href*="goKeiyaku"]',
    )
    clicked = False
    for sel in selectors:
        try:
            for fr in _frames_ordered(page):
                loc = fr.locator(sel).first
                if loc.count() <= 0:
                    continue
                try:
                    if loc.is_visible():
                        loc.click(timeout=timeout_ms)
                    else:
                        loc.click(timeout=timeout_ms, force=True)
                    clicked = True
                    break
                except Exception:
                    try:
                        loc.click(timeout=timeout_ms, force=True)
                        clicked = True
                        break
                    except Exception:
                        pass
            if clicked:
                break
        except Exception:
            continue
    if not clicked:
        clicked = _js_go_menu_101_if_available(page)
    if not clicked:
        clicked = _js_go_keiyaku_if_available(page)

    try:
        page.wait_for_load_state("domcontentloaded", timeout=min(timeout_ms, 60000))
    except Exception:
        pass

    max_poll = min(200, max(30, timeout_ms // 250))
    for _ in range(max_poll):
        if len(_collect_contract_link_rows_any_frame(page)) >= 1:
            _wait_page_ready(page, timeout_ms)
            return
        try:
            page.wait_for_timeout(250)
        except Exception:
            break

    if _js_go_menu_101_if_available(page) or _js_go_keiyaku_if_available(page):
        try:
            page.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception:
            pass
        for _ in range(80):
            if len(_collect_contract_link_rows_any_frame(page)) >= 1:
                _wait_page_ready(page, timeout_ms)
                return
            try:
                page.wait_for_timeout(250)
            except Exception:
                break

    _wait_page_ready(page, timeout_ms)


def _return_to_contract_list(page, _list_page_url: str, timeout_ms: int) -> None:
    """
    一覧へ戻る。
    go_back だけでは POST 履歴で一覧が欠けたり、2件目のリンクが取れない状態になりうる。
    契約照会詳細にも「契約番号」があるため文言判定は使わない。
    常にヘッダ等から契約内容照会（一覧）を開き直す（go_back は使わない）。
    """
    _reload_orix_contract_inquiry_list(page, timeout_ms)


def _navigate_to_contract_detail(
    page,
    *,
    list_page_url: str,
    row: _ContractLinkRow,
    timeout_ms: int,
    list_row_index: int | None = None,
) -> None:
    """一覧から契約照会詳細へ。通常URLは goto、javascript リンクは行内クリック。"""
    if row.href and not row.click_only:
        page.goto(urljoin(list_page_url, row.href), wait_until="domcontentloaded")
        _wait_page_ready(page, timeout_ms)
        return
    cn = row.contract_no.strip()
    # テーブルは iframe 内のことがあるため全フレームで JS クリックを試す。
    # 再表示後にリンク文字が微妙に変わる場合があるため、収集時の行 index でもクリックする。
    # 一覧再描画の短い待機。
    try:
        page.wait_for_timeout(400)
    except Exception:
        pass
    for attempt in range(3):
        if list_row_index is not None and _click_contract_row_by_index_any_frame(
            page, list_row_index, timeout_ms
        ):
            _wait_page_ready(page, timeout_ms)
            return
        if _click_contract_link_in_any_frame(page, cn, timeout_ms):
            _wait_page_ready(page, timeout_ms)
            return
        if attempt < 2:
            _reload_orix_contract_inquiry_list(page, timeout_ms)
    raise RuntimeError(
        f"契約照会詳細へ遷移できませんでした（契約番号: {cn}）。"
        "契約内容照会（一覧）に該当の契約番号リンクがあるか確認してください。"
    )


def _extract_loan_rows(page) -> list[dict[str, str]]:
    """
    返済実績表照会（一覧）のテーブルから契約番号・借入日・借入残高を拾う。
    """
    return page.evaluate(
        """
() => {
  const out = [];
  const norm = (s) => (s || "").replace(/\\s+/g, " ").trim();
  const tables = Array.from(document.querySelectorAll("table"));
  for (const table of tables) {
    const txt = norm(table.innerText || "");
    if (!txt.includes("契約番号") || !txt.includes("借入残高")) continue;
    const rows = Array.from(table.querySelectorAll("tr"));
    let contractIdx = -1;
    let dateIdx = -1;
    let balanceIdx = -1;
    for (const tr of rows) {
      const cells = Array.from(tr.querySelectorAll("th,td")).map((c) => norm(c.innerText));
      if (!cells.length) continue;
      if (contractIdx < 0 && cells.some((c) => c.includes("契約番号"))) {
        contractIdx = cells.findIndex((c) => c.includes("契約番号"));
        dateIdx = cells.findIndex((c) => c.includes("借入日"));
        balanceIdx = cells.findIndex((c) => c.includes("借入残高"));
        continue;
      }
      if (contractIdx < 0 || balanceIdx < 0) continue;
      if (cells.length <= balanceIdx) continue;
      const contractNo = cells[contractIdx] || "";
      const borrowDate = dateIdx >= 0 && cells.length > dateIdx ? cells[dateIdx] : "";
      const balanceText = cells[balanceIdx] || "";
      if (!contractNo || !balanceText) continue;
      out.push({ contract_no: contractNo, borrow_date: borrowDate, balance_text: balanceText });
    }
  }
  return out;
}
"""
    )


def _extract_detail_balance(
    root,
    *,
    selector: str,
    label: str,
) -> tuple[int | None, str, str]:
    """
    契約照会詳細ページから残債相当の金額を抽出する。
    root は Page または Frame（フレーム内明細向け）。
    戻り値: (amount_jpy, amount_text, mode)
    """
    if selector:
        loc = root.locator(selector).first
        if loc.count() > 0:
            try:
                text = (loc.inner_text() or "").strip()
            except Exception:
                text = ""
            bal = _parse_yen_int(text)
            if bal is not None:
                return bal, text or f"{bal:,}円", "detail-selector"

    try:
        body = (root.locator("body").inner_text() or "").replace("\u3000", " ")
    except Exception:
        body = ""
    labels_to_try: list[str] = []
    for lab in (
        label,
        "残債",
        "残債額",
        "残債金額",
        "借入残高",
        "ご借入残高",
        "ご融資残高",
        "契約残高",
        "現在残高",
        "融資残高",
        "貸付残高",
    ):
        lab = (lab or "").strip()
        if lab and lab not in labels_to_try:
            labels_to_try.append(lab)

    for lab in labels_to_try:
        if not lab:
            continue
        # 「借入残高」が「借入残高合計」の部分文字列になるため、合計行にマッチしないよう除外
        lab_pat = re.escape(lab)
        if lab == "借入残高":
            lab_pat += r"(?!合計)"
        pattern = rf"{lab_pat}[^\n\d]{{0,50}}?([+-]?\d[\d,]+)\s*円?"
        m = re.search(pattern, body)
        if m:
            bal = _parse_yen_int(m.group(1))
            if bal is not None:
                return bal, m.group(0).strip(), f"detail-label:{lab}"
        # ラベルと金額が改行で分かれている表記
        m2 = re.search(
            rf"{lab_pat}[\s\S]{{0,400}}?([+-]?\d[\d,]+)\s*円",
            body,
        )
        if m2:
            bal = _parse_yen_int(m2.group(1))
            if bal is not None:
                snippet = body[max(0, m2.start() - 20) : m2.end() + 10].replace("\n", " ")
                return bal, snippet.strip(), f"detail-label-multiline:{lab}"

    dom_try = root.evaluate(
        """
(labels) => {
  const L = Array.isArray(labels) ? labels : [];
  const norm = (s) => (s || "").replace(/\\s+/g, " ").trim();
  const wantLabel = (s) => L.some((lab) => lab && s.includes(lab));
  const nodes = Array.from(document.querySelectorAll("th,dt,span,div,td,p,label"));
  for (const n of nodes) {
    const t = norm(n.innerText || "");
    if (!t || t.length > 120) continue;
    if (!wantLabel(t)) continue;
    if (t.includes("借入残高合計") || t.includes("残高合計")) continue;
    const row = n.closest("tr,dl,li,div");
    const scope = row || n.parentElement;
    if (!scope) continue;
    const num = scope.querySelector(".money, .yen, [class*='number'], [class*='Numeric']");
    const nt = num ? norm(num.textContent || "") : "";
    if (nt && /\\d/.test(nt)) return nt;
    const around = norm(scope.innerText || "");
    const m = around.match(/([+-]?\\d[\\d,]+)\\s*円/);
    if (m) return m[1];
  }
  return "";
}
""",
        labels_to_try,
    )
    if dom_try:
        bal = _parse_yen_int(str(dom_try))
        if bal is not None:
            return bal, str(dom_try).strip(), "detail-label-dom"

    table_try = root.evaluate(
        """
() => {
  const norm = (s) => (s || "").replace(/\\s+/g, " ").trim();
  const keys = ["残債", "借入残高", "貸付残高", "ご融資残高", "契約残高", "現在残高", "融資残高"];
  for (const table of document.querySelectorAll("table")) {
    for (const tr of table.querySelectorAll("tr")) {
      const cells = Array.from(tr.querySelectorAll("th,td"));
      if (cells.length < 2) continue;
      const left = norm(cells[0].innerText || "");
      if (left.includes("借入残高合計") || left.includes("残高合計")) continue;
      const hitKey = keys.some((k) => {
        if (!left.includes(k)) return false;
        if (k === "借入残高" && left.includes("合計")) return false;
        return true;
      });
      if (!hitKey) continue;
      for (let i = 1; i < cells.length; i++) {
        const raw = norm(cells[i].innerText || "");
        const m = raw.match(/([+-]?\\d[\\d,]+)/);
        if (m) return m[1];
      }
    }
  }
  return "";
}
"""
    )
    if table_try:
        bal = _parse_yen_int(str(table_try))
        if bal is not None:
            return bal, str(table_try).strip(), "detail-table-pair"

    return None, "", "none"


def _extract_detail_balance_any_frame(
    page,
    *,
    selector: str,
    label: str,
) -> tuple[int | None, str, str]:
    for fr in _frames_ordered(page):
        bal, bal_text, mode = _extract_detail_balance(fr, selector=selector, label=label)
        if bal is not None:
            return bal, bal_text, mode
    return None, "", "none"


def _result_from_list_table_only(raw_rows: list[dict[str, str]]) -> list[OrixLoanBalanceItem]:
    items: list[OrixLoanBalanceItem] = []
    for r in raw_rows:
        bal_text = (r.get("balance_text") or "").strip()
        bal = _parse_yen_int(bal_text)
        if bal is None:
            continue
        items.append(
            OrixLoanBalanceItem(
                contract_no=(r.get("contract_no") or "").strip(),
                borrow_date=(r.get("borrow_date") or "").strip(),
                balance_jpy=bal,
                balance_text=bal_text,
                extraction_mode="repayment-list-table",
            )
        )
    return items


def fetch_orix_loan_balances(
    *,
    headless: bool,
    timeout_ms: int,
    save_debug: bool,
    env_file: Path,
    otp_code_override: str | None = None,
) -> OrixLoanBalanceResult:
    _load_env_file(env_file)

    login_url = os.environ.get("ORIX_LOAN_LOGIN_URL", "").strip()
    if not login_url:
        raise RuntimeError("ORIX_LOAN_LOGIN_URL が未設定です。")

    username = os.environ.get("ORIX_LOAN_USERNAME", "").strip()
    password = os.environ.get("ORIX_LOAN_PASSWORD", "").strip()

    login_route_selector = os.environ.get("ORIX_LOAN_LOGIN_ROUTE_SELECTOR", "").strip()
    login_route_text = os.environ.get("ORIX_LOAN_LOGIN_ROUTE_TEXT", "投資用不動産ローン 住宅ローン").strip()

    # 未設定時は login_ft.htm のフォームに合わせる（bk.orixbank.co.jp）
    username_selector = (
        os.environ.get("ORIX_LOAN_USERNAME_SELECTOR", "").strip()
        or 'input[name="LoginId"]'
    )
    password_selector = (
        os.environ.get("ORIX_LOAN_PASSWORD_SELECTOR", "").strip() or 'input[name="pass"]'
    )
    submit_selector = (
        os.environ.get("ORIX_LOAN_SUBMIT_SELECTOR", "").strip()
        or "button.parts_btn._strong:has-text('ログインする')"
    )

    otp_selector = os.environ.get("ORIX_LOAN_OTP_SELECTOR", "").strip()
    otp_submit_selector = os.environ.get("ORIX_LOAN_OTP_SUBMIT_SELECTOR", "").strip()
    otp_code_env = os.environ.get("ORIX_LOAN_OTP_CODE", "").strip()

    repayment_list_url = os.environ.get("ORIX_LOAN_REPAYMENT_LIST_URL", "").strip()
    repayment_list_selector = os.environ.get("ORIX_LOAN_REPAYMENT_LIST_SELECTOR", "").strip()
    repayment_list_text = os.environ.get("ORIX_LOAN_REPAYMENT_LIST_TEXT", "返済実績表照会").strip()

    use_repayment_list_only = os.environ.get("ORIX_LOAN_USE_REPAYMENT_LIST_ONLY", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )

    contract_list_url = os.environ.get("ORIX_LOAN_CONTRACT_LIST_URL", "").strip()
    contract_list_selector = os.environ.get("ORIX_LOAN_CONTRACT_LIST_SELECTOR", "").strip()
    contract_list_text = os.environ.get("ORIX_LOAN_CONTRACT_LIST_TEXT", "契約内容照会").strip()

    if not contract_list_selector and repayment_list_selector:
        contract_list_selector = repayment_list_selector

    detail_balance_selector = os.environ.get("ORIX_LOAN_DETAIL_BALANCE_SELECTOR", "").strip()
    detail_balance_label = os.environ.get("ORIX_LOAN_DETAIL_BALANCE_LABEL", "残債").strip()
    # 詳細で数値が取れないとき、契約内容照会一覧で拾った借入残高へフォールバック（契約ごと）。
    # 既定は可。0 / false / no で無効（詳細のみ許容したい場合）。
    _fb_raw = os.environ.get("ORIX_LOAN_FALLBACK_LIST_BALANCE", "1").strip().lower()
    allow_list_balance_fallback = _fb_raw not in ("0", "false", "no")

    max_contracts_raw = os.environ.get("ORIX_LOAN_MAX_CONTRACTS", "").strip()
    max_contracts = int(max_contracts_raw) if max_contracts_raw.isdigit() else 0

    allow_contract_list_direct_url = os.environ.get(
        "ORIX_LOAN_CONTRACT_LIST_ALLOW_DIRECT_URL", ""
    ).strip().lower() in ("1", "true", "yes")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(locale="ja-JP")
        page = context.new_page()
        page.set_default_timeout(timeout_ms)
        page.goto(login_url, wait_until="domcontentloaded")
        _wait_page_ready(page, timeout_ms)

        # ログイン画面に既にログインID欄がある場合は経路クリックをスキップ（誤クリック防止）
        try:
            has_login_form = page.locator('input[name="LoginId"]').count() > 0
        except Exception:
            has_login_form = False
        if not has_login_form:
            # トップのログイン経路分岐（フレーム内メニュー向けに全フレーム検索）
            _click_by_selector_or_text_any_frame(
                page,
                selector=login_route_selector,
                text=login_route_text,
                timeout_ms=timeout_ms,
            )

        # ログイン（セレクタ指定時のみ）
        if username_selector and username:
            page.locator(username_selector).fill(username)
        if password_selector and password:
            page.locator(password_selector).fill(password)
        if submit_selector and (username_selector or password_selector):
            page.locator(submit_selector).click()
            _wait_page_ready(page, timeout_ms)

        # OTP（必要な場合のみ）
        if otp_selector and page.locator(otp_selector).count() > 0:
            otp_code = _resolve_otp_code(otp_code_env, otp_code_override)
            if not otp_code:
                raise RuntimeError(
                    "確認コード入力ページです。対話実行でコードを入力するか、"
                    "ORIX_LOAN_OTP_CODE もしくは --otp-code を指定して再実行してください。"
                )
            page.locator(otp_selector).fill(otp_code)
            if otp_submit_selector:
                page.locator(otp_submit_selector).first.click()
            _wait_page_ready(page, timeout_ms)

        items: list[OrixLoanBalanceItem] = []
        parser_mode = "repayment-list-table"
        source_url = ""

        if use_repayment_list_only:
            if repayment_list_url:
                page.goto(repayment_list_url, wait_until="domcontentloaded")
                _wait_page_ready(page, timeout_ms)
            else:
                moved = _click_by_selector_or_text(
                    page,
                    selector=repayment_list_selector,
                    text=repayment_list_text,
                    timeout_ms=timeout_ms,
                )
                if not moved:
                    raise RuntimeError(
                        "返済実績表照会（一覧）へ遷移できませんでした。"
                        "ORIX_LOAN_REPAYMENT_LIST_URL か SELECTOR/TEXT を見直してください。"
                    )
            raw_rows = _extract_loan_rows(page)
            items = _result_from_list_table_only(raw_rows)
            source_url = page.url
        else:
            # 契約内容照会（一覧）→ 各「契約照会詳細」で残債を取得
            # 直リンク ORIX_LOAN_CONTRACT_LIST_URL だけだと ERR0010 になりやすいため、
            # メニュー文言／セレクタを優先し、失敗時のみ URL を試す。
            moved = False
            if contract_list_selector:
                moved = _click_by_selector_or_text_any_frame(
                    page,
                    selector=contract_list_selector,
                    text="",
                    timeout_ms=timeout_ms,
                )
            # オリックス TOP: メガメニュー内の同名リンクより、本文の goKeiyaku() を優先
            if not moved:
                for sel in (
                    '#l_main a[href*="goKeiyaku"]',
                    'a[href="javascript:goKeiyaku();"]',
                    'ul.m_links a[href*="goKeiyaku"]',
                ):
                    if _click_by_selector_or_text_any_frame(
                        page,
                        selector=sel,
                        text="",
                        timeout_ms=timeout_ms,
                    ):
                        moved = True
                        break
            if not moved:
                for txt in (
                    contract_list_text,
                    "契約内容照会（一覧）",
                    "契約照会",
                    "契約内容照会",
                ):
                    t = (txt or "").strip()
                    if not t:
                        continue
                    if _click_by_selector_or_text_any_frame(
                        page,
                        selector="",
                        text=t,
                        timeout_ms=timeout_ms,
                    ):
                        moved = True
                        break
            if not moved and contract_list_url and allow_contract_list_direct_url:
                page.goto(contract_list_url, wait_until="domcontentloaded")
                _wait_page_ready(page, timeout_ms)
                moved = True
            if not moved:
                raise RuntimeError(
                    "契約内容照会（一覧）へ遷移できませんでした。"
                    "メニュー内の ORIX_LOAN_CONTRACT_LIST_TEXT（既定: 契約内容照会）がフレーム内にある場合があります。"
                    "ORIX_LOAN_CONTRACT_LIST_SELECTOR を指定するか、"
                    "どうしても直リンクする場合のみ ORIX_LOAN_CONTRACT_LIST_ALLOW_DIRECT_URL=1 と "
                    "ORIX_LOAN_CONTRACT_LIST_URL を併用してください（ERR0010 になることがあります）。"
                )

            try:
                page.wait_for_load_state("domcontentloaded", timeout=min(timeout_ms, 60000))
            except Exception:
                pass
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            try:
                page.wait_for_selector("text=契約番号", timeout=min(timeout_ms, 45000))
            except Exception:
                pass

            if _is_orix_session_error_page(page):
                raise RuntimeError(
                    "オリックス銀行でセッションエラー（ERR0010 / エラーコード10）です。"
                    "契約一覧の URL を直接開くと発生することがあります。"
                    "ORIX_LOAN_CONTRACT_LIST_URL を空にし、ログイン後メニューから "
                    "ORIX_LOAN_CONTRACT_LIST_TEXT（例: 契約内容照会）で遷移するよう設定してください。"
                )

            list_page_url = page.url
            contract_rows = _collect_contract_link_rows_any_frame(page)
            if not contract_rows:
                if save_debug:
                    DEFAULT_DEBUG_DIR.mkdir(parents=True, exist_ok=True)
                    html_path = DEFAULT_DEBUG_DIR / "orix_loan_last_page.html"
                    png_path = DEFAULT_DEBUG_DIR / "orix_loan_last_page.png"
                    try:
                        html_path.write_text(page.content(), encoding="utf-8")
                    except Exception as exc:
                        html_path.write_text(
                            f"<!-- page.content() 取得不可: {exc} -->", encoding="utf-8"
                        )
                    try:
                        page.screenshot(path=str(png_path), full_page=True)
                    except Exception:
                        pass
                raise RuntimeError(
                    "契約内容照会の一覧から契約番号リンクを取得できませんでした。"
                    "ログイン後の画面が「契約内容照会（一覧）」か確認するか、"
                    "ORIX_LOAN_CONTRACT_LIST_URL を直接指定してください。"
                )
            if max_contracts > 0:
                contract_rows = contract_rows[:max_contracts]

            detail_modes: list[str] = []
            last_detail_url = ""

            n_contracts = len(contract_rows)
            for list_row_index in range(n_contracts):
                # 一覧を開き直した直後の DOM に合わせて行を取り直す（2件目クリック失敗の防止）
                fresh_rows = _collect_contract_link_rows_any_frame(page)
                if list_row_index >= len(fresh_rows):
                    raise RuntimeError(
                        f"契約一覧の行が足りません（{list_row_index + 1} 件目を開けません。"
                        f"現在の一覧は {len(fresh_rows)} 件）。"
                    )
                row = fresh_rows[list_row_index]
                _navigate_to_contract_detail(
                    page,
                    list_page_url=list_page_url,
                    row=row,
                    timeout_ms=timeout_ms,
                    list_row_index=list_row_index,
                )
                last_detail_url = page.url

                try:
                    page.wait_for_load_state("domcontentloaded", timeout=min(timeout_ms, 30000))
                except Exception:
                    pass
                try:
                    page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass

                bal, bal_text, dmode = _extract_detail_balance_any_frame(
                    page,
                    selector=detail_balance_selector,
                    label=detail_balance_label,
                )

                if bal is None and allow_list_balance_fallback:
                    list_bal = _parse_yen_int(row.list_balance_text)
                    if list_bal is not None:
                        bal = list_bal
                        bal_text = row.list_balance_text
                        dmode = "fallback-list-balance"

                detail_modes.append(dmode)

                if bal is None:
                    _return_to_contract_list(page, list_page_url, timeout_ms)
                    raise RuntimeError(
                        f"契約照会詳細でも一覧の借入残高でも数値を取得できませんでした（契約: {row.contract_no}）。"
                        "ORIX_LOAN_DETAIL_BALANCE_SELECTOR または ORIX_LOAN_DETAIL_BALANCE_LABEL を見直すか、"
                        "一覧に借入残高が表示されているか確認してください。"
                        "（一覧のみ使う場合は ORIX_LOAN_FALLBACK_LIST_BALANCE を空または 1 のままにしてください。"
                        "詳細のみ許容する場合は ORIX_LOAN_FALLBACK_LIST_BALANCE=0 を指定します。）"
                    )

                items.append(
                    OrixLoanBalanceItem(
                        contract_no=row.contract_no,
                        borrow_date=row.borrow_date,
                        balance_jpy=bal,
                        balance_text=bal_text or f"{bal:,}円",
                        extraction_mode=dmode,
                    )
                )

                _return_to_contract_list(page, list_page_url, timeout_ms)

            source_url = last_detail_url or list_page_url
            parser_mode = "contract-inquiry-detail:" + (
                "+".join(detail_modes) if detail_modes else "none"
            )

        if save_debug:
            DEFAULT_DEBUG_DIR.mkdir(parents=True, exist_ok=True)
            html_path = DEFAULT_DEBUG_DIR / "orix_loan_last_page.html"
            png_path = DEFAULT_DEBUG_DIR / "orix_loan_last_page.png"
            html_path.write_text(page.content(), encoding="utf-8")
            page.screenshot(path=str(png_path), full_page=True)

        if not source_url:
            source_url = page.url
        browser.close()

    if not items:
        raise RuntimeError(
            "借入残高を抽出できませんでした。"
            "契約内容照会の一覧で契約番号リンクが取得できているか、"
            "または ORIX_LOAN_USE_REPAYMENT_LIST_ONLY=1 で一覧のみ取得に切り替えられるか確認し、"
            "debug/orix_loan_last_page.html を参照してください。"
        )

    return OrixLoanBalanceResult(
        items=items,
        source_url=source_url,
        parser_mode=parser_mode,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="オリックス銀行の契約別借入残高を取得")
    parser.add_argument("--headless", action="store_true", help="ヘッドレスで実行する")
    parser.add_argument("--timeout-ms", type=int, default=45000, help="Playwright タイムアウト（ms）")
    parser.add_argument("--save-debug", action="store_true", help="最終ページのHTML/PNGを保存")
    parser.add_argument(
        "--env-file",
        default=str(DEFAULT_ENV_PATH),
        help="環境変数ファイル（既定: finance/.env.lifeplan）",
    )
    parser.add_argument(
        "--otp-code",
        default="",
        help="確認コード（必要時）。未指定で対話実行時は入力を促す",
    )
    parser.add_argument("--json", action="store_true", help="JSONで結果を出力する")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        result = fetch_orix_loan_balances(
            headless=args.headless,
            timeout_ms=args.timeout_ms,
            save_debug=args.save_debug,
            env_file=Path(args.env_file).expanduser(),
            otp_code_override=(args.otp_code or "").strip() or None,
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
                    "items": [
                        {
                            "contract_no": x.contract_no,
                            "borrow_date": x.borrow_date,
                            "balance_jpy": x.balance_jpy,
                            "balance_text": x.balance_text,
                            "extraction_mode": x.extraction_mode,
                        }
                        for x in result.items
                    ],
                    "source_url": result.source_url,
                    "parser_mode": result.parser_mode,
                },
                ensure_ascii=False,
            )
        )
    else:
        print("オリックス銀行 借入残高（契約別）")
        for x in result.items:
            contract = x.contract_no or "(契約番号不明)"
            date = f" / 借入日:{x.borrow_date}" if x.borrow_date else ""
            src = f"  [{x.extraction_mode}]" if x.extraction_mode else ""
            print(f"- {contract}{date}: {x.balance_jpy:,}円{src}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
