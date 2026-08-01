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

### NotebookLM 作業セット

サイドバー **NotebookLM** → `/notebooklm`。Mac で localhost ヘルパー（`127.0.0.1:8766`）が動いていれば Finder（`200_NoteBookLM`）＋ NotebookLM を一括オープン。未起動時は Web リンクのみ。

```bash
~/git-repos/launchd/install_notebooklm_workbench_launchd.sh
```

設定: `config/notebooklm_workbench.yaml`／任意 `NOTEBOOKLM_DRIVE_FOLDER_URL`。

### 収集の役割分担

| 経路 | 内容 |
|---|---|
| Mac | パートナー MD・CHRLINE・フル夜間トリアージ・状況ウォッチ全文 → push |
| GHA Gmail | admin INBOX 未返信候補 → `triage_items`（`jarvis-dashboard-gmail-triage.yml`） |
| GHA Watch | 収集鮮度・WeStudy CI など API 完結項目 → `watch_status`（`jarvis-dashboard-situation-watch.yml`） |
| Cloud Agent | 対話本線。Notion／NotebookLM は Cloud MCP。手順: `docs/Jarvis_Cloud_Agent.md` |
| 表示 | 本 Vercel アプリ（取得経路・Mac/GHA 時刻を概要に表示） |
| Mac 電力CF | `jarvis_energy_cf_collect.py` → `energy_cf.json`＋`metrics`（エネワン／売電／オリコ） |

### 電力・太陽光 CF

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
python scripts/jarvis_energy_cf_collect.py --push
```

設定: `config/energy_cf.yaml`。状況ウォッチ＋`/metrics` に表示。

### OneDrive Graph（レーン GHA・委任）

原本は個人用 OneDrive。GHA／Cloud は **委任＋refresh**（手順正本: `docs/Jarvis_OneDrive_Graph.md`）。

1. Azure でアプリ登録（個人 Microsoft アカウント・パブリッククライアント）
2. 委任: `Files.Read` / `Files.Read.All` / `offline_access` / `User.Read`
3. `.env.jarvis_private` に `MS_GRAPH_CLIENT_ID` / `MS_GRAPH_AUTHORITY=consumers` / `MS_GRAPH_REFRESH_TOKEN`
4. `python scripts/jarvis_ms_graph_device_login.py` → `python scripts/jarvis_onedrive_graph.py --probe`
5. `python scripts/jarvis_ms_graph_secrets_to_gha.py` → `gh workflow run jarvis-dashboard-lanes.yml`
6. refresh 回転: `python scripts/jarvis_ms_graph_sync_refresh.py --push-gha`

Mac のみ: Graph 未設定時はローカル CloudStorage へフォールバック。Journal（Google Drive）は GHA スキップ。

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
