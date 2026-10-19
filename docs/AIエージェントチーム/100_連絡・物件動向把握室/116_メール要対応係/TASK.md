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
- [ ] Builder 組織図に 116 を追加（下記手作業・API無し）
- [x] status_sync → agentTeam.json 更新済（ダッシュ `/agent-team` は push 後反映）
- [x] night_triage Todoist をオーナー確認へ＋コメント

## 成果物

- `scripts/jarvis_mail_action_mute.py`
- `.github/workflows/jarvis-mail-action-noon.yml`
- Dashboard `mailActionSlackAction.ts` streak／Todoist

## Builder 手作業（起床後 2分）

共有ビュー `https://agent-team-builder-teal.vercel.app/s/uksxiDIzE1AEckKH` は **閲覧のみ**（API 書込なし・404）。編集はオーナー画面で:

1. Builder 編集URLを開く（松野アカウント・共有リンクではない方）
2. 部門「100 連絡・物件動向把握室」に社員追加
3. ID `116`／名前 `メール要対応係`／状態 `設計中`
4. 合図: 朝／昼GHA／night／手動／健全性（T1〜T5）
5. 追加後、本 TASK のチェックを `[x]` に

ダッシュ `/agent-team` は `agentTeam.json` 由来なので **Builder未追加でも一覧には出る**（push後）。
