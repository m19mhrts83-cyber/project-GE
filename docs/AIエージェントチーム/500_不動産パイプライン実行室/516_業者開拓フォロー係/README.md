# 【設計中】業者開拓フォロー係

- **AIオートメーション（FlowForge）**: [flow_dCheumorewDolXnfpksSuWKu](https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_dCheumorewDolXnfpksSuWKu)
- **本線**: `scripts/jarvis_vendor_outreach_stall_runner.py --lane all`
- **UI**: vendors · repair-vendors · mgmt-vendors
- **Grok 関係**: 〔Grok:S2+S4+S9〕— **実行は Grok／見守り・補給は 516**（開拓の二重実行はしない）

| 項目 | 内容 |
|---|---|
| ID | 516 |
| 役割 | S2/S4/S9 の見守り（枯渇検知・Drive補給・sync_meta・日次 Slack）。開拓実行はしない |
| 報告 | #report（障害は #ops） |
| 状態 | 設計中（FlowForge を見守り図へ作り直し→運用確認予定） |

正本指示: [`CLAUDE.md`](./CLAUDE.md)
