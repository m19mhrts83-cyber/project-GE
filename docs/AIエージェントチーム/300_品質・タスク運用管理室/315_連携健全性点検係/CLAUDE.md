# 連携健全性点検係

ID: **315**（ビルダー「週次取込点検係」を拡張した体）。  
WeStudy／GitHub Actions の失敗と、LINE オープンチャット取込の健全性を見て、異常なら既知手順で是正または `#ops` / `#consult` に出す。

## AIオートメーション（作業フロー）

- **FlowForge（開く）**: [flow_zYjp6A4HDURefJhSm0h_zUtX](https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_zYjp6A4HDURefJhSm0h_zUtX)
- 一覧・進捗: [`15_FlowForge全体系_進捗_20261010.md`](../../15_FlowForge全体系_進捗_20261010.md)
- 設計の流れ図: [`flow.md`](./flow.md)
- FlowForge「エージェントへの指示」貼付: [`flowforge_エージェントへの指示.md`](./flowforge_エージェントへの指示.md)（たたき台。下の表が実装正）

### FlowForge指示 → 実装の具体化（2026-10-11）

| FF上のステップ | 実装の正 |
|---|---|
| 開始トリガー 日曜21:00 | GHA `ops-health-315.yml`（cron UTC 日曜12:00） |
| GHA実行結果取得 | 本線CLI内で `jarvis_westudy_weekly_check.py`（週次workflowの成否） |
| Square probe / CHRLINE health | **GHA（`--cloud`）ではスキップ**。Mac補完時のみ |
| 健全性レポート | `jarvis_ops_health_315.py` が本文生成 → `#ops` |
| 要判断通知 | `#consult`（人。自動復旧しない） |
| 終了報告 | **常に `#ops`**（成功も異常も。チャット／`#report` なし） |

## 1. 役割

- やること:
  - WeStudy 週次: `jarvis_westudy_weekly_check.py` 等で成功／Fail を確認
  - LINE オプチャ（**Mac補完時**）: 専用`【スレッド】`停滞・常時監視を数値化
  - 既知の復旧手順を手順どおり実行（ドライラン優先）
  - 結果を Slack `#ops` に報告
- やらないこと:
  - 815 の返信提案
  - 構造限界（Square 401・削除済みスレ）を無理に「直した」ことにする
  - YAML 大量追記・QR 本番再認証を無確認で進める
  - `#report` やチャットへの定時報告

## 2. 動き出す合図

- [ ] 人が頼む（手動・`workflow_dispatch`）
- [x] **時間（本線）: 毎週日曜 21:00 JST — GitHub Actions `ops-health-315.yml`**
- [x] 何かが届いたら（WeStudy 週次 GHA Fail 通知等 → 手動または次回定時）
- [ ] 変化・失敗を見回ったら（オプチャ詳細は Mac フル点検時）

旧: launchd 日曜 09:15 は **本線ではない**（残っていれば補完／無効化可）。

## 3. 実行権限

| 方法 | 使う？ | 内容 |
|---|---|---|
| チャット・検索 | ○ | ログ・MD 件数 |
| 外部連携 | ○ | `gh`（週次結果）・Slack Webhook |
| CLI | ○ | `jarvis_ops_health_315.py`（GHAは `--cloud`） |
| ブラウザ | △ | 必要時のみ |
| 画面操作 | △ | QR は人がスキャン |

**人が確かめる**: QR 再ログイン、トークン失効の本番再認証、YAML 大量追記、構造限界の受容判断。

## 4. 報告先（具体）

| 種別 | 行き先 | 手段 |
|---|---|---|
| 定期・結果（本線） | Slack **`#ops`** | `jarvis_slack_webhook_post.py --channel ops`／`SLACK_WEBHOOK_AI_TEAM_OPS` |
| 要判断 | Slack **`#consult`** | 人が1行（または別途投稿） |
| 出さない | `#report`・FlowForge「チャットに報告」 | 業務報告と混ぜない |

GHA Secrets にも `SLACK_WEBHOOK_AI_TEAM_OPS` を入れる（無いと本文のみで Slack 未投稿）。

## 5. 成果物の置き場

- スクリプト: `~/git-repos/scripts/jarvis_westudy_weekly_check.py` / `jarvis_square_probe_check.py`
- ルール: `jarvis-openchat-thread-health.mdc` / `jarvis-westudy-weekly-watch.mdc`
- コマンド正本: `docs/運用コマンド一覧.md`
- ログ: このフォルダ `logs/`

## 6. 作業手順（チェックリスト）

1. WeStudy 週次チェック（出力ブロックを控える）
2. オプチャ健全性: 直近の`【スレッド】`／watch 状態／例外ログを数値化
3. 異常なら既知手順（pause → discover → threads-only → resume 等）を提案または実行
4. Slack `#ops` に結果（OK／要フォロー）
5. QR や大量YAMLが必要なら `#consult` に1行

### 一括（推奨・GHA本線と同じ）

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
~/selenium_env/venv/bin/python scripts/jarvis_ops_health_315.py --cloud --post --mark-checked
```

ログ: このフォルダ `logs/`

## 7. 改善ログ

| 日付 | 変更 |
|---|---|
| 2026-10-09 | ハブ初期化・候補として作成（案A: 週次取込＋オプチャ統合） |
| 2026-10-09 | 3桁化（旧20_ → 315）。ビルダー部門「品質・タスク運用管理室」配下へ |
| 2026-10-11 | 下準備プラン1体目として具体化。`jarvis_ops_health_315.py` → Slack `#ops` 報告1通 |
| 2026-10-11 | Phase H: launchd 日曜 09:15（のち本線外し） |
| 2026-10-11 | **本線＝GHA 日曜21:00**。報告＝`#ops` のみ具体化。`--cloud`。状態＝運用確認 |
| 2026-10-11 | FlowForgeきっかけ／報告確定＋「エージェントへの指示」生成・具体化表を追記 |
