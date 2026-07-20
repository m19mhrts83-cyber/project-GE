# GAS導入手順

## 運用の正本と OneDrive バックアップ

| 役割 | 場所 |
|---|---|
| **正本（運用）** | Google ドライブ上のスプレッドシート（`saiten_google_config_backup.yaml` 参照） |
| **提供版スナップショット** | `WeStudy_採点自動化_V1.0_20260627.xlsx` + `04_gas_Code_V2.1_V1.0.gs`（**V1.0 提供開始 2026-06-27**） |
| **最新 xlsx コピー** | `WeStudy_採点自動化_バックアップ.xlsx` |
| **GAS コード** | 同フォルダの `04_gas_Code_V2.1.gs` |

正本から xlsx を再取得する場合:

```bash
cd ~/git-repos/215_kamiooya/C1_cursor/1c_神・大家さん倶楽部_AI推進/採点自動化
~/selenium_env/venv/bin/python 18_export_spreadsheet_backup.py
```

---

## 0. Excel から復旧する場合（推奨）

`.xlsx` には GAS が含まれません。次の順で **Google スプレッドシートを新規作成** してから GAS をバインドします。

```bash
cd ~/git-repos/215_kamiooya/C1_cursor/1c_神・大家さん倶楽部_AI推進/採点自動化

~/selenium_env/venv/bin/python 15_create_google_spreadsheet.py \
  --source-xlsx "$HOME/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/C1_cursor/1c_神・大家さん倶楽部_AI推進/採点自動化/WeStudy_採点自動化_バックアップ.xlsx" \
  --write-config
```

### 0-1. Apps Script API を有効化（初回のみ・GCP オーナー）

OAuth クライアント `credentials.json` の GCP プロジェクト `yaritori-gmail-487109` で **Apps Script API** を有効にします。  
**オーナー `m19m.hrts83@gmail.com` でログイン**してから次を開き、「有効にする」を押してください。

https://console.cloud.google.com/apis/library/script.googleapis.com?project=yaritori-gmail-487109

有効化後、反映まで 1〜2 分かかることがあります。

### 0-1b. ユーザー設定で Apps Script API を ON（デプロイに使うアカウント）

GCP 側とは別に、**デプロイ実行アカウント**（例: `matsuno.estate@gmail.com`）でも ON が必要です。

1. https://script.google.com/home/usersettings を開く（対象アカウントでログイン）
2. **「Google Apps Script API」** をオン
3. 保存後 1〜2 分待つ

### 0-2. GAS を API でアップロード

```bash
cd ~/git-repos/215_kamiooya/C1_cursor/1c_神・大家さん倶楽部_AI推進/採点自動化

~/selenium_env/venv/bin/python 16_deploy_gas.py \
  --spreadsheet-id "$(grep saiten_spreadsheet_id ~/git-repos/215_kamiooya/C1_cursor/westudy_common/kamiooya_google_config.yaml | awk '{print $2}')"
```

- 初回はブラウザで OAuth 同意（既定: `m19m.hrts83@gmail.com`）。スプレッドシート所有者が `matsuno.estate@gmail.com` の場合は `--login-hint matsuno.estate@gmail.com` でも可（API 有効化さえ済んでいればどちらでも可）。
- スプレッドシートをデプロイ用アカウントに共有済みでないとき: `--share-with m19m.hrts83@gmail.com`（estate 側 Drive トークンで共有）

既に Apps Script がバインドされている場合は、拡張機能 → Apps Script で `04_gas_Code_V2.1.gs` を手動置換するか、空プロジェクトを削除して再実行してください。

API デプロイが使えない場合は、下記「2. Apps Script にコードを貼り付け」の手動手順に進んでください。

---

## 1. スプレッドシートを作成

任意のGoogleスプレッドシートを作成し、以下シートを作る。

- `設定`
- `元データ`
- `得点基準`
- `採点結果`
- `ログ`
- `集計`（任意）
- `補正学習データ`（任意）

`得点基準` には `02_得点基準_seed.csv` の内容を貼り付ける。

## 2. Apps Scriptにコードを貼り付け

1. スプレッドシートから `拡張機能 > Apps Script` を開く
2. デフォルトの `Code.gs` を置換して `04_gas_Code_V2.1.gs` の内容を貼る
3. 保存
4. スプレッドシートを再読込 → メニュー **「採点自動化」** に4項目あることを確認
   - CSV取込
   - 採点実行
   - **補正学習データを追加**
   - ヘッダー初期化

## 3. 設定シートを入力

`設定` シートに以下を入力:

| A列 | B列 |
|---|---|
| GEMINI_API_KEY | あなたのAPIキー |
| GEMINI_MODEL | gemini-2.5-flash |
| TARGET_MONTH | （空白で可・未使用） |
| DRIVE_CSV_FOLDER_ID | 採点用フォルダ ID（初回1回） |
| DRIVE_CSV_FILENAME | WeStudy_for_scoring.csv |
| SOURCE_SHEET_NAME | 元データ |
| RULES_SHEET_NAME | 得点基準 |
| RESULT_SHEET_NAME | 採点結果 |
| LOG_SHEET_NAME | ログ |
| MAX_ROWS_PER_RUN | 5（試行）または 50（本番） |
| INCLUDE_REPLIES | FALSE |

**MAX_ROWS_PER_RUN**: 空白にすると **全件採点** します。試行時は `5` から始めてください。

**CSV 取込**: フォルダ内の `WeStudy_for_scoring.csv` を自動読込。毎月は同名ファイルを **上書き** するだけ（File ID 変更不要）。

## 4. 実行順序

1. Apps Script画面で `initializeSheets` を1回実行（権限許可）※`15_create_google_spreadsheet.py` 使用時はヘッダー済みのため省略可
2. メニュー **「CSV取込」**（元データが既にある場合は省略可）
3. メニュー **「採点実行」**
4. `採点結果` を確認
5. 手動補正後、メニュー **「補正学習データを追加」**（任意）

## 5. 処理フロー

1. `元データ` を上から走査
2. 返信除外設定に従い対象判定
3. `得点基準` を文字列化してGeminiへ送信
4. JSONレスポンスを `採点結果` へ追記
5. エラーは `採点結果.エラー` および `ログ` へ記録

## 6. メニュー「採点自動化」が出ないとき

再読込だけでは出ない場合があります（API デプロイ直後によくある）。**次の3ステップ**を試してください。

1. [Apps Script エディタ](https://script.google.com/home/projects/1Bu6FP_1_ARQ8FPSODi13iAg8aoILrSufc7gm4ff9snx7h_CVn0eAPpD0/edit) を開く
2. 関数一覧で **`setupMenuTrigger`** を選び **実行**（初回は権限 **許可**）
3. スプレッドシートに戻り **再読込**（`Cmd+Shift+R`）

- **「ヘッダー初期化」や `onOpen` をエディタから実行してもメニューは出ません**（UI コンテキストの制限）
- メニューは **ヘルプの左** に **「採点自動化」**（4項目）と表示されます
- ログインは **`matsuno.estate@gmail.com`** で
