# リソース制約要約係

ID: **611**。〔Grok:Resource〕ミックス。報告先: Slack `#ops`（判断は `#consult`）。

## AIオートメーション（作業フロー）

- **FlowForge（開く）**: [flow_azD9MyV6Lk3Pn63YMzf9uIFo](https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_azD9MyV6Lk3Pn63YMzf9uIFo)
- 一覧・進捗: [`15_FlowForge全体系_進捗_20261010.md`](../../15_FlowForge全体系_進捗_20261010.md)
- 設計の流れ図（あれば）: [`flow.md`](./flow.md)

## 1. 役割

- やること:
  - **AI 使用状況**を把握する（Cursor／Claude Code／Codex／GenCode／Grok 等の枠・消費・停滞の兆候）
  - 週次で制約サマリー（何が逼迫／余裕か）を短く出す
  - **レビュー結果（松野／ホークのダメ出し・意図OK）を踏まえ**、各社員の **動く頻度を減らす／増やす**案を出す（リソースコントロール）
  - 案は提案まで。launchd・FlowForge スケジュール・合図の変更は **人確認後**に Jarvis が反映
- やらないこと:
  - kintone 等の未採用ツールを正にしない
  - 無断で社員を止めたり、頻度を本番変更したりしない
  - APIキー・課金カード操作・自動課金アップグレード

## 2. 動き出す合図

- [x] 時間: **週次**（既存週次に相乗り。専用スケジューラ乱立禁止）
- [x] 変化・失敗を見回ったら: 枠逼迫・連続 Fail・「社員が動きすぎ／止まっている」指摘
- 注: Mac 見張り（`/api/mac-watch`）の止まり判定は 15 分・2 回連続で初めて #ops に🔴（2026-11-28 変更。瞬断は通知しない。詳細は 59_）
- [x] 人が頼む: 「リソース見て」「頻度調整して」

## 3. 実行権限

| 方法 | 使う？ | 内容 |
|---|---|---|
| チャット・検索 | ✅ | 週次材料・レビューコメント |
| CLI | ✅ | 状態 JSON・ログ・`agents_registry` 読取（書込は提案→人確認） |
| 外部連携 | △ | Slack 投稿は Webhook 配線後。秘密は env のみ |
| ブラウザ | △ | 利用枠ダッシュボードの目視（値はチャットに貼らない） |

**人が確かめる（必須）**: 頻度の本番変更、ツール有料枠の増減、代行・割り振りの切替（旧813を統合済み）。

## 4. 報告先

| 種別 | 行き先 |
|---|---|
| 週次サマリー・使用状況 | Slack `#ops` |
| 頻度の増減案・要判断 | Slack `#consult` |
| 枠切れ時の割り振り案（旧813分） | `#ops` ＋必要なら Todoist `要Jarvis連携` |

### Slack 書き出し（FRIDAY／Jarvis 共通）

| ch | いつ |
|---|---|
| `#report` | 完了・定型・生存確認 |
| `#consult` | 要判断。末尾「次の担当」3行必須 |
| `#ops` | 障害・失敗・枠切れ |

`#consult` 末尾: `次: Grokで続行 | Jarvisに依頼 | 人判断のみ` ＋ `担当メモ` ＋ `橋渡し`  
正本: [`38_Slack書き出し_FRIDAY_Jarvis_20261018.md`](../../38_Slack書き出し_FRIDAY_Jarvis_20261018.md) · [`36_`](../../36_Slack_consult手渡し_次の担当_20261018.md)

## 5. 成果物の置き場

- 本フォルダ `logs/`（週次メモ）
- 正本メモ: `docs/AIエージェントチーム/15_FlowForge全体系_進捗_20261010.md`（ツール方針）／`agents_registry.yaml`（頻度メモは note 欄提案）
- FlowForge: `flow.md` の URL

## 6. 作業手順

1. 使用状況を集める（枠残り・直近 Fail・社員の起動回数の目安）
2. レビュー結果を見る（意図OK／ダメ出し／「動きすぎ」「足りない」）
3. 制約サマリー 5〜10 行
4. **頻度コントロール表**を付ける（社員ID・現状合図・提案: 減／据置／増・理由1行）
5. `#ops` にサマリー、増減案は `#consult`（または同報で「確認ください」）
6. 了承後だけ Jarvis が registry／launchd／Flow 定義へ反映

### 頻度コントロール表（型）

```
| ID | 係 | 現状 | 提案 | 理由 |
|---|---|---|---|---|
| 114 | 物件一次判定係 | 新着都度 | 減（1日1回まとめ） | レビュー遅延・枠逼迫 |
| 315 | 連携健全性点検係 | 夜間 | 据置 | Failなし |
```

## 7. 改善ログ

| 日付 | 内容 |
|---|---|
| 2026-10-09 | Phase D スタブ |
| 2026-10-10 | 使用状況把握＋レビュー連動の頻度コントロールを役割に追加 |
| 2026-11-01 | 本人契約・使用量を4サービスで一次確認。詳細は `output/20261101_AI使用量管理_本人条件確認.md` とObsidian正本。請求日／月間補充／週次／短期枠を区別し、Genspark Standard無料枠をGenCode用に数えない。課金・起動頻度・代行チェーンは未変更 |
| 2026-11-06 | 実装 第1弾: `scripts/jarvis_ai_usage_weekly.py`（Claude Code・Codex はローカルログ、Cursor・GenCode・ChatGPT は手入力）。314 の土曜 runner に相乗り。Supabase は案のみ（`output/20261106_実装1_使用量集計の結果.md`） |
| 2026-11-09 | Supabase は新テーブルを作らず既存 `metrics`／`sync_meta` に載せる形へ（`--push` は未了承で未使用）。Cursor の自動取得 `scripts/jarvis_cursor_usage_fetch.py` を追加（ログイン済みブラウザ・非公開 API・失敗しても止めない）。Grok Bot 週次％も表に追加 |
| 2026-11-10 | 実装 第2弾（動きB 配車案）: `scripts/jarvis_ai_dispatch_suggest.py`。TASK.md か題から種類を判定し、使用量（その場で集計）で割り振り先・理由・外した候補・次の担当3行の文面を作る。既定は `.jarvis_state/dispatch_suggestions/` に書くだけ。`--post` で #consult（松野さんが文面 OK した後だけ）。LLM なし |
| 2026-11-10 | 実装 第3弾: 配車案への ✅／番号返信で、317 が Codex（codex exec）・ミスレモン（claude -p）・ジャービス（Cloud Agent）を起動しドラフト PR で止める `scripts/jarvis_dispatch_launch.py`。お金・対外送信・本番・削除は起動しない。`JARVIS_DISPATCH_LAUNCH_ENABLE=1` まで dry-run |
| 2026-11-22 | 判断用の画面を追加（松野さん依頼）: Jarvis Dashboard `/ai-usage`（お金 →「AI 使用量」）。`scripts/jarvis_ai_usage_snapshot.py --push` が `ai-usage` と同じ4者の枠を読み、sync_meta `ai_usage_now` に「枠ごとの使用率・回復時刻・値の古さ／週・月ごとの最大値／判断の目安」を写す。起動は既存の runner に相乗り（8:20・18:20 の鮮度監視、12:30 の dashboard push）。LLM なし・新テーブルなし。履歴は `~/.local/state/ai-usage/history.json`。**Claude の値はデスクトップアプリからは自動で入らない**（statusLine は対話型の Claude Code だけ）。古い時は 設定→使用量 の数字を `--set-claude --weekly N --weekly-reset <ISO>` で入れる。目安（Max は Pro の約5倍・週枠20%未満が2週で移行提案）は Miss Lemon の案で、本人の確定基準ではない。方針は「1月まで Max、2月から落ち着かせる」（本人 11/22） |
| 2026-11-22 | `/ai-usage` の月額を「エージェントの道具」と「基盤の維持」に分けた（松野さん指定。分け方は `apps/jarvis-dashboard/lib/aiUsage.ts` の `AGENT_TOOL_IDS`。無い id は基盤）。Claude の値の保存を、毎朝の予定タスク `todoist-daily-313` の手順3.5 に足した（松野さん了承。アプリの使用量を読んで `--set-claude --push`。道具が無い時は何もしない） |
| 2026-11-26 | Claude の使用量の保存が 11/22 22:25 から止まっていた。原因（事実）: `todoist-daily-313` の手順3.5（Claude アプリの get_usage → `jarvis_ai_usage_snapshot.py --set-claude --push`）が、11/23 の 318 への移管で消えた。もう1つの道の statusLine（画面つき Claude Code）は、Orca のチャットと Claude アプリが画面なし（stream-json）で動くので走らない。案B（AI なしで読む口）は見つからず: claude CLI に使用量のコマンドなし、`~/.claude` と Orca に値の保存なし。残りは非公式 API（トークンを扱う）か `claude -p`（AI を呼ぶ）で条件に合わない。対応（松野さん了承「当面A」）: Claude アプリの予定タスク `claude-usage-snapshot`（8:00・18:00）と `claude-usage-snapshot-half`（12:30・23:30）を Miss Lemon が登録。手順は Claude アプリの予定タスクの手順に置く。持ち主は 001 大佐。止める時は2本とも（松野さんから Miss Lemon へ）。初回の確認は 001 が 11/26 8:15 に行う |
