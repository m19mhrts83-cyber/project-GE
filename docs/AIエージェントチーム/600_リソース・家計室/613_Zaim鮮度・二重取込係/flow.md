# フロー — Zaim鮮度・二重取込係（613）

- FlowForge（閲覧）: https://flowforge-259747770348.asia-northeast1.run.app/share/v2D2xrS4Gm9bY0bP
- FlowForge（編集・m19m）: https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_5GzzES3EaIqhlotG9IGGNXjF
- Flowforge 入口: https://flowforge-259747770348.asia-northeast1.run.app/
- 更新: 2026-10-14（指示書充填。ノード作り込みは別チャット）
- 作り方: [`06_社員の作り方_二段階_20261009.md`](../../06_社員の作り方_二段階_20261009.md)

## いまの結論（文字1行）

開始（火金09／火金12／キュー／人）→ **鮮度 check→（Mac）stale更新** と **CSV→learn→費目・集計 apply** を分岐 → **同じ `/zaim` 投影**に合流 → 異常時だけ `#ops`。

## 合流の考え方

09:00 と 12:00 はトリガーと手段が違うが、**別社員ではない**。どちらも「家計データが開いたときに正しい」ための一本。GHA は check／Watch まで（更新ボタンは Mac）。Playwright は `zaim_playwright.lock` で直列化。

## ステップ一覧

| # | 内容 | 方法 | 人/AI | ツール例 |
|---|---|---|---|---|
| 1a | **火金 09:00** 鮮度枠 | 時間 | AI | `com.matsunoma.jarvis.zaim-bank-sync-*` launchd |
| 1b | **火金 12:00** CSV＋学習枠 | 時間 | AI | `com.matsunoma.jarvis.zaim-csv-weekly` |
| 1c | GHA 日次（check＋Watch） | 時間 | AI | `.github/workflows/zaim-finance-sync.yml` |
| 1d | `/zaim`「今すぐ更新」キュー | イベント | AI（Mac poll） | `jarvis_zaim_refresh_queue_poll.py` |
| 1e | （副）「Zaim見て／再接続して」 | 人 | AI | Cursor / Jarvis |
| 2 | bank_sync_check（遅れ・欠落の数値化） | CLI | AI | `jarvis_zaim_bank_sync_check.py` |
| 3 | stale 更新（OTP 可口座のみ自動試行） | Playwright | AI／OTP失敗時は人 | `jarvis_zaim_bank_sync_manual.py` / `reconnect` |
| 4 | CSV export | Playwright | AI | `zaim_csv_export.py`（Mac） |
| 5 | learn（CSV前後・その他=店名／他=店+金額） | CLI | AI | `jarvis_zaim_learn.py`（runner 内） |
| 6 | 高確信度の集計・費目 apply（その他＋店+金額不一致） | CLI＋Playwright | AI | `jarvis_zaim_watch_runner.py` |
| 6b | 直し／学習あれば `#report` | Webhook | AI | runner 内（確認用短報） |
| 7 | snapshot 保存・changelog・Supabase push | CLI | AI | runner 末尾 |
| 8 | 人が `/zaim` で確認（違うときだけ「おかしい」） | Web | **人が確かめる** | `/zaim` |
| 9 | 残留 stale／連続失敗 → `#ops` または Todoist | Webhook | AI→人 | `SLACK_WEBHOOK_OPS` / bank_notify |

**人が確かめる印**: 8＝学習結果／曖昧費目、3＝OTP不可、9＝方針判断。  
**やらない**: GHA から更新ボタン、Suica 等対象外の強制、学習1回での断定適用（合意前）、612／611／316 の領域食い。

## FlowForge 作り込みメモ（別チャットへ渡す用）

- [ ] トリガー3本（09 / 12 / キュー）を分岐→合流で描く（111 と同型）
- [ ] Mac 必須ノード（更新・CSV）と GHA 可ノード（check）を色分け
- [ ] `/zaim` を「人の出口」として明示（Slack は異常時のみ）
- [ ] 費目学習を 5→6 の連続として置く（別フローに切らない）
- [ ] 停止条件（DISABLE／automation:off／lock）をガードノードに

## 手順メモ

（FlowForge 各ノードの磨きはここに追記）
