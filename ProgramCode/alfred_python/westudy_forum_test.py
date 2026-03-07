# ~/alfred_python/westudy_forum_test.py
# -*- coding: utf-8 -*-
import time, csv, traceback
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ===== ログイン情報 =====
EMAIL = "matsuno.estate@gmail.com"
PASSWORD = "matsuno.estate.2016"

# ===== ChromeDriver パス =====
CHROMEDRIVER = "/opt/homebrew/bin/chromedriver"

# ===== 出力CSV =====
OUTPUT = str(Path.home() / "Downloads" / "westudy_comments_test.csv")

# ===== WebDriver準備 =====
options = Options()
options.add_experimental_option("detach", True)  # スクリプト終了後もブラウザを残す
options.add_argument("--disable-gpu")
options.add_argument("--no-sandbox")
options.add_argument("--remote-allow-origins=*")
driver = webdriver.Chrome(service=Service(CHROMEDRIVER), options=options)
wait = WebDriverWait(driver, 12)

def safe_click(css, to=6):
    try:
        el = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, css)))
        driver.execute_script("arguments[0].click();", el)
        return True
    except:
        return False

# ===== ログイン =====
try:
    driver.get("https://westudy.co.jp/login")

    # メールアドレス入力
    wait.until(EC.presence_of_element_located((By.NAME, "log"))).send_keys(EMAIL)
    # パスワード入力
    driver.find_element(By.NAME, "pwd").send_keys(PASSWORD)

    # ログインボタンをクリック
    safe_click("input[type='submit']", to=8)
    time.sleep(4)
    print("✅ ログイン完了")
except Exception:
    print("❌ ログイン失敗")
    traceback.print_exc()
    driver.quit()
    exit(1)


# ===== フォーラム一覧へ =====
driver.get("https://westudy.co.jp/course/kami-ooyasan-club?t=forums")
time.sleep(4)

# トピック一覧から最初の1件だけ取得
topic = driver.find_element(By.CSS_SELECTOR, "div.section-item-title a")
topic_url = topic.get_attribute("href")
print(f"▶ テスト対象トピック: {topic_url}")

results = []

driver.get(topic_url)
time.sleep(2)

# 「続きを見る」ボタンを展開
buttons = driver.find_elements(By.CSS_SELECTOR, "label.comment-content-grad-btn")
for b in buttons:
    try:
        driver.execute_script("arguments[0].click();", b)
        time.sleep(0.3)
    except:
        pass

# コメント抽出
comments = driver.find_elements(By.CSS_SELECTOR, "li.comment")
for c in comments:
    try:
        author = c.find_element(By.CSS_SELECTOR, "span.fn.user-profile").text.strip()
    except:
        author = ""
    try:
        date = c.find_element(By.CSS_SELECTOR, "span.comment_date").text.strip()
    except:
        date = ""
    try:
        body = c.find_element(By.CSS_SELECTOR, "div.comment-content").text.strip()
    except:
        body = ""

    if body:
        results.append({
            "topic_url": topic_url,
            "author": author,
            "date": date,
            "comment": body
        })

# ===== CSV保存 =====
with open(OUTPUT, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=["topic_url", "author", "date", "comment"])
    writer.writeheader()
    writer.writerows(results)

print(f"🎉 テスト完了！ {len(results)} 件のコメントを {OUTPUT} に保存しました")
