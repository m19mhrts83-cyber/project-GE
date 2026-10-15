# 【運用確認】業者開拓フォロー係

- **AIオートメーション（FlowForge）**: [業者開拓 見守り（516／GHA16:00）](https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_dCheumorewDolXnfpksSuWKu)（設計図・実行エンジンではない）
- **本線**: `scripts/jarvis_vendor_outreach_stall_runner.py --lane all`
- **UI**: vendors · repair-vendors · mgmt-vendors
- **Grok 関係**: 〔Grok:S2+S4+S9〕— **実行は Grok／見守り・補給は 516**（開拓の二重実行はしない）

| 項目 | 内容 |
|---|---|
| ID | 516 |
| 役割 | S2/S4/S9 の見守り（枯渇検知・Drive補給・sync_meta・週次 Slack）。開拓実行はしない |
| 報告 | 週次 #report（healthy）／即時 #ops |
| 状態 | 運用確認（格上げ条件: `docs/promote-to-ops.md`） |

正本指示: [`CLAUDE.md`](./CLAUDE.md)
