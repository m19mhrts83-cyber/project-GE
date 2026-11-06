# フロー — 113 物件買進め確認係（#deal-active 棚卸し＋KURASHIFT連携）

- FlowForge: https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_RM18Xwo_pNXzMLpYwB9mU-pM （この flow.md を写す。未反映）
- 出典: 提案「#deal-active 棚卸し運用とKURASHIFT連携の提案」 https://claude.ai/artifact/G2ffExn6DTxaNt1A5dEyrk
- 承認: 松野さん 2026-11-05「いいね、進めて」（担当113・内見候補から載せる・14日／月曜朝・閉じた案件は7日後に削除、の4点とも推奨案で確定）
- 更新: 2026-11-05（初版。チャッピーで磨く前の叩き台）

## いまの結論（文字1行）

KURASHIFT（正本）で内見候補以上になった案件を、113 が #deal-active に **1案件1スレッド** で写し、段階が変われば書き換え、**14日動きがなければ月曜朝に「どうしますか？」**（続ける／保留／見送り）。消すのは**松野さんがボタンで閉じた案件だけ**で、見送りは KURASHIFT 側にも戻す。

## 案件スレッドの状態

```
進行中 ──14日動きなし──▶ 要確認 ──「続ける」──▶ 進行中（次回確認 +14日）
  ▲                        │  「保留」──▶ 保留（30日後に再確認）
  │段階が変わった          │  2回無回答かつ30日動きなし ──▶ 休眠（たたむ。KURASHIFT は変えない）
  └────────────────────────┘
どの状態からでも 松野さん「見送り」「完了」 ──▶ クローズ ──7日後──▶ 削除
```

AI が自分で動かすのは「要確認」「休眠」まで。クローズは必ず松野さんのボタン（または手での削除）から始まる。

## 4点の型

### 1. トリガー（合図）

| # | 合図 | 種別 | 実装 |
|---|---|---|---|
| T1 | 毎朝 7:30 JST の見回り（KURASHIFT 差分を写す） | 時間 | GHA（`kurashift-re-daily-inquiry` に相乗り or 専用 `deal-active-113.yml`） |
| T2 | 月曜 8:00 JST の「どうしますか？」 | 時間 | 同じ GHA の月曜分岐 |
| T3 | Slack のボタンが押された | 届いたら | jarvis-dashboard `/api/slack/consult-action` に `deal113_*` の受け口を追加 |
| T4 | 「deal-active 整理して」と頼まれた | 人が頼む | 同じスクリプトを手動実行（workflow_dispatch） |
| T5 | 内見日確定の前日 | 時間 | T1 の中で `summary_json.viewing.date = 明日` を拾う |

### 2. 実行権限

| 操作 | 可否 | 線引き |
|---|---|---|
| Supabase `kurashift_re_deals`・`kurashift_re_deal_events`・台帳 `comm_items` を読む | ○ 自動 | 読むだけ |
| #deal-active へ親メッセージ投稿・書き換え・スレッド返信（Bot トークン） | ○ 自動 | 社内 Slack への写し。対外送信ではない |
| `summary_json.slack_deal_active` の書き込み（ts・次回確認日など） | ○ 自動 | 113 が持つ項目のみ。他の項目は触らない |
| KURASHIFT の status を `passed` にする | △ ボタン経由のみ | 松野さんが「見送り」を押したときだけ。`deal_events` に記録 |
| Slack メッセージの削除 | △ ルール許可済み | 松野さんが閉じた案件を7日後に消すのみ（2026-11-05 一度許可） |
| 仲介・銀行への連絡、買付、申込 | × | やらない（511 の許可付き送信・松野さん） |

### 3. 作業内容（ステップ）

| # | 内容 | 方法 | 人/AI |
|---|---|---|---|
| 1 | 対象を読む: status が `viewing`・`offer`・`loan`、または `summary_json.pursue` が立っているフォロー中の案件（`pursue_exclude` は除く。判定は `apps/trade-desk/lib/reDealPursue.ts` に合わせる） | Supabase 読取 | AI |
| 2 | 「最後に動いた日」を出す: `deal_events` と `comm_items`（仲介とのやり取り）の新しい方 | ルール | AI |
| 3 | 未掲載の案件 → 親メッセージを投稿（4行: 段階・次の一手・期限・KURASHIFT リンク）し、ts を `summary_json.slack_deal_active` に保存 | Slack Bot | AI |
| 4 | 段階が変わった案件 → 親メッセージを書き換え、スレッドに経緯を1行（例「11/8 内見日確定」） | Slack Bot | AI |
| 5 | 内見日が明日の案件 → スレッドに内見チェックリスト（`VIEWING_CHECKLIST`・S3 ヒアリング項目） | Slack Bot | AI |
| 6 | 月曜のみ: 14日動きなし・期限切れ・保留の再確認日が来た案件を1枚の「どうしますか？」カードにまとめて #deal-active に投稿（各案件に 続ける／保留／見送り） | Slack Bot | AI → **人が決める** |
| 7 | ボタン処理: 続ける=次回確認+14日／保留=+30日／見送り=status `passed`＋クローズ表示／完了=クローズ表示 | consult-action | **人が押す** → AI |
| 8 | 2回無回答かつ30日動きなし → 親メッセージを「休眠」表示にたたむ | Slack Bot | AI |
| 9 | クローズから7日経った親メッセージ・スレッドを削除 | Slack Bot | AI（ルール許可済み） |
| 10 | Slack で手で消された案件を見つけたら「KURASHIFT も見送りにしますか？」と聞くだけ | Slack Bot | AI → **人が決める** |

**「次の一手」の文面**: ルール（段階ごとの定型文）で作る。AI で整えるのは任意で、なくても動く。
**初回**: 既存の手作業スレッド3件（瀬戸 西吉田町 400万／碧南 幸町 190万／キャラメル101 募集賃料）を、最初の「どうしますか？」カードに載せて松野さんに決めてもらう。キャラメル101 は保有物件なので「見送り」ではなく「完了（deal-active から外す）」を推奨表示にする。

### 4. 報告

| 種別 | 行き先 | 内容 |
|---|---|---|
| 案件そのもの | `#deal-active` | 1案件1スレッド＋月曜の「どうしますか？」カード |
| 日次の要約 | `#report` | 追加・更新・休眠・削除の件数。**変化ゼロなら送らない** |
| 要判断 | `#consult` | 手で消された案件の扱い、KURASHIFT と食い違う案件。末尾「次の担当」3行 |
| 失敗 | `#ops` | Supabase／Slack API の失敗 |
| 判断の履歴 | Todoist | 「見送り」「完了」の判断は Todoist の 113 タスクにコメント（後で） |

## データの持ち方（migration 不要）

`kurashift_re_deals.summary_json.slack_deal_active`:

```json
{
  "channel": "C0CAJQT7QQY",
  "ts": "1729000000.000100",
  "state": "active | needs_check | hold | dormant | closed",
  "last_moved_at": "2026-11-05",
  "next_check_at": "2026-11-19",
  "asked_count": 0,
  "closed_at": null
}
```

Supabase 集約（[[comm-hub-db-design]]）を前提に、正本は KURASHIFT／台帳、Slack は写しとする。

## 実装の順番（611 配車係の割り振りで実装者を決める）

1. KURASHIFT → Slack の書き込み（ステップ1〜5・8）— GHA スクリプト `scripts/kurashift_deal_active_113.py`（ドライラン付き）
2. 「どうしますか？」カードとボタン（ステップ6〜7）— consult-action に `deal113_*` 追加
3. 休眠・クローズ・削除（ステップ8〜10）
4. KURASHIFT 案件ページに「Slack スレッドを開く」「最後に確認した日」（815 KURASHIFT更新係のスレッドへ）

## やらないこと

- 仲介・銀行への送信、買付・申込
- 松野さんが閉じていない案件の削除、KURASHIFT status の勝手な変更
- 内見前の案件（問合せ段階）を #deal-active に載せる（そちらは 114／#consult）
- 変化ゼロの「特になし」報告

## 関係する社員

| 社員 | 役割 |
|---|---|
| 114 物件一次判定係 | 変更なし。内見候補になって初めて 113 が載せる |
| 511・512 | 変更なし。仲介返信の取込が「動きあり」の材料 |
| 815 KURASHIFT更新係 | 案件ページに Slack リンク・最終確認日（実装順4） |
| 816 Slack俯瞰連携係 | 親メッセージ体裁の助言のみ |
| Grok 部長（S1・S5・S6・S7） | 案件スレッドへの調査・評価の書き込み先として任意 |
