# フロー — ポイント・還元ウォッチ係（614）素案

第2段階（動きの作り込み）のたたき。編成は第1段階（ビルダー）で追加済。  
作り方: [`06_社員の作り方_二段階_20261009.md`](../../06_社員の作り方_二段階_20261009.md)

- FlowForge（閲覧／編集）: **未作成**（作り込み待ち。本 MD が当面の正）
- Flowforge 入口: https://flowforge-259747770348.asia-northeast1.run.app/
- 動きの例（型参考）: https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_uGZ3apXgbHVdZJfnuqYA8_QZ
- ビルダー共有: https://agent-team-builder-teal.vercel.app/s/uksxiDIzE1AEckKH （不動産・家計室）
- 更新: 2026-10-17（素案。Slack 配線は実装済）

## いまの結論（文字1行）

開始（月木テイチャン／20–26日ETC／窓CVポイント／朝取りこぼし／人）→ 各取得・確認 → **ダッシュ投影** と **Slack `#report`【614｜種別】** に合流。失敗は `#ops`。払う側は **612** に渡さない。

## 合流の考え方

3本の定例はトリガーが違うが、**「お得（得る側）が動いた」を1係で見せる**ための一本。  
Slack 見出しで種別を分ける（`｜テイチャン`／`｜ETC還元`／`｜Vポイント`）。別社員に割らない。

```mermaid
flowchart TD
  T1[月木 10:15 テイチャン] --> A[取得・確認]
  T2[毎月20-26 09:30 ETC] --> A
  T3[窓C 25-末日 Vポイント] --> A
  T4[朝オープン取りこぼし] --> A
  T5[人依頼] --> A
  T6[毎月28日 09:50 年間特典] --> A
  T7[朝オープン取りこぼし 28日以降] --> A
  A --> B{種別}
  B -->|teiki| C1[jarvis_teiki_barai_chance --push]
  B -->|etc| C2[jarvis_etc_rebate_fetch --apply --push]
  B -->|vpoint| C3[jarvis_vpoint_routine --apply --push]
  B -->|card_benefit| C4[jarvis_card_benefit_watch --refresh]
  C1 --> D[jarvis_points_rebate_slack_report]
  C2 --> D
  C3 --> D
  D --> E["Slack #report 【614｜…】"]
  D --> F["/vpoint または /etc"]
  D -->|failed| G["Slack #ops"]
```

## ステップ一覧

| # | 内容 | 方法 | 人/AI | ツール例 |
|---|---|---|---|---|
| 1a | **月・木 10:15** テイチャン枠 | 時間 | AI | `teiki_draw_runner.sh` / launchd |
| 1b | **毎月 20–26日 09:30** ETC還元枠 | 時間 | AI | `etc_rebate` launchd |
| 1c | **25–末日 09:40** Vポイント窓C | 時間 | AI | `vpoint_routine` launchd |
| 1d | 朝オープン取りこぼし | イベント | AI | `jarvis_morning_mac_refresh` |
| 1e | （副）「テイチャン／ETC還元／Vポイント定例」 | 人 | AI | Cursor / Jarvis |
| 2a | テイチャン: 券確認→あれば抽選 | Playwright/CDP | AI（規約未同意は人） | `jarvis_teiki_barai_chance.py` |
| 2b | ETC: smile-etc 還元額取得 | Playwright | AI | `jarvis_etc_rebate_fetch.py` |
| 2c | Vポイント: 付与サマリ＋cadence＋asks | CLI | AI（OTP等は人） | `jarvis_vpoint_routine.py` |
| 3 | state 更新 | CLI | AI | `teiki_*` / `etc_monthly` / `vpoint_*` |
| 4 | ダッシュ投影 | CLI | AI | `jarvis_dashboard_push.py --watch-only`（`--push` 内） |
| 5 | Slack 短報 | Webhook | AI | `jarvis_points_rebate_slack_report.py` |
| 2d | 年間特典（Olive／Bonvoy）: Olive=Gmail 月次メール→確定値、Bonvoy=Zaim 行→概算。達成率・月あたり必要額・届くペースか | CLI | AI | `jarvis_card_benefit_watch.py --refresh` |
| 6 | 人が Slack／`/vpoint`／`/etc` で把握 | Web | **人が確かめる** | ダッシュ・Slack |
| 7 | 失敗・ログイン不能 → `#ops` | Webhook | AI→人 | `SLACK_WEBHOOK_OPS` |

**人が確かめる印**: 6＝数値の妥当性（年間特典は条件の金額が推定／要確認のうちは目安。寄せ先を決めるのは人）、2a＝規約／迷うサービス追加、2c＝TサイトOTP・Wallet。  
**やらない**: 年会費退会操作（**612**）、Zaim鮮度・費目（**613**）、秘密の Slack 再掲、対外送信。

## FlowForge 作り込みメモ（別チャットへ渡す用）

- [ ] トリガー3本（テイチャン／ETC／Vポイント）を分岐→合流で描く（111・613 と同型）
- [ ] Mac 必須ノード（Vpass／smile-etc）と state のみノードを色分け
- [ ] Slack `#report` を出口、失敗だけ `#ops`
- [ ] 612（払う側）との境界を注釈で明示
- [ ] 停止条件（各 `*_DISABLE`／`JARVIS_POINTS_REBATE_SLACK_REPORT_DISABLE`）をガードノードに
- [ ] 作成後: registry の `flowforge_url` と本ファイル先頭リンクを更新 → `jarvis_agent_team_status_sync.py`

## 手順メモ（実装本線・いま動くもの）

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
# テイチャン
~/selenium_env/venv/bin/python scripts/jarvis_teiki_barai_chance.py --run --push
# ETC
~/selenium_env/venv/bin/python scripts/jarvis_etc_rebate_fetch.py --apply --push
# Vポイント定例
~/selenium_env/venv/bin/python scripts/jarvis_vpoint_routine.py --apply --push
# Slack だけ確認
~/selenium_env/venv/bin/python scripts/jarvis_points_rebate_slack_report.py --kind etc --from-state --dry-run
```

（FlowForge 各ノードの磨きはここに追記）

## 年間特典ウォッチ（2026-11-23 追加・Olive／Bonvoy の2枚だけ）

| 段 | 内容 | 成功の線 |
|---|---|---|
| 取り込み | Olive: `orca gmail` で三井住友カードの月次メール（15日現在・約10日後に届く）→ 確定値。Bonvoy: Zaim 取込行（年会費は除く）→ 概算（基準日つき） | state に保存できた＝取込成功（画面反映とは別） |
| 計算 | 達成率・残り日数／月数・月あたり必要額・判定（届く／厳しい／届かない見込み）。月ペースは期間開始からの平均 | state だけで再計算できる |
| 画面 | `jarvis_situation_watch.py` → push → `/vpoint#card-benefit` | 画面に出たのを人が見て確認（保存とは別） |
| Slack | `--kind card_benefit`。番号＋短い役割語、末尾に「今月はこちらを使うのがおすすめ」1行 | dry-run で確認→実投稿は了承後 |

- 判断点: 寄せ先を決めるのは松野さん。方針メモ＝定期払いは Olive に寄せ済み／今後の支払いを Bonvoy に寄せて狙い、狙えなければ打ち切り（年会費の前に判断）。
- 条件の金額は `threshold_status` を併記（確認済み／推定／要確認／未確認）。公式確認で `confirmed` に上げる。
- 取り込み失敗（メール未着・Zaim 古い）は「データなし／基準日」で表示し、基準なしと扱って推奨を出さない。
- 戻り条件: 条件の金額を公式で確認できたら config を直して計算へ戻る（無条件の反復なし）。
- 起動: 毎月28日 09:50（launchd）＋朝オープンの取りこぼし（28日以降・今月未成功）。実行本体は `jarvis_card_benefit_monthly.py`（取り込み失敗・投稿失敗は `#ops`、成功時だけ月の印）。
- Zaim の基準日が古い（既定10日超）ときは短報に「Zaim が古い（基準日◯）」を出し、概算は目安扱い。Olive の確定値が45日超なら「◯月◯日現在の確定値（古い）」も出す。
