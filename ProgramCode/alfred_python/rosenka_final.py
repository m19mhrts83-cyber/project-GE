# ~/alfred_python/rosenka_final.py
# -*- coding: utf-8 -*-
import sys, time, traceback
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
# from selenium.webdriver.chrome.service import Service  # ← もう不要なのでコメントアウト or 削除
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# ===== 入力アドレス =====
ADDR = " ".join(sys.argv[1:]).strip()
if not ADDR:
    print("❌ 住所（引数）が指定されていません")
    sys.exit(1)
print(f"📍 入力住所: {ADDR}")

# ===== ChromeDriver パス（M1/M2 Homebrew 既定）=====
CHROMEDRIVER = "/opt/homebrew/bin/chromedriver"

# ===== WebDriver 準備（ブラウザは開いたまま）=====
options = Options()
options.add_experimental_option("detach", True)  # スクリプト終了後もブラウザを残す
options.add_argument("--disable-gpu")
options.add_argument("--no-sandbox")
options.add_argument("--remote-allow-origins=*")

# ★ Selenium Manager に ChromeDriver 管理を任せる（パス指定なし）
driver = webdriver.Chrome(options=options)

driver.set_window_size(1300, 900)
wait = WebDriverWait(driver, 12)

# ===== ユーティリティ =====
def safe_find(by, value, to=12):
    return WebDriverWait(driver, to).until(EC.presence_of_element_located((by, value)))

def safe_click_css(css, to=8):
    try:
        el = WebDriverWait(driver, to).until(EC.element_to_be_clickable((By.CSS_SELECTOR, css)))
        driver.execute_script("arguments[0].click();", el)
        return True
    except Exception:
        return False

def js_set_value(el, text):
    driver.execute_script("""
        const el = arguments[0], val = arguments[1];
        el.focus();
        el.value = val;
        el.dispatchEvent(new Event('input', {bubbles:true}));
        el.dispatchEvent(new Event('change', {bubbles:true}));
    """, el, text)

# =================================================================
# ① 全国地価マップ（chikamap） 同意→住所入力→検索→相続路線価リンク
# =================================================================
try:
    driver.get("https://www.chikamap.jp/chikamap/PrefecturesSelect?mid=324")

    # 同意ページが出たら「同意する」をクリック
    try:
        if safe_click_css("#Agree", to=5) or safe_click_css("input#Agree", to=2):
            print("✅ 同意する をクリック")
            time.sleep(1.2)
    except Exception:
        pass  # 同意ページが出ないケースもあり（既に同意済み）

    # 住所入力欄を待つ（どちらかにヒットすればOK）
    try:
        safe_find(By.CSS_SELECTOR, "form#AddressSearchForm, input[name='skw']", to=10)
    except TimeoutException:
        print("⚠️ 検索フォームが見つかりませんでした（ページ遷移に時間がかかっている可能性）")

    # 入力（優先: name='skw'、ダメなら実績のあるフォールバックCSS）
    filled = False
    try:
        box = driver.find_element(By.CSS_SELECTOR, "input[name='skw']")
        box.clear()
        box.send_keys(ADDR)
        filled = True
        print(f"✅ 住所入力(name=skw): {ADDR}")
    except Exception:
        pass

    if not filled:
        try:
            # ユーザーさんの実績CSS（Safari検証時に効いたセレクタ）
            box = driver.find_element(By.CSS_SELECTOR, "#AddressSearchForm > input[type='text']:nth-child(5)")
            js_set_value(box, ADDR)
            filled = True
            print(f"✅ 住所入力(フォールバックCSS): {ADDR}")
        except Exception as e:
            print(f"⚠️ 住所入力失敗: {e}")

    # 検索（クリック → だめなら form submit）
    clicked = False
    for sel in [
        "#AddressSearchForm input[type='submit'][value='検索']",
        "#AddressSearchForm input[type='submit']",
    ]:
        if safe_click_css(sel, to=3):
            print("✅ 検索ボタンをクリック")
            clicked = True
            break

    if not clicked:
        try:
            form = driver.find_element(By.CSS_SELECTOR, "#AddressSearchForm")
            driver.execute_script("arguments[0].submit();", form)
            print("✅ フォームを submit() 実行")
            clicked = True
        except Exception:
            print("⚠️ 検索の実行に失敗（フォーム送信も不可）")

    time.sleep(2.0)

    # 相続路線価リンク（ユーザーさん実績セレクタ）
    try:
        link = WebDriverWait(driver, 6).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "#jtg1 > a"))
        )
        driver.execute_script("arguments[0].click();", link)
        print("✅ 相続路線価リンクをクリックしました")
    except TimeoutException:
        print("⚠️ 相続路線価リンクが見つかりませんでした（場所によっては出ないことがあります）")

except Exception as e:
    print(f"❌ 路線価処理でエラー: {e}")
    traceback.print_exc()

# =================================================================
# ② 重ねるハザードマップ（住所入力→検索）
# =================================================================
try:
    # 新しいタブで開く
    driver.switch_to.new_window('tab')
    driver.get("https://disaportal.gsi.go.jp/maps/")

    # 検索ボックス（#query）
    query = safe_find(By.CSS_SELECTOR, "#query", to=10)
    js_set_value(query, ADDR)
    print(f"✅ ハザード: 住所入力 {ADDR}")

    # 検索ボタン（パターンいくつか → 最後は form submit）
    if safe_click_css("#search-addr-btn", to=2):
        print("✅ ハザード: 検索ボタン（#search-addr-btn）クリック")
    elif safe_click_css("#search_f > div > span > button[type='button']", to=2):
        print("✅ ハザード: 検索ボタン（img親button）クリック")
    else:
        try:
            form = driver.find_element(By.CSS_SELECTOR, "#search_f")
            driver.execute_script("arguments[0].submit();", form)
            print("✅ ハザード: フォーム submit() 実行")
        except Exception:
            # ボタンonclickが jQuery の submit を呼ぶケースに備えた保険
            driver.execute_script("""
                var btn = document.querySelector("button[onclick*='submit()']");
                if (btn) btn.click();
            """)
            print("⚠️ ハザード: onclick経由で検索を試行")

    # 少し待って地図反映
    time.sleep(2.5)

except Exception as e:
    print(f"❌ ハザード処理でエラー: {e}")
    traceback.print_exc()

print("🎉 ブラウザは開いたままです（detach=true）。目視確認してください。")
