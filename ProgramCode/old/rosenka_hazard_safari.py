from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import sys
import time

# ==== Alfredから住所を受け取る ====
if len(sys.argv) < 2:
    print("住所を入力してください")
    sys.exit(1)

target_address = sys.argv[1]

# ==== Safari 起動 ====
driver = webdriver.Safari()
driver.set_window_size(1280, 900)

# ==== 1. ハザードマップ ====
driver.get("https://disaportal.gsi.go.jp/maps/")

try:
    box = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "#query"))
    )
    box.clear()
    box.send_keys(target_address)

    btn = driver.find_element(By.CSS_SELECTOR, "#search-addr-btn")
    btn.click()
    print(f"✅ ハザードマップ検索実行: {target_address}")
except TimeoutException:
    print("❌ ハザードマップ検索に失敗しました")

time.sleep(2)

# ==== 2. 路線価（全国地価マップ） ====
driver.execute_script("window.open('https://www.chikamap.jp/chikamap/PrefecturesSelect?mid=324','_blank');")
driver.switch_to.window(driver.window_handles[-1])

try:
    # 同意ボタンがあればクリック
    try:
        agree_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "#Agree"))
        )
        agree_btn.click()
        print("✅ 路線価サイト: 同意ボタンをクリックしました")
        time.sleep(2)
    except TimeoutException:
        print("ℹ️ 同意画面はスキップされました")

    # 検索窓に住所を入力
    box = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "#AddressSearchForm > input[type='text']:nth-child(5)"))
    )
    box.clear()
    box.send_keys(target_address)

    # 検索ボタンを押す
    btn = driver.find_element(By.CSS_SELECTOR, "#AddressSearchButton")
    btn.click()
    print(f"✅ 路線価検索実行: {target_address}")

except TimeoutException:
    print("❌ 路線価検索に失敗しました")

print("🎉 検索完了！ブラウザで確認してください")

