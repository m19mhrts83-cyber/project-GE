#!/usr/bin/env python3
"""
ライフプラン自動化 Step3:
ソニー生命の契約者向けWebページから解約返戻金を抽出する。

複数の利用者IDを SONYLIFE_USERNAME_1/2/… と SONYLIFE_PASSWORD_1/2/… で指定した場合、
1人目でログイン→解約返戻金を取得→セッションを切ってログインURLへ戻る→2人目で再ログイン→取得…を順に行う。

ログイン後の既定導線（SONYLIFE_TARGET_URL 未設定時）:
「契約内容の照会」→ 契約一覧の「貸付金／解約返戻金」列の「選択する」→「解約返戻金の照会」。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_ENV_PATH = SCRIPT_DIR / ".env.lifeplan"
DEFAULT_DEBUG_DIR = SCRIPT_DIR / "debug"


@dataclass
class SonySurrenderAccountResult:
    """1利用者IDあたりの解約返戻金。"""

    account_index: int
    username: str
    value_jpy: int
    value_text: str
    source_url: str
    parser_mode: str


@dataclass
class SurrenderValueResult:
    """items に各アカウントの結果。value_jpy は合計。"""

    items: list[SonySurrenderAccountResult]
    value_jpy: int
    value_text: str
    source_url: str
    parser_mode: str


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


def _parse_first_jpy(text: str) -> tuple[int | None, str]:
    normalized = (text or "").replace("\u3000", " ")
    m = re.search(r"([+-]?\d[\d,]{0,})(?:\s*円)?", normalized)
    if not m:
        return None, ""
    raw = m.group(1).replace(",", "")
    if not raw:
        return None, ""
    try:
        value = int(raw)
    except ValueError:
        return None, ""
    return value, m.group(0).strip()


def _wait_page_ready(page, timeout_ms: int) -> None:
    page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
    try:
        page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 10000))
    except Exception:
        pass


def _sonylife_default_login_selectors() -> tuple[str, str, str]:
    """
    契約者向けログイン（PYFW1011 系）でよくある JSF の name / alt に合わせた既定セレクタ。
    SONYLIFE_*_SELECTOR が空のときに使う。
    """
    username_sel = 'input[name*="acctId"]'
    password_sel = 'input[type="password"]'
    submit_sel = 'input[type="image"][alt="ログイン"]'
    return username_sel, password_sel, submit_sel


def _page_looks_like_sony_contractor_login(page) -> bool:
    """契約者向けログイン画面（PYFW1011）かどうかの簡易判定。"""
    try:
        title = page.title() or ""
        url = page.url or ""
    except Exception:
        return False
    if "PYFW1011" not in url:
        return False
    return "ログイン" in title


def _frames_in_order(page) -> list:
    """メインフレーム優先で全フレームを列挙（iframe 内のナビ対応）。"""
    seen: set[int] = set()
    out: list = []
    for fr in getattr(page, "frames", []) or []:
        fid = id(fr)
        if fid not in seen:
            seen.add(fid)
            out.append(fr)
    return out


def _click_contract_inquiry_tab_robust(page, tab_text: str, tab_sel: str, timeout_ms: int) -> bool:
    """
    「契約内容の照会」相当のナビを、全フレーム・複数パターンでクリックする。
    tab_sel があれば最優先。
    """
    if tab_sel:
        for fr in _frames_in_order(page):
            try:
                loc = fr.locator(tab_sel)
                if loc.count() == 0:
                    continue
                el = loc.first
                el.scroll_into_view_if_needed(timeout=min(8000, timeout_ms))
                el.click(timeout=timeout_ms)
                return True
            except Exception:
                continue
        return False

    name_patterns = [
        re.compile(re.escape(tab_text)),
        re.compile(r"契約内容\s*の\s*照会"),
        re.compile(r"契約内容.*照会"),
    ]
    roles = ("tab", "link", "menuitem", "button")

    for fr in _frames_in_order(page):
        for role in roles:
            for pat in name_patterns:
                try:
                    loc = fr.get_by_role(role, name=pat)
                    if loc.count() == 0:
                        continue
                    el = loc.first
                    el.scroll_into_view_if_needed(timeout=min(8000, timeout_ms))
                    el.click(timeout=timeout_ms)
                    return True
                except Exception:
                    continue
        try:
            loc = fr.locator(
                "a, button, [role='tab'], [role='button'], [role='link'], span, div"
            ).filter(has_text=re.compile(r"契約内容.*照会"))
            n = loc.count()
            for i in range(min(n, 15)):
                el = loc.nth(i)
                try:
                    if not el.is_visible():
                        continue
                    t = (el.inner_text() or "").replace("\n", "").strip()
                    if "契約内容" in t and "照会" in t:
                        el.scroll_into_view_if_needed(timeout=min(8000, timeout_ms))
                        el.click(timeout=timeout_ms)
                        return True
                except Exception:
                    continue
        except Exception:
            pass

    try:
        clicked = page.evaluate(
            """
() => {
  const norm = (s) => (s || "").replace(/\\s/g, "").replace(/\\u3000/g, "");
  const candidates = Array.from(
    document.querySelectorAll("a, button, [role='tab'], [role='button'], [role='link'], span, div")
  );
  for (const el of candidates) {
    const t = norm(el.innerText || el.textContent || "");
    if (!t.includes("契約内容") || !t.includes("照会")) continue;
    const style = window.getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden") continue;
    const r = el.getBoundingClientRect();
    if (r.width < 1 && r.height < 1) continue;
    el.scrollIntoView({ block: "center", inline: "center" });
    el.click();
    return true;
  }
  return false;
}
"""
        )
        return bool(clicked)
    except Exception:
        return False


def _collect_sony_accounts() -> list[tuple[str, str]]:
    """(USERNAME_i, PASSWORD_i) のリスト。1人目は従来名 SONYLIFE_USERNAME も可。"""
    pairs: list[tuple[str, str]] = []
    for i in range(1, 11):
        u = os.environ.get(f"SONYLIFE_USERNAME_{i}", "").strip()
        p = os.environ.get(f"SONYLIFE_PASSWORD_{i}", "").strip()
        if i == 1:
            if not u:
                u = os.environ.get("SONYLIFE_USERNAME", "").strip()
            if not p:
                p = os.environ.get("SONYLIFE_PASSWORD", "").strip()
        if not u and not p:
            if i == 1:
                raise RuntimeError(
                    "SONYLIFE_USERNAME_1 / SONYLIFE_PASSWORD_1（または "
                    "SONYLIFE_USERNAME / SONYLIFE_PASSWORD）を設定してください。"
                )
            break
        if not u or not p:
            raise RuntimeError(
                f"SONYLIFE_USERNAME_{i} と SONYLIFE_PASSWORD_{i} は両方必要です。"
            )
        pairs.append((u, p))
    return pairs


def _otp_env_for_account(account_1based: int) -> str:
    if account_1based <= 1:
        return os.environ.get("SONYLIFE_OTP_CODE", "").strip()
    key = f"SONYLIFE_OTP_CODE_{account_1based}"
    return os.environ.get(key, "").strip() or os.environ.get("SONYLIFE_OTP_CODE", "").strip()


def _resolve_otp_code(
    otp_code_from_env: str,
    otp_code_override: str | None,
    *,
    account_index: int,
) -> str:
    code = (otp_code_override or otp_code_from_env or "").strip()
    if code:
        return code
    if not sys.stdin.isatty():
        return ""
    suffix = f"（アカウント{account_index}）" if account_index > 1 else ""
    return input(f"ソニー生命の確認コードを入力してください{suffix}: ").strip()


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


def _reset_session_before_relogin(
    page,
    context,
    *,
    login_url: str,
    logout_url: str,
    logout_selector: str,
    logout_text: str,
    timeout_ms: int,
) -> None:
    """2人目以降: 可能ならログアウトし、cookie を消してログインURLへ。"""
    if logout_selector:
        try:
            loc = page.locator(logout_selector)
            if loc.count() > 0 and loc.first.is_visible():
                loc.first.click()
                _wait_page_ready(page, timeout_ms)
        except Exception:
            pass
    elif logout_text:
        _click_by_selector_or_text(page, selector="", text=logout_text, timeout_ms=timeout_ms)
    if logout_url:
        try:
            page.goto(logout_url, wait_until="domcontentloaded")
            _wait_page_ready(page, timeout_ms)
        except Exception:
            pass
    try:
        context.clear_cookies()
    except Exception:
        pass
    page.goto(login_url, wait_until="domcontentloaded")
    _wait_page_ready(page, timeout_ms)


def _extract_by_selector(page, selector: str) -> tuple[int | None, str]:
    if not selector:
        return None, ""
    loc = page.locator(selector)
    if loc.count() <= 0:
        return None, ""
    txt = (loc.first.inner_text() or "").strip()
    return _parse_first_jpy(txt)


def _extract_by_label_dom(page, label: str) -> tuple[int | None, str]:
    if not label:
        return None, ""
    raw = page.evaluate(
        """
(label) => {
  const nodes = Array.from(document.querySelectorAll("p,dt,th,span,div,td,li"));
  for (const n of nodes) {
    const txt = (n.innerText || "").replace(/\\s+/g, " ").trim();
    if (!txt || !txt.includes(label)) continue;
    const container = n.closest("div,li,section,article,tr,dl,table") || n.parentElement;
    if (!container) continue;
    const num = container.querySelector(".c-text-number-num, .amount, .money, .yen");
    if (num) {
      const t = (num.textContent || "").replace(/\\s+/g, " ").trim();
      if (t) return t;
    }
    const around = (container.innerText || "").replace(/\\s+/g, " ").trim();
    const m = around.match(/([+-]?\\d[\\d,]{0,})(?:\\s*円)?/);
    if (m && m[1]) return m[1];
  }
  return "";
}
""",
        label,
    )
    return _parse_first_jpy(raw or "")


def _extract_by_label_fallback(page, label: str) -> tuple[int | None, str]:
    body = (page.inner_text("body") or "").replace("\u3000", " ")
    if not body or not label:
        return None, ""
    pattern = rf"{re.escape(label)}[^\n\r]{{0,40}}?([+-]?\d[\d,]{{0,}}(?:\s*円)?)"
    m = re.search(pattern, body)
    if not m:
        return None, ""
    return _parse_first_jpy(m.group(1))


def _lifeplanner_nav_to_surrender_value_page(page, timeout_ms: int) -> None:
    """
    LIFEPLANNER WEB 想定:
    1. 「契約内容の照会」
    2. 契約一覧テーブルで「貸付金／解約返戻金」列の「選択する」（行は SONYLIFE_NAV_CONTRACT_ROW_INDEX）
    3. 「解約返戻金の照会」
    """
    tab_text = os.environ.get("SONYLIFE_NAV_CONTRACT_TAB_TEXT", "契約内容の照会").strip()
    tab_sel = os.environ.get("SONYLIFE_NAV_CONTRACT_TAB_SELECTOR", "").strip()
    row_idx = int(os.environ.get("SONYLIFE_NAV_CONTRACT_ROW_INDEX", "0") or "0")
    inquiry_text = os.environ.get("SONYLIFE_NAV_SURRENDER_INQUIRY_TEXT", "解約返戻金の照会").strip()
    inquiry_sel = os.environ.get("SONYLIFE_NAV_SURRENDER_INQUIRY_SELECTOR", "").strip()
    post_ms = int(os.environ.get("SONYLIFE_POST_LOGIN_WAIT_MS", "4000") or "4000")
    try:
        page.wait_for_timeout(post_ms)
    except Exception:
        pass

    if not _click_contract_inquiry_tab_robust(page, tab_text, tab_sel, timeout_ms):
        raise RuntimeError(
            f"「{tab_text}」を開けませんでした。"
            "SONYLIFE_NAV_CONTRACT_TAB_SELECTOR に CSS セレクタを指定するか、"
            "ログイン直後の画面を debug に保存して DOM を確認してください。"
        )
    _wait_page_ready(page, timeout_ms)

    try:
        page.wait_for_selector("table", timeout=min(timeout_ms, 25000))
    except Exception:
        pass

    err = page.evaluate(
        """
(rowIdx) => {
  const wantCol = (txt) => {
    const n = (txt || "").replace(/\\s/g, "").replace(/\\u3000/g, "");
    return n.includes("解約返戻金") || (n.includes("貸付") && n.includes("解約"));
  };
  for (const table of document.querySelectorAll("table")) {
    const headerRow = table.querySelector("thead tr") || table.rows[0];
    if (!headerRow) continue;
    const hs = headerRow.querySelectorAll("th, td");
    let col = -1;
    for (let i = 0; i < hs.length; i++) {
      if (wantCol(hs[i].innerText)) { col = i; break; }
    }
    if (col < 0) {
      for (let i = 0; i < hs.length; i++) {
        if ((hs[i].innerText || "").indexOf("解約返戻金") >= 0) { col = i; break; }
      }
    }
    if (col < 0) continue;
    let rows = [];
    if (table.tBodies && table.tBodies[0] && table.tBodies[0].rows.length) {
      rows = Array.from(table.tBodies[0].rows);
    } else {
      const trs = table.querySelectorAll("tbody tr");
      rows = trs.length ? Array.from(trs) : Array.from(table.querySelectorAll("tr")).slice(1);
    }
    if (!rows[rowIdx]) return "no-row";
    const cells = rows[rowIdx].querySelectorAll("th, td");
    if (!cells[col]) return "no-cell";
    const cell = cells[col];
    const clickable = cell.querySelector(
      'button, a[href], [role="button"], input[type="button"], input[type="submit"]'
    );
    if (!clickable) return "no-button";
    clickable.click();
    return "ok";
  }
  return "no-table";
}
""",
        row_idx,
    )
    if err != "ok":
        raise RuntimeError(
            "契約一覧の「貸付金／解約返戻金」列の「選択する」をクリックできませんでした。"
            f"（{err}）複数契約がある場合は SONYLIFE_NAV_CONTRACT_ROW_INDEX を調整してください。"
        )
    _wait_page_ready(page, timeout_ms)

    if inquiry_sel:
        page.locator(inquiry_sel).first.click(timeout=timeout_ms)
    else:
        clicked_inq = False
        for attempt in (
            lambda: page.get_by_role("link", name=re.compile("解約返戻金の照会")).first.click(
                timeout=timeout_ms
            ),
            lambda: page.get_by_role("button", name=re.compile("解約返戻金の照会")).first.click(
                timeout=timeout_ms
            ),
            lambda: page.get_by_text(inquiry_text, exact=True).first.click(timeout=timeout_ms),
            lambda: page.get_by_text(inquiry_text, exact=False).first.click(timeout=timeout_ms),
        ):
            try:
                attempt()
                clicked_inq = True
                break
            except Exception:
                continue
        if not clicked_inq:
            raise RuntimeError(
                f"「{inquiry_text}」をクリックできませんでした。"
                "SONYLIFE_NAV_SURRENDER_INQUIRY_SELECTOR を設定してください。"
            )
    _wait_page_ready(page, timeout_ms)


def _extract_sony_surrender_primary_amount(page) -> tuple[int | None, str]:
    """
    貸付金・解約返戻金照会ページの「解約時解約返戻金」行から金額を取る。
    証券番号（polNo）等の数値を拾わないため、汎用ラベル探索より優先する。
    """
    raw = page.evaluate(
        r"""
() => {
  const norm = (s) => (s || "").replace(/\s/g, "").replace(/\u3000/g, "");
  for (const tr of document.querySelectorAll("table tr")) {
    const th = tr.querySelector("th");
    if (!th) continue;
    const t = norm(th.innerText || "");
    if (!t.includes("解約時解約返戻金")) continue;
    const td = tr.querySelector("td:last-of-type") || tr.querySelector("td");
    if (!td) continue;
    return (td.innerText || "").replace(/\s+/g, " ").trim();
  }
  return "";
}
"""
    )
    return _parse_first_jpy((raw or "").strip())


def _extract_surrender_from_page(
    page,
    *,
    value_selector: str,
    value_label: str,
) -> tuple[int | None, str, str]:
    value: int | None = None
    value_text = ""
    mode = "none"
    if value_selector:
        value, value_text = _extract_by_selector(page, value_selector)
        if value is not None:
            mode = "selector"
    if value is None:
        value, value_text = _extract_sony_surrender_primary_amount(page)
        if value is not None:
            mode = "sony:解約時解約返戻金行"
    if value is None:
        value, value_text = _extract_by_label_dom(page, value_label)
        if value is not None:
            mode = f"label-dom:{value_label}"
    if value is None:
        value, value_text = _extract_by_label_fallback(page, value_label)
        if value is not None:
            mode = f"label:{value_label}"
    return value, value_text, mode


def fetch_sony_surrender_value(
    *,
    headless: bool,
    timeout_ms: int,
    save_debug: bool,
    env_file: Path,
    otp_code_override: str | None = None,
) -> SurrenderValueResult:
    _load_env_file(env_file)

    login_url = os.environ.get("SONYLIFE_LOGIN_URL", "").strip()
    if not login_url:
        raise RuntimeError("SONYLIFE_LOGIN_URL が未設定です。")

    accounts = _collect_sony_accounts()

    username_selector = os.environ.get("SONYLIFE_USERNAME_SELECTOR", "").strip()
    password_selector = os.environ.get("SONYLIFE_PASSWORD_SELECTOR", "").strip()
    submit_selector = os.environ.get("SONYLIFE_SUBMIT_SELECTOR", "").strip()
    du, dp, ds = _sonylife_default_login_selectors()
    if not username_selector:
        username_selector = du
    if not password_selector:
        password_selector = dp
    if not submit_selector:
        submit_selector = ds

    logout_url = os.environ.get("SONYLIFE_LOGOUT_URL", "").strip()
    logout_selector = os.environ.get("SONYLIFE_LOGOUT_SELECTOR", "").strip()
    logout_text = os.environ.get("SONYLIFE_LOGOUT_TEXT", "").strip()

    otp_selector = os.environ.get("SONYLIFE_OTP_SELECTOR", "").strip()
    otp_submit_selector = os.environ.get("SONYLIFE_OTP_SUBMIT_SELECTOR", "").strip()

    target_url = os.environ.get("SONYLIFE_TARGET_URL", "").strip()
    after_login_click_selector = os.environ.get("SONYLIFE_AFTER_LOGIN_CLICK_SELECTOR", "").strip()
    after_login_click_text = os.environ.get("SONYLIFE_AFTER_LOGIN_CLICK_TEXT", "").strip()

    value_selector = os.environ.get("SONYLIFE_SURRENDER_VALUE_SELECTOR", "").strip()
    value_label = os.environ.get("SONYLIFE_SURRENDER_VALUE_LABEL", "解約返戻金").strip()

    items: list[SonySurrenderAccountResult] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(locale="ja-JP")
        page = context.new_page()
        page.set_default_timeout(timeout_ms)

        for idx, (username, password) in enumerate(accounts):
            account_no = idx + 1
            if idx > 0:
                _reset_session_before_relogin(
                    page,
                    context,
                    login_url=login_url,
                    logout_url=logout_url,
                    logout_selector=logout_selector,
                    logout_text=logout_text,
                    timeout_ms=timeout_ms,
                )
            else:
                page.goto(login_url, wait_until="domcontentloaded")
                _wait_page_ready(page, timeout_ms)

            if username:
                page.locator(username_selector).first.fill(username)
            if password:
                page.locator(password_selector).first.fill(password)
            if username and password:
                page.locator(submit_selector).first.click()
                _wait_page_ready(page, timeout_ms)

            otp_override = otp_code_override if account_no == 1 else None
            otp_env = _otp_env_for_account(account_no)
            if otp_selector and page.locator(otp_selector).count() > 0:
                otp_code = _resolve_otp_code(
                    otp_env,
                    otp_override,
                    account_index=account_no,
                )
                if not otp_code:
                    raise RuntimeError(
                        "確認コード入力ページです。対話実行でコードを入力するか、"
                        "SONYLIFE_OTP_CODE"
                        + (f" / SONYLIFE_OTP_CODE_{account_no}" if account_no > 1 else "")
                        + " もしくは --otp-code（1人目のみ）を指定してください。"
                    )
                page.locator(otp_selector).fill(otp_code)
                if otp_submit_selector:
                    page.locator(otp_submit_selector).first.click()
                _wait_page_ready(page, timeout_ms)

            if _page_looks_like_sony_contractor_login(page):
                raise RuntimeError(
                    "ログインに失敗しているか、ログイン画面のままです。"
                    "ID・パスワードを確認するか、追加認証が必要なら "
                    "SONYLIFE_OTP_SELECTOR / SONYLIFE_OTP_CODE を設定してください。"
                )

            if target_url:
                page.goto(target_url, wait_until="domcontentloaded")
                _wait_page_ready(page, timeout_ms)
            elif after_login_click_selector or after_login_click_text:
                moved = _click_by_selector_or_text(
                    page,
                    selector=after_login_click_selector,
                    text=after_login_click_text,
                    timeout_ms=timeout_ms,
                )
                if not moved:
                    raise RuntimeError(
                        "解約返戻金ページへの遷移に失敗しました。"
                        "SONYLIFE_TARGET_URL または AFTER_LOGIN_CLICK_* を見直してください。"
                    )
            else:
                try:
                    _lifeplanner_nav_to_surrender_value_page(page, timeout_ms)
                except Exception:
                    DEFAULT_DEBUG_DIR.mkdir(parents=True, exist_ok=True)
                    fail_html = DEFAULT_DEBUG_DIR / f"sony_life_nav_fail_account{account_no}.html"
                    try:
                        fail_html.write_text(page.content(), encoding="utf-8")
                    except Exception:
                        pass
                    raise

            value, value_text, mode = _extract_surrender_from_page(
                page,
                value_selector=value_selector,
                value_label=value_label,
            )

            if save_debug:
                DEFAULT_DEBUG_DIR.mkdir(parents=True, exist_ok=True)
                html_path = DEFAULT_DEBUG_DIR / f"sony_life_last_page_account{account_no}.html"
                png_path = DEFAULT_DEBUG_DIR / f"sony_life_last_page_account{account_no}.png"
                html_path.write_text(page.content(), encoding="utf-8")
                page.screenshot(path=str(png_path), full_page=True)

            source_url = page.url

            if value is None:
                browser.close()
                raise RuntimeError(
                    f"アカウント{account_no}（{username}）で解約返戻金を抽出できませんでした。"
                    "SONYLIFE_SURRENDER_VALUE_SELECTOR もしくは SONYLIFE_SURRENDER_VALUE_LABEL を見直し、"
                    f"debug/sony_life_last_page_account{account_no}.html を確認してください。"
                )

            items.append(
                SonySurrenderAccountResult(
                    account_index=account_no,
                    username=username,
                    value_jpy=value,
                    value_text=value_text or f"{value:,}円",
                    source_url=source_url,
                    parser_mode=mode,
                )
            )

        browser.close()

    total = sum(x.value_jpy for x in items)
    lines = [f"アカウント{x.account_index}（{x.username}）: {x.value_text}" for x in items]
    combined_text = "\n".join(lines) + f"\n合計: {total:,}円"
    parser_mode = f"multi:{len(items)}accounts"
    last_url = items[-1].source_url if items else ""

    return SurrenderValueResult(
        items=items,
        value_jpy=total,
        value_text=combined_text,
        source_url=last_url,
        parser_mode=parser_mode,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ソニー生命の解約返戻金を取得")
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
        help="確認コード（1人目のログインで必要な場合のみ）。2人目は SONYLIFE_OTP_CODE_2 または対話入力",
    )
    parser.add_argument("--json", action="store_true", help="JSONで結果を出力する")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        result = fetch_sony_surrender_value(
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
                    "value_jpy": result.value_jpy,
                    "value_text": result.value_text,
                    "source_url": result.source_url,
                    "parser_mode": result.parser_mode,
                    "items": [asdict(x) for x in result.items],
                },
                ensure_ascii=False,
            )
        )
    else:
        print(f"解約返戻金 合計: {result.value_jpy:,}円")
        for x in result.items:
            print(f"  - アカウント{x.account_index}（{x.username}）: {x.value_jpy:,}円")
        print(result.value_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
