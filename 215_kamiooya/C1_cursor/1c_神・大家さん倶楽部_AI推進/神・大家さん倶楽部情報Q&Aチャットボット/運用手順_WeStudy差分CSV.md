# WeStudy 全件抽出・管理者CSV・差分運用

## 概要

1. **スクレイプ**（`westudy_forum_all.py`）でフォーラム全トピックのコメントをトピック別 CSV に保存  
2. **変換**（`scripts/convert_to_admin_csv.py`）で WeStudy **管理者CSV** と同じ列名・形式の全件 CSV を生成  
3. **差分**（`scripts/build_delta_csv.py`）で「前回までに state に記録したコメントID以外」を差分 CSV に出力し、チャットボットの「CSV取込」に渡す  
4. **自動取込**（`scripts/upload_csv_to_limo.py`）で LIMO アプリへ管理者ログインし、`delta_*.csv` を画面から取り込む  

生成物の既定の保存先は **OneDrive 固定**です（`CHATBOT_OUTPUT_ROOT` 未設定時）。
`CHATBOT_OUTPUT_ROOT` を設定した場合のみ、任意の保存先へ変更できます。

| 種別 | パス |
|------|------|
| 生スクレイプ（トピック別フォルダ） | `<CHATBOT_OUTPUT_ROOT>/exports/raw/<RUN_ID>/` |
| 管理者形式・全件 | `<CHATBOT_OUTPUT_ROOT>/exports/full_<RUN_ID>.csv` |
| 管理者形式・差分 | `<CHATBOT_OUTPUT_ROOT>/exports/delta_<RUN_ID>.csv` |
| 実行ログ | `<CHATBOT_OUTPUT_ROOT>/exports/logs/pipeline_<RUN_ID>.log` |
| 一気通貫ログ | `<CHATBOT_OUTPUT_ROOT>/exports/logs/update_and_import_<RUN_ID>.log` |
| スクレイプ完了フラグ・done_topics | `<CHATBOT_STATE_ROOT>/westudy_scrape/`（未設定時 `<CHATBOT_OUTPUT_ROOT>/state/...`） |
| 差分判定用（既知コメントID） | `<CHATBOT_STATE_ROOT>/westudy_comment_ids.json`（未設定時 `<CHATBOT_OUTPUT_ROOT>/state/...`） |

## 前提

- **Python 3**（`python3`）
- **Google Chrome** と **Selenium** 用 **ChromeDriver**（`westudy_forum_all.py` が `webdriver.Chrome()` を使用）
- 環境変数（`~/.zshrc` 等）:
  - `WESTUDY_USER` … WeStudy / WordPress ログインID  
  - `WESTUDY_PASS` … パスワード  
  - `LIMO_APP_URL` … LIMO アプリURL  
  - `LIMO_ADMIN_EMAIL` … 管理者ログインID  
  - `LIMO_ADMIN_PASSWORD` … 管理者パスワード  

スクレイパ本体の正本は `git-repos` 側です（既定パス）:

- `~/git-repos/ProgramCode/alfred_python/westudy_forum_all.py`  
  別の場所に置いている場合は `WESTUDY_SCRAPER` で上書きしてください。

## ワンショット実行（推奨）

```bash
chmod +x scripts/run_westudy_pipeline.sh   # 初回のみ
chmod +x scripts/run_update_and_import.sh  # 初回のみ

# フル: スクレイプ → 全件CSV → 差分CSV（state 更新）
./scripts/run_westudy_pipeline.sh

# 一気通貫: スクレイプ → 差分生成 → LIMOへ自動取込（推奨）
./scripts/run_update_and_import.sh

# ブラウザ表示でスクレイプ（デバッグ時）
./scripts/run_westudy_pipeline.sh --show

# 全トピック再取得（完了フラグを無視）
./scripts/run_westudy_pipeline.sh --force

# 一気通貫で再取得（--force はそのまま透過）
./scripts/run_update_and_import.sh --force

# 既に raw があるときは変換・差分だけ
./scripts/run_westudy_pipeline.sh --convert-only "/path/to/exports/raw/20260101-120000"

# スクレイプを省略し、指定 raw から変換・差分だけ
./scripts/run_westudy_pipeline.sh --skip-scrape "/path/to/raw"
```

`PYTHON` / `WESTUDY_SCRAPER` / `CHATBOT_OUTPUT_ROOT` / `CHATBOT_STATE_ROOT` を変えたい場合は実行前に export してください。

LIMO ログイン情報は `scripts/.env.example` をもとに環境変数へ設定してください。

```bash
set -a && source scripts/.env && set +a
```

## 個別コマンド

### 1. スクレイプのみ

```bash
export WESTUDY_USER=... WESTUDY_PASS=...
python3 ~/git-repos/ProgramCode/alfred_python/westudy_forum_all.py \
  --output-root "/path/to/raw_run" \
  --state-dir "/path/to/神・大家さん倶楽部情報Q&Aチャットボット/state/westudy_scrape"
```

### 2. 管理者形式への変換のみ

```bash
python3 scripts/convert_to_admin_csv.py \
  --input-dir "/path/to/raw_run" \
  -o exports/full_manual.csv -v
```

### 3. 差分のみ

```bash
python3 scripts/build_delta_csv.py \
  --full exports/full_manual.csv \
  --state state/westudy_comment_ids.json \
  --delta exports/delta_manual.csv \
  --update-state
```

### 初回だけ「DBには入れたが state は空」のとき

アプリ側に既に全件取り込み済みで、これ以降は差分だけ出したい場合:

```bash
python3 scripts/build_delta_csv.py \
  --full exports/full_初回.csv \
  --state state/westudy_comment_ids.json \
  --delta exports/delta_empty.csv \
  --init-state-only \
  --replace-state
```

これで `westudy_comment_ids.json` が「そのフルCSVのID集合」に完全一致し、差分CSVはヘッダのみになります。

## チャットボットへの取り込み

1. 通常は `./scripts/run_update_and_import.sh` を実行（自動ログイン＋自動取込）  
2. 原則 **`<CHATBOT_OUTPUT_ROOT>/exports/delta_<RUN_ID>.csv`** を投入（初回は state が空なので実質全件）  
3. 2回目以降は純粋な差分のみ投入  
4. 監査や再同期が必要なときだけ **`<CHATBOT_OUTPUT_ROOT>/exports/full_<RUN_ID>.csv`** を手動利用  

取込仕様は `app.js` の `importCsvComments`（日本語ヘッダ `コメントID` / `投稿日時` / `コメント内容` 等）に整合しています。

## 定期実行（例: launchd / cron）

- 実行コマンド: `run_westudy_pipeline.sh` のフルパスを指定  
- 頻度: 日次または週次  
- 長時間になるため `caffeinate` と併用してもよいです  

```bash
caffeinate -dimsu /path/to/.../scripts/run_westudy_pipeline.sh
```

## GitHub Actions での週次実行

`215_kamiooya/.github/workflows/westudy-limo-weekly.yml` で、以下を**毎週 1 回**（日曜 06:30 JST 目安）自動実行します。

1. WeStudy スクレイプ  
2. 差分CSV生成  
3. 差分が 1 件以上のときのみ LIMO 自動取込（0件ならスキップ）

いつでも手動実行する場合は、GitHub の **Actions** タブで **WeStudy Delta Import Weekly** を選び **Run workflow** から実行できます。

### 事前設定（GitHub Secrets）

必須:

- `WESTUDY_USER`
- `WESTUDY_PASS`
- `LIMO_APP_URL`

推奨（1段目ログイン）:

- `LIMO_PORTAL_EMAIL`
- `LIMO_PORTAL_PASSWORD`

互換（PORTAL を使わない場合）:

- `LIMO_ADMIN_EMAIL`
- `LIMO_ADMIN_PASSWORD`

必要時のみ（2段目ログインが出る環境）:

- `LIMO_APP_EMAIL`
- `LIMO_APP_PASSWORD`

### 補足

- Actions はランナー上の一時ディレクトリに `exports` を出力し、`state` だけをリポジトリへコミットして次回実行に引き継ぎます。
- 実行ログと差分CSVは Actions Artifact（14日保持）に保存されます。
- 手動実行（`workflow_dispatch`）では `force_scrape=true` を指定すると `--force` で再取得できます。

## 障害時の確認

| 症状 | 確認先 |
|------|--------|
| スクレイプが進まない | `<CHATBOT_OUTPUT_ROOT>/exports/raw/<RUN_ID>/westudy_run.log`、同階層の `westudy_heartbeat.json`、ウォッチドッグ PNG |
| 変換0行 | `convert_to_admin_csv.py -v` の `files` / `rows_read`、入力ディレクトリに `*.csv` があるか |
| 差分が常に全件 | `<CHATBOT_STATE_ROOT>/westudy_comment_ids.json` が消えていないか、`--update-state` 付きで一度流したか |
| 取込エラー | Excel で「CSV UTF-8（コンマ区切り）」で保存し直す、1行目ヘッダが管理者形式と一致しているか |
| 自動ログイン失敗 | `LIMO_APP_URL` / `LIMO_ADMIN_EMAIL` / `LIMO_ADMIN_PASSWORD` の値、`<CHATBOT_OUTPUT_ROOT>/exports/logs/limo_import_ng_*.png` を確認 |
| playwright 未導入 | `pip install playwright` と `playwright install chromium` を実行 |

## 補足: dry-run 相当の確認

自動アップロード前に CSV 生成だけ確認したい場合:

```bash
./scripts/run_westudy_pipeline.sh
ls -1t "${CHATBOT_OUTPUT_ROOT:-/Users/matsunomasaharu/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/C1_cursor/1c_神・大家さん倶楽部_AI推進/神・大家さん倶楽部情報Q&Aチャットボット}/exports/delta_"*.csv | head -n 1
```

差分がヘッダのみ（行数1）なら `run_update_and_import.sh` はアップロードをスキップして正常終了します。
