# 借入残高トラッカー — データはどこにあるか（2026-08-13）

アプリ: https://loan-tracker-plum.vercel.app/  
Google アカウント（正）: **estate** `matsuno.estate@gmail.com`

## 結論（画面だけでは分からない理由）

トラッカーの一覧は **ブラウザに永続保存されていません**。  
ログインした Google アカウントの **Google Drive 上の専用ファイル** が正本です。

| 層 | 中身 | KURASHIFT が触るか |
|---|---|---|
| 画面 | 残高・月返済・金利の表示 | 見ない（スクレイピングしない） |
| `GET /api/data` | ログイン後に Drive から読んだ JSON | セッションがあれば読める |
| Google Drive | 専用ファイル（**マイドライブに出ないことが多い**） | 読取投影のみ |

ヘルプ原文: 「Google アカウントでログインし、借入データを Google Drive に保存します。」  
保存ボタンは「Google Drive に保存」。FAQ: 「データはあなたの Google Drive 上のファイル」。

いわゆるスプレッドシート ID を画面からコピーする場所はありません。  
Drive デスクトップ（m19m / admin）を検索しても **該当 JSON は見つかりませんでした**。  
estate の Drive は Mac にマウントされていません。

## なぜ Jarvis の Gmail token では探せないか

`token_estate.json` のスコープは **Gmail のみ**。Drive 一覧は `invalid_scope`。  
さらに、アプリが `drive.file` / `appDataFolder`（アプリ専用の隠し領域）を使っている場合、  
**loan-tracker 自身の OAuth クライアント以外からはファイルが見えない**ことがあります。

## KURASHIFT 側の受け皿（実装済）

- 表: `kurashift_loan_tracker_loans`（読取投影。トラッカーへは書かない）
- ジョブ: `re_sync_loan_tracker` → `scripts/jarvis_kurashift_loan_tracker_sync.py`
- UI: `/realestate/properties` の「ローン投影」

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_loan_tracker_sync.py --discover
```

## 残ブロッカー（どれか1つで同期できる）

1. **JSON 書き出し**（最短）  
   トラッカーで一覧または返済予定の JSON/CSV を保存し、  
   `.env.jarvis_private` に `LOAN_TRACKER_JSON_PATH=/絶対パス` を追記 → `--apply`
2. **estate で Drive 読取 OAuth**（`token_estate_drive.json`）  
   見えるファイルなら Discover が ID を拾う。隠し領域なら 1 か 3。
3. **ログイン済みセッションで `/api/data`**  
   Cursor ブラウザで estate ログイン後に Jarvis が JSON 形を確定して投影。

## 方針（変更なし）

- トラッカーがローン正本。KURASHIFT は二重入力しない
- トラッカーへの書込はしない
