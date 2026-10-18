# TASK — 311 送信前品質係

規格: [`30_共通Agentフォルダ規格_BCP`](../../30_共通Agentフォルダ規格_BCP_20261017.md)

| 項目 | 値 |
|---|---|
| task_id | phase3-upstream-enqueue-20261018 |
| agent_id | 311 |
| executor | cursor |
| status | done |
| started_at | 2026-10-18 |
| finished_at | 2026-10-18 |

## 依頼

Phase 3: 上流（211／ホーク／S9）から `input/` への自動キック。

## 完了条件

- [x] `--enqueue` / `enqueue_request()` 
- [x] 211 朝便 apply 後に enqueue
- [x] ホーク `action: send_gate_311` → bucho poll apply
- [x] docs（phase3-upstream・PROGRESS・CLAUDE）

## 成果物

- `scripts/jarvis_send_gate_311.py`（enqueue）
- `scripts/jarvis_hawk_send_gate_311_apply.py`
- `scripts/jarvis_reply_draft_211.py`（配線）
- `scripts/jarvis_bucho_inbox_poll.py`（配線）
- `docs/phase3-upstream.md`
