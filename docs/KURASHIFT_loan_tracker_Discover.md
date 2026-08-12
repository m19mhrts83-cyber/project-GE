# 借入残高トラッカー — Drive 調査メモ（Sprint 2）

日付: 2026-08-13  
Google アカウント（正）: **estate** `matsuno.estate@gmail.com`  
アプリ: https://loan-tracker-plum.vercel.app/

## 調査結果

| 項目 | 結果 |
|---|---|
| KURASHIFT 側ジョブ | `re_sync_loan_tracker`（playbook 登録済み・実装なし） |
| `.env` の専用 ID | **未設定**（`LOAN_TRACKER_*` なし） |
| `token_estate.json` のスコープ | Gmail のみ（Drive なし） |
| Drive 検索 | **不可**（`invalid_scope`）。estate に Drive readonly を付与して再調査が必要 |

## 次の一手（ユーザー起床後で可）

1. estate で Drive API 用 OAuth を追加（または loan-tracker が使うシート／フォルダ ID を `.env.jarvis_private` に `LOAN_TRACKER_DRIVE_FOLDER_ID` / `LOAN_TRACKER_SHEET_ID` として追記）
2. 形式（Sheets か CSV か JSON）を確定
3. `scripts/jarvis_kurashift_loan_tracker_sync.py` で読取投影のみ実装

## 方針（変更なし）

- トラッカーがローン正本。KURASHIFT は二重入力しない
- トラッカーへの書込はしない
