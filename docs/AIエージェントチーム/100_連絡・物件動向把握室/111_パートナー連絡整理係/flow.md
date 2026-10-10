# フロー — パートナー連絡整理係（定時レポート改訂）

- FlowForge: https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_AZNxdNkT5-DNZyL5pK4AMrbj
- （旧版・線が分岐したまま）: `flow_TDZ4csQg3-8uaOCiIP4vyGrM`
- Flowforge 入口: https://flowforge-259747770348.asia-northeast1.run.app/
- 更新: 2026-10-10（一本合流・Notion削除。昼11:50 GHA／夜20:30 Mac＋ダッシュボード）

## いまの結論（文字1行）

開始（昼／夜／副合図）→ **枠ごとに取込**（昼=Gmail+CW／夜=Dashboard+LINE）→ **同じ**「更新時のみ Slack `#report`」に**合流** → 人は MD／Gmail で対処。Notionログは使わない。815はダッシュボード別枠。

## 合流の考え方

昼と夜はトリガー・取込手段が違うが、**並行の別フローではなく分岐→合流**。外部ツール（GHA／launchd）は「取込」ノードの実装手段であり、AI要約や Slack 報告と線が切れない。最終出口は常に `#report`（更新ゼロなら送らない）。

## チャネル色分け

| 色 | チャネル | 昼 | 夜 |
|---|---|---|---|
| パートナー本線 | Gmail / Chatwork / LINEグループ | GHA（Gmail/CW） | Macフル（LINE中心） |
| 補完 | iMessage / MailGates / くらさぽ | なし | Macフル |
| 情報収集（別枠） | 815オプチャ | 報告に載せない | Jarvis `/openchat` |

## ステップ一覧

| # | 内容 | 方法 | 人/AI | ツール例 |
|---|---|---|---|---|
| 1a | **昼トリガー** 11:50 JST（GHA） | 時間 | AI | GitHub Actions |
| 1b | **夜トリガー** 20:30 JST（launchd）／未実施なら Jarvis 会話でも可 | 時間＋起動 | AI | `com.matsunoma.jarvis.partner-111-night` |
| 1c | （副）合図「パートナー確認して」 | 1 | AI | Cursor / Jarvis |
| 2 | 昼: Gmail＋Chatwork → `5.やり取り.md` | 2+3 | AI | `jarvis_gha_partner_*`（Graph） |
| 3 | 夜: ダッシュボードを開く | 2 | AI（表示）／人が見る | Jarvis dashboard |
| 4 | 夜: LINEグループ取込（Tcell/LEAF/823）。必要なら iMessage・MailGates | 2+3（QR時は人） | AI | CHRLINE／公式エクスポート／yoritoori |
| 5 | 件数集計。**更新ゼロなら Slack 送らない** | 3 | AI | state／集計 |
| 6 | Slack `#report`（枠=昼 or 夜・チャネル別件数・失敗・相談有無） | 1 | **人が確かめる** | Webhook `#report` |
| 7 | 松野がダッシュボード／Slack／必要なら `5.やり取り.md` で要否判断 | （人） | **人が確かめる** | |
| 8 | 送信は別係・了承後のみ | 2+3 | **人が確かめる** | `yoritoori_send` 等 |

**人が確かめる印**: 6＝報告材料／7＝読み直し／8＝送信。金・削除はこの係では原則やらない。  
**やらない**: 昼に CHRLINE／オプチャ必須、夜に全社員フロー個別オープン、更新ゼロの「特になし」連投、**Notion へのワークログ記録**。  
**人が見る場所**: 詳細は `5.やり取り.md` のみで足りる。気づきは Slack `#report`（受動）＋ Gmail 要対応（能動）→ Jarvis に指示。→ [`運用メモ_人が見る場所.md`](./運用メモ_人が見る場所.md)
