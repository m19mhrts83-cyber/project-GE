#!/usr/bin/env python3
"""アクサ生命 MyAXA から積立金／払いもどし金と特別勘定比率を取得（Mac・Playwright）。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_axa_balance.py --headless --json

OTP 画面が出たら Gmail API（m19m）で取得を試す。失敗時は対話なしで終了。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

LOGIN_URL = "https://myweb.axa.co.jp/login"
ACCOUNT_VALUE_URL = "https://myweb.axa.co.jp/fund-allocation/account-value"
FUND_ALLOC_URL = "https://myweb.axa.co.jp/fund-allocation"
DEBUG_DIR = Path.home() / "Library" / "Logs" / "jarvis_portfolio" / "debug"
REPO = Path(__file__).resolve().parents[1]

OTP_HINTS = ("認証コード", "ワンタイム", "確認コード", "2段階", "二段階", "SMS", "メールでお送り")
VALUE_LABELS = ("積立金", "払いもどし", "払戻", "評価額", "特別勘定残高", "口座価額")


@dataclass
class AxaFund:
    name: str
    pct: float


@dataclass
class AxaResult:
    value_jpy: int
    value_text: str
    source_url: str
    parser_mode: str
    funds: list[AxaFund] = field(default_factory=list)
    funds_as_of: str = ""
    funds_source: str = ""


def _yen_near_labels(text: str) -> tuple[int | None, str]:
    norm = (text or "").replace("\u3000", " ").replace(",", "")
    for label in VALUE_LABELS:
        m = re.search(
            rf"{re.escape(label)}[^0-9]{{0,40}}(\d{{4,12}})\s*円",
            norm,
        )
        if m:
            return int(m.group(1)), f"label:{label}"
    # フォールバック: 大きめの円金額を拾う
    nums = [int(x.replace(",", "")) for x in re.findall(r"(\d{1,3}(?:,\d{3})+)\s*円", text or "")]
    nums = [n for n in nums if n >= 10_000]
    if nums:
        return max(nums), "max_yen"
    return None, ""


def _parse_fund_pcts(text: str) -> list[AxaFund]:
    """本文から『名称 … NN.N%』風の特別勘定行を抽出（ヒューリスティック）。"""
    funds: list[AxaFund] = []
    seen: set[str] = set()
    # 例: 世界株式型 45.0% / 世界株式　45％
    for m in re.finditer(
        r"([^\n\r%]{2,40}?)\s*([0-9]{1,3}(?:\.[0-9]+)?)\s*[%％]",
        text or "",
    ):
        name = re.sub(r"\s+", " ", m.group(1)).strip(" ・:-|")
        if len(name) < 2 or len(name) > 32:
            continue
        if any(x in name for x in ("合計", "100", "配分", "変更", "割合", "％", "%")):
            continue
        # ノイズ除外
        if re.fullmatch(r"[\d\s.,]+", name):
            continue
        pct = float(m.group(2))
        if pct <= 0 or pct > 100:
            continue
        key = name
        if key in seen:
            continue
        seen.add(key)
        funds.append(AxaFund(name=name, pct=pct))
    # 合計が 95–105 に近いサブセットを優先（先頭から累積）
    if not funds:
        return []
    total = sum(f.pct for f in funds)
    if 95 <= total <= 105:
        return funds
    # 多すぎる場合は上位（pct 大きい順）で 100 に近づける
    ranked = sorted(funds, key=lambda f: -f.pct)
    chosen: list[AxaFund] = []
    acc = 0.0
    for f in ranked:
        if acc >= 99.5:
            break
        chosen.append(f)
        acc += f.pct
    if 90 <= acc <= 110:
        return sorted(chosen, key=lambda f: -f.pct)
    return funds[:12]


def _dismiss_overlays(page) -> None:
    for name in ("はい", "閉じる", "同意する", "同意して続ける", "Accept", "OK"):
        try:
            btn = page.get_by_role("button", name=re.compile(f"^{re.escape(name)}$"))
            if btn.count() > 0 and btn.first.is_visible(timeout=800):
                btn.first.click(timeout=2000)
                page.wait_for_timeout(600)
        except Exception:
            pass
        try:
            txt = page.get_by_text(name, exact=True)
            if txt.count() > 0 and txt.first.is_visible(timeout=500):
                txt.first.click(timeout=2000)
                page.wait_for_timeout(600)
        except Exception:
            pass
    # 「治療された方は ○○ さんですか？」系
    try:
        if "さんですか" in (page.inner_text("body") or ""):
            page.get_by_role("button", name="はい").first.click(timeout=3000)
            page.wait_for_timeout(800)
    except Exception:
        pass


def _select_axa_policy_if_needed(page) -> None:
    """証券選択が必要な画面なら先頭のユニット・リンク等を選ぶ。"""
    try:
        body = page.inner_text("body") or ""
    except Exception:
        return
    if "証券を選択" not in body and "依頼する証券" not in body:
        return
    print("⏳ MyAXA: 証券を選択します…", file=sys.stderr)
    candidates = [
        "ユニット・リンク",
        "変額",
        "862-",
    ]
    for label in candidates:
        try:
            loc = page.get_by_text(label, exact=False)
            if loc.count() > 0 and loc.first.is_visible(timeout=1500):
                loc.first.click(timeout=4000)
                page.wait_for_timeout(2000)
                _dismiss_overlays(page)
                return
        except Exception:
            continue
    # select / radio フォールバック
    try:
        sel = page.locator("select").first
        if sel.count() > 0:
            options = sel.locator("option").all_text_contents()
            for i, opt in enumerate(options):
                if i == 0:
                    continue
                if any(x in opt for x in ("ユニット", "変額", "862")):
                    sel.select_option(index=i)
                    page.wait_for_timeout(2000)
                    return
            if len(options) > 1:
                sel.select_option(index=1)
                page.wait_for_timeout(2000)
    except Exception:
        pass


def _navigate_axa_value_pages(page, timeout_ms: int) -> None:
    """口座価額・配分ページへ進み、モーダルと証券選択を処理。"""
    urls = (
        ACCOUNT_VALUE_URL,
        "https://myweb.axa.co.jp/fund-allocation/contribution-rate",
        "https://myweb.axa.co.jp/fund-allocation/transfer",
        FUND_ALLOC_URL,
        "https://myweb.axa.co.jp/",
    )
    for url in urls:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(2500)
        except PlaywrightTimeoutError:
            continue
        if "not-found" in (page.url or ""):
            continue
        _dismiss_overlays(page)
        _select_axa_policy_if_needed(page)
        _dismiss_overlays(page)
        text = ""
        try:
            text = page.inner_text("body") or ""
        except Exception:
            pass
        value, _ = _yen_near_labels(text)
        if value is not None:
            return
        if any(x in text for x in ("積立金", "特別勘定", "口座価額", "繰入割合", "%", "％")):
            return



def _page_looks_like_otp(page) -> bool:
    try:
        body = page.inner_text("body") or ""
    except Exception:
        return False
    if "認証コードの送信先選択" in body or "2段階認証" in body:
        return True
    return any(h in body for h in OTP_HINTS)


def _complete_axa_mfa(page, timeout_ms: int) -> None:
    """送信先選択 → メール → 次へ → Gmail OTP 入力。"""
    body = ""
    try:
        body = page.inner_text("body") or ""
    except Exception:
        pass

    otp_request_ms = int(time.time() * 1000)
    if "認証コードの送信先選択" in body or page.locator("#email-radio-button").count() > 0:
        print("⏳ MyAXA MFA: メール送信先を選択します…", file=sys.stderr)
        try:
            email_radio = page.locator("#email-radio-button").first
            if email_radio.count() > 0:
                try:
                    email_radio.click(force=True, timeout=3000)
                except Exception:
                    page.locator(
                        "[data-e2e='email-radio-button'], label:has(#email-radio-button)"
                    ).first.click(timeout=3000)
            else:
                page.get_by_text("ログインID（メールアドレス）", exact=False).first.click(
                    timeout=3000
                )
            page.wait_for_timeout(500)
            next_btn = page.get_by_role("button", name=re.compile("次へ"))
            if next_btn.count() == 0:
                next_btn = page.get_by_text("次へ進む", exact=False)
            next_btn.first.click(timeout=5000)
            page.wait_for_load_state("domcontentloaded")
            page.wait_for_timeout(2000)
            otp_request_ms = int(time.time() * 1000)
        except Exception as exc:
            raise RuntimeError(f"MyAXA MFA 送信先選択に失敗: {exc}") from exc

    # OTP 入力待ち
    deadline = time.time() + max(60, timeout_ms / 1000)
    while time.time() < deadline:
        loc = page.locator(
            "input[type='tel'], input[name*='otp' i], input[name*='code' i], "
            "input[id*='otp' i], input[id*='code' i], input[autocomplete='one-time-code'], "
            "input[maxlength='6']"
        )
        try:
            if loc.count() > 0 and loc.first.is_visible(timeout=500):
                break
        except Exception:
            pass
        page.wait_for_timeout(800)
    else:
        raise RuntimeError("MyAXA OTP 入力欄が表示されませんでした")

    print("📧 MyAXA OTP を Gmail（m19m）から取得します…", file=sys.stderr)
    code: str | None = None
    for _ in range(18):
        code = _gmail_otp_simple(
            lookback_minutes=20,
            after_ms=otp_request_ms - 30_000,
        )
        if code:
            break
        time.sleep(5)
    if not code:
        raise RuntimeError("MyAXA OTP メールを Gmail から取得できませんでした")

    otp = page.locator(
        "input[type='tel'], input[name*='otp' i], input[name*='code' i], "
        "input[id*='otp' i], input[id*='code' i], input[autocomplete='one-time-code'], "
        "input[maxlength='6']"
    ).first
    otp.wait_for(state="visible", timeout=min(20000, timeout_ms))
    otp.fill("")
    otp.fill(str(code))
    submit = page.locator("button[type='submit'], input[type='submit']").first
    if submit.count() > 0 and submit.is_visible(timeout=2000):
        submit.click()
    else:
        page.get_by_role("button", name=re.compile("送信|認証|次へ|ログイン|確認")).first.click()
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(3500)
    _dismiss_overlays(page)

    # ログイン完了待ち（ログイン画面に戻っていたら失敗）
    for _ in range(20):
        try:
            cur = page.url or ""
            body2 = page.inner_text("body") or ""
        except Exception:
            page.wait_for_timeout(500)
            continue
        if "自動的にログアウト" in body2:
            raise RuntimeError("MyAXA が自動ログアウトしました（OTP後）")
        if "/login" not in cur and "ログインID" not in body2[:800]:
            print("✓ MyAXA ログイン完了。", file=sys.stderr)
            return
        if "認証コード" in body2 and "送信先" not in body2:
            # まだ OTP 画面
            page.wait_for_timeout(1000)
            continue
        page.wait_for_timeout(800)
    raise RuntimeError("MyAXA OTP 後もログイン画面のままです")


def _try_fill_otp_from_gmail(page, timeout_ms: int) -> bool:
    try:
        _complete_axa_mfa(page, timeout_ms)
        return True
    except Exception as exc:
        print(f"MyAXA MFA/OTP 失敗: {exc}", file=sys.stderr)
        return False


def _gmail_otp_simple(
    lookback_minutes: int = 30,
    after_ms: int | None = None,
) -> str | None:
    token = (
        os.environ.get("AXA_GMAIL_TOKEN_PATH")
        or os.environ.get("PRUDENTIAL_GMAIL_TOKEN_PATH")
        or ""
    ).strip()
    if not token:
        token = str(
            REPO
            / "215_kamiooya"
            / "C1_cursor"
            / "1b_Cursorマニュアル"
            / "token_m19m.json"
        )
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except Exception:
        return None
    try:
        creds = Credentials.from_authorized_user_file(
            token,
            ["https://www.googleapis.com/auth/gmail.readonly"],
        )
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        svc = build("gmail", "v1", credentials=creds, cache_discovery=False)
        queries = [
            f"(from:axa.co.jp OR from:mail.axa.co.jp OR MyAXA OR アクサ) (認証 OR 確認 OR ワンタイム OR コード OR パスコード) newer_than:1d",
            f"(from:axa.co.jp OR MyAXA) newer_than:1d",
        ]
        min_internal = int(after_ms) if after_ms else 0
        for q in queries:
            res = svc.users().messages().list(userId="me", q=q, maxResults=10).execute()
            for m in res.get("messages") or []:
                full = (
                    svc.users()
                    .messages()
                    .get(userId="me", id=m["id"], format="full")
                    .execute()
                )
                internal = int(full.get("internalDate") or 0)
                if min_internal and internal and internal < min_internal:
                    continue
                blob = full.get("snippet") or ""
                payload = full.get("payload") or {}
                for h in payload.get("headers") or []:
                    if (h.get("name") or "").lower() in ("subject", "from"):
                        blob += " " + (h.get("value") or "")

                def walk(part: dict) -> str:
                    out = ""
                    if part.get("mimeType") == "text/plain" and part.get("body", {}).get(
                        "data"
                    ):
                        import base64

                        raw = part["body"]["data"]
                        out += base64.urlsafe_b64decode(raw + "==").decode(
                            "utf-8", "replace"
                        )
                    for sp in part.get("parts") or []:
                        out += walk(sp)
                    return out

                blob += " " + walk(payload)
                found = re.search(r"(?<!\d)(\d{6})(?!\d)", blob)
                if not found:
                    continue
                if (
                    "アクサ" in blob
                    or "AXA" in blob.upper()
                    or "MyAXA" in blob
                    or "axa.co.jp" in blob.lower()
                ):
                    return found.group(1)
    except Exception as exc:
        print(f"📧 AXA OTP 簡易Gmail失敗: {exc}", file=sys.stderr)
    return None


def fetch_axa_balance(*, headless: bool, timeout_ms: int, save_debug: bool) -> AxaResult:
    user = (os.environ.get("AXA_MYAXA_ID") or "").strip()
    password = (os.environ.get("AXA_MYAXA_PASSWORD") or "").strip()
    if not user or not password:
        raise RuntimeError("AXA_MYAXA_ID / AXA_MYAXA_PASSWORD が未設定です")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = browser.new_context(locale="ja-JP").new_page()
        page.set_default_timeout(timeout_ms)
        page.goto(LOGIN_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(2500)
        _dismiss_overlays(page)

        user_loc = page.locator("#username").first
        if user_loc.count() == 0 or not user_loc.is_visible(timeout=3000):
            user_loc = page.locator(
                "input[name='username'], input[type='email'], "
                "input[autocomplete='username']"
            ).first
        pw_loc = page.locator("#password").first
        if pw_loc.count() == 0 or not pw_loc.is_visible(timeout=2000):
            pw_loc = page.locator("input[type='password']").first

        user_loc.wait_for(state="visible", timeout=timeout_ms)
        user_loc.fill(user)
        pw_loc.fill(password)
        submit = page.locator(
            "button[type='submit'], input[type='submit'], button:has-text('ログイン')"
        ).first
        submit.click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(2500)

        if _page_looks_like_otp(page):
            print("⏳ MyAXA が OTP を要求。Gmail から取得を試します…", file=sys.stderr)
            if not _try_fill_otp_from_gmail(page, timeout_ms):
                if save_debug:
                    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
                    (DEBUG_DIR / "axa_otp_required.html").write_text(
                        page.content(), encoding="utf-8"
                    )
                raise RuntimeError("MyAXA が OTP を要求し、自動取得に失敗しました")

        _dismiss_overlays(page)
        _navigate_axa_value_pages(page, timeout_ms)

        text = page.inner_text("body")
        value, mode = _yen_near_labels(text)
        if value is None:
            # 証券選択後に再試行
            _select_axa_policy_if_needed(page)
            page.wait_for_timeout(2500)
            text = page.inner_text("body")
            value, mode = _yen_near_labels(text)
        if value is None:
            if save_debug:
                DEBUG_DIR.mkdir(parents=True, exist_ok=True)
                (DEBUG_DIR / "axa_last_page.html").write_text(page.content(), encoding="utf-8")
                page.screenshot(path=str(DEBUG_DIR / "axa_last_page.png"), full_page=True)
            raise RuntimeError("積立金／払いもどし金を抽出できませんでした")

        funds: list[AxaFund] = _parse_fund_pcts(text)
        funds_source = "account-value"
        if not funds:
            try:
                page.goto(FUND_ALLOC_URL, wait_until="domcontentloaded")
                page.wait_for_timeout(2500)
                _dismiss_overlays(page)
                _select_axa_policy_if_needed(page)
                funds = _parse_fund_pcts(page.inner_text("body"))
                if funds:
                    funds_source = "fund-allocation"
            except Exception:
                pass

        from datetime import date

        result = AxaResult(
            value_jpy=value,
            value_text=f"{value:,}円",
            source_url=page.url,
            parser_mode=mode,
            funds=funds,
            funds_as_of=date.today().isoformat() if funds else "",
            funds_source=funds_source if funds else "",
        )
        if save_debug:
            DEBUG_DIR.mkdir(parents=True, exist_ok=True)
            (DEBUG_DIR / "axa_last_page.html").write_text(page.content(), encoding="utf-8")
            page.screenshot(path=str(DEBUG_DIR / "axa_last_page.png"), full_page=True)
        browser.close()
        return result


def main() -> int:
    ap = argparse.ArgumentParser(description="MyAXA 積立金取得")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--timeout-ms", type=int, default=45000)
    ap.add_argument("--save-debug", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    try:
        result = fetch_axa_balance(
            headless=args.headless,
            timeout_ms=args.timeout_ms,
            save_debug=args.save_debug,
        )
    except Exception as exc:
        print(f"取得失敗: {exc}", file=sys.stderr)
        return 1
    if args.json:
        payload = asdict(result)
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(f"アクサ生命 積立金目安: {result.value_text} ({result.parser_mode})")
        if result.funds:
            parts = ", ".join(f"{f.name} {f.pct:g}%" for f in result.funds)
            print(f"特別勘定: {parts} ({result.funds_source})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
