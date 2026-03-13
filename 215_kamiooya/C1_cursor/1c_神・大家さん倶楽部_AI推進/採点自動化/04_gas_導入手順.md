# GAS導入手順

## 1. スプレッドシートを作成

任意のGoogleスプレッドシートを作成し、以下シートを作る。

- `設定`
- `元データ`
- `得点基準`
- `採点結果`
- `ログ`

`得点基準` には `02_得点基準_seed.csv` の内容を貼り付ける。

## 2. Apps Scriptにコードを貼り付け

1. スプレッドシートから `拡張機能 > Apps Script` を開く
2. デフォルトの `Code.gs` を置換して `04_gas_Code.gs` の内容を貼る
3. 保存

## 3. 設定シートを入力

`設定` シートに以下を入力:

| A列 | B列 |
|---|---|
| GEMINI_API_KEY | あなたのAPIキー |
| GEMINI_MODEL | gemini-2.0-flash |
| TARGET_MONTH | 2026-03 |
| DRIVE_CSV_FILE_ID | Drive上CSVのFile ID |
| SOURCE_SHEET_NAME | 元データ |
| RULES_SHEET_NAME | 得点基準 |
| RESULT_SHEET_NAME | 採点結果 |
| LOG_SHEET_NAME | ログ |
| MAX_ROWS_PER_RUN | 50 |
| INCLUDE_REPLIES | FALSE |

## 4. 実行順序

1. Apps Script画面で `initializeSheets` を1回実行（権限許可）
2. `importCsvByConfig` を実行してCSV取込
3. `runScoring` を実行
4. `採点結果` を確認

## 5. 処理フロー

1. `元データ` を上から走査
2. 返信除外設定に従い対象判定
3. `得点基準` を文字列化してGeminiへ送信
4. JSONレスポンスを `採点結果` へ追記
5. エラーは `採点結果.エラー` および `ログ` へ記録

