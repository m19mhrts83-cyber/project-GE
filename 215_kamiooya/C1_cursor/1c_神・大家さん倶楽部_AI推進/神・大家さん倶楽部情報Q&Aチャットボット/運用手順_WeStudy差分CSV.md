# WeStudy 全件抽出・管理者CSV・差分運用

## 概要

1. **スクレイプ**（`westudy_forum_all.py`）でフォーラム全トピックのコメントをトピック別 CSV に保存  
2. **変換**（`scripts/convert_to_admin_csv.py`）で WeStudy **管理者CSV** と同じ列名・形式の全件 CSV を生成  
3. **差分**（`scripts/build_delta_csv.py`）で「前回までに state に記録したコメントID以外」を差分 CSV に出力し、チャットボットの「CSV取込」に渡す  
4. **自動取込**（`scripts/upload_csv_to_raimo.py`）で Raimo アプリへ管理者ログインし、`delta_*.csv` を画面から取り込む  
5. **Supabase 取込**（`scripts/upload_csv_to_supabase.py`）で `delta_*.csv` を `comments` テーブルへ upsert（`SUPABASE_URL` 設定時。`run_update_and_import.sh` に統合済み）

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
  - `RAIMO_APP_URL` … Raimo 公開URL（ミニアプリ）  
  - `RAIMO_APP_EMAIL` / `RAIMO_APP_PASSWORD` … 公開URLの1段ログイン（推奨）  
  - `RAIMO_PORTAL_*` … 従来のポータル経由（2段）を使う場合のみ  
  - `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` … Supabase へ差分 upsert（任意・並行運用時）  

スクレイパ本体の正本は `git-repos` 側です（既定パス）:

- `~/git-repos/ProgramCode/alfred_python/westudy_forum_all.py`  
  別の場所に置いている場合は `WESTUDY_SCRAPER` で上書きしてください。

## ワンショット実行（推奨）

```bash
chmod +x scripts/run_westudy_pipeline.sh   # 初回のみ
chmod +x scripts/run_update_and_import.sh  # 初回のみ

# フル: スクレイプ → 全件CSV → 差分CSV（state 更新）
./scripts/run_westudy_pipeline.sh

# 一気通貫: スクレイプ → 差分生成 → Supabase upsert → Raimoへ自動取込（推奨）
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

Raimo ログイン情報は `scripts/.env.example` をもとに環境変数へ設定してください。

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

**project-GE リポジトリ直下**の `.github/workflows/westudy-raimo-weekly.yml` で、以下を**毎週 1 回**（日曜 06:30 JST 目安）自動実行します。  
（`215_kamiooya/.github/` 配下に置いても GitHub は読み込みません。）

1. WeStudy スクレイプ（**cron 週次は `--force` で全トピック再取得**。新規コメントは完了済みトピックにも付くため）  
2. 差分CSV生成（**state 更新は Raimo 取込成功後**）  
3. 差分が 1 件以上のときのみ Raimo 自動取込（0件ならスキップ）

いつでも手動実行する場合は、GitHub の **Actions** タブで **WeStudy Delta Import Weekly** を選び **Run workflow** から実行できます。

### 事前設定（GitHub Secrets）

必須:

- `WESTUDY_USER`
- `WESTUDY_PASS`
- `RAIMO_APP_URL`

推奨（1段目ログイン）:

- `RAIMO_PORTAL_EMAIL`
- `RAIMO_PORTAL_PASSWORD`

互換（PORTAL を使わない場合）:

- `RAIMO_ADMIN_EMAIL`
- `RAIMO_ADMIN_PASSWORD`

必要時のみ（2段目ログインが出る環境）:

- `RAIMO_APP_EMAIL`
- `RAIMO_APP_PASSWORD`

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
| 自動ログイン失敗 | `RAIMO_APP_URL` / `RAIMO_ADMIN_EMAIL` / `RAIMO_ADMIN_PASSWORD` の値、`<CHATBOT_OUTPUT_ROOT>/exports/logs/raimo_import_ng_*.png` を確認 |
| Supabase 取込失敗 | `Supabase取込完了:` 行、プロジェクト Active、`SUPABASE_SERVICE_ROLE_KEY` |
| playwright 未導入 | `pip install playwright` と `playwright install chromium` を実行 |

## 補足: dry-run 相当の確認

自動アップロード前に CSV 生成だけ確認したい場合:

```bash
./scripts/run_westudy_pipeline.sh
ls -1t "${CHATBOT_OUTPUT_ROOT:-/Users/matsunomasaharu2/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/C1_cursor/1c_神・大家さん倶楽部_AI推進/神・大家さん倶楽部情報Q&Aチャットボット}/exports/delta_"*.csv | head -n 1
```

差分がヘッダのみ（行数1）なら `run_update_and_import.sh` はアップロードをスキップして正常終了します。

## Supabase 初回ブートストラップ（全件取込）

Raimo に既に取込済みの過去分を Supabase `comments` に揃える手順です。

1. Supabase プロジェクト `kamiooya-qa` が **Active** であること（休止中は Dashboard で Restore）
2. [`apps/kamiooya-qa-web/supabase/schema.sql`](../../../../apps/kamiooya-qa-web/supabase/schema.sql) が適用済みであること
3. `scripts/.env` に `SUPABASE_URL` と `SUPABASE_SERVICE_ROLE_KEY` を設定
4. WeStudy 全件再取得（4月以前の `full_*.csv` だけでは Raimo state より不足するため `--force` 推奨）:

```bash
set -a && source scripts/.env && set +a
./scripts/run_westudy_pipeline.sh --force
```

5. 最新 `full_*.csv` を Supabase へ一括 upsert:

```bash
LATEST_FULL="$(ls -1t exports/full_*.csv | head -n 1)"
python3 scripts/upload_csv_to_supabase.py --bootstrap --csv "$LATEST_FULL"
```

6. 件数確認（目安: `state/westudy_comment_ids.json` の ID 数と同程度）:

```bash
# Supabase SQL Editor または MCP
# SELECT count(*) FROM public.comments;
```

初回ブートストラップでは **`westudy_comment_ids.json` は更新しません**（Raimo 週次と state を共有するため）。

### Supabase 週次（Raimo 並行）

`run_update_and_import.sh` 実行時、環境変数があれば **Supabase → Raimo** の順で `delta_*.csv` を取り込みます。GitHub Actions（`westudy-raimo-weekly.yml`）でも同様。Secrets に `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` を登録してください。

### Supabase 障害時

| 症状 | 確認先 |
|------|--------|
| `SUPABASE_URL が未設定` | `scripts/.env`、Actions Secrets |
| upsert 失敗 | ログの `Supabase取込完了:` 行、プロジェクトが Active か |
| 重複エラー | `comments_comment_id_unique` インデックスが適用されているか |
| state が進まない | `SUPABASE_FAIL_OPEN=0` 時は Supabase 失敗で state 更新しない（意図どおり） |

## 関連: 動画文字起こし（Notta）

詳細は `運用手順_Notta取込.md` を参照。
