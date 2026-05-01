#!/usr/bin/env python3
"""
ライフプラン自動化 Step1:
太陽光発電ローンのWebページから金額を抽出する。

サイト差分に対応するため、ログイン項目や金額セレクタは環境変数で指定する。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_ENV_PATH = SCRIPT_DIR / ".env.lifeplan"
DEFAULT_DEBUG_DIR = SCRIPT_DIR / "debug"


@dataclass
class LoanAmountResult:
    amount_jpy: int
    amount_text: str
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
    """
    テキストから最初に見つかる金額を抽出する。
    例: "ローン残高 1,234,567円" -> (1234567, "1,234,567円")
    """
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


def _extract_by_selector(page, selector: str) -> tuple[int | None, str]:
    loc = page.locator(selector).first
    if loc.count() == 0:
        return None, ""
    text = (loc.inner_text() or "").strip()
    value, amount_text = _parse_first_jpy(text)
    return value, amount_text


def _extract_by_label_fallback(page, label: str) -> tuple[int | None, str]:
    """
    ページ本文からラベル近傍の金額を探す。
    """
    body = (page.inner_text("body") or "").replace("\u3000", " ")
    if not body:
        return None, ""
    pattern = rf"{re.escape(label)}[^\n\r]{{0,40}}?([+-]?\d[\d,]{{0,}}(?:\s*円)?)"
    m = re.search(pattern, body)
    if not m:
        return None, ""
    value, amount_text = _parse_first_jpy(m.group(1))
    return value, amount_text


def _extract_by_label_dom(page, label: str) -> tuple[int | None, str]:
    """
    ラベル文言の近傍DOMから金額を拾う（eオリコの「ご利用残高」向け）。
    """
    if not label:
        return None, ""
    result = page.evaluate(
        """
(label) => {
  const nodes = Array.from(document.querySelectorAll("p,dt,th,span,div"));
  for (const n of nodes) {
    const txt = (n.innerText || "").replace(/\\s+/g, " ").trim();
    if (!txt || !txt.includes(label)) continue;
    const container = n.closest("div,li,section,article,tr,dl") || n.parentElement;
    if (!container) continue;
    const num = container.querySelector(".c-text-number-num, .js-payment-display, .p-loan-accordion-data-text .c-text-number-num");
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
    value, amount_text = _parse_first_jpy(result or "")
    return value, amount_text


def _detect_otp_error(page) -> str:
    """
    OTP入力エラー（例: U0011）をページ文言から検知して返す。
    """
    try:
        body = (page.inner_text("body") or "").strip()
    except Exception:
        return ""
    if not body:
        return ""
    if "U0011" in body or "入力された確認コードが誤っているか、有効期限が切れています" in body:
        return "確認コードが誤っているか有効期限切れです（U0011）。新しい確認コードで再実行してください。"
    return ""


def _wait_page_ready(page, timeout_ms: int) -> None:
    """
    networkidle が終わらないページ対策:
    まず domcontentloaded、余裕があれば networkidle を短めで試す。
    """
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
    typed = input("確認コード（6桁）を入力してください: ").strip()
    return typed


def _env_int_nonneg(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        return default


def fetch_solar_loan_amount(
    *,
    headless: bool,
    timeout_ms: int,
    save_debug: bool,
    env_file: Path,
    otp_code_override: str | None = None,
) -> LoanAmountResult:
    _load_env_file(env_file)

    login_url = os.environ.get("SOLAR_LOAN_LOGIN_URL", "").strip()
    if not login_url:
        raise RuntimeError("SOLAR_LOAN_LOGIN_URL が未設定です。")

    username = os.environ.get("SOLAR_LOAN_USERNAME", "").strip()
    password = os.environ.get("SOLAR_LOAN_PASSWORD", "").strip()

    username_selector = os.environ.get("SOLAR_LOAN_USERNAME_SELECTOR", "#username").strip()
    password_selector = os.environ.get("SOLAR_LOAN_PASSWORD_SELECTOR", "#password").strip()
    submit_selector = os.environ.get("SOLAR_LOAN_SUBMIT_SELECTOR", "#idpwbtn").strip()
    cookie_accept_selector = os.environ.get(
        "SOLAR_LOAN_COOKIE_ACCEPT_SELECTOR",
        "#datasign_cmp__cmp_content_apply-button",
    ).strip()
    amount_selector = os.environ.get("SOLAR_LOAN_AMOUNT_SELECTOR", "").strip()
    amount_label = os.environ.get("SOLAR_LOAN_AMOUNT_LABEL", "ご利用残高").strip()
    after_login_click_selector = os.environ.get("SOLAR_LOAN_AFTER_LOGIN_CLICK_SELECTOR", "").strip()
    after_login_click_text = os.environ.get("SOLAR_LOAN_AFTER_LOGIN_CLICK_TEXT", "お支払計算書").strip()
    target_url_after_login = os.environ.get("SOLAR_LOAN_TARGET_URL", "").strip()
    otp_code_env = os.environ.get("SOLAR_LOAN_OTP_CODE", "").strip()
    otp_selector = os.environ.get("SOLAR_LOAN_OTP_SELECTOR", "#otp").strip()
    otp_submit_selector = os.environ.get(
        "SOLAR_LOAN_OTP_SUBMIT_SELECTOR",
        "button:has-text('次へ進む')",
    ).strip()
    fetch_otp_from_gmail = (
        os.environ.get("SOLAR_LOAN_FETCH_OTP_FROM_GMAIL", "").strip().lower()
        in ("1", "true", "yes", "on")
    )
    otp_gmail_to = os.environ.get("SOLAR_LOAN_GMAIL_EXPECT_EMAIL", "").strip() or os.environ.get(
        "PRUDENTIAL_GMAIL_EXPECT_EMAIL", ""
    ).strip()
    otp_gmail_strict = (
        os.environ.get("SOLAR_LOAN_OTP_GMAIL_STRICT_AFTER_LOGIN", "").strip().lower()
        in ("1", "true", "yes", "on")
    )
    strict_lookback_ms = _env_int_nonneg("SOLAR_LOAN_OTP_GMAIL_STRICT_LOOKBACK_MS", 120000)
    pause_before_gmail_otp_ms = _env_int_nonneg("SOLAR_LOAN_PAUSE_BEFORE_GMAIL_OTP_MS", 8000)
    otp_gmail_lookback_ms = _env_int_nonneg("SOLAR_LOAN_OTP_GMAIL_LOOKBACK_MS", 60000)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(locale="ja-JP")
        page = context.new_page()
        page.set_default_timeout(timeout_ms)
        page.goto(login_url, wait_until="domcontentloaded")
        login_submit_ms = 0

        # Cookie 同意（表示される場合のみ）
        if cookie_accept_selector:
            try:
                c = page.locator(cookie_accept_selector).first
                if c.count() > 0 and c.is_visible():
                    c.click()
                    page.wait_for_timeout(300)
            except Exception:
                pass

        # セレクタが設定されている場合のみログイン操作を行う。
        if username_selector and username:
            page.locator(username_selector).fill(username)
        if password_selector and password:
            page.locator(password_selector).fill(password)
        if submit_selector and (username_selector or password_selector):
            page.locator(submit_selector).click()
            login_submit_ms = int(time.time() * 1000)
            _wait_page_ready(page, timeout_ms)

        # 追加認証（確認コード）画面に来た場合は、指定があれば入力して進む
        if otp_selector and page.locator(otp_selector).count() > 0:
            otp_code = _resolve_otp_code(otp_code_env, otp_code_override)
            if not otp_code and fetch_otp_from_gmail:
                if pause_before_gmail_otp_ms > 0:
                    page.wait_for_timeout(pause_before_gmail_otp_ms)
                try:
                    from solar_gmail_otp import poll_solar_otp_from_gmail
                except Exception as exc:
                    raise RuntimeError(f"Gmail OTP モジュールの読み込みに失敗: {exc}")
                now_ms = int(time.time() * 1000)
                if otp_gmail_strict and login_submit_ms > 0:
                    # ログイン送信より前のメールを拾いにくくする（時計ずれ分は solar_gmail_otp 側で吸収）
                    min_ms = max(0, login_submit_ms - strict_lookback_ms)
                else:
                    # 非 strict: 現在時刻から lookback
                    min_ms = max(0, now_ms - otp_gmail_lookback_ms)
                otp_code = poll_solar_otp_from_gmail(to_email=otp_gmail_to, min_internal_date_ms=min_ms)
            if not otp_code:
                raise RuntimeError(
                    "確認コード入力ページです。対話実行でコードを入力するか、"
                    "SOLAR_LOAN_OTP_CODE もしくは --otp-code を指定して再実行してください。"
                )
            page.locator(otp_selector).fill(otp_code)
            if otp_submit_selector:
                page.locator(otp_submit_selector).first.click()
            _wait_page_ready(page, timeout_ms)
            otp_err = _detect_otp_error(page)
            if otp_err:
                raise RuntimeError(otp_err)

        if target_url_after_login:
            page.goto(target_url_after_login, wait_until="domcontentloaded")
            _wait_page_ready(page, timeout_ms)

        # ログイン後の導線: 「お支払計算書」を開く（必要な場合）
        clicked = False
        if after_login_click_selector:
            loc = page.locator(after_login_click_selector)
            if loc.count() > 0 and loc.first.is_visible():
                loc.first.click()
                _wait_page_ready(page, timeout_ms)
                clicked = True
        if not clicked:
            # eオリコでは「お支払い計算書」/「お支払計算書」の表記ゆれがあるため両方試す
            for txt in (after_login_click_text, "お支払計算書", "お支払い計算書"):
                if not txt:
                    continue
                # 非表示の <p> に当たることがあるため、押下対象を button/a に限定
                loc = page.locator(f"button:has-text('{txt}'), a:has-text('{txt}')")
                if loc.count() > 0 and loc.first.is_visible():
                    loc.first.click()
                    _wait_page_ready(page, timeout_ms)
                    clicked = True
                    break
        if not clicked:
            # 画面要素が拾いにくい場合は導線URLへ直接遷移
            pay_link = page.locator("a[href*='scr0030010/start']")
            if pay_link.count() > 0:
                href = (pay_link.first.get_attribute("href") or "").strip()
                if href:
                    page.goto(urljoin(page.url, href), wait_until="domcontentloaded")
                    _wait_page_ready(page, timeout_ms)

        value: int | None = None
        amount_text = ""
        mode = "none"

        if amount_selector:
            value, amount_text = _extract_by_selector(page, amount_selector)
            if value is not None:
                mode = "selector"

        if value is None and amount_label:
            value, amount_text = _extract_by_label_dom(page, amount_label)
            if value is not None:
                mode = f"label-dom:{amount_label}"

        if value is None and amount_label:
            value, amount_text = _extract_by_label_fallback(page, amount_label)
            if value is not None:
                mode = f"label:{amount_label}"

        if save_debug:
            DEFAULT_DEBUG_DIR.mkdir(parents=True, exist_ok=True)
            html_path = DEFAULT_DEBUG_DIR / "solar_loan_last_page.html"
            png_path = DEFAULT_DEBUG_DIR / "solar_loan_last_page.png"
            html_path.write_text(page.content(), encoding="utf-8")
            page.screenshot(path=str(png_path), full_page=True)

        source_url = page.url
        browser.close()

    if value is None:
        raise RuntimeError(
            "金額を抽出できませんでした。SOLAR_LOAN_AMOUNT_SELECTOR もしくは "
            "SOLAR_LOAN_AMOUNT_LABEL を見直し、debug/solar_loan_last_page.html を確認してください。"
        )

    return LoanAmountResult(
        amount_jpy=value,
        amount_text=amount_text or f"{value:,}円",
        source_url=source_url,
        parser_mode=mode,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="太陽光発電ローン金額を抽出")
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
        help="確認コード（6桁）。未指定で対話実行時は入力を促す",
    )
    parser.add_argument("--json", action="store_true", help="JSONで結果を出力する")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        result = fetch_solar_loan_amount(
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
                    "amount_jpy": result.amount_jpy,
                    "amount_text": result.amount_text,
                    "source_url": result.source_url,
                    "parser_mode": result.parser_mode,
                },
                ensure_ascii=False,
            )
        )
    else:
        print(f"太陽光ローン金額: {result.amount_jpy:,}円")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
