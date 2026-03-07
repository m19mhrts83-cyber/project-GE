# -*- coding: utf-8 -*-

import os
import sys
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

# コマンドライン引数から住所を受け取る
if len(sys.argv) < 2:
    print("❌ 住所を指定してください")
    sys.exit(1)

address = sys.argv[1]
print(f"📍 入力住所: {address}")

# --- 環境 ---
# Homebrew の既定パス。違う場合は書き換えOK
CHROMEDRIVER = "/opt/homebrew/bin/chromedriver"

options = Options()
# デバッグしやすいように残す
options.add_experimental_option("detach", True)  # スクリプト終了後もChromeを残す
# 通常表示
# options.add_argument("--start-maximized")  # 好みで

service = Service(CHROMEDRIVER)
driver = webdriver.Chrome(service=service, options=options)
wait = WebDriverWait(driver, 15)

def js(script, *args):
    return driver.execute_script(script, *args)

def visible(locator):
    return wait.until(EC.visibility_of_element_located(locator))

def clickable(locator):
    return wait.until(EC.element_to_be_clickable(locator))

try:
    # 1) 同意ページ → 同意クリック
    driver.get("https://www.chikamap.jp/chikamap/Agreement?IsPost=False&MapId=324&RequestPage=%2fchikamap%2fPrefecturesSelect%3fmid%3d324")
    try:
        agree = wait.until(EC.element_to_be_clickable((By.ID, "Agree")))
        agree.click()
        print("✅ 同意する をクリック")
    except Exception:
        print("ℹ️ 同意画面は出ませんでした（既に同意済みの可能性）")

    # 2) 住所検索ページに来ているはず。安定セレクタで待つ
    #    第一候補: フォームID＋name=skw
    skw = None
    try:
        skw = visible((By.CSS_SELECTOR, "form#AddressSearchForm input[name='skw']"))
        clickable((By.CSS_SELECTOR, "form#AddressSearchForm input[name='skw']"))
    except Exception:
        # 代替（過去に一度通ったセレクタ）
        try:
            skw = visible((By.CSS_SELECTOR, "#AddressSearchForm > input[type='text']:nth-child(5)"))
            clickable((By.CSS_SELECTOR, "#AddressSearchForm > input[type='text']:nth-child(5)"))
        except Exception:
            pass

    if not skw:
        # さらに最後の保険：name='skw' 単体
        try:
            skw = visible((By.NAME, "skw"))
            clickable((By.NAME, "skw"))
        except Exception:
            raise RuntimeError("検索ボックス(skw)が見つかりませんでした")

    # 3) 入力（まずはsend_keys、ダメならJSフォールバック）
    ok = False
    try:
        skw.clear()
        skw.send_keys(address)
        ok = True
        print(f"✅ 入力(send_keys): {address}")
    except Exception as e:
        print(f"⚠️ send_keys不可: {e}")

    if not ok:
        # JSで強制入力＋イベント発火
        js("""
            const el = arguments[0];
            const v = arguments[1];
            el.value = v;
            el.dispatchEvent(new Event('input', {bubbles:true}));
            el.dispatchEvent(new Event('change', {bubbles:true}));
        """, skw, address)
        print(f"✅ 入力(JS): {address}")

    time.sleep(0.5)

    # 4) 検索ボタン押下（クリック→失敗ならJSクリック→最終手段：関数呼び）
    clicked = False
    for sel in ["#AddressSearchButton", "input#AddressSearchButton", "input[type='submit'][value='検索']"]:
        try:
            btn = clickable((By.CSS_SELECTOR, sel))
            btn.click()
            clicked = True
            print("✅ 検索ボタンをクリック")
            break
        except Exception:
            pass

    if not clicked:
        # JSクリック
        ok = js("""
            const btn = document.querySelector('#AddressSearchButton') 
                      || document.querySelector("input[type='submit'][value='検索']");
            if (btn) { btn.click(); return true; } else { return false; }
        """)
        if ok:
            print("✅ 検索ボタンをクリック(JS)")
            clicked = True

    if not clicked:
        # どうしてもダメならJS関数を直接叩く（あれば）
        try:
            js("if (typeof CheckKeyword==='function'){ CheckKeyword(0); }")
            print("✅ CheckKeyword(0) を実行(JS)")
        except Exception:
            print("⚠️ 検索トリガが見つからず")

    # 5) 画面が遷移するまで少し待ってスクショ（目視の補助）
    time.sleep(2.5)
    os.makedirs("/tmp/rosenka", exist_ok=True)
    shot = "/tmp/rosenka/after_search.png"
    driver.save_screenshot(shot)
    print(f"📸 スクリーンショット: {shot}")
    print("🎉 ここでブラウザは開いたまま（detach=true）なので目視確認してください。")

except Exception as e:
    print(f"❌ 例外: {e}")
    try:
        os.makedirs("/tmp/rosenka", exist_ok=True)
        shot = "/tmp/rosenka/error.png"
        driver.save_screenshot(shot)
        print(f"📸 エラー時スクショ: {shot}")
    except Exception:
        pass
# ※ ドライバは閉じない（Chromeを残すため）

# 検索が終わったあとにリンクをクリック
try:
    # リンクが表示されるまで待機（例：最大10秒）
    link = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "#jtg1 > a"))
    )
    link.click()
    print("✅ 相続路線価リンクをクリックしました")
except Exception as e:
    print("❌ 相続路線価リンクをクリックできませんでした:", e)

# --- ハザードマップ ---
driver.get("https://disaportal.gsi.go.jp/maps/")
time.sleep(5)

try:
    # 検索ボックスに住所を入力
    search_box = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "#query"))
    )
    search_box.clear()
    search_box.send_keys(address)
    print(f"✅ ハザードマップに住所を入力しました: {address}")

    # 検索ボタンをクリック
    search_button = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "button[onclick=\"$('#query').submit()\"]"))
    )
    driver.execute_script("arguments[0].click();", search_button)
    print("✅ ハザードマップ検索ボタンをクリックしました")

except Exception as e:
    print("❌ ハザードマップ処理でエラー:", e)

