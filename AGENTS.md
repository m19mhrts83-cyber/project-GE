# AGENTS.md

## 神大家運営の新規作業（2026-10-29）

さくらいふ株式会社／神・大家さん倶楽部運営に関する新規の有償作業は、概算工数・安全係数・概算金額を提示し、メールまたはChatworkで運営の承認を得てから着手する。未承認の可能性があれば、AI側から「見積もり・運営承認は済んでいますか」と指摘し、過去実績に基づく見積案を出す。詳細の正本: `docs/神大家運営_新規作業の事前見積もり承認ルール_20261029.md`。

作業中は累計実績＋残工数から完了見込みを更新し、超過・2割以上超過見込みを記録して松野さんへ調整案を出す。詳細は同じ正本の「着手後の工数と超過見込みの記録」。表示先は松野さん個人のJARVIS Dashboardで、運営との共有・運営への開発費請求は前提にしない。

## AI使用量とツール選択（2026-10-28）

同じ品質・安全性なら、AI使用量と追加費用が少ない順で進める。原則は、取得済み記録・専用スクリプト → 公式API／コネクタ／MCP／CLI → DOM等を直接読める内蔵ブラウザ／Chrome → スクリーンショット中心のComputer Use → 重いモデル・従量課金。Web作業は内蔵ブラウザを第一候補にするが、構造化経路の方が軽く確実ならそちらを優先する。重い経路へ上げた場合は理由を一言報告する。正本: `docs/AIエージェントチーム/49_共通ルール_AI使用量と入力_20261024.md`。

## ツール間の引き継ぎ（2026-10-26）

JARVIS/Claude Code由来の案件をCodexが続行したら、各ターンの最終報告前に `/Users/matsunomasaharu2/git-repos/agent-handoff/` の元担当宛てメモを更新する（Claude Code→`to_MissLemon/`、Cursor→`to_Jarvis/`）。起点はユーザー指定・元会話で確認する。受取側は再開時に現在の案件のpendingを読み、実変更を確認して続行する。詳細の正本: `docs/AIエージェントチーム/51_ローカル受け渡し_20261026.md`。別worktreeでも上記絶対パスを使う。

## 議事録のまとめ方（2026-10-29・全エージェント共通）

Notion に議事録を残すときは、Genspark 等の要約をそのまま貼らず、`docs/AIエージェントチーム/52_議事録のまとめ方_20261029.md` の型で仕上げてから載せる。Notion に残す前の了承と、チャットでの「3行要約＋宿題」は従来どおり。

## 下書きの判断ログ（2026-11-09・全エージェント共通）

運営・パートナー・LINE など、松野さんに見せる返信／報告の下書きは次の順で作る。
1. 書く前に `python scripts/jarvis_draft_decision_log.py context --recipient <宛先>` で採用済みルールと最近の直しを読み、沿っているかを一言添えて見せる。
2. 下書きは `push` で Nody の「下書きを直す」（/drafts）にも置ける。松野さんが箇所（段落タップ・範囲選択・画面中央の段落）ごとに声でダメ出し → その場で1件ずつ判断ログ（owner_decisions・surface=draft_review, action=comment）に残る → 「まとめて直す」で Mac の Cursor（定額。`scripts/jarvis_draft_revise_worker.py`、`launchd/cursor_revise_worker_runner.sh` が45秒ごと）が新しい版を作る → 差分で確認。版ごとの直しも判断ログに残る。従量課金の AI API は使わない。確定後は `pull --id` で受け取る。
3. チャットで直しを受けたときは、版ごとに `log` で記録する。理由が分からない直しは推測で埋めず、`--reason` を省いて質問として残す。
ルールにするかは松野さんが決める（土曜の週次で候補 → Nody の「今週の学び」で採用 → 211 の learned_rules.md）。エージェントが勝手にルール化しない。

## Cursor Cloud specific instructions

このリポジトリは個人自動化モノレポ（Jarvis）です。クラウドで実際に動かせる「アプリ」は次の4つです。Python スクリプト群（`scripts/`, `215_kamiooya/`, `line_unofficial_poc/` など）は Mac 専用（`/Users/matsunomasaharu2` 等のハードコードパス・launchd・Selenium 前提）で、クラウド環境では動かしません。

### 動かせるアプリと起動方法

| アプリ | 種別 | ポート | 起動 |
|---|---|---|---|
| `apps/kamiooya-qa-web` | Next.js 16 (API サービス) | 3000 | `cd apps/kamiooya-qa-web && npm run dev` |
| `apps/jarvis-dashboard` | Next.js 15 (認証ダッシュボード) | 3001 | 下記の env を渡して `npm run dev` |
| `apps/prompt-share` | Next.js 16 (チャプロ代替プロンプト共有) | 3002 | `cd apps/prompt-share && npm run dev`（本番: https://prompt-share-taupe.vercel.app） |
| `apps/trade-desk` | Next.js 15 (KURASHIFT・ライフプラン／資産HQ) | 3003 | 下記の env を渡して `npm run dev` |
| `apps/loopware` | Next.js 15 (312/313 判断 UI) | 3004 | `cd apps/loopware && npm run dev`（本番: https://jarvis-loopware.vercel.app。ダッシュは外部リンクのみ） |
| `apps/loopware-mini` | 素の Node.js（依存なし。SNS投稿文ミニループウェア） | 3000（`PORT` で変更可） | `cd apps/loopware-mini && npm start`（`.env.local` が必要。キー無しは `LLM_PROVIDER=mock`。手順は同フォルダの `SETUP.md`） |
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

### apps/trade-desk（KURASHIFT）

- 起動（注入済み env を利用）:
  `NEXT_PUBLIC_SUPABASE_URL="$JARVIS_SUPABASE_URL" NEXT_PUBLIC_SITE_URL="http://localhost:3003" npm run dev`
- ③-C 保有マスタの鍵番号ライブ取得には `NOTION_API_TOKEN`（Jarvis ダッシュボードと同じ Internal Integration）。未設定時は YAML キャッシュ（`config/property_info.yaml`）。
- Cloud Secrets と Vercel プロジェクト `jarvis-trade-desk` の両方に入れる。対象 DB「DB_物件情報」（所有物件関係）を Integration の「接続」で共有すること。トークンの値はチャットに出さない。

### ルート静的サイト（不動産賃貸管理会社検索）

- `python3 -m http.server 8000` で配信。地図検索の実行にはブラウザで Google Maps API キー入力が必要（キー無しでも UI シェルは表示）。
