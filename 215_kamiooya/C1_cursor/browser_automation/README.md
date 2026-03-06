# ブラウザ自動取得（ログイン後の情報抽出）

日能研 MY NICHINOKEN や、今後は銀行サイトなど、ログインが必要なページの内容を自動で取得し、Markdown ファイルに保存するためのスクリプトです。

## 前提

- Python 3.9+
- 認証情報は **環境変数または .env** で管理し、リポジトリには含めません。

## セットアップ（初回のみ）

```bash
cd "C1_cursor/browser_automation"
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

## 日能研 MY NICHINOKEN の設定

1. **認証情報**
   - `browser_automation` フォルダに `.env.example` をコピーして `.env` にリネーム
   - `.env` に ID とパスワードを記入（値は各自のものに置き換え）
   - `.env` は .gitignore 済みなのでコミットされません

2. **設定ファイル**
   - `config_nichinoken.example.yaml` をコピーして `config_nichinoken.yaml` にリネーム
   - 必要に応じて `login_url` や `target_urls` を編集（大人用ログインURLなど）
   - `config_nichinoken.yaml` は .gitignore 済みなのでコミットされません

3. **もしすでにリポジトリに含まれている場合**
   - 過去に `.env` や `config_nichinoken.yaml` をコミットしてしまった場合は、追跡だけ外しローカルファイルは残します。
   - リポジトリルートで次のいずれかを実行:
     - `./C1_cursor/browser_automation/untrack_secrets.sh`（推奨）
     - または手動: `git rm --cached C1_cursor/browser_automation/.env C1_cursor/browser_automation/config_nichinoken.yaml`
   - その後コミットすると、それらはリポジトリから削除され、今後は .gitignore によりコミットされません。

4. **ログイン先の確認**
   - 学生用: https://login.mynichinoken.jp/auth/student/login
   - 大人用: https://login.mynichinoken.jp/auth/parent/login

## 実行方法

```bash
cd "C1_cursor/browser_automation"
source .venv/bin/activate
python fetch_after_login.py nichinoken
```

- 初回は `headless: false` のまま実行し、ブラウザでログインが成功するか確認してください。
- 取得結果は `output/日能研_取得結果_YYYYMMDD_HHMMSS.md` に保存されます（`config_nichinoken.yaml` で `output_dir` を指定すると、そのフォルダに保存されます。例: 500_Obsidian の 02_Clippings/日能研）。
- **月間スケジュールなどの PDF** を取得してテキスト化します。
  - 各ページで見つかった `.pdf` リンクを自動取得（`fetch_pdfs: true`）。
  - **月間スケジュールページ**（target_urls で指定した students-schedule.html）では、「2月」「3月」等のテキストを持つリンク先も PDF として取得を試みます（`fetch_schedule_pdfs: true`）。会場名・日程が書かれたPDFをテキストで検索できるようにします。

## ログインがうまくいかない場合

サイトのログインフォームは変更されることがあります。その場合は以下を確認してください。

- `fetch_after_login.py` 内の「ログインフォーム」コメント付近で、入力欄やボタンのセレクタを調整する必要がある場合があります。
- まずは `config_nichinoken.yaml` で `headless: false` にし、画面を見ながら実行してどこで止まるか確認するとよいです。

## 東海労金 インターネットバンキングの設定

1. **認証情報**
   - `.env` に `TOKAIROKIN_USER` と `TOKAIROKIN_PASS` を追加
   - `TOKAIROKIN_USER`: ログインID（6〜12桁の半角英数字）
   - `TOKAIROKIN_PASS`: パスワード

2. **設定ファイル**
   - `config_tokairokin.example.yaml` をコピーして `config_tokairokin.yaml` にリネーム
   - ログインURLは既定で parasol.anser.ne.jp（実際のログインフォーム）
   - `config_tokairokin.yaml` は .gitignore 済みなのでコミットされません

3. **実行方法**
   - `python fetch_after_login.py tokairokin` でログイン → 振込画面へ遷移
   - **手動クリックモード**（既定: 有効）: トップページで「振込」が押せない場合、`manual_click_transfer_menu: true` のときは「画面上で振込をクリック → クリックしたら Enter」で次を自動実行。`false` にすると従来どおり自動で振込メニューをクリック
   - **振込の自動入力**（オプション）:
     ```bash
     python fetch_after_login.py tokairokin --bank 0005 --branch 405 --account 0526519 --amount 100000
     ```
     - config_tokairokin.yaml の `transfer_form` に各入力欄のCSSセレクタを設定する必要あり
     - 振込フォーム入力後、ワンタイムパスワード（OTP）の入力で一時停止 → 手動で OTP 入力・実行
   - 初回は `headless: false` のまま実行し、画面で動作を確認してください

4. **パスワード変更画面が出る場合（自動化検知の回避）**
   - プログラム起動のブラウザが自動操作と検知され、パスワード変更を促されることがあります
   - **推奨：undetected-chromedriver**（代替手段）
     - `config_tokairokin.yaml` で `use_undetected_chromedriver: true` に設定
     - `pip install undetected-chromedriver selenium` でインストール（requirements.txt に含まれています）
     - WebDriver の検知を回避する専用ライブラリで、CDP・stealth で効果がなかった場合に試してください
   - その他の対策（config_tokairokin.yaml）:
     - **CDP接続モード**: `use_connect_cdp: true` + `auto_start_chrome: true`（既存Chromeを終了→起動→接続）
     - `use_chrome: true`（既定）: インストール済み Chrome を使用
     - `human_like_input: true`: 1文字ずつ遅延入力（補助的な効果）

## 今後：その他銀行サイト用

同じ仕組みで `config_bank.yaml` と `fetch_after_login.py` に `bank` 用の分岐を追加すれば、銀行ログイン後の情報抽出も自動化できます。その際も ID/パスワードは環境変数で管理してください。
