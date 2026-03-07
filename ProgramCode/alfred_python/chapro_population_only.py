#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import subprocess
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


CHAPRO_URL = "https://chapro.jp/prompt/321186/2526"
CHATGPT_URL = "https://chat.openai.com/"


def get_address_from_alfred() -> str:
    if len(sys.argv) > 1:
        return sys.argv[1].strip()
    return sys.stdin.read().strip()


def copy_to_clipboard(text: str):
    p = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
    p.communicate(text.encode("utf-8"))


def open_chatgpt():
    subprocess.run(["open", CHATGPT_URL])


def inject_address_safely(prompt: str, address: str) -> str:
    """
    プロンプトの先頭に住所情報を明示的に追加する
    （ChapRoの内部構造に一切依存しない安全版）
    """
    header = (
        "【調査対象住所】\n"
        f"{address}\n\n"
    )
    return header + prompt


def main():
    address = get_address_from_alfred()
    if not address:
        return

    options = Options()
    options.add_argument("--lang=ja-JP")
    options.add_argument("--window-size=1200,900")

    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, 30)

    try:
        # =====================
        # ChapRo
        # =====================
        driver.get(CHAPRO_URL)

        prompt_area = wait.until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "textarea.form-control")
            )
        )

        original_prompt = prompt_area.get_attribute("value")

        # ★ ここが最終解
        new_prompt = inject_address_safely(original_prompt, address)

        # React対策：全文を書き戻す
        driver.execute_script(
            """
            arguments[0].value = arguments[1];
            arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
            arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
            """,
            prompt_area,
            new_prompt
        )

        # プロンプト生成
        generate_btn = wait.until(
            EC.element_to_be_clickable(
                (By.XPATH, "//button[contains(text(),'プロンプトを生成')]")
            )
        )
        generate_btn.click()

        # 生成結果取得
        result = wait.until(
            EC.presence_of_element_located(
                (
                    By.XPATH,
                    "//pre[string-length(normalize-space()) > 200]"
                    " | //div[string-length(normalize-space()) > 200]"
                )
            )
        )

        chapro_prompt = result.text.strip()

        # 人間に渡す
        copy_to_clipboard(chapro_prompt)
        open_chatgpt()

    finally:
        driver.quit()


if __name__ == "__main__":
    main()
