# 【運用確認】Todoist起票整理係 — 一目でわかる1枚

- **AIオートメーション（FlowForge）**: [flow_M8SvKC1IDTDi496Vw-DgGjpD](https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_M8SvKC1IDTDi496Vw-DgGjpD)
- **人の依頼**: Cursor `/todoist`・「起票整理して」「認定して」
- **フロー正本**: [flow.md](./flow.md)

| 項目 | 内容 |
|---|---|
| ID | `312` |
| 役割 | **Todoist起票本線**。登録動線①L2採用create／②L0直／③116追加。塩梅 L0/L1/L2 |
| 合図 | 材料できたとき即／人依頼／定期保険／ホーク・JarvisBox |
| 権限の境界 | L0＝操作なし／L1＝見るだけ／L2＝採用・見送り。create は了承後。完了疑いは列挙のみ。close は 313＋オーナー確認二段 |
| 報告 | 即時 L1/L2 とも Slack `#consult`／`#report`（短く） |
| 指示書 | [CLAUDE.md](./CLAUDE.md) |
| 状態 | 設計中（flow 本線化済・Slack L1/L2 カード実装は後続） |
| 対になる係 | [313 完了候補確認係](../313_完了候補確認係/)／[116 メール](../../100_連絡・物件動向把握室/116_メール要対応係/) |

出典: Agent Team Builder「物件と連絡の見守り隊」／更新 2026-10-21
