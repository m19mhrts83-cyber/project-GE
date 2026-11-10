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
- 書体: **Jarvis ダッシュボードと同じゴシック**（ヒラギノ角ゴ → Noto Sans JP → メイリオ）。見出し・柱の金額も明朝は使わない（2026-11-10 松野さん「視認性・親しみやすさ」）。Web フォントは読み込まず端末の書体を使う
- アイコン: `components/Icon.tsx`（Jarvis と同じ線アイコン、外部ライブラリなし）。メニューのアイコンは `components/Shell.tsx` の `NAV[].icon`
- ホーム: 「いまやること」を注目カード（`hq-focus`）、「データの鮮度」は1行に畳む（`hq-fresh`、詳細は開いて見る）、送信ジョブ失敗は控えめな赤枠（`job-fail`）

## お金の判断ログ（ループウェア型・2026-11-10〜）

お金の判断を「決める → 理由をひとつ残す → 後日に答え合わせ → 週1で基準を見直す」で回す。型は池田朋弘さんのループウェア パターン集（入力 S・伝え方 T・学び方 L）に合わせる。契約は `lib/decisionContract.ts`（正本 `apps/loopware/lib/decisionContract.ts` の写し。`scripts/tests/test_decision_contract.py` が一致を確かめる）。

| 仕掛け | 型 | 実装 |
|---|---|---|
| 判断メモ（理由タグ＋ひとこと。任意） | T02・T03 | `components/DecisionNotePanel.tsx`。資金移動の 承認・相談中へ・取消・完了、物件の 見送り・内見にする・買付へ の直前に出るシート（スマホは下から） |
| よく使う理由を前に並べ、「前回と同じ理由で決める」をワンタップに | L09・L02 | `GET /api/decisions/hints?ctx=money:approved`（`buildHints`）。本人の過去の記録を引くだけで AI は呼ばない。AI が理由を推測して埋めない |
| 「次も同じに」は同じ理由が2回目のときだけ聞く | T09・L03 | 判断メモ内。付けたものは基準の候補（採用は週1で本人が決める） |
| 決める前に、前の「やり直したい」を見せる | S21 | 判断メモの「前の答え合わせ」 |
| 後日の答え合わせ（良かった／まあまあ／やり直したい） | S21 | `components/DecisionRetro.tsx`・`POST /api/decisions/retro`。進めてから14日で `/decisions` の上に出る。元の判断は書き換えず足すだけ |
| 判断にかかった時間・画面が出した候補・前回と同じを使ったか | L11・T01 | `decide_ms`・`suggested_tags`・`same_as_last` |
| AIに渡す文章をコピー（件数に合った頼み方つき） | 学びはツールの外 | `components/CopyForAi.tsx`・`toAiBrief` |
| どの画面でも「声を残す」（使い勝手への声） | 道具そのものの改善 | `components/FeedbackButton.tsx`・`POST /api/feedback`。相談メモ（`kurashift_consultations`・`metadata.kind=app_feedback`・path・tags）に溜まる。815 KURASHIFT更新係が週次で拾って直し、直したら status=decided |

- 記録先（アプリの表）: 資金移動は `kurashift_money_ops.assist_payload.decision_log`（追記のみ・最大50件、最新は `last_decision`、答え合わせは各件の `retro` と `last_retro`）、物件は `kurashift_re_deal_events.payload`（答え合わせは `event_type=note`・`payload.action=retro`・`ref_event_id`）
- 共有の判断ログ: DB トリガー `apps/jarvis-dashboard/supabase/migrations/20261111_kurashift_owner_decisions_retro.sql`（20261110 の上位互換。これ1本でよい）が `owner_decisions` へ写す。surface=`kurashift_money`／`kurashift_deal`、source=`kurashift`（スクリプトが status を変えたときは `script`）。答え合わせは action=`good`／`meh`／`wrong`。Nody `/review` と 314 週次が読む
- 画面: `/decisions`（お金の判断ログ）。件数と内訳・理由が残っている割合・答え合わせ・基準の候補、答え合わせ待ち、共通パターン（同じ理由2件以上）、日ごとの一覧（資金移動／物件で絞れる）、使い勝手への声
- ルールにするかは本人が週1のレビューで決める。アプリ内で自動学習しない。理由が空の判断を推測で埋めない
- テスト: `npm run test:decisions`
