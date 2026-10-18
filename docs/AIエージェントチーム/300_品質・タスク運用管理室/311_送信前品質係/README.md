# 【運用確認】送信前品質係 — 一目でわかる1枚

## 作業フロー（FlowForge）

DX向けデモのため、**変更前フローは上書きせず残す**。本線の磨きは改訂版。

| 版 | 用途 | リンク |
|---|---|---|
| **改訂版（本線）** | きっかけ起動・3点ゲート | [flow_x4Sw8mVvuGVme1fXz9JGfs3v を開く](https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_x4Sw8mVvuGVme1fXz9JGfs3v) |
| **変更前（デモ用）** | 紹介・比較用。触らない | [flow_AKQv6lgUEtudWlE5fQUhQnh2 を開く](https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_AKQv6lgUEtudWlE5fQUhQnh2) |

| 項目 | 内容 |
|---|---|
| 役割 | 対外文面の送信前ゲート（宛先等のOK／NGのみ。送信しない） |
| 文面の誤字・トーン | **やらない**（Jarvis送信プレビュー＝`jarvis-outbound-confirm`） |
| 合図 | **都度起動** — 入口 A（inbox MD・15分 poll）／B（CLI）→ 合流後は **AI**（人待ちなし）。送信だけ人 |
| 実装 | Phase1〜3 済（CLI／poll／上流キック）。`PROGRESS.md` |
| 点検 | 宛先一致・本人名義・運営宛禁止（3点のみ） |
| 権限の境界 | 読む・点検＝可／送信＝人（送信直前のみ人が見る） |
| 報告 | Slack `#report`（通過は件数） |
| 相談 | Slack `#consult`（NG＋理由1行） |
| 指示書 | [CLAUDE.md](./CLAUDE.md) |
| フローメモ | [flow.md](./flow.md) |
