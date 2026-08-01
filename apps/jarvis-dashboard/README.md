# Jarvis Dashboard（自分用）

Next.js + Supabase Auth（メール／パスワード）。プロジェクト `jarvis-dashboard`。

## ローカル

```bash
cd ~/git-repos/apps/jarvis-dashboard
# .env.local は .env.example を参考に JARVIS_SUPABASE_* から埋める
npm run dev   # http://localhost:3001
```

ログイン: `.env.jarvis_private` の `PERSONAL_EMAIL` / `JARVIS_DASHBOARD_PASSWORD`

## Mac → Supabase push

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
/Users/matsunomasaharu2/selenium_env/venv/bin/python scripts/jarvis_dashboard_push.py
```

夜間トリアージ後にも自動 push（`JARVIS_SUPABASE_SERVICE_ROLE_KEY` があるとき）。

## Vercel デプロイ（Phase 3・iPhone 閲覧）

1. Vercel にログインし、ルートを `apps/jarvis-dashboard` にして import
2. Environment Variables:
   - `NEXT_PUBLIC_SUPABASE_URL`
   - `NEXT_PUBLIC_SUPABASE_ANON_KEY`
   - `NEXT_PUBLIC_SITE_URL` = 本番 URL（例 `https://….vercel.app`）
3. Supabase Auth → URL Configuration:
   - Site URL = 本番 URL
   - Redirect URLs に `https://….vercel.app/auth/callback` を追加（ローカルも残す）
4. service_role は Vercel に載せない（Mac push 専用）

```bash
# CLI がある場合
cd ~/git-repos/apps/jarvis-dashboard
npx vercel --prod
```
