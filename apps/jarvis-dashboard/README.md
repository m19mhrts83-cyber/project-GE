# Jarvis Dashboard（自分用）

Supabase プロジェクト **`jarvis-dashboard`**（ref `idkdqneutpvkhxhpjtgc`）上の認証付き閲覧 UI。  
運営提供の `kamiooya-qa` とは **分離**（引き渡さない）。

## ローカル起動

1. `.env.jarvis_private` に `JARVIS_SUPABASE_*`（特に **SERVICE_ROLE_KEY**）を設定
2. このフォルダの `.env.local` を作成（`.env.example` 参照）。`NEXT_PUBLIC_SUPABASE_ANON_KEY` は private の `JARVIS_SUPABASE_ANON_KEY`
3. ログインは **メール＋パスワード**（`PERSONAL_EMAIL` + `JARVIS_DASHBOARD_PASSWORD`）。Jarvis が Auth ユーザ作成済み。Google OAuth は任意（要 GCP クライアント）
4. データ push:

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
/Users/matsunomasaharu2/selenium_env/venv/bin/python scripts/jarvis_dashboard_push.py
```

5. Web:

```bash
cd ~/git-repos/apps/jarvis-dashboard
npm install
npm run dev
# http://localhost:3001
```

## スキーマ

`supabase/schema.sql`（適用済み: triage_items / watch_status / cards / metrics / sync_meta）
