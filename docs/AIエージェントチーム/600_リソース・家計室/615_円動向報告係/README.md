# 【設計中】615 円動向報告係

USD/JPY の推移をグラフ付きで報告する係。**売買推奨・ポジション指図はしない**（Phase1＝報告のみ）。

| 項目 | 内容 |
|---|---|
| 本線 | `scripts/jarvis_yen_rate_watch.py`（Yahoo USDJPY=X → Frankfurter フォールバック） |
| グラフ | 直近31日＝日足／それ以前〜24ヶ月＝月次。高安・終値・前日比 |
| Slack | `#report` `【615 円動向報告係｜USDJPY】` |
| 定期 | GHA 月・木 08:00 JST（`yen-rate-watch.yml`） |
| 組織図 | [ビルダー共有](https://agent-team-builder-teal.vercel.app/s/uksxiDIzE1AEckKH) |
| 作業フロー素案 | [`flow.md`](./flow.md)（FlowForge 未作成） |
| 指示書 | [`CLAUDE.md`](./CLAUDE.md) |
| 停止 | `JARVIS_YEN_RATE_WATCH_DISABLE=1` または state `disabled` |
