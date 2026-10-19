# TASK

| 項目 | 値 |
|---|---|
| task_id | mail-action-116-bootstrap-20261019 |
| agent_id | 116 |
| executor | cursor |
| status | done |
| started_at | 2026-10-19 |
| finished_at | 2026-10-19 |

## 依頼

メール要対応 Slack レーンの社員化（116）・合図 T1〜T5・見送り連続学習硬化・unmute CLI・ダッシュ反映。

## 完了条件

- [x] フォルダ／CLAUDE／flow.md／registry／permissions／索引
- [x] 硬化（streak／Todoist GenMail型／mute CLI／T2 GHA／T3 night／T5 health）
- [x] Builder 組織図に 116 を追加（Jarvis・2026-10-19）
- [x] status_sync → agentTeam.json 更新済（ダッシュ `/agent-team` は push 後反映）
- [x] night_triage Todoist をオーナー確認へ＋コメント

## 成果物

- `scripts/jarvis_mail_action_mute.py`
- `.github/workflows/jarvis-mail-action-noon.yml`
- Dashboard `mailActionSlackAction.ts` streak／Todoist

## Builder（済）

- 共有: https://agent-team-builder-teal.vercel.app/s/uksxiDIzE1AEckKH（**41体**・連絡室に `116 メール要対応係`）
- 手順: 編集画面の `atb:plan` に挿入 → `/api/share` 再公開（同一 shareId）
