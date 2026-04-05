#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
WeStudy フォーラム収集スクリプト（完全版）
- ログイン: 方式②（環境変数 WESTUDY_USER / WESTUDY_PASS を利用）
- デフォルト: ヘッドレス（--show で表示、HEADLESS=0 でオフ）
- 取得単位: トピックごとに CSV を分割出力（Notion 取り込み想定）
- 冪等: 既に出力済みのトピックはスキップ（--force で再取得）
- 安定化: 安全な JS 実行 safe_js(), セッション切断時の自動再起動と復旧
- 可視化: ハートビート JSON とログ、ウォッチドッグで停滞検知＆スクショ

実行例（スリープ防止 & ヘッドレス）:
  caffeinate -dimsu python3 ~/git-repos/ProgramCode/alfred_python/westudy_forum_all.py

画面表示したい時:
  caffeinate -dimsu python3 .../westudy_forum_all.py --show

出力先:
  既定はこのファイルから見た ProgramCode/outputs/westudy/<RUN_ID>/ 。
  WESTUDY_OUTPUT_ROOT で1本のディレクトリを直接指定、または --output-root で上書き。
  WESTUDY_STATE_DIR で完了フラグ・done_topics.json の場所（既定: ProgramCode/outputs/westudy_state）。
"""

from __future__ import annotations

import os
import re
import csv
import sys
import json
import time
import queue
import random
import string
import signal
import shutil
import argparse
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from threading import Thread, Event, Lock

from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import (
    TimeoutException,
    WebDriverException,
    JavascriptException,
    NoSuchElementException,
    StaleElementReferenceException,
    InvalidSessionIdException,
)
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# -------------------------
# 定数・グローバル
# -------------------------
# 既定は会員向け /login（フォームは wp-login.php と同一の user_login / user_pass）。上書き: WESTUDY_LOGIN_URL
_DEFAULT_MEMBER_LOGIN_URL = "https://westudy.co.jp/login"


# 会員サイトでは /forum/ トップが404のことがあり、コース内のフォーラムタブが一覧になる
_DEFAULT_FORUM_ENTRY_URL = "https://westudy.co.jp/course/kami-ooyasan-club?t=forums"
_DEFAULT_TOPIC_HREF_PREFIX = "https://westudy.co.jp/forum/"


def forum_base_url() -> str:
    """フォーラム一覧ページのURL（完全な文字列）。上書き: WESTUDY_FORUM_URL"""
    u = (os.environ.get("WESTUDY_FORUM_URL") or "").strip()
    if u:
        return u
    return _DEFAULT_FORUM_ENTRY_URL


def forum_topic_href_prefix() -> str:
    """トピック詳細への a[href^=…] 用プレフィックス（末尾スラッシュ付き）。上書き: WESTUDY_TOPIC_HREF_PREFIX"""
    u = (os.environ.get("WESTUDY_TOPIC_HREF_PREFIX") or "").strip().rstrip("/")
    if u:
        return u + "/"
    return _DEFAULT_TOPIC_HREF_PREFIX


def wait_for_forum_ready(reason: str = "") -> None:
    """ログイン後など、フォーラム相当のページに到達したことを a[href*='forum'] で判定（厳密な CSS より寛容）。"""
    global driver
    deadline = time.time() + float(PAGELOAD_TIMEOUT)
    note = f" ({reason})" if reason else ""
    last_log = 0.0
    while time.time() < deadline:
        now = time.time()
        try:
            cur = driver.current_url or ""
            is404 = driver.execute_script(
                "return !!(document.body && document.body.classList.contains('error404'));"
            )
            n = int(
                driver.execute_script(
                    r"""
                    return document.querySelectorAll(
                        'a[href*="forum"], .section-item-title a[href]'
                    ).length;
                    """
                )
                or 0
            )
        except Exception:
            cur, is404, n = "", False, 0
        if n >= 1:
            return
        if now - last_log >= 30:
            extra = " error404" if (is404 and "forum" in cur.lower()) else ""
            log(f"… フォーラム到達待機{note} n={n}{extra} URL={cur[:120]}")
            last_log = now
        time.sleep(1.0)
    cur = driver.current_url or ""
    if OUTPUT_ROOT:
        try:
            driver.save_screenshot(str(OUTPUT_ROOT / "forum_ready_timeout.png"))
            log(f"📸 スクリーンショット: {OUTPUT_ROOT / 'forum_ready_timeout.png'}")
        except Exception as e:
            log(f"⚠️ スクリーンショット保存失敗: {e}")
    raise TimeoutException(f"フォーラム到達待機タイムアウト{note} URL={cur}")

# このスクリプトの場所（ProgramCode/alfred_python）
_SCRIPT_FILE = Path(__file__).resolve()
_SCRIPT_DIR = _SCRIPT_FILE.parent
_DEFAULT_CODE_BASE = _SCRIPT_FILE.parents[1]  # ProgramCode

RUN_ID: str | None = None
OUTPUT_ROOT: Path | None = None
LOG_PATH: Path | None = None
HEARTBEAT_PATH: Path | None = None
STATE_DIR: Path | None = None
DONE_TOPICS_PATH: Path | None = None


def configure_paths(output_root: str | Path | None = None, state_dir: str | Path | None = None, run_id: str | None = None):
    """
    実行開始時に1回呼ぶ。OUTPUT_ROOT / STATE_DIR / ログパスを確定する。
    - output_root 未指定: WESTUDY_OUTPUT_ROOT があればそれをそのまま使用、なければ
      ProgramCode/outputs/westudy/<RUN_ID>/
    - state_dir 未指定: WESTUDY_STATE_DIR があればそれ、なければ ProgramCode/outputs/westudy_state
    """
    global RUN_ID, OUTPUT_ROOT, LOG_PATH, HEARTBEAT_PATH, STATE_DIR, DONE_TOPICS_PATH
    rid = run_id or datetime.now().strftime("%Y%m%d-%H%M%S")
    RUN_ID = rid
    base = _DEFAULT_CODE_BASE

    if output_root is not None:
        OUTPUT_ROOT = Path(output_root).expanduser().resolve()
    else:
        env_out = os.environ.get("WESTUDY_OUTPUT_ROOT")
        if env_out:
            OUTPUT_ROOT = Path(env_out).expanduser().resolve()
        else:
            OUTPUT_ROOT = base / "outputs" / "westudy" / rid

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    LOG_PATH = OUTPUT_ROOT / "westudy_run.log"
    HEARTBEAT_PATH = OUTPUT_ROOT / "westudy_heartbeat.json"

    if state_dir is not None:
        STATE_DIR = Path(state_dir).expanduser().resolve()
    else:
        env_st = os.environ.get("WESTUDY_STATE_DIR")
        STATE_DIR = Path(env_st).expanduser().resolve() if env_st else base / "outputs" / "westudy_state"
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    DONE_TOPICS_PATH = STATE_DIR / "done_topics.json"

# ウォッチドッグ設定
WATCHDOG_INTERVAL_SEC = 30
WATCHDOG_STALL_SEC = 180  # この秒数以上ハートビートが更新されないと停滞とみなす

# Selenium 共通
PAGELOAD_TIMEOUT = 120
SCRIPT_TIMEOUT = 60
IMPLICIT_WAIT = 0

# 共有オブジェクト
driver = None
wait: WebDriverWait = None
driver_lock = Lock()

# CLI 引数をグローバルで参照
_CLI_ARGS = None


# -------------------------
# ユーティリティ
# -------------------------
def log(msg: str):
    msg2 = f"{datetime.now().strftime('%H:%M:%S')} | {msg}"
    print(msg2, flush=True)
    if not LOG_PATH:
        return
    try:
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(msg2 + "\n")
    except Exception:
        pass


def write_json(path: Path, data: dict):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp.replace(path)
    except Exception as e:
        log(f"⚠️ JSON書き込み失敗 {path.name}: {e}")


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log(f"⚠️ JSON読み込み失敗 {path.name}: {e}")
        return default


def sanitize_filename(name: str, extra: str = "") -> str:
    base = re.sub(r"[\\/:*?\"<>|]", "_", name).strip()
    base = re.sub(r"\s+", " ", base)
    if extra:
        base = f"{base}__{extra}"
    # 長過ぎると扱いにくいので短縮
    return (base[:90]).rstrip("_ ")


def topic_output_paths(title: str, url: str):
    slug = url.rstrip("/").split("/")[-1]
    safe = sanitize_filename(title, slug)
    folder = OUTPUT_ROOT / safe
    folder.mkdir(parents=True, exist_ok=True)
    csv_path = folder / f"{safe}.csv"
    done_flag = STATE_DIR / f"done__{slug}.json"  # スキップ判定にも使う
    return folder, csv_path, done_flag


def is_headless() -> bool:
    env = os.environ.get("HEADLESS")
    if env is not None:
        return env.lower() not in ("0", "false", "no")
    return _CLI_ARGS.headless if _CLI_ARGS is not None else True


def get_env_or_raise(key: str) -> str:
    val = os.environ.get(key)
    if not val:
        raise RuntimeError(
            f"環境変数 {key} が未設定です。~/.zshrc に以下を追加し、shell を再読み込みしてください。\n"
            f"  echo \"export {key}='...'\" >> ~/.zshrc\n  source ~/.zshrc"
        )
    return val


# -------------------------
# ドライバ生成・制御
# -------------------------
def create_driver() -> webdriver.Chrome:
    options = ChromeOptions()
    if is_headless():
        # Chrome 109+ 推奨
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-infobars")
    options.add_argument("--window-size=1366,900")
    options.add_argument("--lang=ja-JP")
    options.set_capability("goog:loggingPrefs", {"browser": "ALL"})
    # ヘッドレス検知で中身が空になるサイト向けの一般的緩和
    options.add_argument("--disable-blink-features=AutomationControlled")
    try:
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
    except Exception:
        pass

    drv = webdriver.Chrome(options=options)
    try:
        drv.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {
                "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});",
            },
        )
    except Exception:
        pass
    drv.set_page_load_timeout(PAGELOAD_TIMEOUT)
    drv.set_script_timeout(SCRIPT_TIMEOUT)
    drv.implicitly_wait(IMPLICIT_WAIT)
    return drv


def quit_driver_silent():
    global driver
    try:
        if driver:
            driver.quit()
    except Exception:
        pass
    finally:
        driver = None


def restart_and_recover(recover_url: str = None):
    """Chrome を再起動し、必要なら再ログイン＆対象URLへ復帰"""
    global driver, wait
    log("🔁 Chrome を再起動します...")
    quit_driver_silent()
    time.sleep(1.0)

    driver = create_driver()
    wait = WebDriverWait(driver, PAGELOAD_TIMEOUT)

    login_wordpress()
    if recover_url:
        try:
            driver.get(recover_url)
            log("🔁 復旧URLを開きました")
        except Exception as e:
            log(f"⚠️ 復旧URLオープン失敗: {e}")


# -------------------------
# ログイン
# -------------------------
def _westudy_login_url() -> str:
    u = (os.environ.get("WESTUDY_LOGIN_URL") or "").strip()
    if u:
        return u
    return _DEFAULT_MEMBER_LOGIN_URL


def login_wordpress():
    user = get_env_or_raise("WESTUDY_USER")
    pw = get_env_or_raise("WESTUDY_PASS")
    login_url = _westudy_login_url()
    log(f"🔐 ログインURL: {login_url}")

    driver.get(login_url)

    try:
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, "user_login")))
    except TimeoutException:
        log("ℹ️ ログインフォームが見つかりません（既にログイン済みの可能性）。フォーラムで確認します。")
        driver.get(forum_base_url())
        wait_for_forum_ready("既存セッション")
        log("✅ ログイン完了（既存セッション）")
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
    except Exception:
        pass
    driver.find_element(By.ID, "wp-submit").click()

    def _login_page_resolved(drv: webdriver.Chrome) -> bool:
        """wp-login から遷移した、または画面上にログインエラーが出たら True（待機終了）。"""
        u = (drv.current_url or "").lower()
        if u and "wp-login.php" not in u:
            return True
        try:
            for e in drv.find_elements(By.CSS_SELECTOR, "#login_error, #login_error_msg"):
                if e.is_displayed() and (e.text or "").strip():
                    return True
        except Exception:
            pass
        return False

    try:
        WebDriverWait(driver, 90).until(_login_page_resolved)
    except TimeoutException:
        cur = driver.current_url or ""
        log(f"💥 ログイン応答タイムアウト URL={cur}")
        if OUTPUT_ROOT:
            try:
                driver.save_screenshot(str(OUTPUT_ROOT / "login_failed.png"))
                log(f"📸 スクリーンショット: {OUTPUT_ROOT / 'login_failed.png'}")
            except Exception as e:
                log(f"⚠️ スクリーンショット保存失敗: {e}")
        raise RuntimeError(
            "WeStudy ログインがタイムアウトしました（ID/パスワード・ネットワークを確認）。"
            f" URL={cur}"
        )

    time.sleep(1.0)
    cur = driver.current_url or ""
    log(f"🔁 ログインPOST後のURL: {cur}")
    if "wp-login.php" in cur.lower():
        try:
            for sel in ("#login_error", "#login_error_msg"):
                for e in driver.find_elements(By.CSS_SELECTOR, sel):
                    if e.is_displayed() and (e.text or "").strip():
                        log(f"📝 サイト側メッセージ: {(e.text or '').strip()[:800]}")
                        break
        except Exception:
            pass
        if OUTPUT_ROOT:
            try:
                driver.save_screenshot(str(OUTPUT_ROOT / "login_still_wplogin.png"))
                log(f"📸 スクリーンショット: {OUTPUT_ROOT / 'login_still_wplogin.png'}")
            except Exception:
                pass
        raise RuntimeError(
            "ログインに失敗しています（パスワード誤り・会員停止・追加認証など）。"
            " 画面上のメッセージを確認してください。"
            f" URL={cur}"
        )

    cnames = sorted({(c.get("name") or "") for c in driver.get_cookies()})
    wp_cookies = [n for n in cnames if "wordpress" in n.lower()]
    log(f"🍪 WordPress系クッキー: {wp_cookies if wp_cookies else '（なし）'}")
    if not wp_cookies:
        if OUTPUT_ROOT:
            try:
                driver.save_screenshot(str(OUTPUT_ROOT / "login_no_wp_cookie.png"))
            except Exception:
                pass
        raise RuntimeError(
            "ログイン後に WordPress クッキーが付きませんでした（認証できていない可能性）。"
            " --show または HEADLESS=0 で手元確認してください。"
        )

    # クッキーを westudy.co.jp 全体に馴染ませてからフォーラムへ
    driver.get("https://westudy.co.jp/")
    time.sleep(2.0)
    driver.get(forum_base_url())
    wait_for_forum_ready("ログイン直後")
    log("✅ ログイン完了")


# -------------------------
# 安全な JS 実行
# -------------------------
def safe_js(code: str, *args, recover_url: str = None, retries: int = 1):
    """InvalidSession などが起こったら自動再起動＆復旧して再実行"""
    last_err = None
    for attempt in range(retries + 1):
        try:
            with driver_lock:
                return driver.execute_script(code, *args)
        except (InvalidSessionIdException, WebDriverException, JavascriptException) as e:
            last_err = e
            log(f"⚠️ JS実行エラー（{e.__class__.__name__}）: {e}")
            if attempt < retries:
                restart_and_recover(recover_url)
                time.sleep(1.5)
            else:
                raise
        except Exception as e:
            last_err = e
            log(f"⚠️ JS実行例外: {e}")
            if attempt < retries:
                restart_and_recover(recover_url)
                time.sleep(1.0)
            else:
                raise
    if last_err:
        raise last_err


# -------------------------
# ハートビート＆ウォッチドッグ
# -------------------------
def mark_progress(current_topic: str = "", current_url: str = "", harvested: int = 0, note: str = ""):
    if not HEARTBEAT_PATH:
        return
    hb = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "topic": current_topic,
        "url": current_url,
        "harvested": harvested,
        "note": note,
        "run_id": RUN_ID,
        "headless": is_headless(),
    }
    write_json(HEARTBEAT_PATH, hb)


def start_watchdog(stop_event: Event):
    def _loop():
        last_seen = time.time()
        while not stop_event.is_set():
            time.sleep(WATCHDOG_INTERVAL_SEC)
            try:
                if HEARTBEAT_PATH.exists():
                    mtime = HEARTBEAT_PATH.stat().st_mtime
                    if mtime > last_seen:
                        last_seen = mtime
                    else:
                        # 停滞チェック
                        stalled = time.time() - last_seen
                        if stalled >= WATCHDOG_STALL_SEC:
                            # スクショしてログ
                            shot = OUTPUT_ROOT / f"watchdog_stall_{int(time.time())}.png"
                            with driver_lock:
                                try:
                                    driver.save_screenshot(str(shot))
                                except Exception as e:
                                    log(f"⚠️ スクショ失敗: {e}")
                            log(f"⏱️ 停滞検知（{int(stalled)}秒）。スクショ保存: {shot.name}")
                            last_seen = time.time()  # 重複通知を防止
            except Exception as e:
                log(f"⚠️ ウォッチドッグ例外: {e}")

    t = Thread(target=_loop, daemon=True)
    t.start()
    return t


# -------------------------
# トピック一覧取得
# -------------------------
def get_topics():
    """フォーラムトップからトピックの (title, url) を抽出"""
    topic_base = forum_topic_href_prefix().rstrip("/")
    prefix = forum_topic_href_prefix()
    driver.get(forum_base_url())
    time.sleep(1.2)

    # 一覧はコース ?t=forums でも、トピックURLは /forum/… のことが多い
    links = safe_js(
        r'''
        const prefix = arguments[0];
        const anchors = Array.from(document.querySelectorAll("a[href^='" + prefix + "']"));
        const items = [];
        const seen = new Set();
        const rootPath = prefix.replace(/\/+$/, "");
        for (const a of anchors) {
            const href = (a.getAttribute("href") || "").split("#")[0].replace(/\/+$/, "");
            if (!href) continue;
            if (href.includes("/page/")) continue;
            if (href === rootPath || href.endsWith("/forum")) continue;
            const t = (a.textContent || "").trim();
            if (!t) continue;
            const key = href;
            if (seen.has(key)) continue;
            seen.add(key);
            items.push({title: t, url: href});
        }
        return items;
        ''',
        prefix,
        recover_url=forum_base_url(),
        retries=1,
    )

    # フォーラムには同一URLに複数のアンカーがある場合が多いので、URLでユニーク化
    uniq = {}
    for it in links:
        url = it.get("url") or ""
        title = (it.get("title") or "").strip()
        if not url or topic_base not in url:
            continue
        # タイトルは長いときがあるので最初に見つかったものを採用
        if url not in uniq:
            uniq[url] = title or url.split("/")[-1]
    lst = [(v, k) for k, v in uniq.items()]
    log(f"📌 検出トピック: {len(lst)}件")
    return lst


# -------------------------
# コメント展開 & スナップショット
# -------------------------
def force_expand_all_bodies(current_url: str):
    """『続きを読む』『もっと見る』やグラデのトグルを“開く方向だけ”で実行（トグルしない）"""
    safe_js(r'''
        // チェックボックスでグラデ解除系: ON 方向だけ
        document.querySelectorAll('input.comment-grad-trigger').forEach(cb => {
            if (!cb.checked) cb.checked = true;
        });

        // 「もっと見る」「続きを読む」などのボタン/リンクを探してクリック（開いていない場合のみ）
        const selectors = [
            "button", "a", "[role='button']", ".more-link", ".read-more"
        ];
        for (const sel of selectors) {
            document.querySelectorAll(sel).forEach(el => {
                const txt = (el.textContent || "").trim();
                // 日本語/英語の代表的な「展開」文言
                if (/[もﾓ]っと(見る|みる)|続きを読む|Read\s*More|More|Show\s*More|Expand/i.test(txt)) {
                    // 既に展開済みっぽい文言は除外
                    if (/閉じる|折りたたむ|Less|Hide/i.test(txt)) return;
                    try { el.click(); } catch(e) {}
                }
            });
        }
    ''', recover_url=current_url, retries=1)


def get_comment_snapshot(current_url: str):
    """ページ内のコメントを配列で返す（id/author/time/body）"""
    items = safe_js(r'''
        const out = [];
        const roots = Array.from(document.querySelectorAll(
            "[id^='comment-'], li.comment, article.comment, div.comment, div.bbp-reply, li.bbp-reply, .comment-item, li[id^='post-']"
        ));
        for (const el of roots) {
            try {
                let id = (el.getAttribute("id") || "").trim();
                if (!id) {
                    const idNode = el.querySelector("[id^='comment-'], [id^='post-']");
                    if (idNode) id = (idNode.getAttribute("id") || "").trim();
                }
                if (id && /^(comment-trigger|comment-reply|comment-edit|comment-form|comment-content)-/i.test(id)) {
                    continue;
                }
                if (id && id.startsWith("comment-") && !/^comment-\d+$/i.test(id)) {
                    continue;
                }
                let author = "";
                let timeText = "";
                let timeISO = "";
                let body = "";

                const aSel = [
                    ".comment-author", ".bbp-author-name", ".author", "[rel='author']", ".user-name", ".poster-name"
                ];
                for (const s of aSel) {
                    const n = el.querySelector(s);
                    if (n && n.textContent) { author = n.textContent.trim(); break; }
                }
                if (!author) {
                    // 近傍の strong/em などから推定
                    const cand = el.querySelector("strong, b, .username, .vcard, .fn, .name");
                    if (cand && cand.textContent) author = cand.textContent.trim();
                }

                const tSel = [
                    "time", "time[datetime]", ".time", ".date", "abbr.published", "span.published",
                    ".comment_date", ".comment-date", ".bbp-reply-post-date", ".reply-date", ".comment-date"
                ];
                for (const s of tSel) {
                    const t = el.querySelector(s);
                    if (t) {
                        timeText = (t.textContent || "").trim();
                        const dt = t.getAttribute("datetime");
                        if (dt) timeISO = dt;
                        break;
                    }
                }
                if (!timeText) {
                    const near = el.querySelector(".comment_date, .bbp-reply-post-date, .reply-date, .comment-date");
                    if (near) timeText = (near.textContent || "").trim();
                }
                if (!timeText) {
                    // コメントmeta全体から日付らしい部分を抽出（class名変更への保険）
                    const meta = el.querySelector(".comment-meta, .commentmetadata, .bbp-reply-header");
                    const metaText = meta ? (meta.textContent || "").trim() : "";
                    if (metaText) {
                        const m = metaText.match(/(\d{4}年\d{1,2}月\d{1,2}日\\s*\\d{1,2}時\\d{1,2}分|\\d{4}[\\/-]\\d{1,2}[\\/-]\\d{1,2}(?:\\s+\\d{1,2}:\\d{1,2}(?::\\d{1,2})?)?)/);
                        if (m) timeText = (m[1] || "").trim();
                    }
                }

                let profileUrl = "";
                const prof = el.querySelector(
                    "a.user-profile[href], .comment-author a[href*='user-profile'], " +
                    ".vcard a.url[href], .vcard .fn a[href], a[href*='/user-profile']"
                );
                if (prof) profileUrl = (prof.getAttribute("href") || "").trim();

                let parentNum = "";
                const cls = (el.getAttribute("class") || "");
                const pr = cls.match(/comment-parent-(\d+)/);
                if (pr) parentNum = pr[1];
                if (!parentNum) {
                    const metaA = el.querySelector(".comment-metadata a[href*='comment-'], .reply a[href*='comment-']");
                    if (metaA) {
                        const mh = (metaA.getAttribute("href") || "").match(/comment-(\d+)/);
                        if (mh) parentNum = mh[1];
                    }
                }

                const bSel = [".comment-content", ".bbp-reply-content", ".content", ".entry", ".text", ".message"];
                for (const s of bSel) {
                    const b = el.querySelector(s);
                    if (b) {
                        body = (b.innerText || b.textContent || "").trim();
                        break;
                    }
                }
                if (!body) {
                    body = (el.innerText || el.textContent || "").trim();
                }

                if (id || body) {
                    out.push({id, author, timeText, timeISO, body, profileUrl, parentNum});
                }
            } catch(e) {}
        }
        return out;
    ''', recover_url=current_url, retries=1)
    # JS -> Python で安全に扱える構造のみ返す
    cleaned = []
    for it in items or []:
        cleaned.append({
            "id": (it.get("id") or "").strip(),
            "author": (it.get("author") or "").strip(),
            "time_text": (it.get("timeText") or "").strip(),
            "time_iso": (it.get("timeISO") or "").strip(),
            "body": (it.get("body") or "").strip(),
            "profile_url": (it.get("profileUrl") or "").strip(),
            "parent_comment_id": (it.get("parentNum") or "").strip(),
        })
    return cleaned


def click_load_more_once(current_url: str) -> bool:
    """『もっと読む/次へ』などを1回だけクリック。押せたら True"""
    clicked = safe_js(r'''
        const cand = [];
        const sels = [
            "button.load-more", "a.load-more", ".load-more",
            ".pagination a.next", "a.next", "button.next",
            "a[aria-label*='more' i]", "button[aria-label*='more' i]",
            "a[aria-label*='次' i]", "button[aria-label*='次' i]",
            "#load_more_comments"
        ];
        for (const s of sels) document.querySelectorAll(s).forEach(x => cand.push(x));
        // テキストで判定
        document.querySelectorAll("a,button,[role='button']").forEach(x => {
            const t = (x.textContent || "").trim();
            if (/[もﾓ]っと(見る|みる)|続きを読む|もっと読む|次へ|さらに読み込む|Load More|More|Next/i.test(t)) {
                cand.push(x);
            }
        });
        // 画面下部にある要素から優先的に
        cand.sort((a,b)=> (a.getBoundingClientRect().top - b.getBoundingClientRect().top));
        for (const el of cand.reverse()) {
            try {
                el.scrollIntoView({behavior:"instant",block:"center"});
                el.click();
                return true;
            } catch(e) {}
        }
        return false;
    ''', recover_url=current_url, retries=1)
    return bool(clicked)


def click_load_more_until_done(expected_count: int | None, current_url: str):
    """
    ページ全体を展開してコメントを最大までロード。
    - スナップショットを前後比較し、新規IDが出なくなるまでループ
    - 無限ループ対策: 進捗なしループが続いたら中断
    """
    force_expand_all_bodies(current_url)
    seen_ids = set()
    no_progress_loops = 0
    total_clicks = 0

    while True:
        snap1 = get_comment_snapshot(current_url)
        new_ids = [s["id"] for s in snap1 if s["id"] and s["id"] not in seen_ids]
        for cid in new_ids:
            seen_ids.add(cid)

        # 期待件数があって既に満たしたら終了
        if expected_count and len(seen_ids) >= expected_count:
            log(f"  - 吸い上げ件数: {len(seen_ids)}（期待件数に到達）")
            break

        # もっと読む等をクリック
        clicked = click_load_more_once(current_url)
        if clicked:
            total_clicks += 1
            time.sleep(1.2)
            force_expand_all_bodies(current_url)
        else:
            # ボタンがなく、増えなければ終わり
            snap2 = get_comment_snapshot(current_url)
            if len(snap2) <= len(snap1):
                break

        # 進捗確認
        snap2 = get_comment_snapshot(current_url)
        added = [s["id"] for s in snap2 if s["id"] and s["id"] not in seen_ids]
        if not added and not clicked:
            no_progress_loops += 1
        else:
            no_progress_loops = 0
        for cid in added:
            seen_ids.add(cid)

        mark_progress(harvested=len(seen_ids), current_topic="", current_url=current_url)

        # 無限ループ対策
        if no_progress_loops >= 3:
            log("  ⚠️ 進捗がないループを検知したため、ロードを打ち切ります。")
            break

        # 過剰クリック抑止
        if total_clicks > 200:
            log("  ⚠️ クリック回数が多すぎるため中断します。")
            break


# -------------------------
# 収集フロー
# -------------------------
def build_comment_url(topic_url: str, comment_id_attr: str) -> str:
    """HTMLの id=comment-123 から WeStudy のコメントURLを組み立てる。"""
    raw = (comment_id_attr or "").strip()
    num = ""
    if raw.startswith("comment-"):
        num = raw[8:].strip()
    else:
        num = re.sub(r"\D", "", raw)
    if not num:
        return ""
    base = (topic_url or "").split("#")[0].rstrip("/")
    return f"{base}?comment={num}#comment-{num}"


def harvest_topic(title: str, url: str, expected_count: int | None):
    """
    1トピック収集
    返り値: rows(list[dict])
    """
    current_title = title.strip()
    current_url = url.strip()

    mark_progress(current_topic=current_title, current_url=current_url, harvested=0)
    log(f"\n▶ {current_title}  {current_url}")

    driver.get(current_url)
    time.sleep(1.0)
    force_expand_all_bodies(current_url)
    click_load_more_until_done(expected_count, current_url)

    # 最終スナップショット
    snap = get_comment_snapshot(current_url)

    # 重複除去 & 安全化
    rows = []
    seen = set()
    for s in snap:
        cid = s["id"] or ""
        key = (cid, s["body"])
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "topic_title": current_title,
            "topic_url": current_url,
            "comment_id": cid,
            "comment_url": build_comment_url(current_url, cid),
            "profile_url": s.get("profile_url", "") or "",
            "parent_comment_id": s.get("parent_comment_id", "") or "",
            "author": s["author"],
            "time_text": s["time_text"],
            "time_iso": s["time_iso"],
            "body": s["body"],
        })

    log(f"  - 吸い上げ件数: {len(rows)}（期待件数なし）" if not expected_count else f"  - 吸い上げ件数: {len(rows)}（期待: {expected_count}）")
    mark_progress(current_topic=current_title, current_url=current_url, harvested=len(rows), note="topic_done")
    return rows


def write_topic_csv(csv_path: Path, rows: list[dict]):
    if not rows:
        return
    headers = [
        "topic_title",
        "topic_url",
        "comment_id",
        "comment_url",
        "profile_url",
        "parent_comment_id",
        "author",
        "time_text",
        "time_iso",
        "body",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def should_skip_topic(url: str, done_flag: Path) -> bool:
    # 1) .done（json）フラグでスキップ
    if done_flag.exists() and not _CLI_ARGS.force:
        return True
    # 2) グローバル done_topics.json でもスキップ
    done_topics = read_json(DONE_TOPICS_PATH, default={"urls": []}) or {"urls": []}
    return (url in (done_topics.get("urls") or [])) and (not _CLI_ARGS.force)


def mark_topic_done(url: str, done_flag: Path, title: str, rows_count: int):
    # フラグファイル
    write_json(done_flag, {
        "url": url,
        "title": title,
        "rows": rows_count,
        "finished_at": datetime.now().isoformat(timespec="seconds"),
        "run_id": RUN_ID,
    })
    # グローバル done_topics.json に記録
    obj = read_json(DONE_TOPICS_PATH, default={"urls": []}) or {"urls": []}
    urls = set(obj.get("urls") or [])
    urls.add(url)
    obj["urls"] = sorted(urls)
    write_json(DONE_TOPICS_PATH, obj)


# -------------------------
# メイン
# -------------------------
def main():
    global driver, wait

    if not OUTPUT_ROOT or not STATE_DIR:
        raise RuntimeError("configure_paths() を先に呼び出してください")

    # 初期化
    os.environ.setdefault("TZ", "Asia/Tokyo")
    try:
        time.tzset()  # macOSでもOK
    except Exception:
        pass

    # Chrome 起動 & ログイン
    driver = create_driver()
    wait = WebDriverWait(driver, PAGELOAD_TIMEOUT)
    login_wordpress()

    # ウォッチドッグ開始
    stop_event = Event()
    start_watchdog(stop_event)
    try:
        # トピック一覧
        topics = get_topics()
        if not topics:
            log("⚠️ トピックが見つかりませんでした。")
            return

        # 簡易に「期待件数なし」として処理（サイト側の件数表示に依存すると壊れやすい）
        for idx, (title, url) in enumerate(topics, start=1):
            # スキップ判定
            _, csv_path, done_flag = topic_output_paths(title, url)
            if should_skip_topic(url, done_flag):
                log(f"⏩ スキップ: {title}  {url}")
                continue

            # 収集
            try:
                rows = harvest_topic(title, url, expected_count=None)
            except (TimeoutException, InvalidSessionIdException, WebDriverException) as e:
                log(f"  ⚠️ 例外発生（再起動してリカバリ）: {e.__class__.__name__}: {e}")
                restart_and_recover(url)
                rows = harvest_topic(title, url, expected_count=None)

            # CSV 書き出し
            write_topic_csv(csv_path, rows)
            mark_topic_done(url, done_flag, title, len(rows))

        log("\n🎉 全トピック処理が完了しました。")
    finally:
        stop_event.set()
        cleanup()


def cleanup():
    quit_driver_silent()
    try:
        # 最後のハートビート
        mark_progress(note="cleanup", harvested=0)
    except Exception:
        pass


# -------------------------
# CLI
# -------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WeStudy フォーラム収集")

    # デフォルトはヘッドレス。--show を付けた時だけ表示ありにする
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--headless", dest="headless", action="store_true",
                       help="ヘッドレスで実行（デフォルト）")
    group.add_argument("--show", dest="headless", action="store_false",
                       help="ブラウザ表示で実行")
    parser.set_defaults(headless=True)

    parser.add_argument("--force", action="store_true", help="完了済みトピックも再取得する")
    parser.add_argument(
        "--output-root",
        default=None,
        help="この実行のCSV出力先ディレクトリ（未指定時は WESTUDY_OUTPUT_ROOT または ProgramCode/outputs/westudy/<RUN_ID>/）",
    )
    parser.add_argument(
        "--state-dir",
        default=None,
        help="完了フラグ・done_topics.json の保存先（未指定時は WESTUDY_STATE_DIR または ProgramCode/outputs/westudy_state）",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="出力フォルダ名に使う RUN_ID（--output-root 未指定かつ WESTUDY_OUTPUT_ROOT 未設定時のみ有効）",
    )
    _CLI_ARGS = parser.parse_args()

    configure_paths(
        output_root=_CLI_ARGS.output_root,
        state_dir=_CLI_ARGS.state_dir,
        run_id=_CLI_ARGS.run_id,
    )

    try:
        main()
    except KeyboardInterrupt:
        log("⛔ 中断されました（Ctrl+C）")
        cleanup()
    except Exception as e:
        log(f"💥 異常終了: {e}\n{traceback.format_exc()}")
        cleanup()
        sys.exit(1)
