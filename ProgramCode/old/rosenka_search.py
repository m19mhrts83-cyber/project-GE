from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

def main(address):
    options = webdriver.ChromeOptions()
    driver = webdriver.Chrome(service=Service(), options=options)

    try:
        # ページを開く
        driver.get("https://www.chikamap.jp/chikamap/PrefecturesSelect?mid=324")

        wait = WebDriverWait(driver, 10)

        # 「同意する」ボタンがある場合はクリック
        try:
            agree_btn = wait.until(EC.presence_of_element_located((By.ID, "Agree")))
            agree_btn.click()
            print("同意ボタンをクリックしました")
            time.sleep(2)
        except Exception:
            print("同意ボタンは表示されませんでした")

        # Shadow DOMの検索ボックスに住所を入力
        driver.execute_script("""
            let shadowRoot = document.querySelector('input[name="skw"]').shadowRoot;
            if (shadowRoot) {
                let box = shadowRoot.querySelector('div[contenteditable]');
                if (box) {
                    box.innerText = arguments[0];
                    box.dispatchEvent(new Event('input', { bubbles: true }));
                }
            }
        """, address)
        print(f"住所を入力しました: {address}")
        time.sleep(2)

        # 検索ボタンを押す
        try:
            search_btn = driver.find_element(By.ID, "AddressSearchButton")
            search_btn.click()
            print("検索ボタンをクリックしました")
        except Exception as e:
            print("検索ボタンが押せませんでした:", e)

        # 検索結果を確認できるように待機
        time.sleep(10)

    finally:
        driver.quit()


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("住所を引数で指定してください")
    else:
        main(sys.argv[1])
import sys
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options

# 引数（住所）
if len(sys.argv) > 1:
    address = sys.argv[1]
else:
    address = "住所が入力されていません"

# Chrome起動
options = Options()
options.add_argument("--start-maximized")
driver = webdriver.Chrome(options=options)

# サイトを開く
driver.get("https://www.chikamap.jp/chikamap/PrefecturesSelect?mid=324")
time.sleep(3)

# 同意画面が出たらクリック
try:
    driver.execute_script("document.querySelector('#Agree').click();")
    time.sleep(2)
    print("同意ボタンをクリックしました")
except:
    print("同意画面はスキップされました")

# JavaScriptで強制入力
try:
    driver.execute_script("""
        let input = document.querySelector('input[name="skw"]');
        if(input){
            input.value = arguments[0];
            input.dispatchEvent(new Event('input', { bubbles: true }));
        }
    """, address)
    time.sleep(1)
    print("住所を入力しました:", address)

    # 検索ボタンをクリック
    driver.execute_script("document.querySelector('#AddressSearchButton').click();")
    print("検索ボタンをクリックしました")

except Exception as e:
    print("エラー:", e)
import sys
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

# Alfredからの入力
if len(sys.argv) > 1:
    address = sys.argv[1]
else:
    address = "住所が入力されていません"

driver = webdriver.Chrome()
driver.get("https://www.chikamap.jp/chikamap/PrefecturesSelect?mid=324")

# 同意画面が出たら処理
try:
    agree_button = WebDriverWait(driver, 5).until(
        EC.element_to_be_clickable((By.ID, "Agree"))
    )
    agree_button.click()
    time.sleep(2)
except:
    print("同意画面はスキップされました")

try:
    # iframeが存在すれば切り替える
    WebDriverWait(driver, 10).until(
        EC.frame_to_be_available_and_switch_to_it((By.TAG_NAME, "iframe"))
    )
    print("iframeに切り替えました")
except:
    print("iframeは見つかりませんでした")

try:
    # JavaScriptで直接入力し、イベントも発火させる
    search_box = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.NAME, "skw"))
    )
    driver.execute_script("""
        let input = arguments[0];
        input.value = arguments[1];
        input.dispatchEvent(new Event('input', { bubbles: true }));
    """, search_box, address)

    # 検索ボタンを押す
    search_button = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.ID, "AddressSearchButton"))
    )
    search_button.click()
    print("検索を実行しました:", address)

except Exception as e:
    print("エラー:", e)
import sys
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

# Alfredからの入力
if len(sys.argv) > 1:
    address = sys.argv[1]
else:
    address = "住所が入力されていません"

# Chromeを起動
driver = webdriver.Chrome()

# 路線価の検索ページを開く
driver.get("https://www.chikamap.jp/chikamap/PrefecturesSelect?mid=324")

# ① 「同意する」画面が出たら処理
try:
    agree_button = WebDriverWait(driver, 5).until(
        EC.element_to_be_clickable((By.ID, "Agree"))
    )
    agree_button.click()
    time.sleep(2)
except:
    print("同意画面はスキップされました")

# ② 検索ボックスに住所を入力
try:
    search_box = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.NAME, "skw"))
    )
    search_box.clear()
    search_box.send_keys(address)

    # ③ 検索ボタンを押す
    search_button = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.ID, "AddressSearchButton"))
    )
    search_button.click()
    print("検索を実行しました:", address)

except Exception as e:
    print("エラー:", e)
import sys
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import time

# Alfredからの入力
if len(sys.argv) > 1:
    address = sys.argv[1]
else:
    address = "住所が入力されていません"

# Chromeを起動
driver = webdriver.Chrome()

# 路線価の検索ページを開く
driver.get("https://www.chikamap.jp/chikamap/PrefecturesSelect?mid=324")
time.sleep(3)

# ① 「同意する」画面が出たら処理
try:
    agree_button = driver.find_element(By.ID, "Agree")
    agree_button.click()
    time.sleep(2)
except:
    print("同意画面はスキップされました")

# ② 検索ボックスに住所を入力
try:
    search_box = driver.find_element(By.NAME, "skw")
    search_box.clear()
    search_box.send_keys(address)
    time.sleep(1)

    # ③ 検索ボタンを押す
    search_button = driver.find_element(By.ID, "AddressSearchButton")
    search_button.click()
    print("検索を実行しました:", address)

except Exception as e:
    print("エラー:", e)

