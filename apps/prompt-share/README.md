# prompt-share（チャプロ代替プロンプト共有）

神大家向けのプロンプト共有アプリ。チャプロ MyPrompt の「通常」相当を自前で提供する。

## 技術

- Next.js 16 + React 19
- Supabase `kamiooya-qa`（service_role。既存 `users` で管理者判定）
- 独自 cookie セッション（HMAC）

## 環境変数

| 変数 | 用途 |
|---|---|
| `SUPABASE_URL` | kamiooya-qa URL |
| `SUPABASE_SERVICE_ROLE_KEY` | service_role |
| `SESSION_SECRET` | セッション署名 |
| `NEXT_PUBLIC_SITE_URL` | 公開URL生成用（例: https://prompt-share.vercel.app） |

## 本番

https://prompt-share-taupe.vercel.app

## 起動

```bash
cd apps/prompt-share
npm install
# .env.local に上記を設定
npm run dev   # http://localhost:3002
```

## ルート

| パス | 内容 |
|---|---|
| `/` | 公開プロンプト一覧 |
| `/g/{slug}` | グループ別一覧 |
| `/p/{token}` | プロンプト利用（変数入力・コピー） |
| `/admin/login` | 管理者ログイン |
| `/admin` | ダッシュボード |
| `/admin/prompts` | プロンプト一覧・編集 |
| `/admin/groups` | グループ管理 |
| `/admin/stats` | 利用統計 |

## DB

`supabase/schema.sql` → `prompt_groups` / `prompts` / `prompt_usage_events`
