# コメント起動係（317）

Slack FB スレ返信と Todoist タスクコメントを **チャット依頼なし**で拾い、Ack／分類し、許可リスト内だけ AI 処置して Slack に「やりました」と報告する。

設計正本: [`../../44_コメント常駐起動_317_20261022.md`](../../44_コメント常駐起動_317_20261022.md)  
作業フロー: [`flow.md`](./flow.md)

## AIオートメーション（作業フロー）

- **FlowForge（開く）**: https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_8mwIkbI0S9kV2u5kSwl2I-Oi
- **FlowForge（閲覧 share）**: https://flowforge-259747770348.asia-northeast1.run.app/share/qbbUffZBcoAq1lKG
- 一覧・進捗: [`15_FlowForge全体系_進捗_20261010.md`](../../15_FlowForge全体系_進捗_20261010.md)
- 設計の流れ図: [`flow.md`](./flow.md)
- CLI: `scripts/jarvis_comment_dispatch.py`
- 部品: `jarvis_todoist_webhook_handle.py`／`jarvis_slack_report_fb_poll.py`
- 枠: [`813_代行指揮枠切替係`](../../800_俯瞰UI・投影更新室/813_代行指揮枠切替係/CLAUDE.md)

## 1. 役割

- **やること**
  - L0: Todoist Webhook 受信済みイベントを読む（受信自体は Vercel）
  - L1: 未処理コメント／FB を拾い Ack・分類（Mac 本線／stale 時 GHA 冗長）
  - L1 可視性: Slack は返信＋👀／Todoist は `【Jarvis】見たよ（受けた）`（`40_` 同コンセプト）
  - L2: 許可リスト内だけ Local Agent（Mac）。枠ありなら Cloud フォールバック
  - L2 完了を Slack `#report`「対応したよ」＋Todoist 同文。冗長時は `(failover)` を付ける
- **やらないこと**
  - 対外送信・振込・解約・無確認 apply
  - 815 返信提案
  - 秘密・トークンの再掲
  - GAS ポーリング
  - 許可リスト外の全コメント自動実装

## 2. 動き出す合図

- [x] 時間: Mac launchd 300秒／GHA 5分（stale 時のみ L1）。JST 0–6時除外
- [x] イベント: Todoist `note:added`（Webhook）／Slack FB スレ返信
- [x] 人が頼む: 「コメント拾って」「317回して」
- [ ] 変化・失敗: heartbeat 長期途絶 → 315／`#ops` 相乗り可

## 3. 実行権限

| 方法 | 使う？ | 内容 |
|---|---|---|
| チャット・検索 | ○ | 分類・要約 |
| 外部連携（API/MCP） | ○ | Slack／Todoist／Supabase |
| CLI | ○ | `jarvis_comment_dispatch.py` 本線 |
| ブラウザ | △ | 画面照合のみ |
| 画面操作 | × | 対外・課金は人 |

**人が確かめる**: 対外・金・方針・許可リスト外の実装。L1 Ack は自動可。

### 冗長の3層

| 層 | Mac ダウン時 |
|---|---|
| L0 受信 | Vercel Webhook 継続 |
| L1 Ack／分類 | GHA failover（AIなし） |
| L2 AI処置 | Cloud 枠ありのみ／なしはキュー残留 |

停止: `JARVIS_COMMENT_DISPATCH_DISABLE=1`／`JARVIS_COMMENT_DISPATCH_FAILOVER=0`  
夜間除外（JST）: 既定 **0:00〜6:00** スキップ（`QUIET_START`／`END`／`QUIET_DISABLE=1`）

## 4. 報告先

| 種別 | 行き先 |
|---|---|
| 完了・Ack まとめ | Slack `#report` |
| 要判断 | Slack `#consult` |
| 障害・heartbeat 途絶 | Slack `#ops` |

書き出し: `【報告】317 コメント起動｜…`  
**同一未処理メモ集合は再掲しない**（fingerprint／`sync_meta.comment_dispatch_slack_fp`）。連投掃除は `jarvis_comment_dispatch_slack_cleanup.py`。

## 5. 成果物の置き場

- 依頼: [`TASK.md`](./TASK.md)
- **Slack FB の毎日の対応記録**: `output/YYYYMMDD_FB対応.md`（Claude 定期タスク `slack-fb-daily` が PR で追加。Drive へ同期。他エージェントはここで経過を見る）
- state: `~/git-repos/.jarvis_state/comment_dispatch.json`
- Slack FB state: `~/git-repos/.jarvis_state/slack_report_fb.json`（`done_at` が付けば対応済み）
- heartbeat: Supabase `sync_meta` キー `comment_dispatch_heartbeat_at`
- Slack dedupe: `sync_meta.comment_dispatch_slack_fp`
- 外部正本: Todoist コメント／Slack スレ

## 6. 作業手順

1. `jarvis_comment_dispatch.py --apply`（Mac）または failover
2. L1 で Ack／分類。確認のみは 313 候補化可（二段維持）
3. Phase B・許可リスト命中時のみ L2
4. Slack は **内容が変わったときだけ** 完了1通。Todoist には `【AIチーム】` コメント
5. Slack FB スレの「受けた → 対応した」は毎日 21:00 の `slack-fb-daily`（Miss Lemon）。手順は [`40_`](../../40_Slack報告FB_スレ拾い_20261020.md) Phase 2


## 7. 改善ログ

| 日付 | 変更 |
|---|---|
| 2026-10-22 | 新設。Mac本線＋GHA L1冗長＋Cloud L2フォールバック設計 |
| 2026-10-22 | 対応可視性（L1 見たよ／👀・L2 対応したよ）を 40_ と揃える |
| 2026-10-23 | #report 同一 fingerprint 連投防止。webhook 返信1件失敗でバッチ中断しない。滞留 `note:added` 消化＋cleanup CLI |
| 2026-10-25 | 名乗りを `【AIチーム】` に。FB の「ラベルを付けて再送」依頼と投稿末尾の FB 案内をやめる。毎日の FB 対応（`slack-fb-daily`・`--pending`／`--done`）を追加。記録は `output/YYYYMMDD_FB対応.md` |

## 4. #report の形（2026-10-25 iPhone 見直し）

- 先頭1行: `【報告】317 コメント起動｜未処理 N件`（rc・path は出さない。path は failover 時のみ「（Mac停止中・GHA）」）
- 📌要ボス N件 → 項目（番号＋タイトル／種別｜コメント）を空行で区切る（最大5件、超過は「他N件はTodoistで確認」）
- 締めのコメント（了承・クローズ・完了）は種別「メモ」（分類器は「？」で要判断に寄るため報告側で補正）
- 対応したよ（Local／Cloud）も同じ形の短報
- 正本の表示ルール: `41_Slackスマホレイアウト_草案_20261022.md`
