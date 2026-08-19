# KURASHIFT（旧 Trade Desk）

**暮らしを整え、資産を動かす。** Jarvis ダッシュボードとは別アプリ（別 Vercel プロジェクト）。

- 認証・データ: 自己用 Supabase `jarvis-dashboard`
- ローカル: `npm run dev` → http://localhost:3003
- コードパスは当面 `apps/trade-desk`（npm パッケージ名は `kurashift`）
- 定型ルーティン: 画面ボタン → `kurashift_jobs` → Mac `jarvis_kurashift_job_worker.py`
- 手順正本: `docs/Trade_Desk.md` / `docs/運用コマンド一覧.md` §7.6
- **ユーザー検証**: `docs/KURASHIFT_検証プラン.md`（サイクル A〜F）

## 環境変数

`.env.example` を参照。本番は Vercel に `NEXT_PUBLIC_SUPABASE_*` と `NEXT_PUBLIC_SITE_URL` を入れる。  
Notion 看板（`/notion`）は `NOTION_API_TOKEN`（正本 `.env.jarvis_private`、投影は `scripts/jarvis_notion_token_sync.py`）。

## Vercel ブランド

- リンク済みプロジェクト名（現状）: `jarvis-trade-desk`
- 画面タイトル／ログイン見出しは **KURASHIFT**（`app/layout.tsx` / `login`）
- ダッシュボード上の表示名を変えるときは Vercel → Project Settings → General → Project Name  
  （例: `kurashift`）。ルート URL を変える場合はドメイン設定も合わせて確認
