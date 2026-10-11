# 【運用確認】連携健全性点検係 — 一目でわかる1枚

- **AIオートメーション（FlowForge）**: [flow_zYjp6A4HDURefJhSm0h_zUtX](https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_zYjp6A4HDURefJhSm0h_zUtX)

| 項目 | 内容 |
|---|---|
| 役割 | WeStudy/GHA と（Mac時）LINEオプチャ取込の健全性点検 |
| きっかけ | **本線: 日曜 21:00 JST / GitHub Actions**（副: Fail時・手動） |
| ゴール報告 | Slack **`#ops`** 1通（要判断は `#consult`。チャット報告なし） |
| 権限の境界 | チェック・既知復旧＝可／QR・大量YAML＝人 |
| 実行 | `scripts/jarvis_ops_health_315.py --cloud --post`（GHA本線） |
| Workflow | `.github/workflows/ops-health-315.yml` |
| 指示書 | [CLAUDE.md](./CLAUDE.md) |
| フロー | [flow.md](./flow.md) |
| FF貼付 | [flowforge_エージェントへの指示.md](./flowforge_エージェントへの指示.md) |
