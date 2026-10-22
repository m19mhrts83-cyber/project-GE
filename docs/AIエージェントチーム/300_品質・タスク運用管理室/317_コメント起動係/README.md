# 【設計中】コメント起動係（317）— 一目でわかる1枚

- **AIオートメーション（FlowForge）**: （作成後に URL）

| 項目 | 内容 |
|---|---|
| 役割 | Slack FB／Todoistコメントを常駐で拾い Ack→許可リスト AI→Slack報告 |
| 合図 | launchd 2〜5分／GHA stale／Webhook／手動 |
| 権限の境界 | L1 Ack＝自動可／L2＝許可リスト／外に出す・金＝人 |
| 報告 | Slack `#report` |
| 相談 | Slack `#consult` |
| 指示書 | [CLAUDE.md](./CLAUDE.md) |
| 今回の依頼 | [TASK.md](./TASK.md) |
| フロー | [flow.md](./flow.md) |
| 入出力 | `input/` · `output/` · `tests/` · `config/` |
| 設計 | [`44_コメント常駐起動_317_20261022.md`](../../44_コメント常駐起動_317_20261022.md) |

詳細・チェックリストは `CLAUDE.md`。
