# Phase 3 — 上流から 311 `input/` へのキック

## 入口の使い分け

| 上流 | やり方 | source |
|---|---|---|
| **211** | 朝便で正本書込後に **自動 enqueue**（`jarvis_reply_draft_211.py`） | `211` |
| **ホーク／S9** | Drive `10_inbox_from_grok/` に `action: send_gate_311` MD → bucho poll が enqueue | `hawk` / `s9` |
| **手動／Jarvis** | CLI `--enqueue` または `input/` に直接 MD | `manual` 等 |
| **211 GHA（即時）** | 経路B: `--draft … --post`（enqueue せず直接ゲート可） | `211` |

## CLI

```bash
~/selenium_env/venv/bin/python scripts/jarvis_send_gate_311.py \
  --enqueue --draft '/path/4.送信下書き.txt' --source s9
```

無効化: `JARVIS_SEND_GATE_311_ENQUEUE_DISABLE=1`  
ホーク apply 無効: `JARVIS_SEND_GATE_311_HAWK_APPLY_DISABLE=1`  
bucho 自動 apply 無効: `JARVIS_SEND_GATE_311_INBOX_AUTO_APPLY=0`

## ホーク MD 例

```yaml
---
action: send_gate_311
target: jarvis
source: hawk
draft_path: /絶対パス/4.送信下書き.txt
partner_or_thread: 103_Tcell
---
```

成功分は `90_archive` へ。15分以内に 311 poll がゲート→Slack。
