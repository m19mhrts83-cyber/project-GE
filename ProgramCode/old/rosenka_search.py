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

