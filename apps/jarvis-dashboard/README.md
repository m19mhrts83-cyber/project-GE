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

### Jarvis Cloud / Gemini（見直し・聞く）

UI で **Jarvis Cloud**（既定）／ **Gemini** を明示選択。

| 画面 | 本線 | フォールバック |
|---|---|---|
| パートナー下書き見直し | Cloud Agent | Mac `jarvis_triage_cursor_revise_worker.py`（通知付き） |
| タスク／ウォッチ「聞く」 | Cloud →（失敗時）Gemini | ローカル用コピー ＋ Mac `jarvis_card_cursor_ask_worker.py` |

切替時はバナーで「Cloud が失敗したため Gemini に…」等を必ず表示。

### 聞くの文脈ソース（注入型）

**Web／no-repo Cloud は OneDrive・Google Drive・ローカル path を直接見ない。**  
Server Action が読んでプロンプトに注入する（`lib/askContextBundle.ts`）。

| ソース | 既定オン | Vercel 秘密 |
|---|---|---|
| カード／コメントスレ | 常時 | `JARVIS_SUPABASE_*`（既存） |
| 神大家 kamiooya-qa | 運営／戸建／物件レーン | `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY`（**運営 PJ・読取のみ**） |
| OneDrive `5.やり取り.md` | partner／物件レーン | `MS_GRAPH_CLIENT_ID` / `REFRESH_TOKEN` / `AUTHORITY` |
| admin Drive／NotebookLM | 手動オン | `GDRIVE_CLIENT_ID` / `SECRET` / `REFRESH_TOKEN` / `NOTEBOOKLM_FOLDER_ID`（`jarvis_gdrive_admin_login.py`） |

失敗したソースは notice のみで聞く自体は続行。同じ根拠ブロックをローカルコピー／Mac キューに同梱する。

```bash
# Mac Worker（一度だけ・revise と ask を同じ runner）
~/git-repos/launchd/install_cursor_revise_worker_launchd.sh
# 手動:
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
/Users/matsunomasaharu2/selenium_env/venv/bin/python scripts/jarvis_triage_cursor_revise_worker.py
/Users/matsunomasaharu2/selenium_env/venv/bin/python scripts/jarvis_card_cursor_ask_worker.py
```

ログ: `~/Library/Logs/jarvis_night_triage/cursor_revise.*.log`  
キー発行: https://cursor.com/dashboard/api → `.env.jarvis_private` と Vercel に `CURSOR_API_KEY`

### NotebookLM 作業セット

サイドバー **NotebookLM** → `/notebooklm`。Mac で localhost ヘルパー（`127.0.0.1:8766`）が動いていれば Finder（`200_NoteBookLM`）＋ NotebookLM を一括オープン。未起動時は Web リンクのみ。

```bash
~/git-repos/launchd/install_notebooklm_workbench_launchd.sh
```

設定: `config/notebooklm_workbench.yaml`／任意 `NOTEBOOKLM_DRIVE_FOLDER_URL`。

### アプリ・プロンプト集（`/apps`）

サイドバー **アプリ・プロンプト集**。自作アプリ・MyPrompt・NotebookLM の入口一覧。正本 `config/apps_prompts_catalog.yaml`（表示用 JSON と同期）。周辺MAP自動作成の Raimo 入口: https://ma-qr4gudwmgqtg.raimo-app.buzz

### 課金／SaaS（`/billing`）

サイドバー **サブスク・課金**。正本 `config/subscriptions.yaml` → `jarvis_subscriptions_push.py --push`（`jarvis_dashboard_push.py` にも同梱）。

- push 時に `.jarvis_state/subscriptions_snapshots/YYYY-MM.json` と `sync_meta.subscriptions_monthly_summary` を更新
- `/billing` 先頭に確認サマリー（新規・金額変更・注視・前月比）
- 月次促し（1〜8日）: `jarvis_billing_monthly_check.py` / `--mark-done`

### 設計メモ・引き継ぎ

- 本体: [`docs/Jarvis_Dashboard_設計メモ_20260801.md`](../../docs/Jarvis_Dashboard_設計メモ_20260801.md)
- NotebookLM 投入: [`docs/Jarvis_Dashboard_NotebookLM投入_20260801.md`](../../docs/Jarvis_Dashboard_NotebookLM投入_20260801.md)
- Drive: `200_NoteBookLM/05_Jarvisダッシュボード_設計と引き継ぎ/`

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
   - `NEXT_PUBLIC_SUPABASE_URL` / `NEXT_PUBLIC_SUPABASE_ANON_KEY`（**jarvis-dashboard**・`sb_publishable_…`）
   - `NEXT_PUBLIC_SITE_URL` = 本番 URL
   - （送信・見直し・聞く）`CURSOR_API_KEY` / 任意 `GEMINI_API_KEY` / `GMAIL_*`
   - （聞く・神大家注入）`SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY`（**kamiooya-qa 読取のみ**。JARVIS_SUPABASE_* とは別）
   - （聞く・OneDrive 注入）`MS_GRAPH_CLIENT_ID` / `MS_GRAPH_REFRESH_TOKEN` / `MS_GRAPH_AUTHORITY=consumers`
   - （聞く・Drive／NotebookLM）`GDRIVE_CLIENT_ID` / `GDRIVE_CLIENT_SECRET` / `GDRIVE_REFRESH_TOKEN` / `GDRIVE_NOTEBOOKLM_FOLDER_ID`
3. Supabase Auth → URL Configuration:
   - Site URL = 本番 URL
   - Redirect URLs に `https://….vercel.app/auth/callback` を追加（ローカルも残す）
4. **jarvis-dashboard** の `JARVIS_SUPABASE_SERVICE_ROLE_KEY` は Mac push 専用（Vercel のブラウザ向けには載せない）。運営 `SUPABASE_SERVICE_ROLE_KEY` は Server Action 読取用のみ Vercel 可

```bash
# CLI がある場合
cd ~/git-repos/apps/jarvis-dashboard
npx vercel --prod
```
