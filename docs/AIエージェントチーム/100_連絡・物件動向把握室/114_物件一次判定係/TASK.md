# TASK — 114 物件一次判定係

規格: [`30_共通Agentフォルダ規格_BCP`](../../30_共通Agentフォルダ規格_BCP_20261017.md)

| 項目 | 値 |
|---|---|
| task_id | （実行ごとに Todoist／run_id を記入） |
| agent_id | 114 |
| executor | launchd / jarvis_property_gate_degraded.py（本線）／cursor（診断） |
| status | queued |
| started_at | |
| finished_at | |

## 依頼（定常）

Grok調査取込後の deals を A/B/C 振分し、人判断が要る B を Slack `#consult` に出す。  
上限時も CLI／launchd で回す（[`24_Jarvis上限時`](../../24_Jarvis上限時_物件進行ゲート_次善策_20261012.md)）。

## 完了条件

- [ ] 振分結果が deals／ログに残っている
- [ ] B カードが必要な件数だけ `#consult` に出ている（または「対象0」がログにある）
- [ ] `tests/checklist.md` を通す
- [ ] 障害時は `#ops` またはログに理由

## 成果物

- `logs/` … 実行メモ
- `output/` … 要約・パスメモ（大きい正本は KURASHIFT deals）
- 外部: KURASHIFT `/realestate/deals` · Slack `#consult`

## メモ・障害

- 
