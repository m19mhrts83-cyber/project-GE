# 【運用確認】完了候補確認係 — 一目でわかる1枚

- **AIオートメーション（FlowForge）**: [flow_6s1nyBIKzluSsdgR-hs9IolD](https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_6s1nyBIKzluSsdgR-hs9IolD)
- **人の依頼**: Cursor `/todoist-batch`（掃除）／入口は `/todoist`／「閉じて N」
- **続き**: [PROGRESS.md](./PROGRESS.md)

| 項目 | 内容 |
|---|---|
| ID | `313` |
| 役割 | 確認のみ close／要判断はオーナー残し。**処置・完了は Todoist コメント必須** |
| 合図 | `/todoist-batch`・Todoist掃除・完了相当・313 digest |
| 権限の境界 | 確認のみ＝自動 close 可／方針・金・対外＝人 |
| 報告 | Slack `#report` |
| 相談 | Slack `#consult`（L1ダイジェスト） |
| 指示書 | [CLAUDE.md](./CLAUDE.md) |
| フロー | [flow.md](./flow.md)（微修正はここ） |
| CLI | `scripts/jarvis_todoist_313_digest.py` |
| 状態 | Phase1 実装済・運用A〜B（定時はC） |
| 対になる係 | [312 Todoist起票整理係](../312_Todoist起票整理係/) |

出典: Agent Team Builder「物件と連絡の見守り隊」／更新 2026-10-21
