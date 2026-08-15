# KURASHIFT — 買い進め Job（千三つファネル）仕様

最終更新: 2026-08-15  
対象: Sprint 2 骨格（実装境界の固定）

## 目的

長期目標 **CF 月50万** に向け、条件に合う物件を **情報→内見→買付→融資→購入** で積み上げる。  
「買えない＝失敗」にせず、**件数と転換率**で千三つを可視化する。

## ステータス（`kurashift_re_deals.status`）

| status | 意味 | 千三つ対応 |
|---|---|---|
| `info` | 情報収集・メール候補 | 情報 1000 |
| `viewing` | 内見予定／実施 | 内見 100 |
| `offer` | 買付・交渉 | 引っかかり 10 |
| `loan` | 融資審査中 | — |
| `purchased` | 購入完了 | 購入 3 |
| `passed` | 見送り（学習として残す） | 非失敗 |
| `archived` | 完了アーカイブ | — |

## 供給経路

| 優先 | source | 実装 |
|---|---|---|
| ベース | `mail_admin`（主）＋ `mail_estate`（補完） | dry-run → 候補カード。自動送信なし |
| 追加 | `kenbiya` / `rakumachi` | Sprint 3 |
| 手動 | `manual` | UI／Jarvis |

対外問い合わせは **送信前確認必須**（`jarvis-outbound-confirm`）。

## Gmail 既読（確認／対象外）

| 操作 | status | Gmail |
|---|---|---|
| メール取込・**明らかに対象外** | `passed`（`auto_pass_reason`） | **取込時に既読** |
| メール取込・境界／候補 | `info` / 高スコアは `viewing` | **既読にしない** |
| **確認した** | `info`→`viewing`（以降は維持） | `re_deal_mark_gmail_read` で UNREAD 除去 |
| **対象外**（手動） | `passed` | 同上 |

取込時 auto_pass の判定（`clearly_out_of_scope`）:

- 件名ノイズ（号外・ダイジェスト・税理士 等）
- 区分／ワンルームで戸建なし
- 都内寄りで戸建なし・東海ヒントなし
- スコア `< 2.0`（`CANDIDATE_SCORE_MIN`）

- 紐づけ: `summary_json.gmail_id` ＋ `source`（`mail_admin`→admin token／`mail_estate`→estate）
- 二重実行防止: `summary_json.gmail_read_at`
- UI: `/realestate/deals` → API `POST /api/re/deals/[id]` `{ action: confirm|pass }` → Mac worker
- Jarvis メール振り分け:
  1. **パートナー**（連絡先一覧）→ ダッシュボード「パートナー」（管理軸）
  2. **物件紹介・購入**（**パートナー由来も含む**）→ KURASHIFT で同一土俵評価（Jarvis と併存可）
  3. **その他非パートナー** → Jarvis general（取込時 `mail`＝要確認 / `skim`＝要約）
- ジャンル別要約: `jarvis_other_mail_digest.py`（ホーム「確認したよ」で skim 既読）
- 既存 general pending の物件紹介掃除: `jarvis_triage_gmail_read_catchup.py --cleanup-re-pending`（partner lane は触らない）
- ダッシュボードでスキップ／送信済みにしたメールは Gmail 既読
- KURASHIFT で確認／対象外にした案件も Gmail 既読（`re_deal_mark_gmail_read`）

## 第一問い合わせ（不動産会社）＋返信蓄積＋運営相談

| 操作 | 内容 |
|---|---|
| **第一問い合わせ** | From=**admin**。テンプレは `config/kurashift_re_inquiry_template.yaml`。画面確認後 `re_deal_inquiry_send` |
| **返信取込** | `re_deal_inquiry_poll`（スレッドから inbound を蓄積） |
| **運営相談パック** | `re_deal_ops_pack` → `kurashift_consultations`（lane=`realestate` 予定。未DDL時は general） |

- 蓄積先: `kurashift_re_deal_messages`（DDL: `20260815_kurashift_re_inquiry.sql`）。未適用時は `summary_json.messages` にフォールバック
- 問い合わせ状態: 列 `inquiry_status` または `summary_json.inquiry_status`
- 運営への自動送信はしない（パック作成まで）。Notion 購入判断メモ URL を metadata に保持
- 細かい仕様は第1号案件で詰める

## マッチ入力（買い進め Excel から）

- `kurashift_buy_plan_criteria`（エリア・戸建・利回・価格・土地値・ハザード）
- `kurashift_buy_plan_constraints`（銀行・融資枠・地理条件）
- 現行版: `version_key=251124`（`is_canonical`）

## Q&A 助言

- ソース: `kamiooya-qa`／WeStudy 知識（融資・修繕・空室ヒント優先）
- 保存先: `kurashift_re_deals.advice_json`
- UI: `/realestate/deals` の案件詳細パネル（検索クエリ＝エリア＋構造＋制約キーワード）

## 運営経緯

- 表: `kurashift_ops_consult_events`
- 初回: `809_神大家運営回答/5.やり取り.md` → `scripts/jarvis_kurashift_ops_consult_ingest.py`
- 将来: Gmail admin 主走査＋estate 補完（年次 LP／プラン件名）

## ローン正本

- [借入残高トラッカー](https://loan-tracker-plum.vercel.app/)（Google: **estate**）
- ジョブ案: `re_sync_loan_tracker`（読取投影のみ。Drive 形式調査後）

## Excel export

- 目標: 運営共有用に **STEP3 シート互換** の出力
- 入力: canonical `kurashift_buy_plan_events`
- Sprint 2 では「取込→画面表示」まで。export は次イテレーション可

## ジョブ案（worker）

| job_type | 内容 | 危険度 |
|---|---|---|
| `buy_plan_ingest` | Excel 再取込 | 低 |
| `re_mail_match` | admin/estate 物件メール候補。明らかに対象外は passed＋既読 | 低（候補は送信・既読なし） |
| `re_deal_mark_gmail_read` | 確認／対象外後の Gmail 既読 | 低（UNREAD のみ） |
| `re_deal_inquiry_send` | 不動産会社へ第一問い合わせ（admin） | 中（UI確認必須） |
| `re_deal_inquiry_poll` | 問い合わせスレッドの返信取込 | 低 |
| `re_deal_ops_pack` | 運営相談パック作成 | 低（送信なし） |
| `re_deal_advice` | Q&A 注入 | 低 |
| `re_sync_loan_tracker` | ローン投影 | 低（読取） |
| （将来）問い合わせ下書き | 送信は別確認 | 高 |

## UI 導線（2026-08-13）

1. **長期プラン** `/realestate/buy-plan` — events 年表・criteria・constraints・Excel Jobs  
2. **今狙う** — 同画面 Focus（Notion 条件＋ Excel）  
3. **実行** `/realestate/deals` — 千三つファネル・メール候補・確認／対象外  
4. **運用** `/realestate` — CF・DSCR・名義切替（③-A）

編集者向け: [`docs/KURASHIFT_編集者引き継ぎ_不動産AB_20260813.md`](KURASHIFT_編集者引き継ぎ_不動産AB_20260813.md)

- [ ] canonical Excel が DB に入り、イベント件数が 0 でない
- [ ] `/realestate` に CF 月50万 KPI（定義メモリンク）
- [ ] `/realestate/deals` にファネル件数（空でもステータス軸）
- [ ] 運営経緯が1件以上（キーワードヒットがある場合）
- [ ] 自動問い合わせ送信が走っていない
- [ ] 確認／対象外で Gmail 既読ジョブが succeeded になる
