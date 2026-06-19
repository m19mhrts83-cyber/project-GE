#!/usr/bin/env python3
"""
オリックス銀行（投資用不動産ローン）の返済実績表 PDF をダウンロードする。

使い方:
  python orix_bank_statement.py \
      --start-month 2025-06 --end-month 2025-06 \
      --group G1 \
      --output-dir ".../00_元ファイル_サイト取得/オリックス銀行_借入/"

認証情報: .env.tax_docs（同ディレクトリ）に
  ORIX_LOGIN_ID / ORIX_PASSWORD を設定する。

取得元:
  https://bk.orixbank.co.jp/login/login_ft.htm → ログイン
  → 返済実績表照会 → 法人契約を選択 → 照会期間指定 → PDF ダウンロード

注意:
  税理士提出は法人のみのため、**既定で法人名義（Zinkaku=2）の契約**を自動選択する。
  個人名義（Zinkaku=1）は --contract-index で明示指定した場合のみ。
  法人契約は照会期間（--start-month / --end-month）の指定が必須。
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_ENV_PATH = SCRIPT_DIR / ".env.tax_docs"

ORIX_LOGIN_URL = "https://bk.orixbank.co.jp/login/login_ft.htm"


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


def _wait_ready(page, *, timeout_ms: int = 15000) -> None:
    page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
    try:
        page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 10000))
    except Exception:
        pass


def _login(page, login_id: str, password: str) -> None:
    """投資用不動産ローンのログイン画面でログインする。"""
    page.goto(ORIX_LOGIN_URL, wait_until="load")
    _wait_ready(page)
    page.wait_for_timeout(1500)

    page.locator('input[name="LoginId"]').fill(login_id)
    page.locator('input[name="pass"]').fill(password)

    login_btn = page.locator('input[type="submit"], button, a').filter(
        has_text=re.compile(r"ログイン(する)?")
    )
    if login_btn.count() > 0:
        login_btn.first.click()
    else:
        page.locator('input[type="submit"]').first.click()

    _wait_ready(page, timeout_ms=30000)
    page.wait_for_timeout(3000)

    body_text = page.inner_text("body")
    if "契約照会" in body_text or "お客さま" in body_text or "ホーム" in body_text:
        print(f"  ログイン成功: {page.url}")
        return

    if "ワンタイム" in body_text or "認証" in body_text:
        raise RuntimeError(
            "追加認証（ワンタイムパスワード等）が求められています。"
            " headed モードで手動操作してください。"
        )

    raise RuntimeError(
        "オリックス銀行へのログインに失敗しました。"
        " .env.tax_docs の ORIX_LOGIN_ID / ORIX_PASSWORD を確認してください。"
    )


def _navigate_to_repayment_history(page) -> None:
    """返済実績表照会（一覧）へ遷移する。"""
    has_func = page.evaluate("() => typeof goHensaiJisseki === 'function'")
    if has_func:
        page.evaluate("() => goHensaiJisseki()")
    else:
        page.evaluate("() => goMenu('103')")
    _wait_ready(page, timeout_ms=30000)
    page.wait_for_timeout(2000)

    body = page.inner_text("body")
    if "返済実績表" not in body and "契約番号" not in body:
        raise RuntimeError("「返済実績表照会」画面に遷移できませんでした")
    print("  返済実績表照会を表示")


def _list_contracts(page) -> list[dict]:
    """一覧の契約情報を返す。"""
    return page.evaluate("""() => {
        const table = document.querySelector('table');
        if (!table) return [];
        return [...table.querySelectorAll('a')]
            .filter(a => /\\d{3}-/.test(a.innerText.trim()))
            .map(a => {
                const href = a.getAttribute('href') || '';
                const m = href.match(/KeiyakuShokai\\('([^']+)','(\\d+)'\\)/);
                return {
                    text: a.innerText.trim(),
                    keiyakuNo: m ? m[1] : '',
                    zinkaku: m ? m[2] : '',
                };
            });
    }""")


def _resolve_contract(contracts: list[dict], contract_index: int | None) -> tuple[dict, int]:
    """契約を決定する。未指定時は法人名義（Zinkaku=2）を優先する。"""
    if contract_index is not None:
        if contract_index >= len(contracts):
            raise RuntimeError(
                f"契約インデックス {contract_index} は範囲外（{len(contracts)} 件）"
            )
        return contracts[contract_index], contract_index

    for i, c in enumerate(contracts):
        if c.get("zinkaku") == "2":
            print(f"  法人契約を自動選択: [{i}] {c['text']}")
            return c, i

    raise RuntimeError(
        "法人名義の契約が見つかりませんでした。"
        " 一覧を確認するか --contract-index で明示指定してください。"
    )


def _download_pdf_zinkaku1(page, contract: dict, output_dir: Path) -> Path | None:
    """個人名義（Zinkaku=1）: ポップアップで PDF が直接生成される。"""
    kno = contract["keiyakuNo"]
    output_dir.mkdir(parents=True, exist_ok=True)

    with page.expect_popup(timeout=30000) as popup_info:
        page.evaluate(f"() => KeiyakuShokai('{kno}', '1')")
    popup = popup_info.value
    popup.wait_for_load_state("domcontentloaded", timeout=30000)
    popup.wait_for_timeout(3000)

    # ポップアップの「こちら」リンクから PDF URL を取得
    pdf_url = popup.evaluate("""() => {
        const links = [...document.querySelectorAll('a')];
        const pdfLink = links.find(a => {
            const href = a.getAttribute('href') || '';
            return href.endsWith('.pdf') && !href.startsWith('javascript');
        });
        return pdfLink ? pdfLink.href : null;
    }""")

    if not pdf_url:
        # transfardata 関数内のURLを探す
        pdf_url = popup.evaluate("""() => {
            const scripts = [...document.querySelectorAll('script')];
            for (const s of scripts) {
                const m = (s.textContent || '').match(/window\\.open\\("([^"]+\\.pdf)"/);
                if (m) return m[1];
            }
            const hidden = document.querySelector('input[name="__FILE1"]');
            if (hidden) {
                const v = hidden.value;
                if (v.endsWith('.pdf')) return v;
            }
            return null;
        }""")

    if not pdf_url:
        popup.close()
        print("  ❌ ポップアップから PDF URL を取得できませんでした")
        return None

    print(f"  PDF URL: {pdf_url}")

    # PDF をダウンロード（popup の認証済みコンテキストを利用）
    raw_name = pdf_url.rsplit("/", 1)[-1]
    dest = output_dir / raw_name

    try:
        resp = popup.request.get(pdf_url)
        if resp.ok:
            dest.write_bytes(resp.body())
            print(f"  ✅ ダウンロード完了: {dest.name} ({len(resp.body()) // 1024}KB)")
            popup.close()
            return dest
    except Exception:
        pass

    # フォールバック: メインページの認証コンテキストで取得
    try:
        resp = page.request.get(pdf_url)
        if resp.ok:
            dest.write_bytes(resp.body())
            print(f"  ✅ ダウンロード完了 (main ctx): {dest.name} ({len(resp.body()) // 1024}KB)")
            popup.close()
            return dest
    except Exception:
        pass

    popup.close()
    print("  ❌ PDF のダウンロードに失敗しました")
    return None


def _download_pdf_zinkaku2(page, contract: dict, output_dir: Path,
                           start_year: int, start_month: int,
                           end_year: int, end_month: int) -> Path | None:
    """法人名義（Zinkaku=2）: 照会期間を指定してPDFを取得する。"""
    kno = contract["keiyakuNo"]

    # 契約を選択（同一ページ内で遷移）
    page.evaluate(f"() => KeiyakuShokai('{kno}', '2')")
    _wait_ready(page, timeout_ms=30000)
    page.wait_for_timeout(2000)

    body = page.inner_text("body")
    if "照会する期間" not in body and "照会期間" not in body:
        print("  ⚠ 照会期間の入力画面が表示されませんでした")
        return None

    # 年月を入力
    filled = page.evaluate("""(args) => {
        const [sy, sm, ey, em] = args;
        const selects = [...document.querySelectorAll('select')];
        const inputs = [...document.querySelectorAll('input[type="text"]')];
        const all = [...selects, ...inputs].filter(el => el.offsetParent !== null);
        if (all.length < 4) return false;
        for (let i = 0; i < 4; i++) {
            const el = all[i];
            const val = [sy, sm, ey, em][i];
            if (el.tagName === 'SELECT') {
                el.value = String(val);
                el.dispatchEvent(new Event('change', { bubbles: true }));
            } else {
                el.value = String(val);
                el.dispatchEvent(new Event('input', { bubbles: true }));
            }
        }
        return true;
    }""", [str(start_year), str(start_month).zfill(2),
           str(end_year), str(end_month).zfill(2)])

    if not filled:
        print("  ⚠ 照会期間の入力フィールドが見つかりませんでした")
        return None

    print(f"  照会期間: {start_year}/{start_month:02d} 〜 {end_year}/{end_month:02d}")

    # 「表示する」
    display_btn = page.locator('input[type="submit"], button, a').filter(has_text="表示する")
    if display_btn.count() > 0:
        display_btn.first.click()
    _wait_ready(page, timeout_ms=30000)
    page.wait_for_timeout(3000)

    # 「印刷する」
    print_btn = page.locator('input[type="submit"], button, a').filter(has_text="印刷する")
    if print_btn.count() == 0:
        print("  ⚠ 「印刷する」ボタンが見つかりませんでした")
        return None

    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        with page.expect_popup(timeout=15000) as popup_info:
            print_btn.first.click()
        popup = popup_info.value
        popup.wait_for_load_state("domcontentloaded", timeout=30000)
        popup.wait_for_timeout(3000)

        pdf_url = popup.evaluate("""() => {
            const links = [...document.querySelectorAll('a')];
            const link = links.find(a => (a.getAttribute('href') || '').endsWith('.pdf'));
            return link ? link.href : null;
        }""")

        if pdf_url:
            raw_name = pdf_url.rsplit("/", 1)[-1]
            dest = output_dir / raw_name
            resp = popup.request.get(pdf_url)
            if resp.ok:
                dest.write_bytes(resp.body())
                print(f"  ✅ ダウンロード完了: {dest.name} ({len(resp.body()) // 1024}KB)")
                popup.close()
                return dest
        popup.close()
    except PlaywrightTimeoutError:
        pass

    print("  ❌ PDF のダウンロードに失敗しました")
    return None


def run(
    *,
    contract_index: int | None = None,
    group: str = "G1",
    output_dir: Path,
    start_year: int = 0,
    start_month: int = 0,
    end_year: int = 0,
    end_month: int = 0,
    headed: bool = True,
    dry_run: bool = False,
    pause_on_error: bool = True,
) -> Path | None:
    """オリックス銀行から返済実績表PDFを取得する。"""
    login_id = os.environ.get("ORIX_LOGIN_ID", "")
    password = os.environ.get("ORIX_PASSWORD", "")

    if not all([login_id, password]):
        print(
            "エラー: ORIX_LOGIN_ID / ORIX_PASSWORD が未設定です。\n"
            f"  → {DEFAULT_ENV_PATH} を作成してください",
            file=sys.stderr,
        )
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = None

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not headed)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        try:
            print("[1/4] ログイン...")
            _login(page, login_id, password)

            print("[2/4] 返済実績表照会へ遷移...")
            _navigate_to_repayment_history(page)

            contracts = _list_contracts(page)
            print(f"  契約一覧: {len(contracts)} 件")
            for i, c in enumerate(contracts):
                z_label = "個人" if c["zinkaku"] == "1" else "法人"
                print(f"    [{i}] {c['text']} ({z_label})")

            target, idx = _resolve_contract(contracts, contract_index)
            if contract_index is not None:
                print(f"\n[3/4] 契約 {target['text']} を選択 (index={idx})...")
            else:
                print(f"\n[3/4] 契約 {target['text']} を選択...")

            if dry_run:
                print("  [dry-run] PDF ダウンロードをスキップ")
                return None

            print("[4/4] PDF ダウンロード...")
            if target["zinkaku"] == "1":
                print("  ⚠ 個人名義契約です。税理士提出は法人のみのため、通常は法人契約を使います。")
                result_path = _download_pdf_zinkaku1(page, target, output_dir)
            else:
                if not all([start_year, start_month, end_year, end_month]):
                    raise RuntimeError(
                        "法人契約の取得には --start-month / --end-month の指定が必要です"
                        "（例: --start-month 2025-06 --end-month 2025-06）"
                    )
                result_path = _download_pdf_zinkaku2(
                    page, target, output_dir,
                    start_year, start_month, end_year, end_month,
                )

        except PlaywrightTimeoutError as e:
            print(f"タイムアウト: {e}", file=sys.stderr)
            if pause_on_error and headed:
                try:
                    page.pause()
                except KeyboardInterrupt:
                    pass
        except Exception as e:
            print(f"エラー: {e}", file=sys.stderr)
            if pause_on_error and headed:
                try:
                    page.pause()
                except KeyboardInterrupt:
                    pass
        finally:
            context.close()
            browser.close()

    return result_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="オリックス銀行・返済実績表 PDF ダウンロード",
    )
    parser.add_argument(
        "--contract-index", type=int, default=None,
        help="契約一覧での選択位置（0始まり）。未指定時は法人名義を自動選択",
    )
    parser.add_argument(
        "--group", default="G1",
        help="借入グループ名（既定: G1）",
    )
    parser.add_argument(
        "--start-month", default="",
        help="照会開始月（法人名義用。YYYY-MM）",
    )
    parser.add_argument(
        "--end-month", default="",
        help="照会終了月（法人名義用。YYYY-MM）",
    )
    parser.add_argument(
        "--output-dir", required=True,
        help="PDF の保存先ディレクトリ",
    )
    parser.add_argument(
        "--env-file", default=str(DEFAULT_ENV_PATH),
        help=f"認証情報 .env ファイル（既定: {DEFAULT_ENV_PATH}）",
    )
    parser.add_argument(
        "--headless", action="store_true",
        help="ヘッドレスモードで実行",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="ログイン・画面遷移のみ（DL なし）",
    )
    parser.add_argument(
        "--no-pause", action="store_true",
        help="エラー時に page.pause() を呼ばない",
    )
    args = parser.parse_args()

    _load_env_file(Path(args.env_file))

    sy = sm = ey = em = 0
    if args.start_month:
        parts = args.start_month.split("-")
        sy, sm = int(parts[0]), int(parts[1])
    if args.end_month:
        parts = args.end_month.split("-")
        ey, em = int(parts[0]), int(parts[1])

    result = run(
        contract_index=args.contract_index,
        group=args.group,
        output_dir=Path(args.output_dir),
        start_year=sy,
        start_month=sm,
        end_year=ey,
        end_month=em,
        headed=not args.headless,
        dry_run=args.dry_run,
        pause_on_error=not args.no_pause,
    )

    if result:
        print(f"\n完了: {result}")
    elif not args.dry_run:
        print("\n❌ PDF の取得に失敗しました", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
