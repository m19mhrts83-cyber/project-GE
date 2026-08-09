#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WeStudy lesson ページの説明テキストを収集するスクレイパー。

コース一覧ページからタブ（神大家0〜4）→ セクション（目次）→ lesson の階層を
辿り、各 lesson ページの説明テキスト（動画下の本文）を管理者CSV互換で出力する。

フォーラム用の westudy_forum_all.py とは対象が異なる:
  - westudy_forum_all.py: /forum/ のコミュニティコメント（日々追加）
  - 本スクリプト: /lesson/ の説明テキスト（低〜中頻度で更新）

実行例:
  python3 westudy_lesson_pages.py
  python3 westudy_lesson_pages.py --show          # ブラウザ表示
  python3 westudy_lesson_pages.py --output-root /tmp/lesson_out
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.by import By
from selenium.common.exceptions import (
    TimeoutException,
    WebDriverException,
    NoSuchElementException,
)
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

_SCRIPT_DIR = Path(__file__).resolve().parent

_DEFAULT_LOGIN_URL = "https://westudy.co.jp/login"

COURSE_TABS = [
    {
        "label": "神大家0.はじめに",
        "url": "https://westudy.co.jp/course/kami-ooyasan-club-start",
    },
    {
        "label": "神大家1.基礎",
        "url": "https://westudy.co.jp/course/kami-ooyasan-club",
    },
    {
        "label": "神大家2.応用",
        "url": "https://westudy.co.jp/course/level-up",
    },
    {
        "label": "神大家3.継承",
        "url": "https://westudy.co.jp/course/keisho",
    },
    {
        "label": "神大家4.グルコン",
        "url": "https://westudy.co.jp/course/group-consulting",
    },
]

LESSON_FIELDNAMES = [
    "コメントID",
    "投稿日時",
    "投稿者名",
    "投稿者メール",
    "コメント内容",
    "親コメントID",
    "IP アドレス",
    "ユーザーエージェント",
    "ソース",
    "ソース系統",
    "ソース種別",
    "分類",
    "板タイトル",
    "コースタブ",
    "目次セクション",
    "レッスンタイトル",
    "レッスンURL",
    "コンテンツハッシュ",
]

driver = None
RUN_ID: str | None = None
OUTPUT_ROOT: Path | None = None


def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def get_env_or_raise(key: str) -> str:
    v = (os.environ.get(key) or "").strip()
    if not v:
        raise RuntimeError(f"環境変数 {key} が未設定です")
    return v


def create_driver(headless: bool = True) -> webdriver.Chrome:
    opts = ChromeOptions()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1280,1024")
    opts.add_argument("--lang=ja")
    opts.add_argument("--disable-background-networking")
    opts.add_argument("--disable-renderer-backgrounding")
    # 全リソース待機で renderer timeout になりやすいため DOM 完了で打ち切る
    opts.page_load_strategy = "eager"
    d = webdriver.Chrome(options=opts)
    d.set_page_load_timeout(60)
    d.implicitly_wait(5)
    return d


_HEADLESS = True


def _safe_get(url: str, *, retries: int = 3) -> None:
    """page load / renderer timeout 時は部分ロード許容＋ドライバ再生成で再試行。"""
    global driver
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            driver.get(url)
            return
        except TimeoutException as e:
            last_err = e
            ready = ""
            try:
                ready = str(driver.execute_script("return document.readyState") or "")
            except Exception:
                ready = ""
            log(f"page load timeout ({attempt}/{retries}) readyState={ready or 'n/a'} url={url}")
            if ready in ("interactive", "complete"):
                try:
                    driver.execute_script("window.stop();")
                except Exception:
                    pass
                return
            if attempt >= retries:
                break
            try:
                driver.quit()
            except Exception:
                pass
            driver = create_driver(headless=_HEADLESS)
            time.sleep(1.5)
        except WebDriverException as e:
            last_err = e
            log(f"navigation error ({attempt}/{retries}): {e.__class__.__name__}")
            if attempt >= retries:
                break
            try:
                driver.quit()
            except Exception:
                pass
            driver = create_driver(headless=_HEADLESS)
            time.sleep(1.5)
    if last_err is not None:
        raise last_err


def login_westudy() -> None:
    global driver
    user = get_env_or_raise("WESTUDY_USER")
    pw = get_env_or_raise("WESTUDY_PASS")
    login_url = (os.environ.get("WESTUDY_LOGIN_URL") or "").strip() or _DEFAULT_LOGIN_URL

    log(f"ログイン: {login_url}")
    _safe_get(login_url)

    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.ID, "user_login"))
        )
    except TimeoutException:
        log("ログインフォーム未検出（既存セッションの可能性）。続行します。")
        return

    el_user = driver.find_element(By.ID, "user_login")
    el_user.clear()
    el_user.send_keys(user)
    driver.find_element(By.ID, "user_pass").clear()
    driver.find_element(By.ID, "user_pass").send_keys(pw)

    try:
        remember = driver.find_element(By.ID, "rememberme")
        if remember.is_displayed() and not remember.is_selected():
            remember.click()
    except NoSuchElementException:
        pass

    driver.find_element(By.ID, "wp-submit").click()
    time.sleep(3)
    log("ログイン完了")


def safe_js(script: str, default=None):
    """JS実行（例外時は default を返す）"""
    global driver
    try:
        return driver.execute_script(script)
    except Exception:
        return default


def collect_sections_and_lessons(tab: dict) -> list[dict]:
    """
    コースタブページから セクション → lesson の一覧を取得。
    返り値: [{"section": str, "title": str, "url": str}, ...]
    """
    global driver
    tab_url = tab["url"]
    tab_label = tab["label"]
    log(f"タブ取得: {tab_label} → {tab_url}")
    driver.get(tab_url)
    time.sleep(3)

    result = safe_js(r"""
        const items = [];
        // WeStudy はセクション単位で .section-wrap > .section-header + .section-items
        const sections = document.querySelectorAll(
            '.curriculum-section, .section-wrap, [class*="section"]'
        );
        if (sections.length > 0) {
            sections.forEach(sec => {
                const headerEl = sec.querySelector(
                    '.section-header, .section-title, h3, h4, [class*="section-header"]'
                );
                const sectionName = headerEl ? headerEl.textContent.trim() : '';
                const links = sec.querySelectorAll(
                    'a[href*="/lesson/"]'
                );
                links.forEach(a => {
                    items.push({
                        section: sectionName,
                        title: a.textContent.trim(),
                        url: a.href,
                    });
                });
            });
        }
        // フォールバック: セクション構造がない場合、全 lesson リンクを拾う
        if (items.length === 0) {
            document.querySelectorAll('a[href*="/lesson/"]').forEach(a => {
                items.push({
                    section: '',
                    title: a.textContent.trim(),
                    url: a.href,
                });
            });
        }
        return items;
    """, [])

    if not result:
        log(f"  レッスンリンクなし: {tab_label}")
        return []

    seen_urls = set()
    deduped = []
    for item in result:
        url = (item.get("url") or "").strip().rstrip("/")
        if url and url not in seen_urls:
            seen_urls.add(url)
            item["url"] = url
            deduped.append(item)

    log(f"  {tab_label}: {len(deduped)} レッスン検出")
    return deduped


def strip_mokuji_prefix(text: str) -> str:
    """本文先頭の「目次 [非表示]…」を除去（コース目次の混入対策）。"""
    t = (text or "").strip()
    if not t.startswith("目次"):
        return t
    lines = t.split("\n")
    # 先頭行（または連続する目次行）を落とす
    i = 0
    while i < len(lines) and (
        lines[i].strip().startswith("目次")
        or (i == 0 and "目次" in lines[i][:20] and "[非表示]" in lines[i])
    ):
        i += 1
    return "\n".join(lines[i:]).strip() or t


def extract_lesson_description(lesson_url: str) -> str:
    """lesson ページにアクセスし、動画下の説明テキストを取得。"""
    global driver
    driver.get(lesson_url)
    time.sleep(2)

    desc = safe_js(r"""
        // 目次・ナビを除外して説明本文だけ取る
        const stripMokuji = (el) => {
            if (!el) return '';
            const clone = el.cloneNode(true);
            clone.querySelectorAll(
                '.lesson-sidebar, .course-navigation, .ld-topic-list, .ld-lesson-list,' +
                '[class*="curriculum"], [class*="toc"], [class*="mokuji"], nav, aside'
            ).forEach(n => n.remove());
            let t = (clone.textContent || '').trim();
            if (t.startsWith('目次')) {
                const nl = t.indexOf('\n');
                if (nl > 0) t = t.slice(nl + 1).trim();
            }
            return t;
        };
        const selectors = [
            '.content-body',
            '.lesson-content',
            '.lesson-description',
            '.entry-content',
            '.lesson-text',
            '[class*="lesson-desc"]',
            '[class*="lesson-content"]',
            '.wpProQuiz_content',
            'article .content',
        ];
        for (const sel of selectors) {
            const el = document.querySelector(sel);
            const t = stripMokuji(el);
            if (t.length > 10) return t;
        }
        // フォールバック: 動画の下のテキスト要素
        const video = document.querySelector('video, iframe[src*="youtube"], iframe[src*="vimeo"], .video-container, .presto-player');
        if (video) {
            let sibling = video.parentElement;
            while (sibling) {
                sibling = sibling.nextElementSibling;
                if (sibling) {
                    const t = stripMokuji(sibling);
                    if (t.length > 20) return t;
                }
            }
        }
        // 最終フォールバック: ページ本文からヘッダー/ナビを除く
        const main = document.querySelector('main, #main, .site-content, article');
        return stripMokuji(main);
    """, "")

    return strip_mokuji_prefix((desc or "").strip())


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def slug_from_url(url: str) -> str:
    """URL から lesson slug を抽出: https://westudy.co.jp/lesson/xxx → xxx"""
    m = re.search(r"/lesson/([^/?#]+)", url)
    return m.group(1) if m else url.split("/")[-1]


def run_scrape(headless: bool = True) -> list[dict]:
    """全タブ → 全セクション → 全 lesson を巡回し、説明テキストを収集。"""
    global driver, _HEADLESS
    _HEADLESS = headless
    driver = create_driver(headless=headless)

    try:
        login_westudy()

        all_rows: list[dict] = []
        now_iso = datetime.now(timezone.utc).isoformat()

        for tab in COURSE_TABS:
            lessons = collect_sections_and_lessons(tab)
            for i, lesson in enumerate(lessons):
                lesson_url = lesson["url"]
                slug = slug_from_url(lesson_url)
                log(f"  [{i+1}/{len(lessons)}] {slug}")

                try:
                    desc = extract_lesson_description(lesson_url)
                except Exception as e:
                    log(f"    ⚠️ 取得失敗: {e}")
                    desc = ""

                if not desc or len(desc) < 5:
                    log(f"    スキップ（テキストなし）")
                    continue

                chash = content_hash(desc)
                comment_id = f"lesson_desc_{slug}"

                row = {
                    "コメントID": comment_id,
                    "投稿日時": now_iso,
                    "投稿者名": "WeStudy",
                    "投稿者メール": "",
                    "コメント内容": desc,
                    "親コメントID": "",
                    "IP アドレス": "",
                    "ユーザーエージェント": "",
                    "ソース": "WeStudy",
                    "ソース系統": "lesson",
                    "ソース種別": "lesson_desc",
                    "分類": tab["label"],
                    "板タイトル": lesson.get("title", slug),
                    "コースタブ": tab["label"],
                    "目次セクション": lesson.get("section", ""),
                    "レッスンタイトル": lesson.get("title", slug),
                    "レッスンURL": lesson_url,
                    "コンテンツハッシュ": chash,
                }
                all_rows.append(row)
                log(f"    ✅ {len(desc)} 文字")

        log(f"合計: {len(all_rows)} レッスン説明テキスト取得")
        return all_rows

    finally:
        try:
            driver.quit()
        except Exception:
            pass
        driver = None


def write_csv(rows: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=LESSON_FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    log(f"CSV出力: {output_path} ({len(rows)} 行)")


def main():
    parser = argparse.ArgumentParser(description="WeStudy lesson 説明テキスト収集")
    parser.add_argument("--show", action="store_true", help="ブラウザ表示モード")
    parser.add_argument("--output-root", type=str, default=None,
                        help="出力先ルート（既定: ProgramCode/outputs/westudy_lessons/）")
    parser.add_argument("--dry-run", action="store_true", help="取得のみ（CSV出力しない）")
    args = parser.parse_args()

    global RUN_ID, OUTPUT_ROOT
    RUN_ID = datetime.now().strftime("%Y%m%d-%H%M%S")

    if args.output_root:
        OUTPUT_ROOT = Path(args.output_root).expanduser().resolve()
    else:
        env_out = os.environ.get("WESTUDY_LESSON_OUTPUT_ROOT", "").strip()
        if env_out:
            OUTPUT_ROOT = Path(env_out).expanduser().resolve()
        else:
            OUTPUT_ROOT = _SCRIPT_DIR.parent / "outputs" / "westudy_lessons"

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    rows = run_scrape(headless=not args.show)

    if args.dry_run:
        log(f"dry-run: {len(rows)} 件取得（CSV未出力）")
        for r in rows[:5]:
            log(f"  {r['コメントID']}: {r['レッスンタイトル'][:60]}")
        return

    csv_path = OUTPUT_ROOT / f"lesson_full_{RUN_ID}.csv"
    write_csv(rows, csv_path)

    manifest_path = OUTPUT_ROOT / "lesson_manifest.json"
    manifest = {
        "run_id": RUN_ID,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_lessons": len(rows),
        "csv": str(csv_path),
        "tabs": {tab["label"]: sum(1 for r in rows if r["コースタブ"] == tab["label"])
                 for tab in COURSE_TABS},
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"マニフェスト: {manifest_path}")


if __name__ == "__main__":
    main()
