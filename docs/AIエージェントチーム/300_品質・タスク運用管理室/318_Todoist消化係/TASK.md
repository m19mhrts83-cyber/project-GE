# TASK — 318 Todoist消化係

規格: [`30_共通Agentフォルダ規格_BCP`](../../30_共通Agentフォルダ規格_BCP_20261017.md)

| 項目 | 値 |
|---|---|
| task_id | orca task_1588877e6c3e（Phase 1・PR #582 マージ済）／task_becb7616c903（Phase 2・PR #585 マージ済）／task_0036d777fe4a（Phase 3 準備・PR #586 マージ済）／task_e8849b99d861（①自律実行） |
| agent_id | 318 |
| executor | claude_code（Miss Lemon・Orca worker） |
| status | done（PR レビュー待ち。マージはラス隊長が松野さんの了承後） |
| started_at | 2026-11-23 |
| finished_at | 2026-11-23 |

## 依頼

Phase 1 実装（読むだけ・抽出・変化なし除外・3分類・内部ログ・手動実行）。設計の正本は FlowForge flow_HMy15MUxWiSpw5QgAPYa_8e4（承認済み）。

## 完了条件

- [x] 開始チェック（停止スイッチ・排他・Todoist 接続・本人権限・60分・5件）。不成立は処理せず理由を記録
- [x] 1-1 採用済み基準・判断履歴の読込（313 の指紋照合を再利用・取得失敗は安全停止）
- [x] 1-2 抽出（313 の順位付けを直して再利用・読取失敗は失敗終了・最大5件）
- [x] 1-3 変化なしの除外（件数・理由を内部ログへ・判断不能は保留）
- [x] 1-4 3分類（根拠・迷ったら②・大規模は印だけ）。AI 分類は Claude Code 実行内（追加 API なし）
- [x] 内部ログ（.jarvis_state/todoist_318/・保存失敗は正常完了にしない）と判定・報告案の保存
- [x] テスト `scripts/tests/test_todoist_318_triage.py`、実データで手動実行（読むだけ）
- [x] Todoist 書き込み・Slack 送信・定期起動の登録なし

## Phase 2 完了条件

- [x] ② → /313/bulk（既存の取り込み先 sync_meta・CleanupCard 形式）、313 20:00 との二重質問防止、本人回答の読み戻しと再判定
- [x] ③ → 312 今週の9件（既存の週次ピックの候補形式）
- [x] #consult 通知・#ai-hub 報告は案の保存（送信はフラグ）
- [x] 317 の【318】除外とテスト
- [x] 実データの掲載・送信はしない（`--publish`／`--send-slack` は松野さんが朝に決める）

## Phase 3 準備 完了条件（有効化はすべて松野さんが朝に決める。全部既定オフ・未登録）

- [x] 【318】コメント反映（ノード5-1・5-2）: 内部ログ保存成功後・変化のある件だけ・同一内容／同一処理IDの重複確認・応答不明は照合まで再送しない・完了／削除／期限変更はしない。`--write-comments` の時だけ
- [x] 317 の除外を前提にテスト（除外が外れていたら書かない）
- [x] 10:30 の準備: launchd の plist を未登録の雛形で置く（load しない）。313 の 0.5 との排他の取り決めを実装。移管手順書（止める順番・戻し方）
- [x] 313 の予定タスク `todoist-daily-313` は変えない
- [x] ①自律実行は作らない。① の「やる予定の内容」を内部ログに記録
- [x] CLAUDE.md・TASK.md・PROGRESS.md（先頭に朝に決めること）

## ①自律実行 完了条件（既定オフ。有効化は松野さんが朝に決める）

- [x] ノード2-1: ①分類だけ。採用済み基準と作業範囲（work_scope）を確かめ、調査・資料確認・文面下書きまで。成果物は `.jarvis_state/todoist_318/work/`（git 管理外）。コード修正・PR・他エージェント依頼はしない。60分・5件。途中なら進捗・成果物・残作業を記録。大規模は週次へ。Todoist は閉じない
- [x] ノード2-2: 始める前・取り込む直前に安全条件を確かめる。承認が要る操作は②、本人操作は③。停止スイッチ・時間上限で新しく着手せず、中断点で保存。承認待ちは自動で再実行しない
- [x] 追加の有料 AI API なし（材料出し → Claude Code → 結果取り込み）
- [x] `--execute-auto` の時だけ。テスト。実データは dry-run で「やる予定」まで
- [x] CLAUDE.md・TASK.md・PROGRESS.md・移管手順書の「①の可否」

## 成果物

- `scripts/jarvis_todoist_318_triage.py`・`scripts/jarvis_todoist_318_handoff.py`・`scripts/jarvis_todoist_318_comment.py`（Phase 3 準備）・`scripts/jarvis_todoist_morning_slot.py`（朝枠の排他）・`scripts/jarvis_todoist_318_work.py`（①自律実行）
- `config/todoist_318_criteria.yaml`
- `launchd/com.matsunoma.jarvis.todoist-318.plist.template`・`launchd/jarvis_todoist_318_runner.sh`・`launchd/install_jarvis_todoist_318_launchd.sh`・`launchd/uninstall_jarvis_todoist_318_launchd.sh`（未登録）
- `scripts/tests/test_todoist_318_triage.py`・`test_todoist_318_phase2.py`・`test_todoist_318_phase3.py`・`test_todoist_318_auto_exec.py`
- このフォルダの `CLAUDE.md`・`PROGRESS.md`・`flow.md`・`移管手順_10時30分.md`

## メモ・障害

- 手動実行の結果は `PROGRESS.md`（件数だけ）
- 2026-11-27 分類基準の直し（件119の1・62_聞く基準）: ②3の判断は影響大・お金・対外送信・削除・取り返せない・舵取りだけ。印なしは①。残り（上限15件・古い物・済み検出）は次のPR
