# 神・大家さん倶楽部 AIナビ（サーバー側の部品）

本番の画面は Raimo のミニアプリ。画面の正本は
`215_kamiooya/C1_cursor/1c_神・大家さん倶楽部_AI推進/神・大家さん倶楽部情報Q&Aチャットボット/`
（`index.html`・`app.js`・`style.css`・API 定義）で、反映は同フォルダの `scripts/publish_raimo_1346.py`。

このフォルダに残すもの:

- `supabase/functions/` … Edge Functions（raimo-auth・semantic-search・community-attachments・qa-analytics・qa-search-log・srt-ingest）
- `supabase/migrations/` … データベースの変更（本番への適用は `kamiooya-qa-release` のワークフローか手作業。PR では当てない）
- `lib/` … Edge Functions とテストが使う共通部品
- `tests/` … `npm test`（または `node --experimental-strip-types --test tests/*.test.mjs`）
- `data/knowledge.csv` … ローカルの参照データ（`scripts/jarvis_kurashift_deal_advice.py` が読む）

旧 Next.js 版の画面と API（2026-11-28 まで `app/` にあった）は使っていないため消した。
`vercel.json` は自動公開を止めたまま残す（このフォルダを Vercel が build しないように）。

## 運用メモ: 講座動画探し（スイッチ `video_finder`、PR #709 の続き）

2026-11-28 に本番で使える状態にした記録（会員情報・鍵は書かない）。

- 本番（東京プロジェクト）の `semantic-search`（v6）と `raimo-auth`（v11）はどちらも #709 のコード（`video_finder`）を含むことを関数本体で確認した。再 deploy は不要だった。
- スイッチ表 `qa_feature_flags` の `video_finder` を `owner`（名指し1人）→ `admins`（管理者・master_admin の役割の人全員。`lib/featureFlags.ts` の STAFF_ROLES）に変更。会員全体（`all`）には広げていない。
- 確かめ: gateway 証明（`X-Gateway-Proof`）で本番 `semantic-search` に `video_finder:true` で「公庫について解説している講座の動画を探して」を1回投げた。回答の最初に「公庫」がタイトルに入る5件（先頭が「【実践】公庫の基本を知る」）が出た。検索ログ `app_qa_search_events` に確かめ分は1件（session_id `verify-709-20261128`）。
- 注意: `~/git-repos/.env.jarvis_private` の `SEMANTIC_SEARCH_URL` は移行前の旧プロジェクトを指していて、確かめには使えない（東京の `/functions/v1/semantic-search` を使う）。
- 全員に広げる手順（松野さんの了承後）: `update public.qa_feature_flags set stage='all' where feature='video_finder';` 戻す時は `'admins'` または `'off'`。
