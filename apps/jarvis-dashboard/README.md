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

## 本番 URL

https://jarvis-dashboard-amber.vercel.app/

朝の自動オープンは `JARVIS_DASHBOARD_URL`（`.env.jarvis_private`）を優先。

### 収集の役割分担

| 経路 | 内容 |
|---|---|
| Mac | パートナー MD・CHRLINE・フル夜間トリアージ・状況ウォッチ全文 → push |
| GHA Gmail | admin INBOX 未返信候補 → `triage_items`（`jarvis-dashboard-gmail-triage.yml`） |
| GHA Watch | 収集鮮度・WeStudy CI など API 完結項目 → `watch_status`（`jarvis-dashboard-situation-watch.yml`） |
| 表示 | 本 Vercel アプリ（取得経路・Mac/GHA 時刻を概要に表示） |

### OneDrive Graph（Phase 3c・骨格）

原本は OneDrive。クラウド収集・エージェントは `scripts/jarvis_onedrive_graph.py` 経由で読む想定。

1. Azure Portal でアプリ登録（クライアント資格情報）
2. API アクセス許可: `Files.Read.All`（Application）＋管理者同意
3. `.env.jarvis_private` に `MS_GRAPH_TENANT_ID` / `CLIENT_ID` / `CLIENT_SECRET` / `USER_UPN`（または `DRIVE_ID`）
4. 確認: `python scripts/jarvis_onedrive_graph.py --dry-run` → `graph_configured: true`
5. パス例は `config/onedrive_graph.example.yaml`

未設定時は Mac のローカル CloudStorage パスへフォールバック（クラウドでは読めない）。

### Auth Site URL

パスワードログインは現状どおり可。OAuth／マジックリンク用に揃えるなら:

```bash
# Access Token（Dashboard → Account → Access Tokens）を jarvis_private の SUPABASE_ACCESS_TOKEN へ
python scripts/jarvis_supabase_auth_urls.py
```

403 のときは手動: [URL Configuration](https://supabase.com/dashboard/project/idkdqneutpvkhxhpjtgc/auth/url-configuration)  
Site URL = `https://jarvis-dashboard-amber.vercel.app`、Redirect に `/auth/callback` と localhost:3001。


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
