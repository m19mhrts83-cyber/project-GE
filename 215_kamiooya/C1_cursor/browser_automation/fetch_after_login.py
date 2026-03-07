#!/usr/bin/env python3
"""
ログインが必要なサイトにアクセスし、ログイン後のページ内容を取得してファイルに保存する。

使い方:
  1. .env に NICHINOKEN_USER と NICHINOKEN_PASS を設定（または環境変数）
  2. config_nichinoken.yaml を config_nichinoken.example.yaml からコピーして編集
  3. python fetch_after_login.py nichinoken

  結果は output/ に 日能研_取得結果_YYYYMMDD_HHMMSS.md として保存される。

  東海労金:
  - .env に TOKAIROKIN_USER と TOKAIROKIN_PASS を設定
  - config_tokairokin.yaml を config_tokairokin.example.yaml からコピーして編集
  - python fetch_after_login.py tokairokin  # ログインのみ。振込は今後追加

将来: python fetch_after_login.py bank で銀行用も同様に実行できるようにする想定。
"""

import argparse
import os
import platform
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# プロジェクトルートの .env を読む（browser_automation から見て一つ上×2）
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_ENV = SCRIPT_DIR.parent.parent / ".env"
load_dotenv(ROOT_ENV)
load_dotenv(SCRIPT_DIR / ".env")


def _wait_enter(confirm_msg: str = "Enter を受け付けました。次へ進みます。"):
    """Enter が押されるまで待ち、受け取ったら確認メッセージを表示。
    Cursor の統合ターミナルでは stdin に Enter が届かないことがあるため、
    まず /dev/tty（端末デバイス）から直接読みを試みる。
    """
    sys.stderr.flush()
    entered = False
    # /dev/tty から読む（統合ターミナルで stdin が効かない場合に有効）
    if platform.system() != "Windows":
        try:
            with open("/dev/tty", "r", encoding="utf-8") as tty:
                tty.readline()
            entered = True
        except (OSError, IOError):
            pass
    if not entered:
        try:
            sys.stdin.readline()
            entered = True
        except (EOFError, OSError):
            pass
    if not entered:
        try:
            input()
        except (EOFError, OSError):
            pass
    if confirm_msg:
        print(confirm_msg, file=sys.stderr)
        sys.stderr.flush()


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


def _get_secret_phrase_answer(mapping: dict):
    """合言葉のマッピングから回答を取得。answer_env または answer を参照。"""
    """合言葉のマッピングから回答を取得。answer_env または answer を参照。"""
    env_key = mapping.get("answer_env")
    if env_key:
        return os.environ.get(env_key)
    return mapping.get("answer")


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


def _fill_human_like(page, selector: str, text: str, delay_ms: int = 80):
    """人間らしく1文字ずつ入力する（自動化検知回避の補助）。"""
    loc = page.locator(selector)
    loc.click()
    loc.fill("")  # クリア
    loc.press_sequentially(text, delay=delay_ms)


def _ensure_chrome_for_cdp(cdp_port: int = 9222, user_data_dir: str = None) -> subprocess.Popen:
    """
    Chrome をすべて終了し、デバッグポート付きで起動する。
    戻り値: 起動した Chrome の Popen オブジェクト（終了時に kill する想定）
    """
    import socket
    import tempfile
    if user_data_dir is None:
        base = tempfile.gettempdir()
        user_data_dir = str(Path(base) / f"chrome-debug-{cdp_port}")
    Path(user_data_dir).mkdir(parents=True, exist_ok=True)

    system = platform.system()
    if system == "Darwin":
        chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        kill_cmd = ["killall", "Google Chrome"]
    elif system == "Windows":
        chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        kill_cmd = ["taskkill", "/F", "/IM", "chrome.exe"]
    else:
        chrome_path = "google-chrome"
        kill_cmd = ["pkill", "-f", "chrome"]

    # 既存の Chrome を終了
    print("既存の Chrome を終了しています...", file=sys.stderr)
    try:
        subprocess.run(kill_cmd, capture_output=True, timeout=5)
        time.sleep(2)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Chrome をデバッグモードで起動
    if not Path(chrome_path).exists() and system != "Linux":
        chrome_path = "chrome"  # フォールバック
    chrome_args = [
        chrome_path,
        f"--remote-debugging-port={cdp_port}",
        f"--user-data-dir={user_data_dir}",
        "--no-first-run",
    ]
    print(f"Chrome をデバッグモードで起動しています（ポート {cdp_port}）...", file=sys.stderr)
    proc = subprocess.Popen(
        chrome_args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    # ポートが待機するまで待つ
    for _ in range(30):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                s.connect(("127.0.0.1", cdp_port))
            break
        except (socket.error, OSError):
            time.sleep(0.5)
    else:
        proc.kill()
        raise RuntimeError(f"Chrome がポート {cdp_port} で起動しませんでした。")

    time.sleep(1)
    return proc


def _write_tokairokin_transfer_attempt_log(attempt_log: list, script_dir: Path) -> None:
    """
    振込画面遷移の試行結果をテキストログに書き出し、
    東海労金_振込画面遷移_試行履歴.md に「直近実行結果」を追記する。
    """
    if not attempt_log:
        return
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    ts_iso = datetime.now().strftime("%Y-%m-%d %H:%M")

    # 1) 実行ログをテキストで保存
    log_path = script_dir / f"東海労金_振込_実行ログ_{ts}.txt"
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(f"# 東海労金 振込画面遷移 実行ログ {ts_iso}\n\n")
        f.write("| # | 試行内容 | 結果 | 備考 |\n")
        f.write("|---|----------|------|------|\n")
        for i, e in enumerate(attempt_log, 1):
            step = e.get("step", "")
            result = e.get("result", "")
            detail = (e.get("detail") or "").replace("|", "｜").replace("\n", " ")
            f.write(f"| {i} | {step} | {result} | {detail} |\n")
    print(f"実行ログを保存しました: {log_path}", file=sys.stderr)

    # 2) 試行履歴に「直近実行結果」を追記
    history_path = script_dir / "東海労金_振込画面遷移_試行履歴.md"
    if not history_path.exists():
        return
    with open(history_path, "r", encoding="utf-8") as f:
        content = f.read()
    marker = "## 更新履歴"
    if marker not in content:
        return
    table_lines = [
        "",
        "## 直近実行結果",
        "",
        f"**実行日時**: {ts_iso}",
        "",
        "| # | 試行内容 | 結果 | 備考 |",
        "|---|----------|------|------|",
    ]
    for i, e in enumerate(attempt_log, 1):
        step = e.get("step", "")
        result = e.get("result", "")
        detail = (e.get("detail") or "").replace("|", "｜").replace("\n", " ")
        table_lines.append(f"| {i} | {step} | {result} | {detail} |")
    table_lines.extend(["", "---", ""])
    insert_block = "\n".join(table_lines)
    new_content = content.replace(marker, insert_block + "\n" + marker)
    with open(history_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    print(f"試行履歴を更新しました: {history_path}", file=sys.stderr)


def _run_tokairokin_undetected(config: dict, user: str, password: str, headless: bool, transfer: dict = None) -> str:
    """
    undetected-chromedriver（Selenium）で東海労金にログイン。
    自動化検知を回避する代替手段。
    """
    import undetected_chromedriver as uc
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    login_url = config.get("login_url", "https://www.parasol.anser.ne.jp/ib/index.do?PT=BS&CCT0080=2972")
    wait_login = config.get("wait_after_login", 3)
    human_like = config.get("human_like_input", False)
    human_delay = config.get("human_like_input_delay_ms", 80) / 1000.0

    options = uc.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--lang=ja-JP")

    print("undetected-chromedriver で Chrome を起動しています...", file=sys.stderr)
    # version_main: Chromeのメジャーバージョン。不一致エラー時は config の chrome_version_main で指定
    version_main = config.get("chrome_version_main")
    kwargs = {"options": options}
    if version_main is not None:
        kwargs["version_main"] = int(version_main)
    # 他ツールの Chrome パスが優先されるのを防ぐため、標準パスを明示
    chrome_path = config.get("chrome_path")
    if not chrome_path:
        chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        if platform.system() == "Windows":
            chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    if Path(chrome_path).exists():
        kwargs["browser_executable_path"] = chrome_path
    driver = uc.Chrome(**kwargs)
    driver.set_window_size(1280, 900)

    try:
        driver.get(login_url)
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, "#txtBox005")))
        time.sleep(2)

        # ログインID・パスワード入力
        id_el = driver.find_element(By.CSS_SELECTOR, "#txtBox005")
        pass_el = driver.find_element(By.CSS_SELECTOR, "#pswd010")
        id_el.clear()
        pass_el.clear()
        if human_like:
            for c in user:
                id_el.send_keys(c)
                time.sleep(human_delay)
            for c in password:
                pass_el.send_keys(c)
                time.sleep(human_delay)
        else:
            id_el.send_keys(user)
            pass_el.send_keys(password)

        # 送信ボタン
        submit = driver.find_element(By.CSS_SELECTOR, "#btn012")
        submit.click()

        time.sleep(wait_login)

        body_text = driver.find_element(By.TAG_NAME, "body").text
        if "エラー" in body_text or "認証に失敗" in body_text or "ログインに失敗" in body_text or "口座情報が誤っています" in body_text:
            print("ログインに失敗した可能性があります。画面を確認してください。", file=sys.stderr)

        print("東海労金へのログイン処理が完了しました。")

        # 合言葉の自動入力（設定されている場合）
        secret_phrase_filled = False
        secret_phrase_auto = config.get("secret_phrase_auto") or []
        if secret_phrase_auto and ("合言葉" in body_text or "合言葉" in driver.page_source):
            for mapping in secret_phrase_auto:
                match_kw = (mapping.get("match") or "").strip()
                if not match_kw or match_kw not in body_text:
                    continue
                answer = _get_secret_phrase_answer(mapping)
                if not answer:
                    continue
                # 合言葉入力欄を探す（複数セレクタを試行）
                input_selectors = config.get("secret_phrase_input_selectors") or [
                    "input[type='text']:not([readonly])",
                    "input[name*='kotoba'], input[name*='answer'], input[id*='kotoba'], input[id*='answer']",
                    "input.txtBox, input[id^='txtBox']",
                ]
                input_el = None
                for sel in input_selectors:
                    try:
                        els = driver.find_elements(By.CSS_SELECTOR, sel)
                        for el in els:
                            if el.is_displayed() and el.is_enabled():
                                input_el = el
                                break
                        if input_el:
                            break
                    except Exception:
                        continue
                if input_el:
                    input_el.clear()
                    input_el.send_keys(answer)
                    # 送信ボタン（確認・送信・次へ など）
                    for btn_text in ["確認", "送信", "次へ", "認証", "実行", "ログイン", "確認する", "送信する"]:
                        try:
                            btn = driver.find_element(By.XPATH, f"//input[@value='{btn_text}'] | //button[contains(text(),'{btn_text}')] | //a[contains(text(),'{btn_text}')]")
                            if btn.is_displayed():
                                btn.click()
                                secret_phrase_filled = True
                                print(f"合言葉を自動入力しました（キーワード: {match_kw[:20]}...）", file=sys.stderr)
                                time.sleep(3)
                                break
                        except Exception:
                            continue
                if secret_phrase_filled:
                    break
            # 再ログインの案内が出た場合（合言葉入力後）
            if secret_phrase_filled:
                time.sleep(2)
                body_text = driver.find_element(By.TAG_NAME, "body").text
                for relogin_kw in ["再ログイン", "サインイン", "ログイン"]:
                    try:
                        el = driver.find_element(By.XPATH, f"//a[contains(text(),'{relogin_kw}')] | //button[contains(text(),'{relogin_kw}')] | //input[@value='{relogin_kw}']")
                        if el.is_displayed() and relogin_kw in body_text:
                            el.click()
                            print(f"「{relogin_kw}」をクリックしました。", file=sys.stderr)
                            time.sleep(3)
                            break
                    except Exception:
                        continue

        # 再ログイン画面が表示されている場合は必ず「再ログイン」をクリック（合言葉の有無にかかわらず）
        time.sleep(2)
        body_text = driver.find_element(By.TAG_NAME, "body").text
        if "再ログイン" in body_text:
            relogin_clicked = False
            for relogin_kw in ["再ログイン", "サインイン"]:
                try:
                    el = driver.find_element(By.XPATH, f"//a[contains(text(),'{relogin_kw}')] | //button[contains(text(),'{relogin_kw}')] | //input[@value='{relogin_kw}']")
                    if el.is_displayed():
                        el.click()
                        print(f"「{relogin_kw}」ボタンをクリックしました。", file=sys.stderr)
                        time.sleep(3)
                        relogin_clicked = True
                        break
                except Exception:
                    continue
            if not relogin_clicked:
                print("「再ログイン」ボタンが見つかりませんでした。手動でクリックしてください。", file=sys.stderr)

        # 合言葉は自動入力対応済み。自動入力できなかった場合のみここで一時停止（ワンタイムパスワードは手動入力）
        if not secret_phrase_filled and config.get("pause_for_secret_phrase", True):
            print("\n" + "=" * 60, file=sys.stderr)
            print("【一時停止】合言葉は通常は自動入力で対応しています。", file=sys.stderr)
            print("  自動入力が完了したら、このターミナルで Enter キーを押して次へ進んでください。", file=sys.stderr)
            print("  ※ Enter を押しても次に進まない場合は、**Terminal.app** で同じコマンドを実行してください。", file=sys.stderr)
            print("=" * 60 + "\n", file=sys.stderr)
            _wait_enter()

        # 振込画面への遷移（各試行を記録し、試行履歴に反映する）
        go_to_transfer = config.get("go_to_transfer", True)
        transfer_attempt_log = []  # [{ "step": "名前", "result": "success"|"failed"|"skipped", "detail": "..." }, ...]

        if go_to_transfer:
            wait_before = config.get("wait_before_transfer_menu", 5)
            time.sleep(wait_before)

            # オーバーレイを閉じてから待機
            try:
                body = driver.find_element(By.TAG_NAME, "body")
                body.send_keys(Keys.ESCAPE)
                time.sleep(0.8)
                body.send_keys(Keys.ESCAPE)
                time.sleep(0.8)
            except Exception:
                pass

            transfer_clicked = False
            # 振込画面へ直接URLで遷移（クリック不要・確実）
            transfer_direct_url = config.get("transfer_direct_url", "").strip()
            transfer_direct_path = config.get("transfer_direct_path", "").strip()
            if transfer_direct_url and transfer_direct_url.startswith("http"):
                try:
                    driver.get(transfer_direct_url)
                    time.sleep(config.get("wait_after_page", 2) or 3)
                    print("振込画面へ直接URLで遷移しました。", file=sys.stderr)
                    transfer_clicked = True
                    transfer_attempt_log.append({"step": "transfer_direct_url（フルURL直接遷移）", "result": "success", "detail": ""})
                except Exception as e:
                    transfer_attempt_log.append({"step": "transfer_direct_url（フルURL直接遷移）", "result": "failed", "detail": str(e)})
                    print(f"振込画面URLへの遷移に失敗しました: {e}", file=sys.stderr)
            elif transfer_direct_path:
                try:
                    current = driver.current_url
                    # 現在URLの /ib/XXXXDispatch を /ib/{transfer_direct_path} に置換（クエリは維持）
                    if "/ib/" in current:
                        new_url = re.sub(r"(/ib/)[^/?]+", r"\g<1>" + re.escape(transfer_direct_path), current, count=1)
                        if new_url != current:
                            driver.get(new_url)
                            time.sleep(config.get("wait_after_page", 2) or 3)
                            print(f"振込画面へ直接遷移しました（{transfer_direct_path}）。", file=sys.stderr)
                            transfer_clicked = True
                            transfer_attempt_log.append({"step": f"transfer_direct_path（{transfer_direct_path} へパス置換）", "result": "success", "detail": ""})
                        else:
                            transfer_attempt_log.append({"step": f"transfer_direct_path（{transfer_direct_path}）", "result": "failed", "detail": "URLが変化しなかった"})
                    else:
                        transfer_attempt_log.append({"step": f"transfer_direct_path（{transfer_direct_path}）", "result": "failed", "detail": "現在URLに /ib/ が含まれない"})
                except Exception as e:
                    transfer_attempt_log.append({"step": f"transfer_direct_path（{transfer_direct_path}）", "result": "failed", "detail": str(e)})
                    print(f"振込画面への直接遷移に失敗しました: {e}", file=sys.stderr)
            else:
                if transfer_direct_path == "" and not (transfer_direct_url and transfer_direct_url.startswith("http")):
                    transfer_attempt_log.append({"step": "transfer_direct_url / transfer_direct_path", "result": "skipped", "detail": "未設定のためスキップ"})

            transfer_btn_selector = config.get("transfer_menu_button_selector", "").strip()
            wait_timeout = 15
            wait_driver = WebDriverWait(driver, wait_timeout)

            def _click_el(el, msg="振込"):
                """要素をスクロール表示してから JavaScript でクリック（上書き対策）"""
                try:
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                    time.sleep(0.3)
                    driver.execute_script("arguments[0].click();", el)
                    return True
                except Exception:
                    return False

            # 1) セレクタ指定があれば明示待機してクリック（JSクリック）
            if not transfer_clicked and transfer_btn_selector:
                try:
                    el = wait_driver.until(EC.element_to_be_clickable((By.CSS_SELECTOR, transfer_btn_selector)))
                    if _click_el(el, transfer_btn_selector):
                        time.sleep(config.get("wait_after_page", 2) or 3)
                        print(f"振込メニュー（{transfer_btn_selector}）をクリックしました。", file=sys.stderr)
                        transfer_clicked = True
                        transfer_attempt_log.append({"step": f"セレクタクリック（{transfer_btn_selector}）", "result": "success", "detail": ""})
                    else:
                        transfer_attempt_log.append({"step": f"セレクタクリック（{transfer_btn_selector}）", "result": "failed", "detail": "JSクリックが実行できなかった"})
                except Exception as e:
                    transfer_attempt_log.append({"step": f"セレクタクリック（{transfer_btn_selector}）", "result": "failed", "detail": str(e)})
                    print(f"振込ボタン（{transfer_btn_selector}）: {e}", file=sys.stderr)

            # 2) iframe 内で「振込」を探してクリック（口座エリアが iframe のことがある）
            if not transfer_clicked:
                iframe_clicked = False
                for frame in driver.find_elements(By.TAG_NAME, "iframe"):
                    try:
                        driver.switch_to.frame(frame)
                        try:
                            el = wait_driver.until(EC.presence_of_element_located((By.LINK_TEXT, "振込")))
                            if el.is_displayed() and _click_el(el):
                                print("「振込」をクリックしました（iframe内・テキスト検出）。", file=sys.stderr)
                                transfer_clicked = True
                                iframe_clicked = True
                                time.sleep(config.get("wait_after_page", 2) or 3)
                        except Exception:
                            pass
                        driver.switch_to.default_content()
                        if iframe_clicked:
                            break
                    except Exception:
                        try:
                            driver.switch_to.default_content()
                        except Exception:
                            pass
                if iframe_clicked:
                    transfer_attempt_log.append({"step": "iframe内で「振込」リンククリック", "result": "success", "detail": ""})
                else:
                    transfer_attempt_log.append({"step": "iframe内で「振込」リンククリック", "result": "failed", "detail": "全iframeで要素未検出またはクリック不可"})

            # 3) メインコンテンツで「振込」リンク／ボタンを探して JS クリック
            if not transfer_clicked:
                driver.switch_to.default_content()
                main_clicked = False
                for by_method, selector in [
                    (By.LINK_TEXT, "振込"),
                    (By.XPATH, "//a[normalize-space(text())='振込']"),
                    (By.XPATH, "//button[normalize-space(text())='振込']"),
                    (By.XPATH, "//*[normalize-space(text())='振込' and (self::a or self::button)]"),
                ]:
                    try:
                        el = wait_driver.until(EC.presence_of_element_located((by_method, selector)))
                        if el.is_displayed() and _click_el(el):
                            time.sleep(config.get("wait_after_page", 2) or 3)
                            print("「振込」をクリックしました（テキストで検出）。", file=sys.stderr)
                            transfer_clicked = True
                            main_clicked = True
                            break
                    except Exception:
                        continue
                transfer_attempt_log.append({"step": "メインコンテンツで「振込」テキスト検出クリック", "result": "success" if main_clicked else "failed", "detail": "" if main_clicked else "4パターンいずれも未検出またはクリック不可"})

            if not transfer_clicked:
                if config.get("manual_click_transfer_menu", True):
                    transfer_attempt_log.append({"step": "手動クリックの案内（Enter待ち）", "result": "success", "detail": "ユーザーに振込クリックを依頼"})
                    print("\n" + "=" * 60, file=sys.stderr)
                    print("【手動クリック】画面上で「この口座から」の「振込」をクリックしてください。", file=sys.stderr)
                    print("  クリックしたら、ターミナルにフォーカスを移して Enter キーを押してください。", file=sys.stderr)
                    print("=" * 60 + "\n", file=sys.stderr)
                    _wait_enter()
                    time.sleep(3)
                else:
                    # 自動クリック（従来どおり・キーワード検索）
                    transfer_attempt_log.append({"step": "キーワード検索で振込クリック", "result": "pending", "detail": "試行中"})
                    if config.get("pause_before_transfer_click", True):
                        print("\n" + "=" * 60, file=sys.stderr)
                        print("【振込画面へ進む前】「パスワードを保存しますか？」が出ている場合は、", file=sys.stderr)
                        print("  「使用しない」または「保存」で閉じてください。閉じたら Enter キーを押してください。", file=sys.stderr)
                        print("=" * 60 + "\n", file=sys.stderr)
                        _wait_enter()
                    try:
                        body = driver.find_element(By.TAG_NAME, "body")
                        body.send_keys(Keys.ESCAPE)
                        time.sleep(0.5)
                        body.send_keys(Keys.ESCAPE)
                        time.sleep(0.5)
                    except Exception:
                        pass
                    keywords = config.get("transfer_menu_keywords") or [
                        "振込振替・ペイジー", "振込振替", "振込", "振替", "お振込"
                    ]
                    clicked = False
                    for kw in keywords:
                        try:
                            el = driver.find_element(By.XPATH, f"//a[contains(text(),'{kw}')] | //button[contains(text(),'{kw}')] | //input[contains(@value,'{kw}')]")
                            el.click()
                            time.sleep(config.get("wait_after_page", 2))
                            print(f"振込メニュー（「{kw}」）をクリックしました。")
                            clicked = True
                            break
                        except Exception:
                            continue
                    if not clicked:
                        for frame in driver.find_elements(By.TAG_NAME, "iframe"):
                            try:
                                driver.switch_to.frame(frame)
                                for kw in keywords:
                                    try:
                                        el = driver.find_element(By.XPATH, f"//a[contains(text(),'{kw}')] | //button[contains(text(),'{kw}')]")
                                        el.click()
                                        time.sleep(config.get("wait_after_page", 2))
                                        print(f"振込メニュー（「{kw}」）をクリックしました。")
                                        clicked = True
                                        break
                                    except Exception:
                                        continue
                                driver.switch_to.default_content()
                                if clicked:
                                    break
                            except Exception:
                                driver.switch_to.default_content()
                        if not clicked:
                            print("振込メニューへのリンク・ボタンが見つかりませんでした。", file=sys.stderr)
                            print("  → 画面上の「振込」を手動でクリックし、クリック後に Enter を押してください。", file=sys.stderr)
                    # pending のキーワード検索ログを結果で上書き
                    for i, e in enumerate(transfer_attempt_log):
                        if e.get("step") == "キーワード検索で振込クリック" and e.get("result") == "pending":
                            transfer_attempt_log[i] = {"step": "キーワード検索で振込クリック", "result": "success" if clicked else "failed", "detail": "" if clicked else "キーワードに一致する要素なし"}
                            break

            # 振込遷移の試行結果をファイルと試行履歴に出力
            if transfer_attempt_log:
                _write_tokairokin_transfer_attempt_log(transfer_attempt_log, SCRIPT_DIR)

        # 振込フォームの自動入力（transfer パラメータがある場合）
        transfer_filled = False
        has_bank = transfer.get("bank_code") or transfer.get("bank_name")
        has_branch = transfer.get("branch_code") or transfer.get("branch_name")
        if transfer and has_bank and has_branch and transfer.get("account_number") and transfer.get("amount"):
            time.sleep(config.get("wait_after_page", 2))
            tf = config.get("transfer_form") or {}

            # 振込画面で「振込時間の案内」等が消え、振込先入力が使えるまで明示的に待つ
            wait_form_ready = int(config.get("wait_for_transfer_form_ready", 30))
            specify_sel = tf.get("specify_destination_button_selector", "").strip()
            if wait_form_ready > 0 and specify_sel:
                try:
                    wait_driver = WebDriverWait(driver, wait_form_ready)
                    wait_driver.until(EC.element_to_be_clickable((By.CSS_SELECTOR, specify_sel)))
                    print(f"振込入力フォームの準備ができました（最大{wait_form_ready}秒待機）。", file=sys.stderr)
                except Exception as e:
                    print(f"「振込先を指定」が{wait_form_ready}秒以内に表示されませんでした: {e}", file=sys.stderr)
            time.sleep(0.5)

            # 日付振込ボタン（セレクタ指定時のみクリック試行）
            dated_btn_sel = config.get("transfer_dated_transfer_button_selector", "").strip()
            if dated_btn_sel:
                try:
                    by = By.XPATH if (dated_btn_sel.startswith("/") or dated_btn_sel.startswith("(")) else By.CSS_SELECTOR
                    el = driver.find_element(by, dated_btn_sel)
                    if el.is_displayed():
                        el.click()
                        print("「日付振込」をクリックしました。", file=sys.stderr)
                        time.sleep(config.get("wait_after_page", 2))
                except Exception as e:
                    print(f"「日付振込」ボタンのクリックに失敗しました: {e}", file=sys.stderr)

            # 振込先選択画面で「振込先を指定」ボタンをクリック（金融機関選択画面へ遷移）
            specify_clicked = False
            specify_sel = tf.get("specify_destination_button_selector", "").strip()
            if specify_sel:
                try:
                    el = driver.find_element(By.CSS_SELECTOR, specify_sel)
                    if el.is_displayed():
                        el.click()
                        specify_clicked = True
                        print("「振込先を指定」をクリックしました。", file=sys.stderr)
                        time.sleep(config.get("wait_after_page", 2))
                except Exception:
                    pass
            if not specify_clicked:
                for btn_text in ["振込先を指定", "振込先を選択"]:
                    try:
                        el = driver.find_element(By.XPATH, f"//input[@value='{btn_text}'] | //button[contains(text(),'{btn_text}')] | //a[contains(text(),'{btn_text}')]")
                        if el.is_displayed():
                            el.click()
                            specify_clicked = True
                            print(f"「{btn_text}」をクリックしました。", file=sys.stderr)
                            time.sleep(config.get("wait_after_page", 2))
                            break
                    except Exception:
                        continue
            if specify_clicked:
                time.sleep(config.get("wait_after_page", 2))
            # 金融機関・支店の入力: コードを優先（名前指定時のみ名前を使用）
            bank_input = str(transfer.get("bank_code", "")).zfill(4) if transfer.get("bank_code") else (transfer.get("bank_name") or "").strip()
            branch_input = str(transfer.get("branch_code", "")).zfill(3) if transfer.get("branch_code") else (transfer.get("branch_name") or "").strip()
            account_number = str(transfer.get("account_number", "")).zfill(7)
            amount = int(transfer.get("amount", 0))

            def _find_element(sel: str):
                """セレクタがXPath（/ または // で始まる）なら By.XPATH、それ以外は By.CSS_SELECTOR で検索。"""
                sel = (sel or "").strip()
                if not sel:
                    return None
                if sel.startswith("/") or sel.startswith("("):
                    by, val = By.XPATH, sel
                else:
                    if not sel.startswith(("#", ".", "[", "input")):
                        val = f"#{sel}"
                    else:
                        val = sel
                    by, val = By.CSS_SELECTOR, val
                try:
                    return driver.find_element(by, val)
                except Exception:
                    return None

            def _try_fill(selector_key: str, value: str):
                sel = tf.get(selector_key)
                if not sel or not value:
                    return False
                el = _find_element(sel)
                if el and el.is_displayed():
                    try:
                        el.clear()
                        el.send_keys(value)
                        return True
                    except Exception:
                        pass
                return False

            def _click_confirm(selector_key: str, fallback_texts: list):
                """指定セレクタのボタンをクリック。なければ fallback_texts のテキストで検索。"""
                sel = (tf.get(selector_key) or "").strip()
                if sel:
                    el = _find_element(sel)
                    if el and el.is_displayed():
                        el.click()
                        return True
                for btn_text in fallback_texts:
                    try:
                        btn = driver.find_element(By.XPATH, f"//input[@value='{btn_text}'] | //button[contains(text(),'{btn_text}')] | //a[contains(text(),'{btn_text}')]")
                        if btn.is_displayed():
                            btn.click()
                            return True
                    except Exception:
                        continue
                return False

            # 1. 銀行コード入力 → 検索 → 検索結果の「選択」クリック
            if _try_fill("bank_code_selector", bank_input):
                print(f"銀行コードを入力しました（{bank_input}）。", file=sys.stderr)
                time.sleep(0.5)
                if _click_confirm("bank_confirm_button_selector", ["検索", "次へ", "確認"]):
                    print("検索ボタンをクリックしました。", file=sys.stderr)
                    time.sleep(config.get("wait_after_page", 2))
                    if _click_confirm("bank_select_button_selector", ["選択"]):
                        print("検索結果の「選択」をクリックしました。", file=sys.stderr)
                        transfer_filled = True
                        time.sleep(config.get("wait_after_page", 2))
                    else:
                        transfer_filled = True  # 選択ボタンがなければ検索のみで進んだとみなす

            # 2. 支店コード入力 → 検索 → 検索結果の「選択」クリック
            if transfer_filled and _try_fill("branch_code_selector", branch_input):
                print(f"支店コードを入力しました（{branch_input}）。", file=sys.stderr)
                time.sleep(0.5)
                if _click_confirm("branch_confirm_button_selector", ["検索", "次へ", "確認"]):
                    print("検索ボタンをクリックしました。", file=sys.stderr)
                    time.sleep(config.get("wait_after_page", 2))
                    if _click_confirm("branch_select_button_selector", ["選択"]):
                        print("検索結果の「選択」をクリックしました。", file=sys.stderr)
                        time.sleep(config.get("wait_after_page", 2))

            # 3. 口座番号・金額入力 → 確認
            filled = 0
            if _try_fill("account_number_selector", account_number):
                filled += 1
            if _try_fill("amount_selector", str(amount)):
                filled += 1
            if filled >= 2:
                if _click_confirm(None, ["確認", "次へ", "入力する"]):
                    print("振込フォームを入力し、確認ボタンをクリックしました。", file=sys.stderr)
                    transfer_filled = True
                    time.sleep(config.get("wait_after_transfer_confirm", 2))

            # 4. 実行画面へボタンをクリック（確認画面→実行画面）
            if transfer_filled and _click_confirm("execution_screen_button_selector", ["実行画面へ", "実行画面", "次へ"]):
                print("実行画面へボタンをクリックしました。", file=sys.stderr)
                time.sleep(config.get("wait_after_page", 2))

            # 5. 「確認しました」チェックボックスにチェック
            if transfer_filled:
                cb_sel = (tf.get("confirmation_checkbox_selector") or "").strip()
                if cb_sel:
                    el = _find_element(cb_sel)
                    if el and el.is_displayed():
                        try:
                            if not el.is_selected():
                                el.click()
                                print("「確認しました」にチェックを入れました。", file=sys.stderr)
                                time.sleep(0.5)
                        except Exception:
                            pass
                else:
                    # フォールバック: 「確認しました」の横のチェックボックスをXPathで探す
                    try:
                        cb = driver.find_element(By.XPATH, "//label[contains(.,'確認しました')]/preceding-sibling::input[@type='checkbox'] | //label[contains(.,'確認しました')]/following-sibling::input[@type='checkbox'] | //input[@type='checkbox'][preceding::label[contains(.,'確認しました')]] | //input[@type='checkbox'][following::label[contains(.,'確認しました')]]")
                        if cb.is_displayed() and not cb.is_selected():
                            cb.click()
                            print("「確認しました」にチェックを入れました。", file=sys.stderr)
                            time.sleep(0.5)
                    except Exception:
                        pass

        # ワンタイムパスワード（OTP）は手動入力。振込実行前に OTP 入力が必要な場合の待機
        if transfer or transfer_filled:
            print("\n" + "=" * 60, file=sys.stderr)
            print("【一時停止】ワンタイムパスワード（OTP）を入力してください。", file=sys.stderr)
            print("  スマホアプリ等で表示された OTP をブラウザに入力し、振込を実行してください。", file=sys.stderr)
            print("  完了したら、このターミナルで Enter キーを押して次へ進んでください。", file=sys.stderr)
            print("=" * 60 + "\n", file=sys.stderr)
            _wait_enter()

        if config.get("keep_browser_open", True):
            print("\n" + "=" * 60, file=sys.stderr)
            print("振込画面を開いたままにしています。確認や振込をゆっくり行えます。", file=sys.stderr)
            print("", file=sys.stderr)
            print("  ** ブラウザはスクリプトでは閉じません。**", file=sys.stderr)
            print("  作業が終わったら、**ご自身でブラウザを閉じ**てください。", file=sys.stderr)
            print("  ブラウザを閉じたあと、このターミナルで Enter を押すとスクリプトが終了します。", file=sys.stderr)
            print("  （先に Enter を押すとスクリプト終了時にブラウザも閉じる場合があります）", file=sys.stderr)
            print("=" * 60 + "\n", file=sys.stderr)
            _wait_enter(confirm_msg="スクリプトを終了しました。")

        return ""
    except Exception as e:
        # 途中でエラーが出ても Enter 待ちまで進め、ユーザーが操作できる間にブラウザを閉じない
        print(f"エラーが発生しました: {e}", file=sys.stderr)
        if config.get("keep_browser_open", True):
            print("\n振込画面を開いたままにしています。確認や振込を続けてください。", file=sys.stderr)
            print("作業が終わったらご自身でブラウザを閉じ、閉じたあとで Enter を押してください。", file=sys.stderr)
            _wait_enter(confirm_msg="スクリプトを終了しました。")
        return ""
    finally:
        # keep_browser_open 時はブラウザを閉じない（ユーザーが手動で閉じる）
        if not config.get("keep_browser_open", True):
            driver.quit()


def run_tokairokin(headless: bool = False, transfer: dict = None) -> str:
    """東海労金インターネットバンキングにログインする。振込パラメータがあればフォーム入力まで自動化。"""
    config = load_config("tokairokin")
    user, password = get_credentials("tokairokin")
    transfer = transfer or config.get("transfer")

    # undetected-chromedriver を優先（CDP・stealth で検知された場合の代替）
    if config.get("use_undetected_chromedriver", False):
        return _run_tokairokin_undetected(config, user, password, headless or config.get("headless", False), transfer)

    from playwright.sync_api import sync_playwright
    from playwright_stealth import Stealth

    login_url = config.get("login_url", "https://www.parasol.anser.ne.jp/ib/index.do?PT=BS&CCT0080=2972")
    wait_login = config.get("wait_after_login", 3)
    headless = config.get("headless", headless)
    use_connect_cdp = config.get("use_connect_cdp", False)
    cdp_url = config.get("cdp_url", "http://localhost:9222")
    human_like = config.get("human_like_input", False)
    human_delay = config.get("human_like_input_delay_ms", 80)

    use_chrome = config.get("use_chrome", True)
    use_stealth = config.get("use_stealth", True)
    launch_args = ["--disable-blink-features=AutomationControlled"]

    chrome_proc = None
    if use_connect_cdp and config.get("auto_start_chrome", True):
        # 既存のChromeを終了し、デバッグポート付きで起動
        from urllib.parse import urlparse
        parsed = urlparse(cdp_url)
        cdp_port = parsed.port or 9222
        chrome_proc = _ensure_chrome_for_cdp(cdp_port=cdp_port)
        cdp_url = f"http://127.0.0.1:{cdp_port}"

    with sync_playwright() as p:
        if use_connect_cdp:
            # 手動起動したChromeに接続（自動化検知を最も回避しやすい）
            print(f"CDP接続モード: {cdp_url} に接続します...")
            browser = p.chromium.connect_over_cdp(cdp_url)
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.new_page()
        else:
            if use_chrome:
                try:
                    browser = p.chromium.launch(
                        channel="chrome",
                        headless=headless,
                        args=launch_args,
                    )
                except Exception:
                    browser = p.chromium.launch(headless=headless, args=launch_args)
            else:
                browser = p.chromium.launch(headless=headless, args=launch_args)

            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                locale="ja-JP",
            )
            if use_stealth:
                stealth = Stealth(
                    navigator_languages_override=("ja-JP", "ja"),
                    navigator_platform_override="MacIntel",
                )
                stealth.apply_stealth_sync(context)
            page = context.new_page()

        try:
            page.goto(login_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_load_state("networkidle", timeout=20000)
            page.wait_for_timeout(2000)

            # Chromeの「パスワードを保存しますか？」を出にくくするため、ログイン入力に autocomplete=off を付与
            try:
                page.evaluate("""() => {
                    document.querySelectorAll('#txtBox005, #pswd010, input[type="password"]').forEach(el => {
                        el.setAttribute('autocomplete', 'off');
                    });
                }""")
            except Exception:
                pass

            # parasol.anser.ne.jp のログインフォーム（東海労金）
            # ログインID: input#txtBox005 / パスワード: input#pswd010 のみ入力
            # 支店番号・口座番号は入力しない
            if human_like:
                _fill_human_like(page, "#txtBox005", user, human_delay)
                _fill_human_like(page, "#pswd010", password, human_delay)
            else:
                page.locator("#txtBox005").fill(user)
                page.locator("#pswd010").fill(password)

            # 送信ボタン（parasol: #btn012）
            submit = page.locator("#btn012, button:has-text('ログイン'), input[type='submit'][value*='ログイン']").first
            submit.click()

            page.wait_for_timeout(wait_login * 1000)

            current_url = page.url
            body_text = page.locator("body").inner_text()
            if "エラー" in body_text or "認証に失敗" in body_text or "ログインに失敗" in body_text or "口座情報が誤っています" in body_text:
                print("ログインに失敗した可能性があります。headless=false で実行して画面を確認してください。", file=sys.stderr)

            print("東海労金へのログイン処理が完了しました。")

            # 合言葉の自動入力（設定されている場合）
            secret_phrase_filled = False
            secret_phrase_auto = config.get("secret_phrase_auto") or []
            body_text = page.locator("body").inner_text()
            if secret_phrase_auto and ("合言葉" in body_text or "合言葉" in page.content()):
                for mapping in secret_phrase_auto:
                    match_kw = (mapping.get("match") or "").strip()
                    if not match_kw or match_kw not in body_text:
                        continue
                    answer = _get_secret_phrase_answer(mapping)
                    if not answer:
                        continue
                    input_selectors = config.get("secret_phrase_input_selectors") or [
                        "input[type='text']:not([readonly])",
                        "input[name*='kotoba'], input[name*='answer']",
                        "input.txtBox, input[id^='txtBox']",
                    ]
                    input_loc = None
                    for sel in input_selectors:
                        try:
                            loc = page.locator(sel).first
                            loc.wait_for(state="visible", timeout=1000)
                            input_loc = loc
                            break
                        except Exception:
                            continue
                    if input_loc:
                        input_loc.fill("")
                        input_loc.fill(answer)
                        for btn_text in ["確認", "送信", "次へ", "認証", "実行", "ログイン", "確認する", "送信する"]:
                            try:
                                btn = page.locator(f"input[value='{btn_text}'], button:has-text('{btn_text}'), a:has-text('{btn_text}')").first
                                if btn.is_visible():
                                    btn.click()
                                    secret_phrase_filled = True
                                    print(f"合言葉を自動入力しました（キーワード: {match_kw[:20]}...）", file=sys.stderr)
                                    page.wait_for_timeout(3000)
                                    break
                            except Exception:
                                continue
                    if secret_phrase_filled:
                        break
            if secret_phrase_filled:
                page.wait_for_timeout(2000)
                body_text = page.locator("body").inner_text()
                for relogin_kw in ["再ログイン", "サインイン", "ログイン"]:
                    try:
                        el = page.locator(f"a:has-text('{relogin_kw}'), button:has-text('{relogin_kw}'), input[value='{relogin_kw}']").first
                        if el.is_visible() and relogin_kw in body_text:
                            el.click()
                            print(f"「{relogin_kw}」をクリックしました。", file=sys.stderr)
                            page.wait_for_timeout(3000)
                            break
                    except Exception:
                        continue

            # 再ログイン画面が表示されている場合は必ず「再ログイン」をクリック（合言葉の有無にかかわらず）
            page.wait_for_timeout(2000)
            body_text = page.locator("body").inner_text()
            if "再ログイン" in body_text:
                relogin_clicked = False
                for relogin_kw in ["再ログイン", "サインイン"]:
                    try:
                        el = page.locator(f"a:has-text('{relogin_kw}'), button:has-text('{relogin_kw}'), input[value='{relogin_kw}']").first
                        if el.is_visible():
                            el.click()
                            print(f"「{relogin_kw}」ボタンをクリックしました。", file=sys.stderr)
                            page.wait_for_timeout(3000)
                            relogin_clicked = True
                            break
                    except Exception:
                        continue
                if not relogin_clicked:
                    print("「再ログイン」ボタンが見つかりませんでした。手動でクリックしてください。", file=sys.stderr)

            # 合言葉は自動入力対応済み。自動入力できなかった場合のみここで一時停止（ワンタイムパスワードは手動入力）
            if not secret_phrase_filled and config.get("pause_for_secret_phrase", True):
                print("\n" + "=" * 60, file=sys.stderr)
                print("【一時停止】合言葉は通常は自動入力で対応しています。", file=sys.stderr)
                print("  自動入力が完了したら、このターミナルで Enter キーを押して次へ進んでください。", file=sys.stderr)
                print("=" * 60 + "\n", file=sys.stderr)
                _wait_enter()

            # 振込画面への遷移（設定で有効な場合）
            go_to_transfer = config.get("go_to_transfer", True)
            if go_to_transfer:
                wait_before = config.get("wait_before_transfer_menu", 5)
                page.wait_for_timeout(int(wait_before * 1000))

                # 手動クリックモード: こちらで「振込」をクリックしてもらい、クリック後に Enter で次の処理を自動実行
                manual_click = config.get("manual_click_transfer_menu", True)
                if manual_click:
                    print("\n" + "=" * 60, file=sys.stderr)
                    print("【手動クリック】画面上で「振込」または「振込振替 ペイジー」をクリックしてください。", file=sys.stderr)
                    print("  クリックしたら、ターミナルにフォーカスを移して Enter キーを押してください。", file=sys.stderr)
                    print("  ※ Enter が反応しない場合は、Terminal.app で同じコマンドを実行してください。", file=sys.stderr)
                    print("=" * 60 + "\n", file=sys.stderr)
                    _wait_enter()
                    page.wait_for_timeout(3000)  # 画面遷移の待機
                else:
                    # 自動クリック（従来どおり）
                    if config.get("pause_before_transfer_click", True):
                        print("\n" + "=" * 60, file=sys.stderr)
                        print("【振込画面へ進む前】「パスワードを保存しますか？」が出ている場合は、", file=sys.stderr)
                        print("  「使用しない」または「保存」で閉じてください。閉じたら Enter キーを押してください。", file=sys.stderr)
                        print("=" * 60 + "\n", file=sys.stderr)
                        _wait_enter()
                    try:
                        page.keyboard.press("Escape")
                        page.wait_for_timeout(500)
                        page.keyboard.press("Escape")
                        page.wait_for_timeout(500)
                    except Exception:
                        pass
                    wait_page = config.get("wait_after_page", 2)
                    keywords = config.get("transfer_menu_keywords") or [
                        "振込振替・ペイジー", "振込振替", "振込", "振替", "お振込"
                    ]
                    clicked = False
                    frames_to_check = list(page.frames) if page.frames else [page]
                    for frame in frames_to_check:
                        if clicked:
                            break
                        for kw in keywords:
                            try:
                                loc = frame.locator(
                                    f"a:has-text('{kw}'), button:has-text('{kw}'), input[value*='{kw}']"
                                ).first
                                loc.click(timeout=3000)
                                page.wait_for_timeout(int(wait_page * 1000))
                                print(f"振込メニュー（「{kw}」）をクリックし、振込画面へ遷移しました。")
                                clicked = True
                                break
                            except Exception:
                                continue
                    if not clicked:
                        print("振込メニューへのリンク・ボタンが見つかりませんでした。", file=sys.stderr)
                        print("  → 画面上の「振込」を手動でクリックし、クリック後に Enter を押してください。", file=sys.stderr)
            else:
                print("※ 振込画面への遷移はスキップしました（go_to_transfer: false）")

            # ブラウザを開いたままにする（パスワード変更画面などの対応を可能に）
            if config.get("keep_browser_open", True):
                print("\nブラウザを開いたままにしています。処理が終わったら Enter キーを押してください。")
                _wait_enter(confirm_msg="")

            return ""

        except Exception as e:
            print(f"エラー: {e}", file=sys.stderr)
            print("headless=false で実行し、ログインフォームの構造を確認してください。", file=sys.stderr)
            raise
        finally:
            browser.close()


def main():
    parser = argparse.ArgumentParser(description="ログイン後にページ内容を取得して保存")
    parser.add_argument("site", choices=["nichinoken", "tokairokin"], help="サイト名")
    parser.add_argument("--headless", action="store_true", help="ブラウザを表示しない")
    parser.add_argument("--bank", help="振込先銀行コード（4桁、例: 0005）")
    parser.add_argument("--branch", help="振込先支店コード（3桁、例: 405）")
    parser.add_argument("--bank-name", dest="bank_name", help="金融機関名で入力する場合（例: 三菱UFJ銀行）")
    parser.add_argument("--branch-name", dest="branch_name", help="支店名で入力する場合（例: 熱田支店）")
    parser.add_argument("--account", help="振込先口座番号（7桁）")
    parser.add_argument("--amount", type=int, help="振込金額（円）")
    args = parser.parse_args()

    if args.site == "nichinoken":
        path = run_nichinoken(headless=args.headless)
        print(f"出力: {path}")
    elif args.site == "tokairokin":
        transfer = None
        if args.bank or args.branch or args.bank_name or args.branch_name or args.account or args.amount:
            transfer = {
                "bank_code": args.bank or "",
                "branch_code": args.branch or "",
                "bank_name": args.bank_name or "",
                "branch_name": args.branch_name or "",
                "account_number": args.account or "",
                "amount": args.amount or 0,
            }
        run_tokairokin(headless=args.headless, transfer=transfer)
    else:
        print(f"未対応のサイト: {args.site}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
