# TASK

作業のたびにこのファイルを更新する（チャットだけで完了条件を変えない）。  
規格: [`30_共通Agentフォルダ規格_BCP_20261017.md`](../30_共通Agentフォルダ規格_BCP_20261017.md)

| 項目 | 値 |
|---|---|
| task_id | （Todoist id または run_id） |
| agent_id | （例: 114） |
| executor | 今回の実行者: cursor / claude_code / gencode / codex / launchd / gha / … |
| status | queued / running / done / failed / blocked |
| started_at | |
| finished_at | |

## 依頼

（何をするか。入力は `input/` または外部パス）

## 完了条件

- [ ] 期待する成果物が `output/`（または記した外部パス）にある
- [ ] `tests/` のチェックを通す
- [ ] 必要なとき Slack `#report`／`#consult`／`#ops` に報告

## 成果物

- 

## メモ・障害

- 

## 引き継ぎ（入力・判断・進捗が変わったときに更新）

- 最終更新:
- 入力の正本と版: パス・更新日時またはcommit。秘密の値は記載しない
- 完了したこと:
- 判断理由・了承済み範囲:
- 残作業・未解決事項:
- 検証: コマンド／実行日時／結果／未検証の範囲
- 次の一手:
- 作業ロック: task_id・取得／解放状態（状態ファイルで再確認）

目安は各項目1〜3行。詳細はoutput/logsへのリンクを置く。会話の推測で完了扱いにせず、成果物と実行結果を確認する。実行担当が変わっても社員番号・task_id・完了条件を維持する。
