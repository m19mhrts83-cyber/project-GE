# フロー（Flowforge 写し）— 814 Jarvisダッシュボード更新係

- Flowforge: https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_wkFbA0v6bq3ouq9dmpX-cxc1
- 指示書: [`CLAUDE.md`](CLAUDE.md)
- 状態: **案（2026-10-27 Claude 作成・松野確認待ち）**。了承後に FlowForge のノード文言へ写し、エージェント指示を作る

## 1. 現行フローの確認（2026-10-27 時点のコードと logs）

| 段 | 今の動き | 担当 |
|---|---|---|
| 起動 | Mac launchd `dashboard-push` 毎日 12:30 | Mac |
| 取得 | カード引落ウォッチ → `jarvis_situation_watch.py` | AI不要（ルール） |
| 更新 | `jarvis_dashboard_push.py` で Supabase へ投影（triage/watch/lanes/finance 等） | AI不要（ルール） |
| 点検 | `jarvis_ui_cycle_814_815.py` が「最終 push ログが48h以内か」だけ見る | AI不要（ルール） |
| 報告 | OK は `logs/` のみ、要フォローだけ `#ops` | — |

別系統: GHA `jarvis-dashboard-heartbeat`（06:30）は Supabase 休止回避の心拍を書くだけで、Mac 側の鮮度は見ていない。

## 2. コメント（気づいた点）

1. **止まったときに黙る**。点検は push の直後に同じスクリプトから走るので、走れば必ず OK になる。Mac が寝ていた日や push が失敗した日（runner は `set -e` なので push 失敗で点検まで到達しない）は、点検自体が動かず `#ops` にも何も出ない。実際 `logs/` は 10/11〜10/27 の17日間で6日分（10/11・18・23・24・26・27）しかなく、残り11日は点検の記録が無いのに誰にも知らされていない（Mac停止か push 失敗かは未確認）。
2. **見ている鮮度が「ログファイルの時刻」だけ**。画面ごと（triage／watch／カード／finance／`/agent-team`）のデータが古いかは見ていない。
3. **`/agent-team`（実装状況ページ）が対象外**。`agentTeam.json` は手動 sync で 10/25 から更新されていない。814 の担当に入れるのが自然。
4. **815 と点検を共有しているが、815 側は KURASHIFT を一切見ていない**（同じ dashboard ログで判定）。815 の確認時に切り分ける。

## 3. 思い描くフロー（案）

型: 開始トリガー → 経路 → 合流 → 点検 → Slack

| 段 | 内容 | 担当 |
|---|---|---|
| トリガーA（時刻） | Mac launchd 12:30（現行どおり）。push 本体 | Mac・ルール |
| トリガーB（見回り） | **クラウド GHA が毎朝 Supabase `sync_meta` を読み、Mac の最終 push が30h超なら異常**。Mac が止まっていても気づける外側の番人 | GHA・ルール |
| 経路 | カード引落 → situation_watch → push（各レーン）→ `agentTeam.json` sync もここに相乗り | ルール |
| 合流・点検 | 画面ごとの `updated_at` を読み戻し、レーン別の閾値で判定（例: triage/watch 30h、finance 48h、agent-team 7日）。push 失敗でも点検は必ず走らせる | ルール |
| 報告 | OK は `logs/` のみ。NG は `#ops` に1〜2行（どの画面が何時間古いか＋次の一手）。週1回だけ `#report` に生存確認1行 | ルール |
| 人 | ルーティンでは不要。UI の改修案だけ `#consult` | 松野 |

**4点まとめ**

- トリガー: 時刻（12:30 Mac）＋見回り（GHA 朝、Mac 停止検知）
- 権限: 読む＝全部自動／書く＝Supabase 投影と `agentTeam.json` のみ／UI改修・対外送信・削除はしない
- 作業内容: 投影更新 → 画面別鮮度の読み戻し点検
- 報告: NG だけ `#ops`、週1 `#report` 生存確認、改修案は `#consult`

AI（LLM）は使わない。全部ルールで回る社員なので、使用量はゼロのまま。

## 4. 実装の切り出し（FRIDAY へ渡す単位）

1. runner を `set -e` でも点検まで必ず走る形にする（push の exit code を点検に渡す）
2. `jarvis_ui_cycle_814_815.py` を「ログ時刻」から「`sync_meta` の画面別 `updated_at`」判定へ
3. GHA heartbeat に「Mac 最終 push 30h 超 → `#ops`」を追加
4. `jarvis_agent_team_status_sync.py` を 12:30 の経路に相乗り
5. 814 と 815 の点検を分ける（815 は 815 の確認時に中身を決める）
