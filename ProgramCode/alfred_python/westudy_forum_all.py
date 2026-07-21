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
import html as html_lib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from threading import Thread, Event, Lock

import requests

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


import hashlib
from urllib.parse import unquote


def sanitize_filename(name: str, extra: str = "") -> str:
    base = re.sub(r"[\\/:*?\"<>|]", "_", name).strip()
    base = re.sub(r"\s+", " ", base)
    if extra:
        base = f"{base}__{extra}"
    # 長過ぎると扱いにくいので短縮（macOS NAME_MAX=255、URLエンコードslugはすぐ超える）
    return (base[:90]).rstrip("_ ")


def topic_output_paths(title: str, url: str):
    """出力フォルダ・CSV・done フラグ。done は URL の SHA1 短縮（ファイル名長制限対策）。"""
    short = hashlib.sha1(url.strip().encode("utf-8")).hexdigest()[:12]
    label = sanitize_filename(title)[:60] or short
    folder = OUTPUT_ROOT / f"{label}__{short}"
    folder.mkdir(parents=True, exist_ok=True)
    csv_path = folder / f"{label}.csv"
    done_flag = STATE_DIR / f"done__{short}.json"
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
    """フォーラムトップからトピックの (title, url) を抽出。既知URLもマージ。"""
    topic_base = forum_topic_href_prefix().rstrip("/")
    prefix = forum_topic_href_prefix()
    driver.get(forum_base_url())
    time.sleep(1.2)
    # 遅延読み込み対策で下までスクロール
    try:
        for _ in range(8):
            driver.execute_script("window.scrollBy(0, Math.floor(window.innerHeight*0.9));")
            time.sleep(0.35)
        driver.execute_script("window.scrollTo(0, 0);")
    except Exception:
        pass

    # 一覧はコース ?t=forums でも、トピックURLは /forum/… のことが多い
    links = safe_js(
        r'''
        const prefix = arguments[0];
        const anchors = Array.from(document.querySelectorAll("a[href*='/forum/']"));
        const items = [];
        const seen = new Set();
        const rootPath = prefix.replace(/\/+$/, "");
        for (const a of anchors) {
            let href = (a.getAttribute("href") || "").split("#")[0].split("?")[0].replace(/\/+$/, "");
            if (!href) continue;
            if (href.includes("/page/")) continue;
            if (href === rootPath || href.endsWith("/forum")) continue;
            if (!href.startsWith("http")) {
                try { href = new URL(href, location.origin).href.replace(/\/+$/, ""); } catch(e) { continue; }
            }
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
    for it in links or []:
        url = (it.get("url") or "").strip()
        title = (it.get("title") or "").strip()
        if not url or "/forum/" not in url:
            continue
        if url not in uniq:
            uniq[url] = title or url.split("/")[-1]

    # 既知トピック（一覧に出ない板の取りこぼし防止）
    for title, url in _SEED_TOPICS:
        u = url.strip().rstrip("/")
        if u and u not in uniq:
            uniq[u] = title

    # 環境変数 WESTUDY_EXTRA_TOPICS=title|url;title|url
    extra = (os.environ.get("WESTUDY_EXTRA_TOPICS") or "").strip()
    if extra:
        for part in extra.split(";"):
            part = part.strip()
            if "|" not in part:
                continue
            title, url = part.split("|", 1)
            u = url.strip().rstrip("/")
            if u and u not in uniq:
                uniq[u] = title.strip() or u.split("/")[-1]

    lst = [(v, k) for k, v in uniq.items()]
    log(f"📌 検出トピック: {len(lst)}件")
    return lst


# 一覧DOMに出ないことがある板（過去スクレイプ実績URL）
_SEED_TOPICS: list[tuple[str, str]] = [
    ("成果報告【実践し、成果が出た内容を記載】", "https://westudy.co.jp/forum/results"),
    ("月次活動報告 ＆ 来月への宣言【グルコン10日前まで】", "https://westudy.co.jp/forum/monthly_output"),
    ("【その他テーマ】AI活用で業務改善", "https://westudy.co.jp/forum/%E3%80%90%E3%81%9D%E3%81%AE%E4%BB%96%E3%83%86%E3%83%BC%E3%83%9E%E3%80%91ai%E6%B4%BB%E7%94%A8%E3%81%A7%E6%A5%AD%E5%8B%99%E6%94%B9%E5%96%84"),
    ("【神物件名】オリジナル物件名アイディア・キーワード集", "https://westudy.co.jp/forum/%E3%80%90%E7%A5%9E%E7%89%A9%E4%BB%B6%E5%90%8D%E3%80%91%E3%82%AA%E3%83%AA%E3%82%B8%E3%83%8A%E3%83%AB%E7%89%A9%E4%BB%B6%E5%90%8D%E3%82%A2%E3%82%A4%E3%83%87%E3%82%A3%E3%82%A2%E3%83%BB%E3%82%AD%E3%83%BC"),
    ("【不動産】最新融資情報２ ※不動産会社提携ローン専用※", "https://westudy.co.jp/forum/%E3%80%90%E4%B8%8D%E5%8B%95%E7%94%A3%E3%80%91%E6%9C%80%E6%96%B0%E8%9E%8D%E8%B3%87%E6%83%85%E5%A0%B1%EF%BC%92-%E2%80%BB%E4%B8%8D%E5%8B%95%E7%94%A3%E4%BC%9A%E7%A4%BE%E6%8F%90%E6%90%BA%E3%83%AD%E3%83%BC"),
    ("塾生相互支援板　【仕事依頼】【仕事手伝います！】（事業やお店の宣伝もOK）", "https://westudy.co.jp/forum/work-2"),
    ("【その他テーマ】育児教育情報", "https://westudy.co.jp/forum/%E3%80%90%E3%81%9D%E3%81%AE%E4%BB%96%E3%83%86%E3%83%BC%E3%83%9E%E3%80%91%E8%82%B2%E5%85%90%E6%95%99%E8%82%B2%E6%83%85%E5%A0%B1"),
    ("会計ソフト 使用感の共有", "https://westudy.co.jp/forum/%E4%BC%9A%E8%A8%88%E3%82%BD%E3%83%95%E3%83%88-%E4%BD%BF%E7%94%A8%E6%84%9F%E3%81%AE%E5%85%B1%E6%9C%89"),
    ("【自由投稿】会員同士の質問などなんでもOK", "https://westudy.co.jp/forum/%E3%80%90%E8%87%AA%E7%94%B1%E6%8A%95%E7%A8%BF%E3%80%91%E4%BC%9A%E5%93%A1%E5%90%8C%E5%A3%AB%E3%81%AE%E8%B3%AA%E5%95%8F%E3%81%AA%E3%81%A9%E3%81%AA%E3%82%93%E3%81%A7%E3%82%82ok"),
    ("【不動産】公庫融資を見込む創業セミナー系情報、士業紹介など", "https://westudy.co.jp/forum/%E3%80%90%E4%B8%8D%E5%8B%95%E7%94%A3%E3%80%91%E5%85%AC%E5%BA%AB%E8%9E%8D%E8%B3%87%E3%82%92%E8%A6%8B%E8%BE%BC%E3%82%80%E5%89%B5%E6%A5%AD%E3%82%BB%E3%83%9F%E3%83%8A%E3%83%BC%E7%B3%BB%E6%83%85%E5%A0%B1%E3%80%81%E5%A3%AB%E6%A5%AD%E7%B4%B9%E4%BB%8B%E3%81%AA%E3%81%A9"),
]


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

                // WeStudy では .comment-author はアバター画像のみ（テキスト空）。
                // 実際の投稿者名は .comment-meta 内の .fn.user-profile にある。
                const aSel = [
                    ".comment-meta .fn", ".fn.user-profile", ".comment-author .fn",
                    ".comment-author", ".bbp-author-name", ".author", "[rel='author']", ".user-name", ".poster-name"
                ];
                for (const s of aSel) {
                    const n = el.querySelector(s);
                    if (n) {
                        const t = (n.textContent || "").trim();
                        if (t) { author = t; break; }
                    }
                }
                if (!author) {
                    // 近傍の strong/em などから推定（空白のみは採用しない）
                    const cands = el.querySelectorAll("strong, b, .username, .vcard .fn, .fn, .name");
                    for (const cand of cands) {
                        const t = (cand.textContent || "").trim();
                        if (t) { author = t; break; }
                    }
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

                // いいねウィジェット等を一時的に非表示にして本文から除外する
                // （innerText は display:none を含めないため、改行を保ったまま除去できる）
                const readTextWithoutJunk = (node) => {
                    const junk = Array.from(node.querySelectorAll(".wpulike, script, style, .comment-content-grad-btn"));
                    const saved = junk.map(x => x.style.display);
                    junk.forEach(x => { x.style.display = "none"; });
                    const t = (node.innerText || node.textContent || "").trim();
                    junk.forEach((x, i) => { x.style.display = saved[i]; });
                    return t;
                };
                const bSel = [".comment-content", ".bbp-reply-content", ".content", ".entry", ".text", ".message"];
                for (const s of bSel) {
                    const b = el.querySelector(s);
                    if (b) {
                        body = readTextWithoutJunk(b);
                        break;
                    }
                }
                if (!body) {
                    body = readTextWithoutJunk(el);
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


def _more_comments_expected() -> int | None:
    """WeStudy テーマの MORE_COMMENTS.comment_num（全件数）を読む。"""
    try:
        n = driver.execute_script(
            "try {"
            "  if (window.MORE_COMMENTS && MORE_COMMENTS.comment_num)"
            "    return parseInt(MORE_COMMENTS.comment_num, 10);"
            "  return null;"
            "} catch (e) { return null; }"
        )
        if n is None:
            return None
        n = int(n)
        return n if n > 0 else None
    except Exception:
        return None


def _count_top_level_comments() -> int:
    try:
        n = driver.execute_script(
            "return document.querySelectorAll('.commentlist > .comment').length"
            " || document.querySelectorAll(\"li.comment[id^='comment-']\").length"
            " || 0;"
        )
        return int(n or 0)
    except Exception:
        return 0


def click_load_more_once(current_url: str) -> bool:
    """『コメントを読み込む』/#show-more-comments、または次へ等を1回クリック。押せたら True"""
    # WeStudy 正: div#show-more-comments（a/button ではない）
    clicked = safe_js(
        r'''
        const show = document.querySelector("#show-more-comments");
        const wrap = document.querySelector("#more-comments");
        if (show) {
            const wrapHidden = wrap && (
                wrap.style.display === "none"
                || window.getComputedStyle(wrap).display === "none"
            );
            if (!wrapHidden) {
                try {
                    show.scrollIntoView({behavior:"instant", block:"center"});
                    show.click();
                    return true;
                } catch (e) {}
            }
        }
        const cand = [];
        const sels = [
            "button.load-more", "a.load-more", ".load-more",
            ".pagination a.next", "a.next.page-numbers", "a.next", "button.next",
            "a[aria-label*='more' i]", "button[aria-label*='more' i]",
            "a[aria-label*='次' i]", "button[aria-label*='次' i]",
            "#load_more_comments",
            ".nav-links a.next", ".bbp-pagination-links a.next"
        ];
        for (const s of sels) document.querySelectorAll(s).forEach(x => cand.push(x));
        document.querySelectorAll("a,button,[role='button'],div#show-more-comments,div#more-comments").forEach(x => {
            const t = (x.textContent || "").trim();
            if (/コメントを読み込む|[もﾓ]っと(見る|みる)|続きを読む|もっと読む|次へ|さらに読み込む|Load More|More|Next/i.test(t)) {
                cand.push(x);
            }
        });
        const cur = document.querySelector(".pagination .current, .page-numbers.current, .bbp-pagination-links .current");
        if (cur) {
            const n = parseInt((cur.textContent || "").trim(), 10);
            if (!isNaN(n)) {
                document.querySelectorAll(".pagination a.page-numbers, a.page-numbers, .bbp-pagination-links a").forEach(a => {
                    const t = (a.textContent || "").trim();
                    if (t === String(n + 1)) cand.push(a);
                });
            }
        }
        cand.sort((a,b)=> (a.getBoundingClientRect().top - b.getBoundingClientRect().top));
        for (const el of cand.reverse()) {
            try {
                if (el.classList && el.classList.contains("current")) continue;
                el.scrollIntoView({behavior:"instant",block:"center"});
                el.click();
                return true;
            } catch(e) {}
        }
        return false;
        ''',
        recover_url=current_url,
        retries=1,
    )
    return bool(clicked)


def harvest_all_comment_snaps(expected_count: int | None, start_url: str) -> list[dict]:
    """
    WeStudy は #show-more-comments で DOM 追記（/page/N は無効）。
    読み込み完了後に1回だけスナップショットする。
    """
    current_url = start_url
    mc_expected = _more_comments_expected()
    target = expected_count or mc_expected
    if mc_expected:
        log(f"  - MORE_COMMENTS 期待件数: {mc_expected}")

    # show-more がある板: 件数だけ増やしてから最終スナップ
    has_show_more = False
    try:
        has_show_more = bool(
            driver.execute_script("return !!document.querySelector('#show-more-comments,#more-comments');")
        )
    except Exception:
        pass

    if has_show_more:
        clicks = 0
        no_progress = 0
        max_clicks = 400
        prev = _count_top_level_comments()
        log(f"  - show-more 開始: {prev}件")
        while clicks < max_clicks:
            if target and prev >= target:
                break
            clicked = click_load_more_once(current_url)
            if not clicked:
                break
            clicks += 1
            # AJAX 待ち（件数増加 or タイムアウト）
            grew = False
            for _ in range(40):
                time.sleep(0.25)
                now = _count_top_level_comments()
                if now > prev:
                    prev = now
                    grew = True
                    no_progress = 0
                    break
            if not grew:
                no_progress += 1
                if no_progress >= 3:
                    log("  ⚠️ show-more で件数が増えず打ち切り")
                    break
            if clicks == 1 or clicks % 10 == 0 or (target and prev >= target):
                log(f"  - show-more click {clicks}: {prev}件" + (f" / {target}" if target else ""))
            mark_progress(harvested=prev, current_topic="", current_url=current_url)

        force_expand_all_bodies(current_url)
        snap = get_comment_snapshot(current_url)
        log(f"  - 最終スナップ: {len(snap)}件")
        return snap

    # フォールバック: 旧ページネーション想定（蓄積マージ）
    by_id: dict[str, dict] = {}
    page_num = 1
    no_progress_loops = 0
    max_pages = 250

    while page_num <= max_pages:
        force_expand_all_bodies(current_url)
        snap = get_comment_snapshot(current_url)
        before = len(by_id)
        for s in snap:
            cid = (s.get("id") or "").strip()
            if cid:
                by_id[cid] = s
        added = len(by_id) - before
        log(f"  - page {page_num}: +{added} (total {len(by_id)})")

        if target and len(by_id) >= target:
            break

        clicked = click_load_more_once(current_url)
        if clicked:
            time.sleep(1.4)
            current_url = driver.current_url or current_url
            if len(by_id) > before:
                no_progress_loops = 0
            else:
                no_progress_loops += 1
            page_num += 1
            if no_progress_loops < 2:
                mark_progress(harvested=len(by_id), current_topic="", current_url=current_url)
                continue

        base = re.sub(r"/page/\d+/?$", "", start_url.split("?")[0].rstrip("/"))
        next_url = f"{base}/page/{page_num + 1}/"
        try:
            driver.get(next_url)
            time.sleep(1.2)
            is404 = False
            try:
                is404 = bool(
                    driver.execute_script(
                        "return /404|見つかりません|Not\\s*Found/i.test(document.body.innerText||'');"
                    )
                )
            except Exception:
                pass
            cur = driver.current_url or ""
            if is404 or "/page/" not in cur:
                if not clicked:
                    break
                no_progress_loops += 1
                if no_progress_loops >= 3:
                    break
                page_num += 1
                continue
            current_url = cur
            page_num += 1
            snap2 = get_comment_snapshot(current_url)
            before2 = len(by_id)
            for s in snap2:
                cid = (s.get("id") or "").strip()
                if cid:
                    by_id[cid] = s
            if len(by_id) == before2:
                no_progress_loops += 1
            else:
                no_progress_loops = 0
            if no_progress_loops >= 3:
                log("  ⚠️ 新規コメントが増えないため打ち切り")
                break
        except Exception as e:
            log(f"  ⚠️ page URL 遷移失敗: {e}")
            break

        mark_progress(harvested=len(by_id), current_topic="", current_url=current_url)

    return list(by_id.values())


def click_load_more_until_done(expected_count: int | None, current_url: str):
    """後方互換: 蓄積は harvest_all_comment_snaps に委譲。"""
    harvest_all_comment_snaps(expected_count, current_url)


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


def _decode_ajax_html(raw: str) -> str:
    """admin-ajax の more_comments は JSON 文字列で HTML を返す。"""
    text = (raw or "").strip()
    if not text:
        return ""
    try:
        decoded = json.loads(text)
        if isinstance(decoded, str):
            return decoded
    except Exception:
        pass
    return text


def _parse_comments_from_html(html: str) -> list[dict]:
    """li.comment / #comment-N 断片からコメント辞書を抽出。"""
    if not html:
        return []
    out: list[dict] = []
    # depth-1 だけでなく返信も含め id=comment-N のブロックを拾う
    for m in re.finditer(
        r'<li[^>]*\bid=["\']comment-(\d+)["\'][^>]*>([\s\S]*?)(?=<li[^>]*\bid=["\']comment-\d+["\']|\Z)',
        html,
        flags=re.I,
    ):
        cid = m.group(1)
        block = m.group(0)
        author = ""
        am = re.search(
            r'class=["\'][^"\']*\bfn\b[^"\']*["\'][^>]*>([^<]+)',
            block,
            flags=re.I,
        )
        if am:
            author = html_lib.unescape(am.group(1)).strip()
        time_text = ""
        time_iso = ""
        tm = re.search(
            r'<time[^>]*datetime=["\']([^"\']+)["\'][^>]*>([^<]*)',
            block,
            flags=re.I,
        )
        if tm:
            time_iso = (tm.group(1) or "").strip()
            time_text = html_lib.unescape(tm.group(2) or "").strip() or time_iso
        if not time_text:
            tm2 = re.search(
                r'class=["\'][^"\']*comment-meta[^"\']*["\'][^>]*>[\s\S]*?<a[^>]*>([^<]+)</a>',
                block,
                flags=re.I,
            )
            if tm2:
                time_text = html_lib.unescape(tm2.group(1)).strip()
        body = ""
        bm = re.search(
            r'class=["\'][^"\']*comment-content[^"\']*["\'][^>]*>([\s\S]*?)</div>',
            block,
            flags=re.I,
        )
        if bm:
            raw_body = bm.group(1)
            raw_body = re.sub(r"<br\s*/?>", "\n", raw_body, flags=re.I)
            raw_body = re.sub(r"</p\s*>", "\n", raw_body, flags=re.I)
            raw_body = re.sub(r"<[^>]+>", "", raw_body)
            body = html_lib.unescape(raw_body).strip()
        parent = ""
        pm = re.search(r'data-parent=["\'](\d+)["\']', block, flags=re.I)
        if pm:
            parent = pm.group(1)
        profile = ""
        pr = re.search(r'profile_href=["\']([^"\']+)["\']', block, flags=re.I)
        if pr:
            profile = pr.group(1).strip()
        out.append(
            {
                "id": f"comment-{cid}",
                "author": author,
                "time_text": time_text,
                "time_iso": time_iso,
                "body": body,
                "profile_url": profile,
                "parent_comment_id": parent,
            }
        )
    # fallback: id only
    if not out:
        for cid in re.findall(r'id=["\']comment-(\d+)["\']', html, flags=re.I):
            out.append(
                {
                    "id": f"comment-{cid}",
                    "author": "",
                    "time_text": "",
                    "time_iso": "",
                    "body": "",
                    "profile_url": "",
                    "parent_comment_id": "",
                }
            )
    # dedupe by id (keep first richer)
    by_id: dict[str, dict] = {}
    for s in out:
        cid = s.get("id") or ""
        if not cid:
            continue
        prev = by_id.get(cid)
        if not prev or (len(s.get("body") or "") > len(prev.get("body") or "")):
            by_id[cid] = s
    return list(by_id.values())


def _selenium_cookie_session() -> requests.Session:
    sess = requests.Session()
    for c in driver.get_cookies():
        try:
            sess.cookies.set(
                c["name"],
                c["value"],
                domain=c.get("domain") or ".westudy.co.jp",
                path=c.get("path") or "/",
            )
        except Exception:
            sess.cookies.set(c["name"], c["value"])
    return sess


def harvest_via_more_comments_ajax(start_url: str) -> list[dict] | None:
    """
    WeStudy の more_comments_forum (admin-ajax) で全件取得。
    DOM に数千件載せない（月次 ~1万件で Chrome が落ちるため）。
    MORE_COMMENTS が無ければ None。
    """
    mc = None
    try:
        mc = driver.execute_script("return window.MORE_COMMENTS || null;")
    except Exception:
        mc = None
    if not mc or not mc.get("endpoint") or not mc.get("post_id"):
        return None

    try:
        max_n = int(mc.get("comment_num") or 0)
    except Exception:
        max_n = 0
    action = mc.get("action") or "more_comments_forum"
    endpoint = mc["endpoint"]
    post_id = mc["post_id"]
    course_id = ""
    lesson = ""
    try:
        course_id = driver.execute_script(
            'return (document.getElementById("comment_course_id")||{}).value || "";'
        ) or ""
        lesson = driver.execute_script(
            'return (document.getElementById("comment_form_lesson")||{}).value || "";'
        ) or ""
    except Exception:
        pass

    top_num = _count_top_level_comments()
    by_id: dict[str, dict] = {}
    for s in _parse_comments_from_html(driver.page_source or ""):
        cid = (s.get("id") or "").strip()
        if cid:
            by_id[cid] = s

    log(f"  - AJAX more_comments: 期待top={max_n or '?'} 開始top={top_num} ids={len(by_id)}")
    sess = _selenium_cookie_session()
    rounds = 0
    max_rounds = 600
    no_progress = 0
    while rounds < max_rounds:
        if max_n and top_num >= max_n:
            break
        try:
            r = sess.post(
                endpoint,
                data={
                    "action": action,
                    "num": top_num,
                    "course_id": course_id,
                    "comment_form_lesson": lesson,
                    "post_id": post_id,
                },
                timeout=120,
                headers={
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": start_url,
                },
            )
            frag = _decode_ajax_html(r.text)
        except Exception as e:
            log(f"  ⚠️ AJAX 失敗: {e}")
            break
        if not frag.strip():
            no_progress += 1
            if no_progress >= 2:
                break
            rounds += 1
            continue
        batch = _parse_comments_from_html(frag)
        new_top = len(
            re.findall(
                r'<li[^>]*class="[^"]*\bcomment\b[^"]*\bdepth-1\b',
                frag,
                flags=re.I,
            )
        )
        if new_top == 0:
            # 返信を含まない top-level 断片想定: class に comment を持つ li
            new_top = len(re.findall(r'<li[^>]*class="[^"]*\bcomment\b', frag, flags=re.I))
        before = len(by_id)
        for s in batch:
            cid = (s.get("id") or "").strip()
            if cid:
                by_id[cid] = s
        added = len(by_id) - before
        if new_top <= 0 and added <= 0:
            no_progress += 1
            if no_progress >= 3:
                break
        else:
            no_progress = 0
            top_num += new_top if new_top > 0 else 50
        rounds += 1
        if rounds == 1 or rounds % 20 == 0 or (max_n and top_num >= max_n):
            log(f"  - AJAX round {rounds}: top≈{top_num}/{max_n or '?'} ids={len(by_id)} (+{added})")
            # OneDrive 上だと毎ラウンドの heartbeat 書き込みが詰まりやすい
            mark_progress(harvested=len(by_id), current_topic="", current_url=start_url)

    log(f"  - AJAX 完了: ids={len(by_id)} rounds={rounds}")
    return list(by_id.values())


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
    snap = harvest_via_more_comments_ajax(current_url)
    if snap is None:
        # MORE_COMMENTS 無しでも初回 DOM を試す（空板・別UI）
        force_expand_all_bodies(current_url)
        snap = get_comment_snapshot(current_url)
        if not snap:
            snap = harvest_all_comment_snaps(expected_count, current_url)
        # harvest_all が空で /page/2 に迷走した場合に戻す
        try:
            if "/page/" in (driver.current_url or ""):
                driver.get(current_url)
                time.sleep(0.8)
        except Exception:
            pass
    if not snap:
        snap = []

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
