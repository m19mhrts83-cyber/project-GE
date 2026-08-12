# KURASHIFT（旧 Trade Desk）

**暮らしを整え、資産を動かす。** Jarvis ダッシュボードとは別アプリ（別 Vercel プロジェクト）。

- 認証・データ: 自分用 Supabase `jarvis-dashboard`
- ローカル: `npm run dev` → http://localhost:3003
- コードパスは当面 `apps/trade-desk`
- 定型ルーティン: 画面ボタン → `kurashift_jobs` → Mac `jarvis_kurashift_job_worker.py`
- 手順正本: `docs/Trade_Desk.md` / `docs/運用コマンド一覧.md` §7.6

## 環境変数

`.env.example` を参照。本番は Vercel に `NEXT_PUBLIC_SUPABASE_*` と `NEXT_PUBLIC_SITE_URL` を入れる。
