from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

address = "名古屋市守山区西城1丁目8-8"

options = Options()
service = Service("/opt/homebrew/bin/chromedriver")  # ← brew で入れた chromedriver
driver = webdriver.Chrome(service=service, options=options)

try:
    driver.get("https://www.chikamap.jp/chikamap/Agreement?IsPost=False&MapId=324&RequestPage=%2fchikamap%2fPrefecturesSelect%3fmid%3d324")

    # 同意ボタン
    try:
        agree_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.ID, "Agree"))
        )
        agree_btn.click()
        print("✅ 同意ボタンをクリックしました")
    except:
        print("ℹ️ 同意ボタンは表示されませんでした")

    # 検索窓に入力
    input_box = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "#AddressSearchForm > input[type='text']:nth-child(5)"))
    )

    driver.execute_script("arguments[0].value = arguments[1];", input_box, address)
    print(f"✅ 住所を入力しました: {address}")

    # 検索ボタン
    search_btn = driver.find_element(By.ID, "AddressSearchButton")
    driver.execute_script("arguments[0].click();", search_btn)
    print("✅ 検索ボタンをクリックしました")

    time.sleep(5)

finally:
    driver.quit()
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

# ====== 設定 ======
address = "名古屋市守山区西城1丁目8-8"

# ChromeDriverのパス（インストールした場所に合わせて調整）
service = Service("/opt/homebrew/bin/chromedriver")

options = Options()
options.binary_location = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

driver = webdriver.Chrome(service=service, options=options)
driver.get("https://www.chikamap.jp/chikamap/PrefecturesSelect?mid=324")

wait = WebDriverWait(driver, 10)

# --- Step 1: 「同意する」ボタンをクリック ---
try:
    agree_button = wait.until(EC.element_to_be_clickable((By.ID, "Agree")))
    agree_button.click()
    print("✅ 同意ボタンをクリックしました")
except Exception as e:
    print("ℹ️ 同意ボタンは表示されませんでした:", e)

time.sleep(2)

# --- Step 2: 住所入力 ---
try:
    # 検索ボックスを待つ
    input_box = wait.until(EC.presence_of_element_located((By.NAME, "skw")))

    # JavaScriptで値を入れて、input/changeイベントを発火
    driver.execute_script("""
        let box = arguments[0];
        box.value = arguments[1];
        box.dispatchEvent(new Event('input', { bubbles: true }));
        box.dispatchEvent(new Event('change', { bubbles: true }));
    """, input_box, address)

    print(f"✅ 住所を入力しました: {address}")

    time.sleep(1)

    # --- Step 3: 検索ボタンをクリック ---
    search_button = wait.until(EC.element_to_be_clickable((By.ID, "AddressSearchButton")))
    driver.execute_script("arguments[0].click();", search_button)
    print("✅ 検索ボタンをクリックしました")

except Exception as e:
    print("❌ 住所入力または検索ボタンクリック失敗:", e)

# 検証用に少し待機
time.sleep(5)
driver.quit()
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import time

service = Service("/opt/homebrew/bin/chromedriver")  # ← which chromedriver のパスに合わせてね
options = webdriver.ChromeOptions()
driver = webdriver.Chrome(service=service, options=options)

driver.get("https://www.chikamap.jp/chikamap/Agreement?IsPost=False&MapId=324&RequestPage=%2fchikamap%2fPrefecturesSelect%3fmid%3d324")

# --- 同意画面処理 ---
try:
    agree = driver.find_element(By.ID, "Agree")
    agree.click()
    print("✅ 同意ボタンをクリックしました")
    time.sleep(2)
except:
    print("同意画面は表示されませんでした")

# --- 入力処理 ---
address = "名古屋市守山区西城1丁目8-8"

# 方法A: JSで直接入力
driver.execute_script(f"document.querySelector('input[name=\"skw\"]').value = '{address}';")
print(f"✅ 住所を入力しました: {address}")
time.sleep(1)

# --- 検索実行 ---
try:
    # 案1: JSクリック
    driver.execute_script("document.getElementById('AddressSearchButton').click();")
    print("✅ 検索ボタンをクリックしました (JS)")
    time.sleep(3)
except Exception as e:
    print("❌ 検索ボタンのクリック失敗:", e)
    try:
        # 案2: Enterキー送信
        box = driver.find_element(By.NAME, "skw")
        box.send_keys(Keys.RETURN)
        print("✅ Enterキーで検索しました")
    except Exception as e2:
        print("❌ Enterキー検索も失敗:", e2)

