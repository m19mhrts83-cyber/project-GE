# フロー（Flowforge 写し）— 815 KURASHIFT更新係

- Flowforge: https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_Xy85GrVwta9qwVlLQcHAwNjI
- 指示書: [`CLAUDE.md`](CLAUDE.md)
- 状態: **案（2026-10-29 Claude 作成・松野確認待ち）**。了承後に FlowForge のノード文言へ写し、エージェント指示を作る
- 関連: [`814 flow.md`](../814_Jarvisダッシュボード更新係/flow.md)（点検の作りを共有している）

## 1. 現行フローの確認（2026-10-29 時点のコードと logs）

KURASHIFT のデータを更新しているジョブは、815 の外に散らばっている。815 自身が回しているのは点検だけ。

| 更新ジョブ | 時刻 | 置き場 | 失敗の気づき方 |
|---|---|---|---|
| 朝の Mac 一括（`jarvis_morning_mac_refresh.py`）: Grok調査メール→deals、S1証拠、業者 sync、Obsidian pick、問合せ poll、日次ダイジェスト、cleanup | 朝 | Mac | soft-fail で stderr に出るだけ。結果は保存されない |
| GHA `kurashift-re-daily-inquiry` | 7:30／12:30／17:30／20:30 | クラウド | `jarvis_ops_fail_watch` が監視（朝1回） |
| GHA `kurashift-grok-mail-noon` | 11:00 | クラウド | 監視対象外 |
| GHA `kurashift-vendor-outreach-stall`（516） | 平日 16:00 | クラウド | 監視対象外 |
| GHA `kurashift-stock-watch-daily` | 平日 16:05 | クラウド | 監視対象外 |
| launchd `kurashift_job_worker` | 常駐 | Mac | — |

815 の点検: 12:30 の dashboard-push に相乗りした `jarvis_ui_cycle_814_815.py --agent both`。判定材料は **814 と同じ dashboard push ログの時刻だけ**。

## 2. コメント（気づいた点）

1. **815 は KURASHIFT を一度も見ていない**。点検はダッシュボードの push ログで判定しているので、KURASHIFT の deals や業者データが何日止まっていても OK になる。`logs/` の中身も 814 と同じ文面。
2. **失敗の気づき方がジョブごとにバラバラ**。Fail Watch が見ているのは `kurashift-re-daily-inquiry` だけで、11:00 の Grok 調査取込・業者開拓・株ウォッチは落ちても誰も気づかない。朝の Mac 一括は結果を残していない。
3. **役割の書き方が実態と合っていない**。CLAUDE.md は「更新サイクルを回す」と書いているが、更新は上の各ジョブが担っていて、815 が回すものは無い。815 は「回す係」ではなく「届いているかを見る番人」にするのが実態に合う。
4. **「deals 停滞の見回り」は他の社員と重なる**。案件の停滞は 516（業者開拓）と日次ダイジェストが見ている。815 はデータの鮮度だけに絞り、案件の中身の判断はしない方が重複しない。

## 3. 思い描くフロー（案）

型: 開始トリガー → 経路 → 合流 → 点検 → Slack

| 段 | 内容 | 担当 |
|---|---|---|
| トリガー（時刻） | 12:30 の dashboard-push 相乗りは残す（朝一括と 11:00 取込の後なので、その日の更新が揃っている時刻） | Mac・ルール |
| トリガー（見回り） | 814 で足すクラウド側の番人（GHA 朝）に、KURASHIFT の鮮度も一緒に見させる。Mac が止まっていても気づける | GHA・ルール |
| 経路A（データ） | Supabase の KURASHIFT テーブルの最終更新を読む（`kurashift_re_deals`・`kurashift_re_vendors`・株ウォッチ等）。テーブルごとに閾値（例: deals 30h、業者 7日、株 平日 30h） | ルール |
| 経路B（ジョブ） | `kurashift-*` の GHA 4本の直近結果と、朝の Mac 一括の各ステップ結果（`.jarvis_state` に残すようにする）を読む | ルール |
| 合流・点検 | A と B を合わせて「どの画面が、どのジョブのせいで古いか」を1行にする | ルール |
| 報告 | OK は `logs/` のみ。NG は `#ops` に1〜2行（古い画面＋原因ジョブ＋次の一手）。814 と1通にまとめず、815 の名前で出す | ルール |
| 人 | ルーティンでは不要。Tier3 の ON や問合せ送信には一切触れない | 松野 |

**4点まとめ**

- トリガー: 時刻（12:30 Mac 相乗り）＋見回り（GHA 朝、814 と同じ番人に相乗り）
- 権限: 読むだけ（Supabase の KURASHIFT テーブル、GHA の実行結果、`.jarvis_state`）。書き込み・送信・Tier3 は不可
- 作業内容: KURASHIFT の鮮度とジョブ結果の突き合わせ
- 報告: NG だけ `#ops`（原因ジョブ付き）。案件の停滞は 516／日次ダイジェストに任せる

AI（LLM）は使わない。814 と同じく、ルールだけで回る社員。

## 4. 実装の切り出し（FRIDAY へ渡す単位）

1. `jarvis_ui_cycle_814_815.py` の 815 判定を、Supabase の KURASHIFT テーブル最終更新に置き換える（814 の画面別判定と同じ作りで、815 は別関数）
2. 朝の Mac 一括の `results["steps"]` を `.jarvis_state/morning_refresh_last.json` に保存する
3. `jarvis_ops_fail_watch.py` の `WATCH_WORKFLOWS` に `kurashift-grok-mail-noon.yml`・`kurashift-vendor-outreach-stall.yml`・`kurashift-stock-watch-daily.yml` を足す
4. 814 で作るクラウド側の番人に、KURASHIFT テーブルの鮮度判定を相乗りさせる
5. CLAUDE.md の役割を「更新を回す」から「更新が届いているかを見る番人」に直す（了承後）
