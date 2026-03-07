# -*- coding: utf-8 -*-
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import ElementNotInteractableException, TimeoutException, JavascriptException
import sys, time

# ===== 引数（住所）=====
if len(sys.argv) < 2:
    print("❌ 住所が渡っていません")
    sys.exit(1)
addr = sys.argv[1]

# ===== Safari 起動 =====
driver = webdriver.Safari()
driver.set_window_size(1280, 900)

def log(s): print(s, flush=True)

try:
    driver.get("https://disaportal.gsi.go.jp/maps/")
    # 検索UI の入力欄を待つ（表示＆クリック可）
    box = WebDriverWait(driver, 12).until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, "#query"))
    )
    WebDriverWait(driver, 12).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "#query"))
    )

    # 画面内に持ってくる＋クリックでフォーカス
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", box)
    time.sleep(0.15)

    # 方法A: そのまま入力（成功パス）
    try:
        box.click()
        # 一部環境で clear() が非対称なので JSで初期化→send_keys
        driver.execute_script("arguments[0].value='';", box)
        box.send_keys(addr)
        # 値が入ったか検証
        val = driver.execute_script("return document.querySelector('#query')?.value || '';")
        if val.strip():
            log(f"✅ 入力OK（send_keys）: {val}")
        else:
            raise ElementNotInteractableException("value not set after send_keys")

    except ElementNotInteractableException:
        # 方法B: JSで強制的に値設定＋イベント発火
        try:
            js = """
            const box = document.querySelector('#query');
            if (box){
              box.value = arguments[0];
              box.dispatchEvent(new Event('input',{bubbles:true}));
              box.dispatchEvent(new Event('change',{bubbles:true}));
            }
            """
            driver.execute_script(js, addr)
            val = driver.execute_script("return document.querySelector('#query')?.value || '';")
            if val.strip():
                log(f"✅ 入力OK（JS直書き）: {val}")
            else:
                raise JavascriptException("query value still empty after JS")
        except Exception as e:
            log(f"❌ 入力失敗: {e}")
            raise

    # 検索ボタン待機
    try:
        btn = WebDriverWait(driver, 8).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "#search-addr-btn"))
        )
    except TimeoutException:
        # レイアウト差分に備え、フォールバックで取得
        btn = driver.find_element(By.CSS_SELECTOR, "#search-addr-btn")

    # 方法1: クリック
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
        time.sleep(0.1)
        btn.click()
        log("✅ 検索ボタンクリック（click）")
    except Exception:
        # 方法2: JSでclick
        driver.execute_script("document.querySelector('#search-addr-btn')?.click();")
        log("✅ 検索ボタンクリック（JS）")

    # 目視用に数秒待つ（ブラウザは閉じない）
    time.sleep(4)
    log("🟢 ハザードマップ検索を実行済み。結果を目視確認してください。")

except Exception as e:
    log(f"❌ エラー: {e}")
    # 失敗時もブラウザは残す

