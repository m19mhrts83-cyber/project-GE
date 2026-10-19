# 【設計中】616 寄せリマインド係

カード引落などの **現金不足を検知して促す**係。**銀行ログイン・送金はしない**。

| 項目 | 内容 |
|---|---|
| 実行 | **ルール＋`CLAUDE.md` 本線**（スキル／スラッシュ不要。どのエージェントツールでも可） |
| 送金 | **Jarvis ＋人了承**のみ（本係の外） |
| 役割 | 不足検知 → Slack／チャット → Jarvis へ手渡し |
| 設計正本 | [`設計案_20261019.md`](./設計案_20261019.md) |
| Cursor ルール | `.cursor/rules/jarvis-agent-616-cash-remind.mdc` |
| 入口 | `card_debit_watch`／Zaim CSV（済確認）／`known_recurring_debits` |
| Slack | `#consult` `【相談】616 寄せリマインド｜…`（番号＋短い役割語） |
| 組織図 | [ビルダー共有](https://agent-team-builder-teal.vercel.app/s/uksxiDIzE1AEckKH) |
| 作業フロー素案 | [`flow.md`](./flow.md)（FlowForge 未作成） |
| 指示書 | [`CLAUDE.md`](./CLAUDE.md) |
| 停止 | `JARVIS_ADJUST_CASH_REMIND_DISABLE=1`（実装後） |
