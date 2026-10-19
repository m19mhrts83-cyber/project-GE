# Todoist起票整理係 — 一目でわかる1枚

- **AIオートメーション（FlowForge）**: [flow_M8SvKC1IDTDi496Vw-DgGjpD](https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_M8SvKC1IDTDi496Vw-DgGjpD)
- **人の依頼**: Cursor `/todoist`

| 項目 | 内容 |
|---|---|
| ID | `312` |
| 役割 | 起票候補整理・了承後 create・レーン／ラベル／二重起票防止。**コメントにサマリ＋アウトプット必須** |
| 合図 | `/todoist`・パートナー確認・宿題検知・hawk create |
| 権限の境界 | 候補提示＝可／create は了承後／外に出す・消す・金＝人 |
| 報告 | Slack `#report` |
| 相談 | Slack `#consult` |
| 指示書 | [CLAUDE.md](./CLAUDE.md) |
| フロー | [flow.md](./flow.md) |
| 状態 | 候補（指示書具体化済・定時は未） |
| 対になる係 | [313 完了候補確認係](../313_完了候補確認係/) |

出典: Agent Team Builder「物件と連絡の見守り隊」／更新 2026-10-19
