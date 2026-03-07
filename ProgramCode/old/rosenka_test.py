from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

# --- ChromeDriver の起動設定 ---
service = Service("/usr/local/bin/chromedriver")
options = webdriver.ChromeOptions()
driver = webdriver.Chrome(service=service, options=options)

driver.get("https://www.chikamap.jp/chikamap/PrefecturesSelect?mid=324")

wait = WebDriverWait(driver, 15)

# --- 同意ボタン処理 ---
try:
    agree_btn = wait.until(EC.element_to_be_clickable((By.ID, "Agree")))
    agree_btn.click()
    print("✅ 同意ボタンをクリックしました")
except:
    print("ℹ️ 同意画面は表示されませんでした")

# --- 検索欄を探して入力を試す ---
address = "名古屋市守山区西城1丁目8-8"

try:
    # 方法1: 通常の send_keys
    search_box = wait.until(EC.presence_of_element_located((By.NAME, "skw")))
    search_box.click()
    search_box.send_keys(address)
    print("✅ 方法1: send_keys で入力しました")
except Exception as e:
    print("❌ 方法1失敗:", e)

try:
    # 方法2: JS で値を直接代入
    driver.execute_script("document.getElementsByName('skw')[0].value = arguments[0];", address)
    print("✅ 方法2: JS で直接入力しました")
except Exception as e:
    print("❌ 方法2失敗:", e)

try:
    # 方法3: フォーカスを与えてから send_keys
    search_box = wait.until(EC.element_to_be_clickable((By.NAME, "skw")))
    search_box.click()
    time.sleep(1)
    search_box.clear()
    search_box.send_keys(address)
    print("✅ 方法3: click → send_keys で入力しました")
except Exception as e:
    print("❌ 方法3失敗:", e)

time.sleep(5)
driver.quit()
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

address = "名古屋市守山区西城1丁目8-8"

driver = webdriver.Chrome(service=Service())
driver.get("https://www.chikamap.jp/chikamap/PrefecturesSelect?mid=324")

# 同意ボタンがあれば押す
try:
    agree_btn = WebDriverWait(driver, 5).until(
        EC.element_to_be_clickable((By.ID, "Agree"))
    )
    agree_btn.click()
    print("同意ボタンをクリックしました")
except:
    print("同意ボタンは出ませんでした")

time.sleep(2)

# JSで検索ボックスに値をセット
try:
    driver.execute_script("""
    let box = document.querySelector('input[name=skw]');
    if (box) {
        box.value = arguments[0];
        box.dispatchEvent(new Event('input', { bubbles: true }));
    }
    """, address)
    print("住所を入力しました:", address)
except Exception as e:
    print("住所入力失敗:", e)

# 検索ボタンを押す
try:
    search_btn = WebDriverWait(driver, 5).until(
        EC.element_to_be_clickable((By.ID, "AddressSearchButton"))
    )
    search_btn.click()
    print("検索ボタンをクリックしました")
except:
    print("検索ボタンが見つかりませんでした")

time.sleep(10)
driver.quit()
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

address = "名古屋市守山区西城1丁目8-8"

driver = webdriver.Chrome(service=Service())
driver.get("https://www.chikamap.jp/chikamap/PrefecturesSelect?mid=324")

# 同意ボタンがあれば押す
try:
    agree_btn = WebDriverWait(driver, 5).until(
        EC.element_to_be_clickable((By.ID, "Agree"))
    )
    agree_btn.click()
    print("同意ボタンをクリックしました")
except:
    print("同意ボタンは出ませんでした")

# 検索ボックス（contenteditable）を探して入力
try:
    box = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "div[contenteditable]"))
    )
    box.click()
    box.send_keys(address)
    print("住所を入力しました:", address)
except Exception as e:
    print("住所入力失敗:", e)

time.sleep(10)  # 入力結果を確認できるよう待機
driver.quit()
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
import time

address = "名古屋市守山区西城1丁目8-8"

driver = webdriver.Chrome(service=Service())
driver.get("https://www.chikamap.jp/chikamap/PrefecturesSelect?mid=324")
time.sleep(3)

# 同意ボタンがあればクリック
try:
    agree_btn = driver.find_element(By.ID, "Agree")
    agree_btn.click()
    print("同意ボタンをクリックしました")
    time.sleep(2)
except:
    print("同意ボタンは出ませんでした")

# Shadow DOM の検索ボックスへ入力
driver.execute_script("""
    let host = document.querySelector('input[name="skw"]');
    let shadow = host.shadowRoot;
    if (shadow) {
        let box = shadow.querySelector('div[contenteditable]');
        if (box) {
            box.innerHTML = arguments[0];
            box.dispatchEvent(new Event('input', { bubbles: true }));
            box.dispatchEvent(new Event('change', { bubbles: true }));
        }
    }
""", address)

print("住所入力を試みました:", address)
time.sleep(10)  # 入力結果を目視確認
driver.quit()

