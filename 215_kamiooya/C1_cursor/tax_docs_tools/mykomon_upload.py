#!/usr/bin/env python3
"""
MyKomon（税理士共有フォルダ）にファイルをアップロードする。

使い方:
  python mykomon_upload.py \
      --file "PayPay銀行明細_6月.pdf" \
      --year "2025年（令和7年）" \
      --quarter "②4-6月" \
      --category "01_預金通帳のコピー"

認証情報: .env.tax_docs（同ディレクトリ）に
  MYKOMON_USER_ID / MYKOMON_PASSWORD を設定する。

階層:
  共有フォルダ → カラフルファイル（法人）→ 年度 → 四半期 → 分類フォルダ → + ファイル追加
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_ENV_PATH = SCRIPT_DIR / ".env.tax_docs"

MYKOMON_URL = "https://www.mykomon.com/MyKomon/"


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


def _login(page, user_id: str, password: str) -> None:
    """MyKomon にログインする。"""
    # 別ブラウザログイン確認などの confirm / alert を自動承認
    page.on("dialog", lambda dialog: dialog.accept())

    page.goto(MYKOMON_URL, wait_until="load")
    _wait_ready(page)
    page.wait_for_timeout(1500)

    page.locator('input[name="loginname"]').fill(user_id)
    page.locator('input[name="pass"]').fill(password)

    page.locator('button[name="btnSubmit"]').click()

    _wait_ready(page, timeout_ms=30000)
    try:
        page.wait_for_function(
            """() => {
                const t = document.body ? document.body.innerText : '';
                return t.includes('共有フォルダ') || t.includes('カラフルファイル');
            }""",
            timeout=45000,
        )
    except PlaywrightTimeoutError:
        raise RuntimeError(
            "MyKomon ログイン後に共有フォルダ画面へ遷移できませんでした。"
            " .env.tax_docs の MYKOMON_USER_ID / MYKOMON_PASSWORD を確認してください。"
        )
    print(f"  ログイン後 URL: {page.url}")


def _find_shared_folder_target(page):
    """共有フォルダタブまたはツリーが表示されているフレーム／ページを返す。"""
    if page.locator("text=共有フォルダ").count() > 0:
        return page
    if page.get_by_text("カラフルファイル（法人）").count() > 0:
        return page
    for frame in page.frames:
        if frame.locator("text=共有フォルダ").count() > 0:
            return frame
        if frame.get_by_text("カラフルファイル（法人）").count() > 0:
            return frame
    return page


def _open_shared_folder_tab(page) -> None:
    """画面上部の「共有フォルダ」タブを開く。"""
    if page.locator("#folder_tree_left").count() > 0:
        print("  共有フォルダ画面は既に表示されています")
        return

    shared_tab = page.locator("a, button, li, span").filter(has_text="共有フォルダ")
    for i in range(shared_tab.count()):
        el = shared_tab.nth(i)
        try:
            if el.is_visible():
                el.click()
                _wait_ready(page)
                page.wait_for_timeout(1500)
                print("  共有フォルダタブを選択")
                return
        except Exception:
            continue
    raise RuntimeError("「共有フォルダ」タブが見つかりませんでした")


def _click_tree_path(page, *segments: str) -> None:
    """左ツリーを親子関係付きで辿り、最終ノードまで展開・選択する。"""
    page.evaluate(
        """(names) => {
            const rows = [...document.querySelectorAll('#folder_tree_left .tree_row')];
            let parentFolderNo = null;

            const folderNoFromRow = (row) => {
                for (const cls of row.classList) {
                    if (cls.startsWith('folder_') && cls !== 'folder_-2') {
                        return cls.slice('folder_'.length);
                    }
                }
                return null;
            };

            for (const name of names) {
                const row = rows.find((r) => {
                    const label = r.querySelector('span.folder_name, a')?.innerText.trim();
                    if (label !== name) return false;
                    if (parentFolderNo === null) return true;
                    return r.classList.contains('parent_' + parentFolderNo);
                });
                if (!row) throw new Error('ツリーパスが見つかりません: ' + name);

                const arrow = row.querySelector('i.arrow');
                if (arrow) arrow.dispatchEvent(new MouseEvent('click', { bubbles: true }));
                const labelEl = row.querySelector('span.folder_name, a');
                labelEl?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
                parentFolderNo = folderNoFromRow(row);
            }
        }""",
        list(segments),
    )
    _wait_ready(page)
    page.wait_for_timeout(1500)
    # ツリー選択後に #inner_right が更新されるまで待つ
    last = segments[-1]
    for _ in range(8):
        inner = page.evaluate(
            "(name) => {"
            "  const el = document.querySelector('#inner_right');"
            "  return el ? el.innerText.includes(name) : false;"
            "}",
            last,
        )
        if inner:
            break
        page.wait_for_timeout(500)
    print(f"  ツリー選択: {' → '.join(segments)}")


def _position_name(page) -> str:
    return page.evaluate(
        """() => {
            const inner = document.querySelector('#inner_right');
            if (!inner) return '';
            const span = inner.querySelector('.title_area .position_name');
            return span ? span.innerText.trim() : '';
        }"""
    )


def _wait_position(page, expected: str, *, timeout_ms: int = 12000) -> bool:
    import time

    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        if _position_name(page) == expected:
            return True
        page.wait_for_timeout(400)
    return _position_name(page) == expected


def _click_listing_folder(page, name: str) -> bool:
    return page.evaluate(
        """(name) => {
            const inner = document.querySelector('#inner_right');
            if (!inner) return false;
            const link = [...inner.querySelectorAll('a.view_folder')]
                .filter(a => !a.closest('.title_area'))
                .find(a => a.innerText.trim() === name);
            if (!link) return false;
            link.click();
            return true;
        }""",
        name,
    )


def _click_breadcrumb(page, name: str) -> bool:
    return page.evaluate(
        """(name) => {
            const inner = document.querySelector('#inner_right');
            if (!inner) return false;
            const link = [...inner.querySelectorAll('.title_area a.view_folder')]
                .find(a => a.innerText.trim() === name);
            if (!link) return false;
            link.click();
            return true;
        }""",
        name,
    )


def _open_listing_folder(page, name: str, *, retries: int = 4) -> bool:
    for _ in range(retries):
        if _click_listing_folder(page, name):
            if _wait_position(page, name, timeout_ms=8000):
                return True
        page.wait_for_timeout(800)
    return False


def _goto_year(page, year: str, *, retries: int = 3) -> bool:
    for _ in range(retries):
        try:
            _open_shared_folder_tab(page)
            _click_tree_path(page, "カラフルファイル（法人）", year)
        except Exception:
            pass
        if _wait_position(page, year, timeout_ms=8000):
            return True
        page.wait_for_timeout(600)
    return _position_name(page) == year


def _goto_quarter_listing(page, year: str, quarter: str) -> bool:
    if _click_breadcrumb(page, quarter) and _wait_position(page, quarter, timeout_ms=5000):
        return True
    if not _goto_year(page, year):
        return False
    return _open_listing_folder(page, quarter)


def _navigate_to_folder(
    page, *, year: str, quarter: str, category: str, subfolder: str | None = None
) -> None:
    """共有フォルダ → カラフルファイル（法人）→ 年度 → 四半期 → 分類フォルダへ遷移。"""
    if not _goto_quarter_listing(page, year, quarter):
        raise RuntimeError(f"四半期に到達できません: {year}/{quarter}")
    print(f"  フォルダを開く: {quarter}")

    if not _open_listing_folder(page, category):
        if not (_goto_quarter_listing(page, year, quarter) and _open_listing_folder(page, category)):
            raise RuntimeError(f"メイン一覧にフォルダが見つかりません: {category}")
    print(f"  フォルダを開く: {category}")

    if subfolder:
        if not _open_listing_folder(page, subfolder):
            raise RuntimeError(f"メイン一覧にフォルダが見つかりません: {subfolder}")
        print(f"  フォルダを開く: {subfolder}")
    _wait_ready(page)


def _upload_file(page, file_path: Path) -> None:
    """「+ ファイル追加」→ ファイル選択 → 保存。"""
    add_btn = page.get_by_text("ファイル追加", exact=False).or_(
        page.get_by_role("button", name="ファイル追加")
    )
    add_btn.first.click()
    page.wait_for_timeout(2000)
    print("  ファイル追加ダイアログを開きました")

    file_input = page.locator('input[type="file"]')
    if file_input.count() == 0:
        with page.expect_file_chooser(timeout=10000) as chooser_info:
            page.get_by_text("ファイル選択", exact=False).first.click()
        chooser_info.value.set_files(str(file_path))
    else:
        file_input.first.set_input_files(str(file_path))
    page.wait_for_timeout(1000)
    print(f"  ファイル設定: {file_path.name}")

    clicked = page.evaluate(
        """() => {
            const btn = [...document.querySelectorAll('button[name="btnSave"]')]
                .find((b) => b.offsetParent !== null && b.innerText.includes('保存'));
            if (!btn) return false;
            btn.click();
            return true;
        }"""
    )
    if not clicked:
        raise RuntimeError("保存ボタンが見つかりませんでした")
    print("  保存ボタンをクリック")
    _wait_ready(page, timeout_ms=30000)
    page.wait_for_timeout(2000)

    listed = page.evaluate(
        """(fname) => {
            const inner = document.querySelector('#inner_right');
            const text = inner ? inner.innerText : document.body.innerText;
            return text.includes(fname);
        }""",
        file_path.name,
    )
    if not listed:
        raise RuntimeError(f"アップロード後の一覧に {file_path.name} が見つかりませんでした")
    print(f"  ✅ アップロード完了: {file_path.name}")


def run(
    *,
    file_path: Path,
    year: str,
    quarter: str,
    category: str,
    subfolder: str | None = None,
    headed: bool = True,
    dry_run: bool = False,
    pause_on_error: bool = True,
) -> bool:
    """MyKomon にファイルをアップロードする。成功時 True。"""
    user_id = os.environ.get("MYKOMON_USER_ID", "")
    password = os.environ.get("MYKOMON_PASSWORD", "")

    if not all([user_id, password]):
        print(
            "エラー: MYKOMON_USER_ID / MYKOMON_PASSWORD が未設定です。\n"
            f"  → {DEFAULT_ENV_PATH} を作成してください（テンプレート: .env.tax_docs.example）",
            file=sys.stderr,
        )
        sys.exit(1)

    if not file_path.exists():
        print(f"エラー: ファイルが見つかりません: {file_path}", file=sys.stderr)
        sys.exit(1)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not headed)
        context = browser.new_context()
        page = context.new_page()

        try:
            print("[1/3] MyKomon ログイン中...")
            _login(page, user_id, password)
            active = _find_shared_folder_target(page)
            page._mykomon_active = active  # type: ignore[attr-defined]

            dest = f"{year} → {quarter} → {category}"
            if subfolder:
                dest += f" → {subfolder}"
            print(f"[2/3] フォルダ遷移: {dest}")
            _navigate_to_folder(
                active, year=year, quarter=quarter, category=category, subfolder=subfolder
            )

            if dry_run:
                print("[dry-run] アップロードはスキップします。")
                active.wait_for_timeout(3000)
                return True

            print(f"[3/3] アップロード: {file_path.name}")
            _upload_file(active, file_path)
            return True

        except PlaywrightTimeoutError as e:
            print(f"タイムアウト: {e}", file=sys.stderr)
            if pause_on_error and headed:
                print("  page.pause() でブラウザを確認できます。Ctrl+C で終了。")
                try:
                    page.pause()
                except KeyboardInterrupt:
                    pass
            return False
        except Exception as e:
            print(f"エラー: {e}", file=sys.stderr)
            if pause_on_error and headed:
                try:
                    page.pause()
                except KeyboardInterrupt:
                    pass
            return False
        finally:
            context.close()
            browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="MyKomon にファイルをアップロードする",
    )
    parser.add_argument(
        "--file", required=True,
        help="アップロードするファイルのパス",
    )
    parser.add_argument(
        "--year", required=True,
        help='年度フォルダ名（例: "2025年（令和7年）"）',
    )
    parser.add_argument(
        "--quarter", required=True,
        help='四半期フォルダ名（例: "②4-6月"）',
    )
    parser.add_argument(
        "--category", required=True,
        help='分類フォルダ名（例: "01_預金通帳のコピー"）',
    )
    parser.add_argument(
        "--subfolder", default="",
        help='サブフォルダ名（例: "取引が全て経費のもの"。省略可）',
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
        help="フォルダ遷移のみ確認し、アップロードしない",
    )
    parser.add_argument(
        "--no-pause", action="store_true",
        help="エラー時に page.pause() を呼ばない",
    )
    args = parser.parse_args()

    _load_env_file(Path(args.env_file))

    success = run(
        file_path=Path(args.file),
        year=args.year,
        quarter=args.quarter,
        category=args.category,
        subfolder=args.subfolder or None,
        headed=not args.headless,
        dry_run=args.dry_run,
        pause_on_error=not args.no_pause,
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
