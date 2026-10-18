# 【設計中】614 ポイント・還元ウォッチ係

**得る側**（テイチャン／Vポイント／ETC還元）の定例結果を、ダッシュボードに加え **Slack `#report`** へ短報する係。  
払う側の年会費ガードは **612**。

| 項目 | 内容 |
|---|---|
| テイチャン | 月・木 10:15 → `/vpoint` ＋ Slack |
| ETC還元 | 毎月20〜26日 → `/etc` ＋ Slack |
| Vポイント | 窓C定例 → `/vpoint` ＋ Slack |
| Slack見出し | `【614 ポイント還元｜…】`（番号＋短い役割語。「係」不要） |
| 組織図 | [ビルダー共有](https://agent-team-builder-teal.vercel.app/s/uksxiDIzE1AEckKH)（不動産・家計室） |
| 作業フロー素案 | [`flow.md`](./flow.md)（FlowForgeノードは未作成） |
| 指示書 | [`CLAUDE.md`](./CLAUDE.md) |
