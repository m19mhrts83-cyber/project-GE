#!/usr/bin/env python3
"""
PayPay銀行（法人）の取引明細 PDF をダウンロードし、
所定フォルダへ命名・配置する。

使い方:
  python paypay_bank_statement.py \
      --start-date 2025-06-01 --end-date 2025-06-30 \
      --output-dir ".../00_元ファイル_サイト取得/PayPay銀行/" \
      --output-name "PayPay銀行明細_6月.pdf"

認証情報: .env.tax_docs（同ディレクトリ）に
  PAYPAY_STORE_NO / PAYPAY_ACCOUNT_NO / PAYPAY_PASSWORD を設定する。
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_ENV_PATH = SCRIPT_DIR / ".env.tax_docs"

PAYPAY_TOP_URL = "https://www.paypay-bank.co.jp/"
PAYPAY_LOGIN_URL = (
    "https://login.japannetbank.co.jp/wctx/AF.do?SikibetuId=2015000"
)


def _load_env_file(path: Path) -> None:
    """dotenv 風に .env ファイルを読み込む（os.environ に未設定の変数のみ）。"""
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


def _wait_ready(page, *, timeout_ms: int = 15000) -> None:
    page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
    try:
        page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 10000))
    except Exception:
        pass


def _is_unavailable_page(page) -> bool:
    """直接ログイン URL 等で「お取り扱いしておりません」が出たか。"""
    try:
        body = page.locator("body").inner_text(timeout=3000)
    except Exception:
        return False
    return "ただいまお取り扱いいたしておりません" in body


def _go_to_paypay_home(page) -> None:
    """エラー画面の「PayPay銀行 ホームページへ」、または公式トップへ遷移。"""
    home_link = page.get_by_role("link", name="PayPay銀行 ホームページへ").or_(
        page.get_by_role("link", name="PayPay銀行　ホームページへ")
    ).or_(page.get_by_text("PayPay銀行", exact=False).filter(has_text="ホームページ"))
    if home_link.count() > 0:
        print("  「PayPay銀行 ホームページへ」リンクをクリック")
        home_link.first.click()
        _wait_ready(page)
        return
    print(f"  公式トップへ直接遷移: {PAYPAY_TOP_URL}")
    page.goto(PAYPAY_TOP_URL, wait_until="domcontentloaded")
    _wait_ready(page)


def _navigate_to_corporate_login(page) -> None:
    """公式トップから 法人・個人事業主 → ログイン へ進む（手順書 Step 1）。"""
    corp_tab = page.get_by_role("tab", name="法人・個人事業主").or_(
        page.get_by_text("法人・個人事業主", exact=False)
    )
    if corp_tab.count() > 0:
        corp_tab.first.click()
        _wait_ready(page)
        print("  「法人・個人事業主のお客さま」タブを選択")

    # ログインリンクはページ下部「口座をお持ちの方はこちら」付近にある
    holder_section = page.get_by_text("口座をお持ちの方はこちら", exact=False)
    if holder_section.count() > 0:
        holder_section.first.scroll_into_view_if_needed()
        page.wait_for_timeout(800)

    login_link = page.locator('a:visible').filter(has_text="ログイン").filter(
        has_not_text="BA-PLUS"
    )
    if login_link.count() == 0:
        login_link = page.get_by_role("link", name="ログイン").filter(has_not_text="BA-PLUS")

    if login_link.count() == 0:
        raise RuntimeError("法人向けログインリンクが見つかりませんでした")

    # 新規タブで開く場合に備えて popup を待つ
    try:
        with page.expect_popup(timeout=10000) as popup_info:
            login_link.first.click()
        login_page = popup_info.value
        _wait_ready(login_page)
        print(f"  ログインページ（新規タブ）: {login_page.url}")
        page._paypay_login_page = login_page  # type: ignore[attr-defined]
        return
    except PlaywrightTimeoutError:
        pass

    login_link.first.click(force=True)
    _wait_ready(page)
    print(f"  ログインページへ: {page.url}")


def _login_page(page):
    """ログインフォームがあるページ（ポップアップの場合はそちら）を返す。"""
    return getattr(page, "_paypay_login_page", page)


def _active_page(page):
    """ログイン後の操作対象ページを返す。"""
    return getattr(page, "_paypay_active_page", _login_page(page))


def _has_login_form(page) -> bool:
    lp = _login_page(page)
    if "login" in lp.url.lower():
        pw = lp.locator('input[type="password"]')
        text_inputs = lp.locator(
            'input[type="text"], input[type="tel"], input[name="Tenant"], '
            'input[name="Account"], input[name*="tenant" i], input[name*="account" i]'
        )
        if pw.count() > 0 and text_inputs.count() >= 2:
            return True
        # ラベルベース
        if lp.get_by_label("店番号").count() > 0 and pw.count() > 0:
            return True
    store_input = lp.locator('input[name="Tenant"]').or_(
        lp.locator('input[id*="Tenant"]')
    ).or_(lp.get_by_placeholder("店番号"))
    return store_input.count() > 0 and store_input.first.is_visible()


def _navigate_to_login_page(page) -> None:
    """ログインフォームが表示されるページまで遷移する。"""
    page.goto(PAYPAY_LOGIN_URL, wait_until="domcontentloaded")
    _wait_ready(page)

    if _is_unavailable_page(page) or not _has_login_form(page):
        print("  直接ログイン URL が使えないため、ホームページ経由で再遷移します")
        _go_to_paypay_home(page)
        _navigate_to_corporate_login(page)
        lp = _login_page(page)
        _wait_ready(lp, timeout_ms=20000)

    if not _has_login_form(page):
        raise RuntimeError(
            f"PayPay銀行のログインフォームに到達できませんでした（URL: {_login_page(page).url}）"
        )


def _fill_login_form(page, store_no: str, account_no: str, password: str) -> None:
    lp = _login_page(page)

    tenant = lp.locator('input[name="Tenant"]').or_(lp.get_by_label("店番号")).or_(
        lp.get_by_placeholder("店番号")
    )
    account = lp.locator('input[name="Account"]').or_(lp.get_by_label("口座番号")).or_(
        lp.get_by_placeholder("口座番号")
    )
    pw_input = lp.locator('input[type="password"]')

    if tenant.count() > 0 and account.count() > 0:
        tenant.first.fill(store_no)
        account.first.fill(account_no)
    else:
        # 表示されているテキスト入力を上から店番号・口座番号として埋める
        visible_text: list = []
        all_text = lp.locator('input[type="text"], input[type="tel"]')
        for i in range(all_text.count()):
            el = all_text.nth(i)
            if el.is_visible():
                visible_text.append(el)
        if len(visible_text) < 2:
            raise RuntimeError("店番号・口座番号の入力欄が見つかりませんでした")
        visible_text[0].fill(store_no)
        visible_text[1].fill(account_no)

    pw_input.first.fill(password)


def _is_overwrite_login_page(lp) -> bool:
    """前回セッション残りで「上書きログイン（ログイン中です）」が出たか。"""
    try:
        body = lp.locator("body").inner_text(timeout=3000)
    except Exception:
        return False
    return "上書きログイン" in body


def _click_login_button(lp) -> None:
    login_btn = lp.get_by_role("button", name="ログイン").or_(
        lp.locator('input[type="submit"][value*="ログイン"]')
    ).or_(lp.locator('button:has-text("ログイン")'))
    login_btn.first.click()
    _wait_ready(lp, timeout_ms=30000)


def _login(page, store_no: str, account_no: str, password: str) -> None:
    """PayPay銀行の法人ログインページでログインする。"""
    _navigate_to_login_page(page)
    lp = _login_page(page)
    _fill_login_form(page, store_no, account_no, password)
    _click_login_button(lp)

    if _is_overwrite_login_page(lp):
        print("  上書きログイン画面を検出。同じ認証情報を再入力してログインします")
        _fill_login_form(page, store_no, account_no, password)
        _click_login_button(lp)

    page._paypay_active_page = lp  # type: ignore[attr-defined]
    print(f"  ログイン後 URL: {lp.url}")


def _is_statement_page(ap) -> bool:
    """取引明細照会画面（期間選択・PDF ボタンあり）か。"""
    period = ap.get_by_text("期間選択", exact=False)
    pdf = ap.get_by_text("PDF", exact=True)
    try:
        if period.count() > 0 and period.first.is_visible():
            return True
        if pdf.count() > 0 and pdf.first.is_visible():
            return True
    except Exception:
        pass
    return False


def _navigate_to_statement(page) -> None:
    """ログイン後トップから取引明細画面へ遷移する。"""
    ap = _active_page(page)
    if _is_statement_page(ap):
        print("  既に取引明細画面です")
        return

    meisai_link = ap.get_by_text("取引明細", exact=False).or_(
        ap.get_by_role("link", name="取引明細")
    )
    meisai_link.first.click()
    _wait_ready(ap)
    ap.get_by_text("期間選択", exact=False).first.wait_for(state="visible", timeout=20000)
    print(f"  取引明細画面: {ap.url}")


def _set_period(page, start: date, end: date) -> None:
    """期間選択ポップアップで開始日・終了日を設定し、照会する。"""
    ap = _active_page(page)
    period_btn = ap.get_by_text("期間選択", exact=False).or_(
        ap.get_by_role("button", name="期間選択")
    )
    period_btn.first.click()
    ap.wait_for_timeout(1500)

    # 開始日
    start_y_sel = ap.locator('select[name*="startYear"], select[name*="FromYear"], select[name*="fromYear"]')
    start_m_sel = ap.locator('select[name*="startMonth"], select[name*="FromMonth"], select[name*="fromMonth"]')
    start_d_sel = ap.locator('select[name*="startDay"], select[name*="FromDay"], select[name*="fromDay"]')

    if start_y_sel.count() > 0:
        start_y_sel.first.select_option(str(start.year))
        start_m_sel.first.select_option(str(start.month))
        start_d_sel.first.select_option(str(start.day))
    else:
        selects = ap.locator("select")
        count = selects.count()
        if count >= 6:
            selects.nth(0).select_option(str(start.year))
            selects.nth(1).select_option(str(start.month))
            selects.nth(2).select_option(str(start.day))
        else:
            print("  ⚠ 期間選択の select 要素が見つかりません。page.pause() で確認してください。")
            ap.pause()
            return

    # 終了日
    end_y_sel = ap.locator('select[name*="endYear"], select[name*="ToYear"], select[name*="toYear"]')
    end_m_sel = ap.locator('select[name*="endMonth"], select[name*="ToMonth"], select[name*="toMonth"]')
    end_d_sel = ap.locator('select[name*="endDay"], select[name*="ToDay"], select[name*="toDay"]')

    if end_y_sel.count() > 0:
        end_y_sel.first.select_option(str(end.year))
        end_m_sel.first.select_option(str(end.month))
        end_d_sel.first.select_option(str(end.day))
    else:
        selects = ap.locator("select")
        count = selects.count()
        if count >= 6:
            selects.nth(3).select_option(str(end.year))
            selects.nth(4).select_option(str(end.month))
            selects.nth(5).select_option(str(end.day))

    inquiry_btn = ap.get_by_role("button", name="照会").or_(
        ap.get_by_text("照会", exact=True)
    )
    inquiry_btn.first.click()
    _wait_ready(ap)
    ap.wait_for_timeout(2000)
    print(f"  照会完了（{start} 〜 {end}）")


def _download_pdf(page, download_dir: Path) -> Path:
    """PDF ボタンをクリックしてダウンロードし、保存先パスを返す。"""
    import time

    ap = _active_page(page)
    ctx = ap.context
    pdf_btn = (
        ap.locator('a[href*="PDF" i], a[href*="Pdf" i], button[onclick*="PDF" i]')
        .or_(ap.get_by_role("button", name="PDF"))
        .or_(ap.get_by_role("link", name="PDF"))
        .or_(ap.get_by_text("PDF", exact=True))
    )
    pdf_btn.first.scroll_into_view_if_needed()

    def _save_bytes(data: bytes, name: str = "paypay_statement.pdf") -> Path:
        tmp_path = download_dir / name
        tmp_path.write_bytes(data)
        print(f"  ダウンロード完了: {tmp_path.name} ({tmp_path.stat().st_size:,} bytes)")
        return tmp_path

    pdf_responses: list = []

    def _on_response(response) -> None:
        ct = (response.headers.get("content-type") or "").lower()
        if "pdf" in ct and response.ok:
            pdf_responses.append(response)

    ap.on("response", _on_response)
    pages_before = len(ctx.pages)
    url_before = ap.url

    pdf_btn.first.click()

    deadline = time.time() + 35
    while time.time() < deadline:
        try:
            dl = ap.wait_for_event("download", timeout=1000)
            name = dl.suggested_filename or "paypay_statement.pdf"
            tmp_path = download_dir / name
            dl.save_as(str(tmp_path))
            print(f"  ダウンロード完了: {tmp_path.name} ({tmp_path.stat().st_size:,} bytes)")
            return tmp_path
        except PlaywrightTimeoutError:
            pass

        if pdf_responses:
            return _save_bytes(pdf_responses[0].body())

        if len(ctx.pages) > pages_before:
            pdf_page = ctx.pages[-1]
            _wait_ready(pdf_page, timeout_ms=5000)
            pdf_url = pdf_page.url
            if pdf_url and "about:blank" not in pdf_url:
                resp = ctx.request.get(pdf_url)
                body = resp.body()
                if resp.ok and body[:4] == b"%PDF":
                    pdf_page.close()
                    return _save_bytes(body)

        if ap.url != url_before:
            resp = ctx.request.get(ap.url)
            body = resp.body()
            if resp.ok and body[:4] == b"%PDF":
                return _save_bytes(body)

        ap.wait_for_timeout(500)

    # フォールバック: 公式 PDF ボタンが反応しない場合、照会結果画面を PDF 保存
    print("  公式 PDF ダウンロード不可のため、画面を PDF として保存します")
    tmp_path = download_dir / "paypay_statement.pdf"
    ap.pdf(path=str(tmp_path), format="A4", print_background=True)
    if tmp_path.stat().st_size > 1000:
        print(f"  画面 PDF 保存: {tmp_path.name} ({tmp_path.stat().st_size:,} bytes)")
        return tmp_path

    raise RuntimeError("PDF のダウンロード方法を特定できませんでした")


def run(
    *,
    start_date: date,
    end_date: date,
    output_dir: Path,
    output_name: str,
    headed: bool = True,
    dry_run: bool = False,
    pause_on_error: bool = True,
) -> Path | None:
    """PayPay銀行から明細 PDF を取得し、output_dir/output_name に配置する。"""
    store_no = os.environ.get("PAYPAY_STORE_NO", "")
    account_no = os.environ.get("PAYPAY_ACCOUNT_NO", "")
    password = os.environ.get("PAYPAY_PASSWORD", "")

    if not all([store_no, account_no, password]):
        print(
            "エラー: PAYPAY_STORE_NO / PAYPAY_ACCOUNT_NO / PAYPAY_PASSWORD が未設定です。\n"
            f"  → {DEFAULT_ENV_PATH} を作成してください（テンプレート: .env.tax_docs.example）",
            file=sys.stderr,
        )
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)
    dest = output_dir / output_name

    with tempfile.TemporaryDirectory(prefix="paypay_dl_") as tmpdir:
        download_dir = Path(tmpdir)

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=not headed)
            context = browser.new_context(accept_downloads=True)
            page = context.new_page()

            try:
                print("[1/4] ログイン中...")
                _login(page, store_no, account_no, password)

                print("[2/4] 取引明細画面へ遷移...")
                _navigate_to_statement(page)

                print(f"[3/4] 期間選択: {start_date} 〜 {end_date}")
                _set_period(page, start_date, end_date)

                if dry_run:
                    print("[dry-run] PDF ダウンロードはスキップします。")
                    page.wait_for_timeout(3000)
                    return None

                print("[4/4] PDF ダウンロード中...")
                tmp_pdf = _download_pdf(page, download_dir)

                shutil.copy2(str(tmp_pdf), str(dest))
                print(f"✅ 保存完了: {dest}")
                return dest

            except PlaywrightTimeoutError as e:
                print(f"タイムアウト: {e}", file=sys.stderr)
                if pause_on_error and headed:
                    print("  page.pause() でブラウザを確認できます。Ctrl+C で終了。")
                    try:
                        page.pause()
                    except KeyboardInterrupt:
                        pass
                return None
            except Exception as e:
                print(f"エラー: {e}", file=sys.stderr)
                if pause_on_error and headed:
                    try:
                        page.pause()
                    except KeyboardInterrupt:
                        pass
                return None
            finally:
                context.close()
                browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="PayPay銀行（法人）の取引明細 PDF を取得する",
    )
    parser.add_argument(
        "--start-date", required=True,
        help="照会開始日 (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end-date", required=True,
        help="照会終了日 (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--output-dir", required=True,
        help="PDF の保存先ディレクトリ",
    )
    parser.add_argument(
        "--output-name", required=True,
        help="保存ファイル名（例: PayPay銀行明細_6月.pdf）",
    )
    parser.add_argument(
        "--env-file", default=str(DEFAULT_ENV_PATH),
        help=f"認証情報 .env ファイル（既定: {DEFAULT_ENV_PATH}）",
    )
    parser.add_argument(
        "--headless", action="store_true",
        help="ヘッドレスモードで実行（既定: headed）",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="画面遷移のみ確認し、PDF ダウンロードしない",
    )
    parser.add_argument(
        "--no-pause", action="store_true",
        help="エラー時に page.pause() を呼ばない",
    )
    args = parser.parse_args()

    _load_env_file(Path(args.env_file))

    start = date.fromisoformat(args.start_date)
    end = date.fromisoformat(args.end_date)

    run(
        start_date=start,
        end_date=end,
        output_dir=Path(args.output_dir),
        output_name=args.output_name,
        headed=not args.headless,
        dry_run=args.dry_run,
        pause_on_error=not args.no_pause,
    )


if __name__ == "__main__":
    main()
