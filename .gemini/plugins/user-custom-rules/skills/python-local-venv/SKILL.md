---
name: python-local-venv
description: Python 実行はローカル venv を使う（OneDrive 上の venv は使わない）。Use when executing Python scripts or recommending Python command lines.
---

# Python 実行環境の指定

## 方針

- **Python スクリプトの実行は、OneDrive 上ではなくローカルの venv（主に /Users/matsunomasaharu2/selenium_env/venv）を使う。**
- OneDrive 上の `.venv_gmail` 等は起動が遅くタイムアウトすることがあるため、エージェントが Python を実行するときは下記のいずれかを指定する。
- **ProgramCode は git-repos に統合済み**。パスは `~/git-repos/ProgramCode/` とする。

## 実行環境のバリエーション

### 共通環境（1つでよい場合）

- **パス**: `/Users/matsunomasaharu2/selenium_env/venv/bin/python`
- **用途**: やり取りメール送信（yoritoori_send.py）、Gmail 取得（gmail_to_yoritoori.py）、iMessage 連携（imessage_to_yoritoori.py）、Excel/PDF変換など、スクリプト実行全般。

### 別環境（分けたい場合）

- **Selenium・スクレイピング・通常用**: `/Users/matsunomasaharu2/selenium_env/venv/bin/python`
- **その他（個別の依存関係がある場合）**: `~/git-repos/ProgramCode/venv_gmail/bin/python` または `~/git-repos/ProgramCode/venv/bin/python` を適宜作成して使用する。

## エージェントの振る舞い

- **具体的な `cd` 行とスクリプト引数のセット**は、`~/git-repos/docs/運用コマンド一覧.md` を開いてそのまま用いる（正本）。
- インタプリタだけ先に決める場合:
  - 基本・Selenium・通常処理 → `/Users/matsunomasaharu2/selenium_env/venv/bin/python`
  - `line_unofficial_poc` → 当該リポジトリの `.venv/bin/python`
  - どちらか不明なときはまず `/Users/matsunomasaharu2/selenium_env/venv/bin/python` でよい。

## 禁止すること

- OneDrive 上の `.venv_gmail/bin/python` を実行に使わない（タイムアウトしやすいため）。
