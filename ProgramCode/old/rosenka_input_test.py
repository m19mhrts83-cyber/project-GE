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

