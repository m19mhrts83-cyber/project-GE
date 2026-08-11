# Trade Desk

株・資産デスク。**Jarvis ダッシュボードとは別アプリ**（別 Vercel プロジェクト）。

- 認証・データ: 自分用 Supabase `jarvis-dashboard`（3つ目の PJ は作らない）
- ローカル: `npm run dev` → http://localhost:3003
- ダッシュボードと同じメール＋パスワードでログイン（ドメインが違うのでクッキーは共有しない）

## 環境変数

`.env.example` を参照。本番は Vercel に `NEXT_PUBLIC_SUPABASE_*` と `NEXT_PUBLIC_SITE_URL` を入れる。

Supabase Auth の Redirect URLs に本番オリジン `/auth/callback` を追加する。
