# 借入残高トラッカー — これから一緒に作る（2026-08-13）

アプリ URL（未使用）: https://loan-tracker-plum.vercel.app/  
Google アカウント（正）: **estate** `matsuno.estate@gmail.com`

## 現状（ユーザー確認 2026-08-13）

- **アプリはまだ使っていない。** 中身のまとめを共有してもらい、教えながら進める。
- Drive OAuth や `/api/data` の探索は **一旦止める**（データがまだ無い）。
- KURASHIFT 側の投影表（`kurashift_loan_tracker_loans`）と同期スクリプトは受け皿だけ用意済み。

## 次の一手

1. ユーザーが「中身のまとめ」（借り入れ一覧・残高・金利・返済など見たい項目）を共有する
2. Jarvis が項目を KURASHIFT の投影表／画面に落とす案を出す
3. アプリを使い始めたら、正本をトラッカーにするか・KURASHIFT 入力にするかを決める

## 受け皿（実装済・未接続）

- 表: `kurashift_loan_tracker_loans`（読取投影。トラッカーへは書かない）
- ジョブ: `re_sync_loan_tracker` → `scripts/jarvis_kurashift_loan_tracker_sync.py`
- UI: `/realestate/properties` の「ローン投影」

アプリを使い始めたあとの接続候補（今は不要）:

1. JSON/CSV 書き出し → `LOAN_TRACKER_JSON_PATH`
2. estate Drive 読取 OAuth
3. ログイン済みセッションで `GET /api/data`

## 方針（変更なし）

- トラッカーを使い始めたら、そちらをローン正本にする。KURASHIFT は二重入力しない
- トラッカーへの書込はしない
