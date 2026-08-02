# AGENTS.md

## Cursor Cloud specific instructions

このリポジトリは個人自動化モノレポ（Jarvis）です。クラウドで実際に動かせる「アプリ」は次の3つです。Python スクリプト群（`scripts/`, `215_kamiooya/`, `line_unofficial_poc/` など）は Mac 専用（`/Users/matsunomasaharu2` 等のハードコードパス・launchd・Selenium 前提）で、クラウド環境では動かしません。

### 動かせるアプリと起動方法

| アプリ | 種別 | ポート | 起動 |
|---|---|---|---|
| `apps/kamiooya-qa-web` | Next.js 16 (API サービス) | 3000 | `cd apps/kamiooya-qa-web && npm run dev` |
| `apps/jarvis-dashboard` | Next.js 15 (認証ダッシュボード) | 3001 | 下記の env を渡して `npm run dev` |
| ルート静的サイト | 素の HTML/JS（Google Maps） | 8000 | `python3 -m http.server 8000`（`index.html`） |

- Node は v22 系。依存は各アプリで `npm install`（lockfile は `package-lock.json` = npm）。標準コマンドは各 `README.md` 参照。
- ビルド確認: 各アプリで `npm run build`（両方成功します）。

### Lint はリポジトリ未整備（既知）

- どちらのアプリにも ESLint 設定ファイルが無く、`npm run lint` は現状機能しません。
  - `kamiooya-qa-web` は Next.js 16 で `next lint` が廃止され、`lint` を引数扱いしてエラーになります。
  - `jarvis-dashboard` の `next lint` は対話プロンプトで停止します（`devDependencies` に eslint も無い）。
- これは環境ではなくリポジトリ側の未整備です。型チェックは `npm run build`（`tsc`）でカバーされます。

### apps/kamiooya-qa-web（神大家 Q&A）

- コア機能は `data/knowledge.csv` に対する検索＋引用で、**シークレット無しで動きます**（`POST /api/search`, `POST /api/chat`）。
- 注意（データの落とし穴）: コミット済みの `data/knowledge.csv` は先頭に `#` コメント行があり、`lib/knowledge.ts` の `loadKnowledge()` は `#` 行をスキップしないため、そのままでは検索ヒットが 0 件になります。実運用では管理者形式 CSV（`コメントID,投稿日時,投稿者名,投稿者メール,コメント内容,…` のヘッダ）で置き換えます（`data/knowledge.sample.csv` が正しい形式の見本）。ローカル検証時は正しいヘッダの CSV を一時的に置いてください。
- 日本語検索のトークナイザは漢字＋ひらがなが連続すると 1 トークンにまとまります。`/api/search`・`/api/chat` はキーワードを**半角スペース区切り**（例: `原状回復 費用`, `火災保険 保険料`）にするとヒットしやすいです。
- 任意: `OPENAI_API_KEY`（AI 回答）、管理/認証系 API は kamiooya-qa プロジェクトの `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY`（`JARVIS_SUPABASE_*` とは別プロジェクト）。無くてもコア検索は動作。
- トップ `/` は `/raimo/index.html`（外部 Raimo バックエンド前提の静的バンドル）へリダイレクトし、このリポジトリ内では動きません。自己完結の確認は上記 API を叩くのが確実です。

### apps/jarvis-dashboard（自分用ダッシュボード）

- 起動には `NEXT_PUBLIC_SUPABASE_URL` と `NEXT_PUBLIC_SUPABASE_ANON_KEY`（新形式 `sb_publishable_…`）が必要（`middleware.ts` が全リクエストで `supabase.auth.getUser()` を呼ぶ）。値が空だと `createServerClient` が throw します。
- クラウド Secrets に次が注入済み: `JARVIS_SUPABASE_URL`（このプロジェクトの URL）、`JARVIS_SUPABASE_SERVICE_ROLE_KEY`（サーバー専用）、`NEXT_PUBLIC_SUPABASE_ANON_KEY`（publishable `sb_publishable_…`）。**service_role キーを `NEXT_PUBLIC_` に載せない**こと（`jarvis-supabase-free-one-project.mdc` 参照）。
- dev 起動（注入済み env を利用。`NEXT_PUBLIC_SUPABASE_ANON_KEY` はそのまま、URL は `JARVIS_SUPABASE_URL` を割当）:
  `NEXT_PUBLIC_SUPABASE_URL="$JARVIS_SUPABASE_URL" NEXT_PUBLIC_SITE_URL="http://localhost:3001" npm run dev`
  → `GET /` は 307 で `/login` にリダイレクト、ログイン後は `/` に認証済みダッシュボードが表示されます。
- ログイン検証（Secrets にアカウントが無い場合）: service_role で使い捨てユーザーを作り、検証後に削除する。作成は `POST $JARVIS_SUPABASE_URL/auth/v1/admin/users`（`{"email":…,"password":…,"email_confirm":true}`、apikey/Authorization=service_role）、ログイン確認は `POST /auth/v1/token?grant_type=password`（apikey=anon）、削除は `DELETE /auth/v1/admin/users/{id}`。自分用DBへの書き込みなので検証後は必ず削除する。
- `.env.local` は `.gitignore` 済み（ルート `.env.*`）。秘密はコミットしないこと。

### ルート静的サイト（不動産賃貸管理会社検索）

- `python3 -m http.server 8000` で配信。地図検索の実行にはブラウザで Google Maps API キー入力が必要（キー無しでも UI シェルは表示）。
