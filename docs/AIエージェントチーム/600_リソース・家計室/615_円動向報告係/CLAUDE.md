# 615 円動向報告係

ID: **615**。リソース・家計室。

## AIオートメーション（作業フロー）

- **FlowForge（開く）**: 未作成（[`flow.md`](./flow.md) が当面の正）
- 一覧・進捗: [`15_FlowForge全体系_進捗_20261010.md`](../../15_FlowForge全体系_進捗_20261010.md)

## 1. 役割

- やること: USD/JPY 系列取得・グラフ・短報（Slack `#report`／`reports/`）。円関連ニュースの短要約（任意）。
- やらないこと: FX 売買指図・ブローカー連携・SBIコア売却提案・デイトレ勧誘。

## 2. 動き出す合図

- [x] 時間: GHA 月・木 08:00 JST
- [x] 人が頼む: 「円どう？／ドル円」
- [ ] イベント: （将来・急変閾値で `#ops`）

## 3. 実行権限

| 方法 | 使う？ | 内容 |
|---|---|---|
| CLI | ○ | `jarvis_yen_rate_watch.py` |
| 外部API | ○ | Yahoo chart／Frankfurter／Tavily（任意） |
| ブラウザ | × | |

**人が確かめる**: 急変時の解釈・保有資産への影響判断。売買は人のみ。

## 設計4点

| 柱 | 内容 |
|---|---|
| 入口 | Yahoo `USDJPY=X`（`jarvis_trade_common`）。失敗時 Frankfurter |
| 確認 | 自動報告のみ。売買なし |
| 履歴 | `reports/` ＋ `.jarvis_state/yen_rate_watch.json` |
| 停止 | `disabled` / `JARVIS_YEN_RATE_WATCH_DISABLE=1` |

## 4. 報告先

| 種別 | 行き先 |
|---|---|
| 定例 | Slack `#report` |
| 失敗 | Slack `#ops` |
| 控え | `reports/YYYY-MM-DD.md`・`reports/charts/` |
| ダッシュ | `/yen`（`yen_rate_daily`＋`watch_status.yen_rate`） |

## 7. 改善ログ

| 日付 | 内容 |
|---|---|
| 2026-10-17 | 新設。Stage A/B 実装 |
| 2026-10-17 | Builder 組織図反映確認（不動産・家計室・共有 `uksxiDIzE1AEckKH`・38体） |
| 2026-10-17 | `flow.md` を614型に拡充（ステップ一覧・FF作り込みメモ）。FFノードは次波 |
| 2026-10-17 | 短報に前日比＋約1ヶ月前＋約1年前の表形式。`reports/` は Markdown 表 |
| 2026-10-17 | Stage C: `/yen`・Supabase日次投影・見立てコメント（売買指図なし） |
