#!/usr/bin/env python3
"""
ログインが必要なサイトにアクセスし、ログイン後のページ内容を取得してファイルに保存する。

使い方:
  1. .env に NICHINOKEN_USER と NICHINOKEN_PASS を設定（または環境変数）
  2. config_nichinoken.yaml を config_nichinoken.example.yaml からコピーして編集
  3. python fetch_after_login.py nichinoken

  結果は output/ に 日能研_取得結果_YYYYMMDD_HHMMSS.md として保存される。

将来: python fetch_after_login.py bank で銀行用も同様に実行できるようにする想定。
"""

import argparse
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# プロジェクトルートの .env を読む（browser_automation から見て一つ上×2）
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_ENV = SCRIPT_DIR.parent.parent / ".env"
load_dotenv(ROOT_ENV)
load_dotenv(SCRIPT_DIR / ".env")


def load_config(site: str) -> dict:
    """サイト名に応じた設定YAMLを読む。"""
    import yaml
    config_path = SCRIPT_DIR / f"config_{site}.yaml"
    if not config_path.exists():
        example = SCRIPT_DIR / f"config_{site}.example.yaml"
        print(f"設定ファイルがありません: {config_path}", file=sys.stderr)
        if example.exists():
            print(f"  {example} をコピーして config_{site}.yaml を作成し、編集してください。", file=sys.stderr)
        sys.exit(1)
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_credentials(site: str):
    """環境変数からIDとパスワードを取得。"""
    prefix = site.upper()
    user = os.environ.get(f"{prefix}_USER") or os.environ.get(f"{prefix}_ID")
    password = os.environ.get(f"{prefix}_PASS") or os.environ.get(f"{prefix}_PASSWORD")
    if not user or not password:
        print(f"環境変数 {prefix}_USER と {prefix}_PASS を設定してください。", file=sys.stderr)
        print("  .env に NICHINOKEN_USER=... NICHINOKEN_PASS=... を書くか、export で設定。", file=sys.stderr)
        sys.exit(1)
    return user, password


def extract_main_text(page) -> str:
    """Playwright の page からメインコンテンツのテキストを抽出。"""
    selectors = [
        "main",
        "[role='main']",
        ".main-content",
        ".content",
        "#content",
        ".main",
    ]
    for sel in selectors:
        try:
            loc = page.locator(sel)
            if loc.count() > 0:
                return loc.first.inner_text(timeout=2000)
        except Exception:
            continue
    return page.locator("body").inner_text()


def get_matching_links(page, base_url: str, keywords: list, max_links: int = 15) -> list:
    """
    ページ内のリンクのうち、テキストまたは href にキーワードを含み、
    かつ same-origin のものを最大 max_links 件返す。重複URLは除く。
    """
    from urllib.parse import urljoin, urlparse
    visited = set()
    result = []
    try:
        links = page.locator("a[href]").all()
    except Exception:
        return result
    base_origin = urlparse(base_url).netloc
    for link in links:
        if len(result) >= max_links:
            break
        try:
            href = link.get_attribute("href")
            if not href or href.startswith("#") or href.startswith("javascript:"):
                continue
            full_url = urljoin(base_url, href)
            parsed = urlparse(full_url)
            if parsed.netloc and parsed.netloc != base_origin:
                continue
            # 同一URLは1回だけ
            norm = full_url.split("#")[0].rstrip("/")
            if norm in visited:
                continue
            try:
                text = link.inner_text() or ""
            except Exception:
                text = ""
            if not any(kw in text or kw in href or kw in full_url for kw in keywords):
                continue
            visited.add(norm)
            result.append((full_url, text.strip() or norm))
        except Exception:
            continue
    return result


def get_schedule_links(page, base_url: str, max_links: int = 10) -> list:
    """
    ページ内の「1月」〜「12月」「月間」「スケジュール」「PDF」等のテキストを持つリンクを返す。
    href が #! や #2 などのハッシュでも含める（月間スケジュールのタブ切り替え用）。
    """
    from urllib.parse import urljoin, urlparse
    keywords = [
        "1月", "2月", "3月", "4月", "5月", "6月",
        "7月", "8月", "9月", "10月", "11月", "12月",
        "月間", "スケジュール", "PDF", "ダウンロード"
    ]
    seen = set()
    result = []
    try:
        links = page.locator("a[href]").all()
    except Exception:
        return result
    base_origin = urlparse(base_url).netloc
    for link in links:
        if len(result) >= max_links:
            break
        try:
            href = link.get_attribute("href")
            if not href or href.startswith("javascript:"):
                continue
            # #! や #2 等のハッシュは許可（students-schedule.html#! で2月表示など）
            full_url = urljoin(base_url, href)
            parsed = urlparse(full_url)
            if parsed.netloc and parsed.netloc != base_origin:
                continue
            # ハッシュ付き（#!, #2 等）は月ごとに別URLとして扱う
            norm = full_url if "#" in full_url and full_url.split("#")[1] else full_url.split("#")[0].rstrip("/")
            if norm in seen:
                continue
            try:
                text = (link.inner_text() or "").strip()
            except Exception:
                text = ""
            if not any(kw in text or kw in href or kw in full_url for kw in keywords):
                continue
            seen.add(norm)
            result.append((full_url, text or norm))
        except Exception:
            continue
    return result


def get_pdf_links(page, base_url: str, max_links: int = 10) -> list:
    """ページ内の .pdf リンクを最大 max_links 件返す（重複URL除く）。"""
    from urllib.parse import urljoin, urlparse
    seen = set()
    result = []
    try:
        links = page.locator("a[href*='.pdf'], a[href*='.PDF']").all()
    except Exception:
        return result
    base_origin = urlparse(base_url).netloc
    for link in links:
        if len(result) >= max_links:
            break
        try:
            href = link.get_attribute("href")
            if not href:
                continue
            full_url = urljoin(base_url, href)
            parsed = urlparse(full_url)
            if parsed.netloc and parsed.netloc != base_origin:
                continue
            norm = full_url.split("#")[0].rstrip("/")
            if norm in seen:
                continue
            seen.add(norm)
            try:
                text = (link.inner_text() or "").strip() or norm
            except Exception:
                text = norm
            result.append((full_url, text))
        except Exception:
            continue
    return result


def fetch_pdf_text(page, pdf_url: str) -> str:
    """
    同じブラウザコンテキスト（ログイン済み）で PDF を取得し、テキストを抽出する。
    失敗時は空文字を返す。
    """
    import base64
    import tempfile
    try:
        # ページ内で fetch するので Cookie が送られる
        b64 = page.evaluate("""async (url) => {
            const r = await fetch(url);
            if (!r.ok) return null;
            const buf = await r.arrayBuffer();
            const bytes = new Uint8Array(buf);
            let binary = '';
            for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
            return btoa(binary);
        }""", pdf_url)
        if not b64:
            return ""
        pdf_bytes = base64.b64decode(b64)
        if not pdf_bytes.startswith(b"%PDF"):
            return ""
    except Exception as e:
        print(f"    PDF取得失敗: {pdf_url[:60]}... ({e})", file=sys.stderr)
        return ""
    try:
        import pdfplumber
    except ImportError:
        print("    pdfplumber がありません。pip install pdfplumber を実行してください。", file=sys.stderr)
        return ""
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(pdf_bytes)
            tmp = f.name
        try:
            with pdfplumber.open(tmp) as pdf:
                parts = []
                for p in pdf.pages:
                    t = p.extract_text()
                    if t:
                        parts.append(t)
                return "\n\n".join(parts) if parts else ""
        finally:
            os.unlink(tmp)
    except Exception as e:
        print(f"    PDF解析失敗: {pdf_url[:60]}... ({e})", file=sys.stderr)
        return ""


def run_nichinoken(headless: bool = False) -> str:
    """日能研 MY NICHINOKEN にログインして情報を取得。保存したファイルパスを返す。"""
    from playwright.sync_api import sync_playwright
    config = load_config("nichinoken")
    user, password = get_credentials("nichinoken")

    login_url = config.get("login_url", "https://login.mynichinoken.jp/auth/student/login")
    target_urls = config.get("target_urls") or []
    wait_login = config.get("wait_after_login", 3)
    wait_page = config.get("wait_after_page", 2)
    headless = config.get("headless", headless)
    explore_links = config.get("explore_links", False)
    link_keywords = config.get("link_keywords") or []
    max_pages_to_follow = config.get("max_pages_to_follow", 10)
    fetch_pdfs = config.get("fetch_pdfs", True)
    max_pdfs_per_page = config.get("max_pdfs_per_page", 5)
    output_dir = config.get("output_dir")

    if output_dir:
        out_dir = Path(output_dir).resolve()
    else:
        out_dir = SCRIPT_DIR / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"日能研_取得結果_{timestamp}.md"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            page.goto(login_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_load_state("networkidle", timeout=15000)

            # ログインフォーム: サイトによって name/id が違うので複数パターン試す
            # MY NICHINOKEN は要確認。ここは汎用で input[type=text], input[type=password]
            id_input = page.locator("input[type='text'], input[name*='id'], input[name*='login'], input[name*='user']").first
            pass_input = page.locator("input[type='password']").first
            id_input.fill(user)
            pass_input.fill(password)

            # 送信ボタン: button[type=submit] または ログイン を含むボタン/リンク
            submit = page.locator("button[type='submit'], input[type='submit'], a:has-text('ログイン'), button:has-text('ログイン')").first
            submit.click()

            page.wait_for_timeout(wait_login * 1000)

            # ログイン後のURLに遷移しているか簡易チェック（エラーページでないこと）
            current_url = page.url
            if "login" in current_url and "error" in current_url.lower():
                print("ログインに失敗した可能性があります。headless=false で実行して画面を確認してください。", file=sys.stderr)

            def append_pdfs_from_current_page(page_url: str):
                """現在のページにある PDF リンクを取得し、テキストを parts に追加する。"""
                if not fetch_pdfs:
                    return
                for pdf_url, link_label in get_pdf_links(page, page_url, max_links=max_pdfs_per_page):
                    pdf_text = fetch_pdf_text(page, pdf_url)
                    if pdf_text:
                        label = (link_label or pdf_url)[:80]
                        parts.append(f"## 【PDF】{label}\n\nURL: {pdf_url}\n\n{pdf_text}\n\n---\n")
                        print(f"  PDF取得: {label}", file=sys.stderr)

            def get_pdf_urls_on_page(page, base_url: str) -> list:
                """現在のページ内の PDF の URL（iframe/embed/a）を最大10件返す。"""
                from urllib.parse import urljoin
                found = []
                try:
                    # iframe / embed の src
                    for sel in ["iframe[src*='.pdf']", "embed[src*='.pdf']", "object[data*='.pdf']"]:
                        for el in page.locator(sel).all():
                            try:
                                src = el.get_attribute("src") or el.get_attribute("data")
                                if src:
                                    found.append(urljoin(base_url, src))
                            except Exception:
                                pass
                    # a タグの .pdf リンク
                    for url, _ in get_pdf_links(page, base_url, max_links=5):
                        if url not in found:
                            found.append(url)
                except Exception:
                    pass
                return list(dict.fromkeys(found))[:10]

            def append_schedule_pdfs_from_current_page(page_url: str):
                """
                月間スケジュールページの場合、「1月」〜「12月」等のリンクを処理する。
                - リンク先が PDF ならそのまま取得。
                - リンク先が #! 等のハッシュの場合はその URL を開き、表示された PDF を探して取得。
                """
                if not config.get("fetch_schedule_pdfs", True):
                    return
                if not fetch_pdfs:
                    return
                if "schedule" not in page_url.lower():
                    return
                schedule_links = get_schedule_links(page, page_url, max_links=max_pdfs_per_page)
                base_schedule_url = page_url.split("#")[0]
                for url, link_label in schedule_links:
                    label = (link_label or url)[:80]
                    pdf_text = ""
                    # 1) リンク先が直接 PDF の場合は fetch
                    if ".pdf" in url.lower():
                        pdf_text = fetch_pdf_text(page, url)
                    else:
                        # 2) ハッシュ付き（students-schedule.html#! 等）: その URL を開いてからページ内の PDF を探す
                        try:
                            page.goto(url, wait_until="domcontentloaded", timeout=15000)
                            page.wait_for_timeout(2500)
                            for pdf_url in get_pdf_urls_on_page(page, page.url):
                                pdf_text = fetch_pdf_text(page, pdf_url)
                                if pdf_text:
                                    break
                        except Exception as e:
                            print(f"  スケジュール取得スキップ: {label} ({e})", file=sys.stderr)
                        finally:
                            page.goto(base_schedule_url, wait_until="domcontentloaded", timeout=10000)
                            page.wait_for_timeout(500)
                    if pdf_text:
                        parts.append(f"## 【PDF】月間スケジュール: {label}\n\nURL: {url}\n\n{pdf_text}\n\n---\n")
                        print(f"  スケジュールPDF取得: {label}", file=sys.stderr)

            parts = []
            # 1) トップ（現在のページ）を取得
            text = extract_main_text(page)
            title = page.title()
            parts.append(f"## {title}\n\nURL: {current_url}\n\n{text}\n\n---\n")
            append_pdfs_from_current_page(current_url)

            # 2) トップからキーワードに合うリンクをたどって取得（お知らせ・メッセージ・模試など）
            if explore_links and link_keywords:
                follow_links = get_matching_links(page, current_url, link_keywords, max_links=max_pages_to_follow)
                seen = {current_url.split("#")[0].rstrip("/")}
                for url, link_text in follow_links:
                    norm = url.split("#")[0].rstrip("/")
                    if norm in seen:
                        continue
                    seen.add(norm)
                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=20000)
                        page.wait_for_timeout(wait_page * 1000)
                        text = extract_main_text(page)
                        title = page.title()
                        parts.append(f"## {title}\n\nリンク: {link_text}\nURL: {url}\n\n{text}\n\n---\n")
                        print(f"  取得: {link_text or title}", file=sys.stderr)
                        append_pdfs_from_current_page(page.url)
                    except Exception as e:
                        print(f"  スキップ: {url} ({e})", file=sys.stderr)
                page.goto(current_url, wait_until="domcontentloaded", timeout=15000)
                page.wait_for_timeout(500)

            # 3) 設定で指定されたURL（月間スケジュール等）を取得し、PDF・スケジュールリンクも取得
            if target_urls:
                for url in target_urls:
                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=20000)
                        page.wait_for_timeout(wait_page * 1000)
                        text = extract_main_text(page)
                        title = page.title()
                        parts.append(f"## {title}\n\nURL: {url}\n\n{text}\n\n---\n")
                        append_pdfs_from_current_page(page.url)
                        append_schedule_pdfs_from_current_page(page.url)
                    except Exception as e:
                        print(f"  URL取得スキップ: {url} ({e})", file=sys.stderr)

            body = f"# 日能研 MY NICHINOKEN 取得結果\n\n取得日時: {datetime.now().isoformat()}\n\n" + "\n".join(parts)
            # 過剰な改行を整理
            body = re.sub(r"\n{4,}", "\n\n\n", body)
            out_path.write_text(body, encoding="utf-8")
            print(f"保存しました: {out_path}")
            return str(out_path)

        finally:
            browser.close()

    return str(out_path)


def main():
    parser = argparse.ArgumentParser(description="ログイン後にページ内容を取得して保存")
    parser.add_argument("site", choices=["nichinoken"], help="サイト名（将来 bank を追加予定）")
    parser.add_argument("--headless", action="store_true", help="ブラウザを表示しない")
    args = parser.parse_args()

    if args.site == "nichinoken":
        path = run_nichinoken(headless=args.headless)
    else:
        print(f"未対応のサイト: {args.site}", file=sys.stderr)
        sys.exit(1)

    print(f"出力: {path}")


if __name__ == "__main__":
    main()
