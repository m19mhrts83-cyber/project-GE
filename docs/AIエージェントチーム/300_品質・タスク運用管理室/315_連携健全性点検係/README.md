# 【運用確認】連携健全性点検係 — 一目でわかる1枚

- **AIオートメーション（FlowForge）**: [flow_zYjp6A4HDURefJhSm0h_zUtX](https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_zYjp6A4HDURefJhSm0h_zUtX)
- **流れ図（HTML）**: [docs/flow-overview.html](./docs/flow-overview.html) ← **Gmail token 監視を含む3系統**

| 項目 | 内容 |
|---|---|
| 役割 | WeStudy/GHA ＋（Mac）オプチャ1回トライ ＋ **Gmail token 切れ／send欠落** |
| きっかけ | **本線: 日曜 21:00 GHA**／**補完: 日曜 21:45 Mac** |
| ゴール報告 | Slack **`#ops`**（未解決・Gmail再同意要は `#consult`。チャット報告なし） |
| 権限の境界 | オプチャ既知復旧1回＝可／QR・Gmail再同意・大量YAML・WeStudy再実行＝人 |
| 実行 | `--cloud --post`（GHA）／`--remediate-once --post`（Mac・Gmail含む） |
| Workflow | `.github/workflows/ops-health-315.yml`（cloudは Gmail スキップ→Mac委譲） |
| 指示書 | [CLAUDE.md](./CLAUDE.md) |
| フロー | [flow.md](./flow.md) |
| 異常時 | [docs/incident-flow.md](./docs/incident-flow.md) |
