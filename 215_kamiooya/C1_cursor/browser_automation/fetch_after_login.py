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

from __future__ import annotations

import argparse
import os
import platform
import re
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# プロジェクトルートの .env を読む（browser_automation から見て一つ上×2）
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_ENV = SCRIPT_DIR.parent.parent / ".env"
load_dotenv(ROOT_ENV)
load_dotenv(SCRIPT_DIR / ".env")


def _tokairokin_non_interactive() -> bool:
    """Jarvis・Cursor Agent・CI 等で Enter 待ちが破綻しないようにするフラグ。"""
    v = os.environ.get("TOKAIROKIN_NON_INTERACTIVE", "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _tokairokin_non_interactive_pause_ms() -> int:
    """非対話時に Enter の代わりに待つ毫秒。ページ描画・キープアライブのため最低数百 ms は確保する。"""
    raw = os.environ.get("TOKAIROKIN_NON_INTERACTIVE_PAUSE_MS", "1800").strip()
    try:
        return max(0, min(int(raw), 120000))
    except ValueError:
        return 1800


def _wait_enter(
    confirm_msg: str = "Enter を受け付けました。次へ進みます。",
    *,
    driver=None,
    keepalive_config: dict | None = None,
):
    """Enter が押されるまで待ち、受け取ったら確認メッセージを表示。
    Cursor の統合ターミナルでは stdin に Enter が届かないことがあるため、
    まず /dev/tty（端末デバイス）から直接読みを試みる。

    driver を渡したときは別スレッドでキープアライブし、ネットバンクの無操作切断（B0470等）を抑える。

    TOKAIROKIN_NON_INTERACTIVE=1（または CLI --non-interactive）のときは Enter を読まず、
    短い固定待機で進む（Jarvis / 統合ターミナルで誤入力や無限待ちを避ける）。
    """
    cfg = keepalive_config if keepalive_config is not None else {}
    if _tokairokin_non_interactive():
        pause_ms = _tokairokin_non_interactive_pause_ms()
        stop_pulse = threading.Event()
        pulse_thr = None
        if driver is not None and cfg.get("session_keepalive_enabled", True):
            iv = float(cfg.get("wait_enter_keepalive_interval_seconds", 5))
            iv = max(2.0, min(iv, 120.0))

            def _pulse_loop():
                while not stop_pulse.wait(timeout=iv):
                    try:
                        _tokairokin_session_keepalive(driver, cfg)
                    except Exception:
                        pass

            pulse_thr = threading.Thread(
                target=_pulse_loop,
                daemon=True,
                name="tokairokin_non_interactive_keepalive",
            )
            pulse_thr.start()
        try:
            time.sleep(pause_ms / 1000.0)
        finally:
            stop_pulse.set()
            if pulse_thr is not None:
                pulse_thr.join(timeout=3.0)
        print(
            f"(TOKAIROKIN_NON_INTERACTIVE) Enter 待ちをスキップし {pause_ms} ms 待機して続行しました。",
            file=sys.stderr,
        )
        sys.stderr.flush()
        if confirm_msg:
            print(confirm_msg, file=sys.stderr)
            sys.stderr.flush()
        return

    stop_pulse = threading.Event()
    pulse_thr = None
    if driver is not None and cfg.get("session_keepalive_enabled", True):
        iv = float(cfg.get("wait_enter_keepalive_interval_seconds", 5))
        iv = max(3.0, min(iv, 120.0))

        def _pulse_loop():
            while not stop_pulse.wait(timeout=iv):
                try:
                    _tokairokin_session_keepalive(driver, cfg)
                except Exception:
                    pass

        pulse_thr = threading.Thread(
            target=_pulse_loop,
            daemon=True,
            name="tokairokin_wait_enter_keepalive",
        )
        pulse_thr.start()

    try:
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
    finally:
        stop_pulse.set()
        if pulse_thr is not None:
            pulse_thr.join(timeout=3.0)

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


def _tokairokin_default_transfer_env() -> dict:
    """東海労金振込の既定先を .env から読む（金額は含めない）。"""
    return {
        "bank_code": (os.environ.get("TOKAIROKIN_DEFAULT_BANK_CODE") or "").strip(),
        "branch_code": (os.environ.get("TOKAIROKIN_DEFAULT_BRANCH_CODE") or "").strip(),
        "bank_name": (os.environ.get("TOKAIROKIN_DEFAULT_BANK_NAME") or "").strip(),
        "branch_name": (os.environ.get("TOKAIROKIN_DEFAULT_BRANCH_NAME") or "").strip(),
        "account_number": (os.environ.get("TOKAIROKIN_DEFAULT_ACCOUNT") or "").strip(),
        "account_kind": (os.environ.get("TOKAIROKIN_DEFAULT_ACCOUNT_KIND") or "").strip(),
    }


def _apply_tokairokin_transfer_defaults(transfer: dict | None) -> dict | None:
    """transfer があれば、未指定の銀行・支店・口座を TOKAIROKIN_DEFAULT_* で補う。"""
    if transfer is None:
        return None
    d = _tokairokin_default_transfer_env()
    out = dict(transfer)
    if not (out.get("bank_code") or "").strip() and not (out.get("bank_name") or "").strip():
        out["bank_code"] = d["bank_code"]
        out["bank_name"] = d["bank_name"]
    if not (out.get("branch_code") or "").strip() and not (out.get("branch_name") or "").strip():
        out["branch_code"] = d["branch_code"]
        out["branch_name"] = d["branch_name"]
    if not (out.get("account_number") or "").strip():
        out["account_number"] = d["account_number"]
    return out


def _env_int_nonneg(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        return default


def _tokairokin_fetch_otp_from_gmail_enabled(config: dict) -> bool:
    """Gmail API で OTP を取得するか。config と TOKAIROKIN_FETCH_OTP_FROM_GMAIL で制御。"""
    v = config.get("fetch_otp_from_gmail")
    if v is not None:
        return bool(v)
    return os.environ.get("TOKAIROKIN_FETCH_OTP_FROM_GMAIL", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _tokairokin_session_keepalive(driver, config: dict | None = None) -> None:
    """ネットバンクの「一定時間無操作で中断」（B0470等）対策。クライアント操作に加え、必要なら同一URLへのHEADでサーバーに触れる。"""
    cfg = config if config is not None else {}
    try:
        driver.execute_script(
            "try { window.scrollBy(0, 2); window.scrollBy(0, -2); "
            "var b = document.body; if (b) { b.dispatchEvent(new Event('mousemove', {bubbles: true})); } "
            "} catch (e) {}"
        )
    except Exception:
        pass
    if not cfg.get("session_keepalive_fetch_head", True):
        return
    try:
        url = driver.current_url
        if not url or not url.startswith("http"):
            return
        # execute_script が Promise を返すだけだと完了前に制御が戻る場合があるため async 版で確実に待つ
        timeout_s = float(cfg.get("session_keepalive_fetch_timeout_seconds", 12))
        timeout_s = max(3.0, min(timeout_s, 60.0))
        driver.set_script_timeout(int(timeout_s) + 2)
        driver.execute_async_script(
            "var u=arguments[0], cb=arguments[arguments.length-1]; "
            "try { fetch(u,{method:'HEAD',credentials:'same-origin',cache:'no-store'})"
            ".then(function(){cb(true);}).catch(function(){cb(false);}); } catch(e) { cb(false); }",
            url,
        )
    except Exception:
        pass


def _tokairokin_page_looks_like_session_timeout(driver) -> bool:
    """画面ID BER020 / エラーコード B0470 など、無操作切断・取引中断ページのヒューリスティック。"""
    from selenium.webdriver.common.by import By

    try:
        driver.switch_to.default_content()
        src = driver.page_source or ""
        body = ""
        try:
            body = driver.find_element(By.TAG_NAME, "body").text or ""
        except Exception:
            pass
        hay = src + "\n" + body
        if "B0470" in hay or "BER020" in hay:
            return True
        if "お取引を中断" in hay and ("一定時間" in hay or "自動的に" in hay):
            return True
    except Exception:
        pass
    return False


def _tokairokin_switch_to_frame_containing_selectors(driver, probes: list[str], max_depth: int) -> bool:
    """いずれかのセレクタが見つかるフレームへ driver を切り替える。見つからなければ default_content のまま False。"""
    driver.switch_to.default_content()
    plist = [(p or "").strip() for p in probes if (p or "").strip()]
    if not plist:
        return True

    def probe_here() -> bool:
        for sel in plist:
            try:
                if _tokairokin_transfer_find(driver, sel) is not None:
                    return True
            except Exception:
                continue
        return False

    def dfs(depth: int) -> bool:
        if probe_here():
            return True
        if depth >= max_depth:
            return False
        frames = driver.find_elements(By.TAG_NAME, "iframe")
        for idx in range(len(frames)):
            try:
                frames_now = driver.find_elements(By.TAG_NAME, "iframe")
                if idx >= len(frames_now):
                    break
                driver.switch_to.frame(frames_now[idx])
                if dfs(depth + 1):
                    return True
                driver.switch_to.parent_frame()
            except Exception:
                try:
                    driver.switch_to.parent_frame()
                except Exception:
                    try:
                        driver.switch_to.default_content()
                    except Exception:
                        pass
        return False

    ok = dfs(0)
    if not ok:
        try:
            driver.switch_to.default_content()
        except Exception:
            pass
    return ok


def _tokairokin_transfer_find(driver, sel: str):
    """transfer_form 用セレクタで要素を1件取得（XPath は先頭 / または (）。"""
    from selenium.webdriver.common.by import By

    s = (sel or "").strip()
    if not s:
        return None
    if s.startswith("/") or s.startswith("("):
        by, val = By.XPATH, s
    else:
        val = s if s.startswith(("#", ".", "[", "input")) else f"#{s}"
        by, val = By.CSS_SELECTOR, val
    try:
        return driver.find_element(by, val)
    except Exception:
        return None


def _tokairokin_wait_clickable_with_keepalive(
    driver,
    config: dict,
    selector: str,
    timeout_s: int,
    frame_probes: list[str] | None = None,
):
    """無操作切断を抑えつつ、要素が表示・有効になるまでポーリング。失敗時は None。

    frame_probes にセレクタを渡すと default のほか iframe を深さ優先で探索し、
    メインコンテンツだけでは見えない振込フォームに対応する。
    """
    if not (selector or "").strip():
        return None
    enabled = config.get("session_keepalive_enabled", True)
    pulse = float(config.get("session_keepalive_interval_seconds", 8))
    poll = float(config.get("session_keepalive_poll_seconds", 1.0))
    poll = max(0.3, min(poll, 5.0))
    pulse = max(3.0, pulse)
    deadline = time.monotonic() + max(1, int(timeout_s))
    last_pulse = 0.0
    search_frames = bool(config.get("transfer_form_search_iframes", True))
    probes = [p for p in (frame_probes or []) if (p or "").strip()]
    max_depth = int(config.get("transfer_form_iframe_max_depth", 5))
    max_depth = max(1, min(max_depth, 12))
    every_poll_dom = bool(config.get("session_keepalive_every_poll_during_form_wait", True))

    while time.monotonic() < deadline:
        try:
            if _tokairokin_page_looks_like_session_timeout(driver):
                print(
                    "無操作切断または取引中断画面を検知しました（B0470 / BER020 等）。セレクタ待機を中止します。",
                    file=sys.stderr,
                )
                try:
                    driver.switch_to.default_content()
                except Exception:
                    pass
                return None
            if search_frames and probes:
                _tokairokin_switch_to_frame_containing_selectors(driver, probes, max_depth)
            else:
                driver.switch_to.default_content()

            el = _tokairokin_transfer_find(driver, selector)
            if el is not None and el.is_displayed() and el.is_enabled():
                return el
        except Exception:
            pass
        now = time.monotonic()
        if every_poll_dom and enabled:
            try:
                driver.execute_script(
                    "try { window.scrollBy(0, 1); window.scrollBy(0, -1); } catch (e) {}"
                )
            except Exception:
                pass
        if enabled and now - last_pulse >= pulse:
            _tokairokin_session_keepalive(driver, config)
            last_pulse = now
        time.sleep(min(poll, max(0.1, deadline - time.monotonic())))
    try:
        driver.switch_to.default_content()
    except Exception:
        pass
    return None


def _tokairokin_js_scroll_click(driver, el) -> bool:
    """オーバーレイや Selenium のクリック阻害があるとき向けにスクロールしてから JS クリック。"""
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        time.sleep(0.25)
        driver.execute_script("arguments[0].click();", el)
        return True
    except Exception:
        return False


def _tokairokin_transfer_page_initial_pulse(driver, config: dict) -> bool:
    """振込URL直後に短周期キープアライブし、無操作切断までの時間を稼ぐ。タイムアウト画面なら False。"""
    burst = int(config.get("transfer_page_keepalive_burst_count", 12))
    burst = max(0, min(burst, 40))
    delay = float(config.get("transfer_page_keepalive_burst_interval_seconds", 0.35))
    delay = max(0.1, min(delay, 2.0))
    for _ in range(burst):
        if _tokairokin_page_looks_like_session_timeout(driver):
            print(
                "振込画面への遷移直後に無操作切断画面（B0470 / BER020）が表示されています。",
                file=sys.stderr,
            )
            return False
        _tokairokin_session_keepalive(driver, config)
        time.sleep(delay)
    return True


def _tokairokin_recover_top_after_direct_transfer_timeout(
    driver,
    config: dict,
    pre_nav_url: str,
) -> bool:
    """振込Dispatchを URL 直叩きした直後に B0470 だけが出たとき、セッションは生きていることがある。
    ログイン後トップへ戻り、メニュー／リンククリックのフォールバックへ渡す。
    """
    if not config.get("transfer_direct_fallback_to_menu_on_b0470", True):
        return False
    u = (pre_nav_url or "").strip()
    if not u.startswith("http"):
        return False
    try:
        driver.get(u)
        time.sleep(float(config.get("wait_after_page", 2) or 2))
        for _ in range(4):
            if _tokairokin_page_looks_like_session_timeout(driver):
                return False
            _tokairokin_session_keepalive(driver, config)
            time.sleep(0.45)
        if _tokairokin_page_looks_like_session_timeout(driver):
            return False
        print(
            "振込URLの直接遷移直後に無操作切断画面が出ました。"
            " セッション維持のためログイン後トップへ戻り、画面上の「振込」等から遷移を試します。",
            file=sys.stderr,
        )
        return True
    except Exception:
        return False


def _get_secret_phrase_answer(mapping: dict):
    """合言葉のマッピングから回答を取得。answer_env または answer を参照。"""
    env_key = mapping.get("answer_env")
    if env_key:
        return os.environ.get(env_key)
    return mapping.get("answer")


def _tokairokin_post_login_dashboard_detected(
    current_url: str,
    body_text: str,
    html_snippet: str,
    config: dict,
) -> bool:
    """ログイン後トップ（合言葉なしルート）か。URL と本文で判定し、合言葉画面と両立しないようにする。"""
    if _tokairokin_secret_phrase_screen_detected(body_text, html_snippet, config):
        return False
    det = config.get("post_login_dashboard_detect") or {}
    url_patterns = det.get("url_contains_any")
    if url_patterns is None:
        url_patterns = ["BLI001Dispatch"]
    elif isinstance(url_patterns, str):
        url_patterns = [url_patterns]
    else:
        url_patterns = list(url_patterns)
    url = current_url or ""
    if not any(str(p).strip() and str(p) in url for p in url_patterns):
        return False
    body_markers = det.get("body_contains_any")
    if body_markers is None:
        body_markers = ["トップページ", "振込振替", "残高照会", "口座情報"]
    elif isinstance(body_markers, str):
        body_markers = [body_markers]
    else:
        body_markers = list(body_markers)
    hay = (body_text or "") + "\n" + (html_snippet or "")
    return any(str(m).strip() and str(m) in hay for m in body_markers)


def _tokairokin_secret_phrase_screen_detected(body_text: str, html_snippet: str, config: dict) -> bool:
    """合言葉・あいことば等の追加認証画面かどうか。文言はサイトにより異なるため markers で拡張可能。"""
    markers = config.get("secret_phrase_page_markers")
    if markers is None:
        markers = [
            "追加認証（合言葉認証）",
            "追加認証の入力",
            "BLI017",
            "母親の誕生日",
            "[必須] 回答",
            "合言葉",
            "あいことば",
            "秘密の質問",
            "確認用の質問",
            "質問にお答え",
            "お答えください",
            "追加認証",
        ]
    elif isinstance(markers, str):
        markers = [markers]
    else:
        markers = list(markers)
    hay = (body_text or "") + "\n" + (html_snippet or "")
    return any((str(m).strip() and str(m) in hay) for m in markers)


def _tokairokin_secret_phrase_haystack(driver, config: dict) -> tuple[str, str]:
    """メインフレームおよび iframe 内の本文を結合。parasol 系で追加認証が iframe 内のみにある場合がある。"""
    from selenium.webdriver.common.by import By

    parts: list[str] = []
    driver.switch_to.default_content()
    try:
        parts.append(driver.find_element(By.TAG_NAME, "body").text)
    except Exception:
        pass
    html_root = driver.page_source or ""
    if config.get("secret_phrase_check_iframes", True):
        frames = driver.find_elements(By.TAG_NAME, "iframe")
        for frame in frames:
            try:
                driver.switch_to.default_content()
                driver.switch_to.frame(frame)
                parts.append(driver.find_element(By.TAG_NAME, "body").text)
            except Exception:
                pass
            finally:
                try:
                    driver.switch_to.default_content()
                except Exception:
                    pass
    combined_body = "\n".join(parts)
    return combined_body, html_root


def _tokairokin_poll_secret_challenge_visible(
    driver,
    config: dict,
    secret_phrase_auto: list,
    *,
    max_wait_override: int | None = None,
) -> bool:
    """ログイン送信後、質問・合言葉の文言が DOM に載るまで待つ。

    描画が遅い SPA や、「再ログイン」が先に見えて質問が後から載る構成で、早押しすると
    目視でも質問が出ないように見える／検出もできない問題を抑える。
    """
    max_wait = int(
        max_wait_override
        if max_wait_override is not None
        else config.get("secret_phrase_dom_wait_seconds", 25)
    )
    if max_wait <= 0:
        return False
    poll = float(config.get("secret_phrase_dom_poll_seconds", 0.5))
    poll = max(0.15, min(poll, 3.0))
    deadline = time.monotonic() + max_wait
    while time.monotonic() < deadline:
        bt, hs = _tokairokin_secret_phrase_haystack(driver, config)
        hay = (bt or "") + "\n" + (hs or "")
        if _tokairokin_secret_phrase_screen_detected(bt, hs, config):
            return True
        for m in secret_phrase_auto:
            mk = (m.get("match") or "").strip()
            if mk and mk in hay:
                return True
        _tokairokin_session_keepalive(driver, config)
        time.sleep(min(poll, max(0.05, deadline - time.monotonic())))
    return False


def _tokairokin_try_secret_phrase_autofill_one_context(driver, config: dict, hay_q: str, secret_phrase_auto: list) -> bool:
    """現在の frame コンテキストで match に一致する質問があれば入力〜送信。"""
    from selenium.webdriver.common.by import By

    for mapping in secret_phrase_auto:
        match_kw = (mapping.get("match") or "").strip()
        if not match_kw or match_kw not in hay_q:
            continue
        answer = _get_secret_phrase_answer(mapping)
        if not answer:
            continue
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
            for btn_text in ["確認", "送信", "次へ", "認証", "実行", "ログイン", "確認する", "送信する"]:
                try:
                    btn = driver.find_element(
                        By.XPATH,
                        f"//input[@value='{btn_text}'] | //button[contains(text(),'{btn_text}')] | //a[contains(text(),'{btn_text}')]",
                    )
                    if btn.is_displayed():
                        btn.click()
                        print(f"合言葉を自動入力しました（キーワード: {match_kw[:20]}...）", file=sys.stderr)
                        time.sleep(3)
                        return True
                except Exception:
                    continue
    return False


def _tokairokin_try_secret_phrase_autofill_selenium(driver, config: dict) -> bool:
    """合言葉画面を検出したときだけ入力〜送信まで試す。成功時 True。iframe 内も探索する。"""
    from selenium.webdriver.common.by import By

    secret_phrase_auto = config.get("secret_phrase_auto") or []
    if not secret_phrase_auto:
        return False
    combined_body, html_src = _tokairokin_secret_phrase_haystack(driver, config)
    hay_q = (combined_body or "") + "\n" + (html_src or "")
    if not _tokairokin_secret_phrase_screen_detected(combined_body, html_src, config):
        return False

    driver.switch_to.default_content()
    if _tokairokin_try_secret_phrase_autofill_one_context(driver, config, hay_q, secret_phrase_auto):
        return True

    if not config.get("secret_phrase_check_iframes", True):
        return False
    frames = driver.find_elements(By.TAG_NAME, "iframe")
    for frame in frames:
        try:
            driver.switch_to.default_content()
            driver.switch_to.frame(frame)
            try:
                sub_body = driver.find_element(By.TAG_NAME, "body").text
            except Exception:
                sub_body = ""
            sub_hay = hay_q + "\n" + sub_body
            if _tokairokin_try_secret_phrase_autofill_one_context(driver, config, sub_hay, secret_phrase_auto):
                driver.switch_to.default_content()
                return True
        except Exception:
            pass
        finally:
            try:
                driver.switch_to.default_content()
            except Exception:
                pass
    return False


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


def _run_tokairokin_undetected(
    config: dict,
    user: str,
    password: str,
    headless: bool,
    transfer: dict = None,
    inspect_transfer_screen: bool = False,
) -> str:
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

    inspect_pause = bool(inspect_transfer_screen or config.get("pause_for_transfer_screen_inspect"))

    def _offer_transfer_screen_inspect(how: str) -> None:
        """振込URL到達直後に DevTools でセレクタ検証できるよう一時停止。"""
        if not inspect_pause or not transfer:
            return
        print("\n" + "=" * 60, file=sys.stderr)
        print(f"【検証用一時停止】振込画面へ遷移しました（{how}）。", file=sys.stderr)
        print(
            "  この画面のまま開発者ツールでセレクタを確認してください。"
            " 終わったらこのターミナルで Enter を押すと自動入力を続けます。",
            file=sys.stderr,
        )
        print("=" * 60 + "\n", file=sys.stderr)
        _tokairokin_session_keepalive(driver, config)
        _wait_enter(driver=driver, keepalive_config=config)
        _tokairokin_session_keepalive(driver, config)

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

        wl = max(1, int(wait_login))
        for _ in range(wl):
            time.sleep(1)
            if config.get("session_keepalive_enabled", True):
                _tokairokin_session_keepalive(driver, config)

        body_text = driver.find_element(By.TAG_NAME, "body").text
        if "エラー" in body_text or "認証に失敗" in body_text or "ログインに失敗" in body_text or "口座情報が誤っています" in body_text:
            print("ログインに失敗した可能性があります。画面を確認してください。", file=sys.stderr)

        print("東海労金へのログイン処理が完了しました。")

        # 合言葉の自動入力（ログイン送信直後）
        secret_phrase_filled = False
        secret_phrase_auto = config.get("secret_phrase_auto") or []
        if secret_phrase_auto:
            if _tokairokin_poll_secret_challenge_visible(driver, config, secret_phrase_auto):
                print(
                    "質問・合言葉の文言を DOM で検出しました（ログイン直後の待機ポーリング）。"
                    " 自動入力を試みます。",
                    file=sys.stderr,
                )
            secret_phrase_filled = _tokairokin_try_secret_phrase_autofill_selenium(driver, config)
            if secret_phrase_filled:
                time.sleep(2)
                body_text = driver.find_element(By.TAG_NAME, "body").text
                for relogin_kw in ["再ログイン", "サインイン", "ログイン"]:
                    try:
                        el = driver.find_element(
                            By.XPATH,
                            f"//a[contains(text(),'{relogin_kw}')] | //button[contains(text(),'{relogin_kw}')] | //input[@value='{relogin_kw}']",
                        )
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

        # 「再ログイン」クリック後にだけ合言葉画面が出る場合があるため再試行
        if secret_phrase_auto and not secret_phrase_filled:
            aw2 = int(config.get("secret_phrase_dom_wait_seconds_after_relogin", 15))
            if aw2 > 0:
                _tokairokin_poll_secret_challenge_visible(
                    driver,
                    config,
                    secret_phrase_auto,
                    max_wait_override=aw2,
                )
            secret_phrase_filled = _tokairokin_try_secret_phrase_autofill_selenium(driver, config)
            if secret_phrase_filled:
                time.sleep(2)
                body_text = driver.find_element(By.TAG_NAME, "body").text
                for relogin_kw in ["再ログイン", "サインイン", "ログイン"]:
                    try:
                        el = driver.find_element(
                            By.XPATH,
                            f"//a[contains(text(),'{relogin_kw}')] | //button[contains(text(),'{relogin_kw}')] | //input[@value='{relogin_kw}']",
                        )
                        if el.is_displayed() and relogin_kw in body_text:
                            el.click()
                            print(f"「{relogin_kw}」をクリックしました。", file=sys.stderr)
                            time.sleep(3)
                            break
                    except Exception:
                        continue

        skip_secret_phrase_pause_for_dashboard = False
        if secret_phrase_auto and not secret_phrase_filled:
            bt, hs = _tokairokin_secret_phrase_haystack(driver, config)
            if not _tokairokin_secret_phrase_screen_detected(bt, hs, config):
                try:
                    curl = driver.current_url or ""
                except Exception:
                    curl = ""
                if _tokairokin_post_login_dashboard_detected(curl, bt, hs, config):
                    skip_secret_phrase_pause_for_dashboard = True
                    print(
                        "合言葉（追加認証）画面は検出されませんでした。"
                        " ログイン後トップページ相当と判断し、合言葉の Enter 待ちをスキップして振込処理へ進みます。",
                        file=sys.stderr,
                    )
                else:
                    print(
                        "secret_phrase_auto は設定されていますが、合言葉系画面の検出キーワードが"
                        " メイン・iframe 結合テキストおよび HTML に見つかりませんでした（ログイン直後・再ログイン後のいずれでもなし）。"
                        " secret_phrase_page_markers に実画面の文言を追加するか、本当に合言葉なしルートか確認してください。",
                        file=sys.stderr,
                    )
            else:
                print(
                    "合言葉系画面は検出できましたが自動入力に失敗しました。"
                    " secret_phrase_auto の match が質問文に含まれるか、TOKAIROKIN_SECRET_*・入力欄セレクタを確認してください。",
                    file=sys.stderr,
                )

        # 合言葉は自動入力対応済み。自動入力できなかった場合のみここで一時停止（ワンタイムパスワードは手動入力）
        if (
            not secret_phrase_filled
            and not skip_secret_phrase_pause_for_dashboard
            and config.get("pause_for_secret_phrase", True)
        ):
            if _tokairokin_non_interactive():
                print(
                    "警告: 非対話モードですが合言葉が自動入力されていません。"
                    " secret_phrase_auto と TOKAIROKIN_SECRET_* を設定しないとログイン後に失敗しやすいです。",
                    file=sys.stderr,
                )
            print("\n" + "=" * 60, file=sys.stderr)
            print("【一時停止】合言葉は通常は自動入力で対応しています。", file=sys.stderr)
            print("  自動入力が完了したら、このターミナルで Enter キーを押して次へ進んでください。", file=sys.stderr)
            print("  ※ Enter を押しても次に進まない場合は、**Terminal.app** で同じコマンドを実行してください。", file=sys.stderr)
            print("=" * 60 + "\n", file=sys.stderr)
            _wait_enter(driver=driver, keepalive_config=config)

        # 振込画面への遷移（各試行を記録し、試行履歴に反映する）
        go_to_transfer = config.get("go_to_transfer", True)
        transfer_attempt_log = []  # [{ "step": "名前", "result": "success"|"failed"|"skipped", "detail": "..." }, ...]

        if go_to_transfer:
            wait_before = int(config.get("wait_before_transfer_menu", 5))
            # Jarvis 等では長い無操作が B0470 を誘発しやすいので上限をかける
            if _tokairokin_non_interactive():
                cap = _env_int_nonneg("TOKAIROKIN_NON_INTERACTIVE_TRANSFER_MENU_WAIT_CAP", 2)
                wait_before = max(1, min(wait_before, max(1, cap)))
            # ログイン直後〜振込遷移まで無操作だとネットバンク側でセッション切断されることがある
            if config.get("session_keepalive_enabled", True):
                for _ in range(max(1, int(wait_before))):
                    time.sleep(1)
                    _tokairokin_session_keepalive(driver, config)
            else:
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
            # transfer_direct で B0470 になったあとフォールバッククリックすると Selenium が長いスタックトレースを出すだけなので抑止する
            xfer_nav_aborted = False
            # 振込画面へ直接URLで遷移（クリック不要・確実）
            transfer_direct_url = config.get("transfer_direct_url", "").strip()
            transfer_direct_path = config.get("transfer_direct_path", "").strip()
            if transfer_direct_url and transfer_direct_url.startswith("http"):
                try:
                    pre_nav_url = driver.current_url
                    driver.get(transfer_direct_url)
                    _tokairokin_session_keepalive(driver, config)
                    time.sleep(config.get("wait_after_page", 2) or 3)
                    pulse_ok = _tokairokin_transfer_page_initial_pulse(driver, config)
                    xfer_dead = _tokairokin_page_looks_like_session_timeout(driver)
                    if not pulse_ok or xfer_dead:
                        recovered = _tokairokin_recover_top_after_direct_transfer_timeout(
                            driver, config, pre_nav_url
                        )
                        if recovered:
                            xfer_nav_aborted = False
                            transfer_attempt_log.append(
                                {
                                    "step": "transfer_direct_url（フルURL直接遷移）",
                                    "result": "failed",
                                    "detail": "遷移直後に B0470 → トップへ復帰しメニュー遷移を試行",
                                }
                            )
                        else:
                            xfer_nav_aborted = True
                            transfer_attempt_log.append(
                                {
                                    "step": "transfer_direct_url（フルURL直接遷移）",
                                    "result": "failed",
                                    "detail": "遷移直後に無操作切断画面（B0470 / BER020）を検知",
                                }
                            )
                            print(
                                "振込URL直後に無操作切断画面が表示されています。セッションが切れている可能性があります。"
                                " やり直すか、ブラウザでホームから振込まで手動で進めてください。",
                                file=sys.stderr,
                            )
                    else:
                        print("振込画面へ直接URLで遷移しました。", file=sys.stderr)
                        transfer_clicked = True
                        transfer_attempt_log.append({"step": "transfer_direct_url（フルURL直接遷移）", "result": "success", "detail": ""})
                        _offer_transfer_screen_inspect("transfer_direct_url")
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
                            pre_nav_url = current
                            driver.get(new_url)
                            _tokairokin_session_keepalive(driver, config)
                            time.sleep(config.get("wait_after_page", 2) or 3)
                            pulse_ok = _tokairokin_transfer_page_initial_pulse(driver, config)
                            xfer_dead = _tokairokin_page_looks_like_session_timeout(driver)
                            if not pulse_ok or xfer_dead:
                                recovered = _tokairokin_recover_top_after_direct_transfer_timeout(
                                    driver, config, pre_nav_url
                                )
                                if recovered:
                                    xfer_nav_aborted = False
                                    transfer_attempt_log.append(
                                        {
                                            "step": f"transfer_direct_path（{transfer_direct_path} へパス置換）",
                                            "result": "failed",
                                            "detail": "遷移直後に B0470 → トップへ復帰しメニュー遷移を試行",
                                        }
                                    )
                                else:
                                    xfer_nav_aborted = True
                                    transfer_attempt_log.append(
                                        {
                                            "step": f"transfer_direct_path（{transfer_direct_path} へパス置換）",
                                            "result": "failed",
                                            "detail": "遷移直後に無操作切断画面（B0470 / BER020）を検知",
                                        }
                                    )
                                    print(
                                        "振込URL直後に無操作切断画面が表示されています。セッションが切れている可能性があります。"
                                        " やり直すか、ブラウザでホームから振込まで手動で進めてください。",
                                        file=sys.stderr,
                                    )
                            else:
                                print(f"振込画面へ直接遷移しました（{transfer_direct_path}）。", file=sys.stderr)
                                transfer_clicked = True
                                transfer_attempt_log.append({"step": f"transfer_direct_path（{transfer_direct_path} へパス置換）", "result": "success", "detail": ""})
                                _offer_transfer_screen_inspect(f"path:{transfer_direct_path}")
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
            if xfer_nav_aborted:
                print(
                    "無操作切断検知済みのため、振込メニューの自動クリック（フォールバック）はスキップします。",
                    file=sys.stderr,
                )
            if not xfer_nav_aborted and not transfer_clicked and transfer_btn_selector:
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
            if not xfer_nav_aborted and not transfer_clicked:
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
            if not xfer_nav_aborted and not transfer_clicked:
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

            if not xfer_nav_aborted and not transfer_clicked:
                if config.get("manual_click_transfer_menu", True):
                    transfer_attempt_log.append({"step": "手動クリックの案内（Enter待ち）", "result": "success", "detail": "ユーザーに振込クリックを依頼"})
                    print("\n" + "=" * 60, file=sys.stderr)
                    print("【手動クリック】画面上で「この口座から」の「振込」をクリックしてください。", file=sys.stderr)
                    print("  クリックしたら、ターミナルにフォーカスを移して Enter キーを押してください。", file=sys.stderr)
                    print("=" * 60 + "\n", file=sys.stderr)
                    _wait_enter(driver=driver, keepalive_config=config)
                    time.sleep(3)
                else:
                    # 自動クリック（従来どおり・キーワード検索）
                    transfer_attempt_log.append({"step": "キーワード検索で振込クリック", "result": "pending", "detail": "試行中"})
                    if config.get("pause_before_transfer_click", True):
                        print("\n" + "=" * 60, file=sys.stderr)
                        print("【振込画面へ進む前】「パスワードを保存しますか？」が出ている場合は、", file=sys.stderr)
                        print("  「使用しない」または「保存」で閉じてください。閉じたら Enter キーを押してください。", file=sys.stderr)
                        print("=" * 60 + "\n", file=sys.stderr)
                        _wait_enter(driver=driver, keepalive_config=config)
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
        if transfer:
            has_bank = transfer.get("bank_code") or transfer.get("bank_name")
            has_branch = transfer.get("branch_code") or transfer.get("branch_name")
            form_ready = (
                has_bank and has_branch and transfer.get("account_number") and transfer.get("amount")
            )
        else:
            form_ready = False
        transfer_form_dead = False
        if form_ready:
            time.sleep(config.get("wait_after_page", 2))
            tf = config.get("transfer_form") or {}

            specify_sel = tf.get("specify_destination_button_selector", "").strip()
            bank_probe = (tf.get("bank_code_selector") or "").strip()
            branch_probe = (tf.get("branch_code_selector") or "").strip()
            frame_probes = [x for x in (specify_sel, bank_probe, branch_probe) if x]
            iframe_depth = int(config.get("transfer_form_iframe_max_depth", 5))
            iframe_depth = max(1, min(iframe_depth, 12))

            _tokairokin_transfer_page_initial_pulse(driver, config)
            transfer_form_dead = bool(_tokairokin_page_looks_like_session_timeout(driver))
            if transfer_form_dead:
                print(
                    "振込フォーム処理の前に無操作切断画面（B0470 / BER020）を検知しました。"
                    " タイマー起因でボタンが無効のままになることがあります。ログイン〜振込までをやり直してください。",
                    file=sys.stderr,
                )

            # 振込画面で「振込時間の案内」等が消え、振込先入力が使えるまで明示的に待つ（iframe 内も探索）
            wait_form_ready = int(config.get("wait_for_transfer_form_ready", 30))
            if not transfer_form_dead and wait_form_ready > 0 and specify_sel:
                _tokairokin_session_keepalive(driver, config)
                el_form = _tokairokin_wait_clickable_with_keepalive(
                    driver,
                    config,
                    specify_sel,
                    wait_form_ready,
                    frame_probes=frame_probes,
                )
                if el_form is not None:
                    print(
                        f"振込入力フォームの準備ができました（最大{wait_form_ready}秒・無操作対策のキープアライブあり）。",
                        file=sys.stderr,
                    )
                else:
                    print(
                        f"「振込先を指定」相当ボタンが{wait_form_ready}秒以内に操作可能になりませんでした（セレクタ: {specify_sel!r}）。"
                        " iframe 外の別ボタンの可能性があります。--inspect-transfer-screen で DOM を確認してください。",
                        file=sys.stderr,
                    )
            time.sleep(0.5)

            # 日付振込ボタン（セレクタ指定時のみクリック試行）
            dated_btn_sel = config.get("transfer_dated_transfer_button_selector", "").strip()
            if not transfer_form_dead and dated_btn_sel:
                try:
                    if config.get("transfer_form_search_iframes", True) and frame_probes:
                        _tokairokin_switch_to_frame_containing_selectors(driver, frame_probes, iframe_depth)
                    by = By.XPATH if (dated_btn_sel.startswith("/") or dated_btn_sel.startswith("(")) else By.CSS_SELECTOR
                    el = driver.find_element(by, dated_btn_sel)
                    if el.is_displayed():
                        if _tokairokin_js_scroll_click(driver, el):
                            print("「日付振込」をクリックしました。", file=sys.stderr)
                        else:
                            el.click()
                            print("「日付振込」をクリックしました。", file=sys.stderr)
                        time.sleep(config.get("wait_after_page", 2))
                except Exception as e:
                    print(f"「日付振込」ボタンのクリックに失敗しました: {e}", file=sys.stderr)

            # 振込先選択画面で「振込先を指定」ボタンをクリック（金融機関選択画面へ遷移）
            specify_clicked = False
            specify_sel = tf.get("specify_destination_button_selector", "").strip()
            if not transfer_form_dead and specify_sel:
                try:
                    if config.get("transfer_form_search_iframes", True) and frame_probes:
                        _tokairokin_switch_to_frame_containing_selectors(driver, frame_probes, iframe_depth)
                    el = _tokairokin_transfer_find(driver, specify_sel)
                    if el is not None and el.is_displayed():
                        specify_clicked = _tokairokin_js_scroll_click(driver, el)
                        if not specify_clicked:
                            try:
                                el.click()
                                specify_clicked = True
                            except Exception:
                                specify_clicked = False
                        if specify_clicked:
                            print("「振込先を指定」をクリックしました。", file=sys.stderr)
                            time.sleep(config.get("wait_after_page", 2))
                except Exception:
                    pass
            if not transfer_form_dead and not specify_clicked:
                if config.get("transfer_form_search_iframes", True) and frame_probes:
                    _tokairokin_switch_to_frame_containing_selectors(driver, frame_probes, iframe_depth)
                for btn_text in ["振込先を指定", "振込先を選択"]:
                    try:
                        el = driver.find_element(By.XPATH, f"//input[@value='{btn_text}'] | //button[contains(text(),'{btn_text}')] | //a[contains(text(),'{btn_text}')]")
                        if el.is_displayed():
                            if _tokairokin_js_scroll_click(driver, el):
                                specify_clicked = True
                            else:
                                el.click()
                                specify_clicked = True
                            print(f"「{btn_text}」をクリックしました。", file=sys.stderr)
                            time.sleep(config.get("wait_after_page", 2))
                            break
                    except Exception:
                        continue
            if specify_clicked:
                time.sleep(config.get("wait_after_page", 2))

            try:
                driver.switch_to.default_content()
            except Exception:
                pass
            if not transfer_form_dead and config.get("transfer_form_search_iframes", True) and frame_probes:
                _tokairokin_switch_to_frame_containing_selectors(driver, frame_probes, iframe_depth)
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

            if transfer_form_dead:
                print(
                    "無操作切断画面のため、銀行・支店・金額の自動入力以降をスキップします。",
                    file=sys.stderr,
                )

            # 1. 銀行コード入力 → 検索 → 検索結果の「選択」クリック
            if not transfer_form_dead and _try_fill("bank_code_selector", bank_input):
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
            if not transfer_form_dead and transfer_filled and _try_fill("branch_code_selector", branch_input):
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
            if not transfer_form_dead:
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
            if not transfer_form_dead and transfer_filled and _click_confirm(
                "execution_screen_button_selector", ["実行画面へ", "実行画面", "次へ"]
            ):
                print("実行画面へボタンをクリックしました。", file=sys.stderr)
                time.sleep(config.get("wait_after_page", 2))

            # 5. 「確認しました」チェックボックスにチェック
            if not transfer_form_dead and transfer_filled:
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

        # ワンタイムパスワード（OTP）: Gmail API で取得して入力するか、手動入力
        if (transfer or transfer_filled) and not transfer_form_dead:
            tf_otp = config.get("transfer_form") or {}
            otp_pause = config.get("pause_for_otp", True)
            fetch_gmail = _tokairokin_fetch_otp_from_gmail_enabled(config)
            otp_sel = (tf_otp.get("otp_input_selector") or "").strip()
            gmail_filled = False

            def _otp_find_el(sel: str):
                sel = (sel or "").strip()
                if not sel:
                    return None
                if sel.startswith("/") or sel.startswith("("):
                    by, val = By.XPATH, sel
                else:
                    val = sel if sel.startswith(("#", ".", "[", "input")) else f"#{sel}"
                    by, val = By.CSS_SELECTOR, val
                try:
                    el = driver.find_element(by, val)
                    return el if el.is_displayed() else None
                except Exception:
                    return None

            if fetch_gmail and otp_sel:
                pause_ms = _env_int_nonneg("TOKAIROKIN_PAUSE_BEFORE_GMAIL_OTP_MS", 3000)
                if pause_ms:
                    print(
                        f"⏳ OTP メールの届きを待つため {pause_ms} ms 待機します（TOKAIROKIN_PAUSE_BEFORE_GMAIL_OTP_MS）。",
                        file=sys.stderr,
                    )
                    time.sleep(pause_ms / 1000.0)
                marker_ms = int(time.time() * 1000)
                base_lb = _env_int_nonneg("TOKAIROKIN_OTP_GMAIL_BASE_LOOKBACK_MS", 120000)
                min_internal = max(0, marker_ms - base_lb)
                to_email = os.environ.get(
                    "TOKAIROKIN_GMAIL_EXPECT_EMAIL",
                    "m19m.hrts83@gmail.com",
                ).strip()
                try:
                    from tokairokin_gmail_otp import poll_tokairokin_otp_from_gmail

                    otp_code = poll_tokairokin_otp_from_gmail(
                        to_email=to_email,
                        min_internal_date_ms=min_internal,
                    )
                    el_otp = _otp_find_el(otp_sel)
                    if el_otp:
                        try:
                            el_otp.clear()
                            el_otp.send_keys(otp_code)
                            gmail_filled = True
                            print(
                                "ワンタイムパスワードを Gmail から取得し、入力欄へ反映しました（番号は表示しません）。",
                                file=sys.stderr,
                            )
                        except Exception as ex:
                            print(f"OTP の自動入力に失敗しました: {ex}", file=sys.stderr)
                    else:
                        print(
                            f"OTP 入力欄が見つかりません（otp_input_selector）。手動で入力してください。",
                            file=sys.stderr,
                        )
                    submit_sel = (tf_otp.get("otp_submit_selector") or "").strip()
                    if gmail_filled and submit_sel:
                        btn = _otp_find_el(submit_sel)
                        if btn:
                            try:
                                btn.click()
                                print(
                                    "OTP 送信・確定ボタン（otp_submit_selector）をクリックしました。",
                                    file=sys.stderr,
                                )
                                time.sleep(config.get("wait_after_page", 2))
                            except Exception as ex:
                                print(f"OTP 送信ボタンのクリックに失敗: {ex}", file=sys.stderr)
                except ImportError as ie:
                    print(
                        "Gmail OTP 用ライブラリが未インストールです（google-api-python-client 等）。"
                        f" browser_automation で pip install -r requirements.txt を実行してください: {ie}",
                        file=sys.stderr,
                    )
                except Exception as e:
                    print(f"Gmail から OTP を取得できませんでした: {e}", file=sys.stderr)
            elif fetch_gmail and not otp_sel:
                print(
                    "fetch_otp_from_gmail は有効ですが transfer_form.otp_input_selector が空です。"
                    " プルデンシャル生命の Gmail OTP と同様に使うにはセレクタを設定してください。"
                    " 参照: finance/prudential_gmail_otp.py（poll_prudential_otp_from_gmail）、"
                    "browser_automation/tokairokin_gmail_otp.py（poll_tokairokin_otp_from_gmail）。",
                    file=sys.stderr,
                )

            if otp_pause:
                print("\n" + "=" * 60, file=sys.stderr)
                if gmail_filled:
                    print(
                        "【確認】画面上で OTP・振込実行を確認してください。"
                        " 問題なければこのターミナルで Enter を押してください。",
                        file=sys.stderr,
                    )
                else:
                    print("【一時停止】ワンタイムパスワード（OTP）を入力してください。", file=sys.stderr)
                    print(
                        "  メール・アプリで OTP を確認しブラウザへ入力するか、"
                        " Gmail 自動取得は TOKAIROKIN_OTP_GMAIL_* と otp_input_selector で調整してください。",
                        file=sys.stderr,
                    )
                    print(
                        "  完了したら、このターミナルで Enter キーを押して次へ進んでください。",
                        file=sys.stderr,
                    )
                print("=" * 60 + "\n", file=sys.stderr)
                _wait_enter(driver=driver, keepalive_config=config)

        if config.get("keep_browser_open", True):
            print("\n" + "=" * 60, file=sys.stderr)
            print("振込画面を開いたままにしています。確認や振込をゆっくり行えます。", file=sys.stderr)
            print("", file=sys.stderr)
            print("  ** ブラウザはスクリプトでは閉じません。**", file=sys.stderr)
            print("  作業が終わったら、**ご自身でブラウザを閉じ**てください。", file=sys.stderr)
            print("  ブラウザを閉じたあと、このターミナルで Enter を押すとスクリプトが終了します。", file=sys.stderr)
            print("  （先に Enter を押すとスクリプト終了時にブラウザも閉じる場合があります）", file=sys.stderr)
            print("=" * 60 + "\n", file=sys.stderr)
            _wait_enter(
                confirm_msg="スクリプトを終了しました。",
                driver=driver,
                keepalive_config=config,
            )

        return ""
    except Exception as e:
        # 途中でエラーが出ても Enter 待ちまで進め、ユーザーが操作できる間にブラウザを閉じない
        print(f"エラーが発生しました: {e}", file=sys.stderr)
        if config.get("keep_browser_open", True):
            print("\n振込画面を開いたままにしています。確認や振込を続けてください。", file=sys.stderr)
            print("作業が終わったらご自身でブラウザを閉じ、閉じたあとで Enter を押してください。", file=sys.stderr)
            _wait_enter(
                confirm_msg="スクリプトを終了しました。",
                driver=driver,
                keepalive_config=config,
            )
        return ""
    finally:
        # keep_browser_open 時はブラウザを閉じない（ユーザーが手動で閉じる）
        if not config.get("keep_browser_open", True):
            driver.quit()


def run_tokairokin(
    headless: bool = False,
    transfer: dict = None,
    inspect_transfer_screen: bool = False,
) -> str:
    """東海労金インターネットバンキングにログインする。振込パラメータがあればフォーム入力まで自動化。"""
    config = load_config("tokairokin")
    user, password = get_credentials("tokairokin")
    transfer = transfer or config.get("transfer")
    transfer = _apply_tokairokin_transfer_defaults(transfer)

    # undetected-chromedriver を優先（CDP・stealth で検知された場合の代替）
    if config.get("use_undetected_chromedriver", False):
        return _run_tokairokin_undetected(
            config,
            user,
            password,
            headless or config.get("headless", False),
            transfer,
            inspect_transfer_screen=inspect_transfer_screen,
        )

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

            body_text = page.locator("body").inner_text()
            if "エラー" in body_text or "認証に失敗" in body_text or "ログインに失敗" in body_text or "口座情報が誤っています" in body_text:
                print("ログインに失敗した可能性があります。headless=false で実行して画面を確認してください。", file=sys.stderr)

            print("東海労金へのログイン処理が完了しました。")

            # 合言葉の自動入力（設定されている場合）
            secret_phrase_filled = False
            secret_phrase_auto = config.get("secret_phrase_auto") or []
            body_text = page.locator("body").inner_text()
            html_pw = page.content()
            current_url = page.url
            hay_pw = (body_text or "") + "\n" + (html_pw or "")
            sp_screen_pw = bool(
                secret_phrase_auto and _tokairokin_secret_phrase_screen_detected(body_text, html_pw, config)
            )
            dashboard_skip_secret_pause = False
            if sp_screen_pw:
                for mapping in secret_phrase_auto:
                    match_kw = (mapping.get("match") or "").strip()
                    if not match_kw or match_kw not in hay_pw:
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
                            el = page.locator(
                                f"a:has-text('{relogin_kw}'), button:has-text('{relogin_kw}'), input[value='{relogin_kw}']"
                            ).first
                            if el.is_visible() and relogin_kw in body_text:
                                el.click()
                                print(f"「{relogin_kw}」をクリックしました。", file=sys.stderr)
                                page.wait_for_timeout(3000)
                                break
                        except Exception:
                            continue

            elif secret_phrase_auto:
                if _tokairokin_post_login_dashboard_detected(current_url, body_text, html_pw, config):
                    dashboard_skip_secret_pause = True
                    print(
                        "合言葉（追加認証）画面は検出されませんでした。"
                        " ログイン後トップページ相当と判断し、合言葉の Enter 待ちをスキップして次へ進みます。",
                        file=sys.stderr,
                    )
                else:
                    print(
                        "secret_phrase_auto は設定されていますが、合言葉系画面の検出キーワードが見つかりませんでした。"
                        " secret_phrase_page_markers を実画面の文言で拡張してください。",
                        file=sys.stderr,
                    )

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
            if (
                not secret_phrase_filled
                and not dashboard_skip_secret_pause
                and config.get("pause_for_secret_phrase", True)
            ):
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
    parser.add_argument(
        "--inspect-transfer-screen",
        action="store_true",
        help="振込URL遷移直後に Enter 待ちで止め、セレクタ検証（pause_for_transfer_screen_inspect と同趣旨）",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="tokairokin のみ: Enter 待ちをスキップ（Jarvis・Cursor Agent・CI）。TOKAIROKIN_NON_INTERACTIVE=1 と同効",
    )
    args = parser.parse_args()

    if args.site == "nichinoken":
        path = run_nichinoken(headless=args.headless)
        print(f"出力: {path}")
    elif args.site == "tokairokin":
        if args.non_interactive:
            os.environ["TOKAIROKIN_NON_INTERACTIVE"] = "1"
        transfer = None
        if (
            args.bank
            or args.branch
            or args.bank_name
            or args.branch_name
            or args.account
            or args.amount is not None
        ):
            transfer = {
                "bank_code": args.bank or "",
                "branch_code": args.branch or "",
                "bank_name": args.bank_name or "",
                "branch_name": args.branch_name or "",
                "account_number": args.account or "",
                "amount": args.amount if args.amount is not None else 0,
            }
        run_tokairokin(
            headless=args.headless,
            transfer=transfer,
            inspect_transfer_screen=args.inspect_transfer_screen,
        )
    else:
        print(f"未対応のサイト: {args.site}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
