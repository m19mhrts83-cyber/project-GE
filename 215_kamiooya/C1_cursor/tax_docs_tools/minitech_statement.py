#!/usr/bin/env python3
"""
ミニテック・オーナーマイページから「送金のご案内」PDFをダウンロードする。

使い方:
  python minitech_statement.py \
      --months 2025-07,2025-08,2025-09 \
      --output-dir ".../00_元ファイル_サイト取得/ミニテック/"

認証情報: .env.tax_docs（同ディレクトリ）に
  MINITECH_EMAIL / MINITECH_PASSWORD を設定する。

取得元:
  https://www.minitech.co.jp/ → オーナーマイページ → 送金情報照会タブ
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

MINITECH_TOP_URL = "https://www.minitech.co.jp/"


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


def _login(page, email: str, password: str) -> None:
    """ミニテック・オーナーマイページにログインする。"""
    page.goto(MINITECH_TOP_URL, wait_until="load")
    _wait_ready(page)
    page.wait_for_timeout(1500)

    owner_btn = page.locator("a").filter(has_text="オーナーマイページ")
    if owner_btn.count() > 0:
        owner_btn.first.click()
        _wait_ready(page)
        page.wait_for_timeout(1500)

    # ログインリンクがある場合（「オーナーマイページログイン」等）
    login_link = page.locator("a").filter(has_text="ログイン")
    if login_link.count() > 0:
        for i in range(login_link.count()):
            el = login_link.nth(i)
            text = el.inner_text().strip()
            if "ログイン" in text and "新規" not in text:
                el.click()
                _wait_ready(page)
                page.wait_for_timeout(1500)
                break

    # メールアドレス・パスワード入力
    email_input = page.locator('input[type="email"], input[type="text"][name*="mail"], input[name*="email"], input[name*="login"]')
    if email_input.count() == 0:
        email_input = page.locator("input[type='text']").first
    email_input.first.fill(email)

    pw_input = page.locator('input[type="password"]')
    pw_input.first.fill(password)

    # ログインボタン
    login_btn = page.locator('button, input[type="submit"]').filter(has_text="ログイン")
    if login_btn.count() == 0:
        login_btn = page.get_by_role("button", name="ログイン")
    login_btn.first.click()

    _wait_ready(page, timeout_ms=30000)
    page.wait_for_timeout(2000)

    try:
        page.wait_for_function(
            """() => {
                const t = document.body ? document.body.innerText : '';
                return t.includes('送金情報照会') || t.includes('お知らせ') || t.includes('ログアウト');
            }""",
            timeout=30000,
        )
    except PlaywrightTimeoutError:
        raise RuntimeError(
            "ミニテック・オーナーマイページへのログインに失敗しました。"
            " .env.tax_docs の MINITECH_EMAIL / MINITECH_PASSWORD を確認してください。"
        )
    print(f"  ログイン成功: {page.url}")


def _navigate_to_soukin(page) -> None:
    """「送金情報照会」タブへ遷移する。"""
    # ナビリンクがレスポンシブで不可視の場合があるので URL 直接遷移を優先
    soukin_url = page.evaluate("""() => {
        const a = [...document.querySelectorAll('a')]
            .find(el => el.innerText.includes('送金情報照会'));
        return a ? a.href : null;
    }""")
    if soukin_url:
        page.goto(soukin_url, wait_until="load")
    else:
        # ベースURLから推測
        base = page.url.rsplit("/", 1)[0]
        page.goto(f"{base}/paym", wait_until="load")
    _wait_ready(page)
    page.wait_for_timeout(1500)
    if "送金情報照会" not in page.inner_text("body"):
        raise RuntimeError("「送金情報照会」画面に遷移できませんでした")
    print("  送金情報照会タブを表示")


def _parse_table_rows(page) -> list[dict]:
    """送金情報照会テーブルの行をパースする。"""
    rows = page.evaluate("""() => {
        const table = document.querySelector('table');
        if (!table) return [];
        const trs = [...table.querySelectorAll('tr')];
        const headers = [...trs[0].querySelectorAll('th')]
            .map(th => th.innerText.trim());
        return trs.slice(1).map(tr => {
            const tds = [...tr.querySelectorAll('td')];
            const row = {};
            headers.forEach((h, i) => {
                if (tds[i]) {
                    row[h] = tds[i].innerText.trim();
                    // <a> リンク
                    const link = tds[i].querySelector('a');
                    if (link) row[h + '_href'] = link.href;
                    // <button onclick="window.open(...)"> からURLを抽出
                    const btn = tds[i].querySelector('button[onclick]');
                    if (btn) {
                        const m = btn.getAttribute('onclick')
                            ?.match(/window\\.open\\(['\"]([^'\"]+)['\"]/)
                        if (m) row[h + '_href'] = m[1];
                    }
                }
            });
            return row;
        });
    }""")
    return rows


def _normalize_month(text: str) -> tuple[int, int] | None:
    """「2025年 7月」「2025年7月」のような表記から (year, month) を返す。"""
    m = re.search(r'(\d{4})\s*年\s*(\d{1,2})\s*月', text)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None


def _download_pdf_for_month(
    page, rows: list[dict], year: int, month: int, output_dir: Path
) -> Path | None:
    """指定月の「送金のご案内」PDFをダウンロードして保存する。"""
    target_row = None
    for row in rows:
        ym = row.get("支払年月", "")
        parsed = _normalize_month(ym)
        if parsed and parsed == (year, month):
            target_row = row
            break

    if target_row is None:
        print(f"  ⚠ {year}年{month}月の行が一覧に見つかりませんでした")
        return None

    pdf_key = None
    for key in target_row:
        if "送金のご案内" in key and key.endswith("_href"):
            pdf_key = key
            break

    if pdf_key is None:
        col_text = target_row.get("送金のご案内", "")
        if "PDF" not in col_text:
            print(f"  ⚠ {year}年{month}月: 送金のご案内に PDF リンクがありません")
            return None

    output_name = f"ミニテック_送金のご案内_{year}年{month}月.pdf"
    dest = output_dir / output_name

    pdf_url = target_row.get(pdf_key) if pdf_key else None

    if pdf_url:
        # URL が取れた場合: response body で直接ダウンロード
        try:
            resp = page.request.get(pdf_url)
            if resp.ok:
                dest.write_bytes(resp.body())
                print(f"  ✅ ダウンロード完了: {output_name} ({len(resp.body()) // 1024}KB)")
                return dest
        except Exception:
            pass

        # フォールバック: window.open + expect_download
        try:
            with page.expect_download(timeout=15000) as dl_info:
                page.evaluate(f"() => window.open('{pdf_url}')")
            download = dl_info.value
            download.save_as(str(dest))
            print(f"  ✅ ダウンロード完了: {output_name}")
            return dest
        except (PlaywrightTimeoutError, Exception):
            pass

    print(f"  ❌ {year}年{month}月: PDF のダウンロードに失敗しました")
    return None


def run(
    *,
    months: list[tuple[int, int]],
    output_dir: Path,
    headed: bool = True,
    dry_run: bool = False,
    pause_on_error: bool = True,
) -> list[dict]:
    """ミニテックから送金のご案内PDFを取得する。"""
    email = os.environ.get("MINITECH_EMAIL", "")
    password = os.environ.get("MINITECH_PASSWORD", "")

    if not all([email, password]):
        print(
            "エラー: MINITECH_EMAIL / MINITECH_PASSWORD が未設定です。\n"
            f"  → {DEFAULT_ENV_PATH} を作成してください",
            file=sys.stderr,
        )
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)
    results = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not headed)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        try:
            print("[1/3] ミニテック・オーナーマイページにログイン中...")
            _login(page, email, password)

            print("[2/3] 送金情報照会へ遷移...")
            _navigate_to_soukin(page)

            rows = _parse_table_rows(page)
            print(f"  一覧: {len(rows)} 行を検出")

            if dry_run:
                for y, m in months:
                    print(f"  [dry-run] {y}年{m}月: スキップ")
                    results.append({"year": y, "month": m, "status": "dry-run", "path": None})
                return results

            print(f"[3/3] PDF ダウンロード ({len(months)} 件)...")
            for y, m in months:
                label = f"{y}年{m}月"
                dest = output_dir / f"ミニテック_送金のご案内_{label}.pdf"
                if dest.exists():
                    print(f"  ⚠ {label}: 既に存在 → スキップ")
                    results.append({"year": y, "month": m, "status": "skipped", "path": dest})
                    continue

                pdf = _download_pdf_for_month(page, rows, y, m, output_dir)
                if pdf:
                    results.append({"year": y, "month": m, "status": "ok", "path": pdf})
                else:
                    results.append({"year": y, "month": m, "status": "failed", "path": None})

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

    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ミニテック・送金のご案内 PDF ダウンロード",
    )
    parser.add_argument(
        "--months", required=True,
        help="対象月（YYYY-MM のカンマ区切り。例: 2025-07,2025-08,2025-09）",
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
        help="ログイン・一覧確認のみ（DL なし）",
    )
    parser.add_argument(
        "--no-pause", action="store_true",
        help="エラー時に page.pause() を呼ばない",
    )
    args = parser.parse_args()

    _load_env_file(Path(args.env_file))

    months: list[tuple[int, int]] = []
    for token in args.months.split(","):
        token = token.strip()
        parts = token.split("-")
        if len(parts) != 2:
            print(f"エラー: 月の形式が不正です: {token}（YYYY-MM）", file=sys.stderr)
            sys.exit(1)
        months.append((int(parts[0]), int(parts[1])))

    results = run(
        months=months,
        output_dir=Path(args.output_dir),
        headed=not args.headless,
        dry_run=args.dry_run,
        pause_on_error=not args.no_pause,
    )

    ok = sum(1 for r in results if r["status"] == "ok")
    fail = sum(1 for r in results if r["status"] == "failed")
    print(f"\n完了: {ok} 件成功, {fail} 件失敗")
    sys.exit(1 if fail > 0 else 0)


if __name__ == "__main__":
    main()
