from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import time
import sys

address = "名古屋市守山区西城1丁目8-8"

options = Options()
options.add_argument("--start-maximized")

service = Service("/opt/homebrew/bin/chromedriver")  # 適宜パス修正
driver = webdriver.Chrome(service=service, options=options)

try:
    # 路線価ページを開く
    driver.get("https://www.chikamap.jp/chikamap/PrefecturesSelect?mid=324")
    time.sleep(3)

    # 同意画面が出た場合、ボタンを押す
    try:
        agree_button = driver.find_element(By.ID, "Agree")
        agree_button.click()
        print("同意ボタンをクリックしました")
        time.sleep(2)
    except Exception:
        print("同意ボタンは表示されませんでした")

    # iframe を探す
    iframes = driver.find_elements(By.TAG_NAME, "iframe")
    print("iframe数:", len(iframes))
    for idx, iframe in enumerate(iframes):
        print(idx, "id:", iframe.get_attribute("id"), "name:", iframe.get_attribute("name"))

    # ページタイトルを確認
    print("ページタイトル:", driver.title)

    time.sleep(5)

finally:
    driver.quit()

