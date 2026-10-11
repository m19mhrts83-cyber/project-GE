# 【運用】連携健全性点検係 — 一目でわかる1枚

- **AIオートメーション（FlowForge）**: [flow_zYjp6A4HDURefJhSm0h_zUtX](https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_zYjp6A4HDURefJhSm0h_zUtX)

| 項目 | 内容 |
|---|---|
| 役割 | WeStudy/GHA と LINEオプチャ取込の健全性点検・是正 |
| 合図 | 時間／Fail検知／停滞の見回り |
| 権限の境界 | チェック・既知復旧＝可／QR・大量YAML＝人 |
| 報告 | Slack `#ops` |
| 相談 | Slack `#consult` |
| 実行 | `scripts/jarvis_ops_health_315.py --post` |
| 指示書 | [CLAUDE.md](./CLAUDE.md) |
| フロー | [flow.md](./flow.md) |
