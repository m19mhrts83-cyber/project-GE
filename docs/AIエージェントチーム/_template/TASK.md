# TASK

作業のたびにこのファイルを更新する（チャットだけで完了条件を変えない）。  
規格: [`30_共通Agentフォルダ規格_BCP_20261017.md`](../30_共通Agentフォルダ規格_BCP_20261017.md)

| 項目 | 値 |
|---|---|
| task_id | （Todoist id または run_id） |
| agent_id | （例: 114） |
| executor | cursor / claude_code / gencode / launchd / gha / … |
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
