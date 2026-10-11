# 【運用確認】連携健全性点検係 — 一目でわかる1枚

- **AIオートメーション（FlowForge）**: [flow_zYjp6A4HDURefJhSm0h_zUtX](https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_zYjp6A4HDURefJhSm0h_zUtX)

| 項目 | 内容 |
|---|---|
| 役割 | WeStudy/GHA 点検＋（Mac）オプチャ1回トライ復旧 |
| きっかけ | **本線: 日曜 21:00 GHA**／**補完: 日曜 21:45 Mac** |
| ゴール報告 | Slack **`#ops`**（未解決は `#consult`。チャット報告なし） |
| 権限の境界 | 既知復旧1回＝可／QR・大量YAML・WeStudy再実行＝人 |
| 実行 | `--cloud --post`（GHA）／`--remediate-once --post`（Mac） |
| Workflow | `.github/workflows/ops-health-315.yml` |
| 指示書 | [CLAUDE.md](./CLAUDE.md) |
| フロー | [flow.md](./flow.md) |
| 異常時 | [docs/incident-flow.md](./docs/incident-flow.md) |
