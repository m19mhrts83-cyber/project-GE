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
③-C の鍵番号ライブ取得には、ダッシュボードと同じ `NOTION_API_TOKEN` を **Vercel `jarvis-trade-desk`** にも入れる（未設定時は YAML キャッシュ）。

## Vercel ブランド

- リンク済みプロジェクト名（現状）: `jarvis-trade-desk`
- 画面タイトル／ログイン見出しは **KURASHIFT**（`app/layout.tsx` / `login`）
- ダッシュボード上の表示名を変えるときは Vercel → Project Settings → General → Project Name  
  （例: `kurashift`）。ルート URL を変える場合はドメイン設定も合わせて確認

## 見た目（Personal Board デザインシステム・2026-11-07〜）

- 正本: Claude の Design System「Personal Board」https://claude.ai/artifact/F9dySGWWbRcU6yT3WW4nJj （Jarvis と部品は共通・テーマは別）
- 実装: `app/theme-kurashift.css` を `globals.css` の後に読み込み、色・背景グラデーション・すりガラスのカード・森の緑のサイドバー・注目カードだけを上書き
- テーマ: アイボリーの紙＋深い森の緑（`--accent`）＋真鍮（注目）。Jarvis（紺＋シアン）と被せない
- 書体: 本文はゴシックのまま。**ホームの見出しと「3本の柱」の金額だけ明朝**（Shippori Mincho／ヒラギノ明朝。Web フォントは読み込まず、端末の明朝を使う）
- アイコン: `components/Icon.tsx`（Jarvis と同じ線アイコン、外部ライブラリなし）。メニューのアイコンは `components/Shell.tsx` の `NAV[].icon`
- ホーム: 「いまやること」を注目カード（`hq-focus`）、「データの鮮度」は1行に畳む（`hq-fresh`、詳細は開いて見る）、送信ジョブ失敗は控えめな赤枠（`job-fail`）
