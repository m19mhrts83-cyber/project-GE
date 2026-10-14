# Zaim鮮度・二重取込係 — 一目でわかる1枚

- **AIオートメーション（FlowForge）**: [閲覧](https://flowforge-259747770348.asia-northeast1.run.app/share/v2D2xrS4Gm9bY0bP) · [編集](https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_5GzzES3EaIqhlotG9IGGNXjF)

| 項目 | 内容 |
|---|---|
| 役割 | 銀行連携の鮮度・二重取込の安全直し・費目学習。開いたとき `/zaim` が整っている状態へ |
| 合図 | 火金 09:00（鮮度）／火金 12:00（CSV＋学習）／GHA check／「今すぐ更新」／会話 |
| 権限の境界 | check・学習・高確信度 apply＝自動可／OTP不可・曖昧費目・suppress＝人 |
| 報告 | 異常時 Slack `#ops`。平常は `/zaim` のみ |
| 相談 | Slack `#consult`（閾値・口座方針） |
| 隣係 | 612 年会費／611 AI枠／316 メトリクス分析 |
| 指示書 | [CLAUDE.md](./CLAUDE.md) |
| フロー | [flow.md](./flow.md) |

候補（指示書充填済・2026-10-14）。FlowForge の作り込みは別チャット。
