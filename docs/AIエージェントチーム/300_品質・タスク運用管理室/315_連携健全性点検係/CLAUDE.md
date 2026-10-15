# 連携健全性点検係

> **作業を始めたら、まず [`PROGRESS.md`](./PROGRESS.md) を読む。**  
> 本線: 日曜21:00 GHA検知 → `#ops`。Mac補完: 日曜21:45 `--remediate-once`（1回トライ→結果）。  
> **運用引き上げ**: 日曜 cron（schedule）成功を Jarvis がセッションついでに確認→sync（`docs/promote-to-ops.md`）。手動dispatchだけでは上げない。

ID: **315**（ビルダー「週次取込点検係」を拡張した体）。  
WeStudy／GitHub Actions の失敗、LINE オープンチャット取込、**Gmail OAuth token（スコープ・refresh）** の健全性を見て、異常なら既知手順を1回試し、`#ops` / `#consult` に出す。

## AIオートメーション（作業フロー）

- **FlowForge（開く）**: [flow_zYjp6A4HDURefJhSm0h_zUtX](https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_zYjp6A4HDURefJhSm0h_zUtX)
- 一覧・進捗: [`15_FlowForge全体系_進捗_20261010.md`](../../15_FlowForge全体系_進捗_20261010.md)
- 設計の流れ図: [`flow.md`](./flow.md)
- FlowForge「エージェントへの指示」貼付: [`flowforge_エージェントへの指示.md`](./flowforge_エージェントへの指示.md)（たたき台。下の表が実装正）
- 異常時: [`docs/incident-flow.md`](./docs/incident-flow.md)

### FlowForge指示 → 実装の具体化（2026-10-11）

| FF上のステップ | 実装の正 |
|---|---|
| 開始トリガー 日曜21:00 | GHA `ops-health-315.yml`（cron UTC 日曜12:00） |
| GHA実行結果取得 | 本線CLI内で `jarvis_westudy_weekly_check.py`（週次workflowの成否） |
| Square probe / CHRLINE health | **GHA（`--cloud`）ではスキップ**。Mac 日曜21:45 `--remediate-once` |
| Gmail token ヘルス | **GHAではスキップ**。Mac: `jarvis_gmail_token_health`（send欠落・refresh欠如を検知） |
| 健全性レポート | `jarvis_ops_health_315.py` が本文生成 → `#ops` |
| 1回トライ | Mac: オプチャ health push → recover_worker／watch resume。**Gmail・WeStudyは自動復旧しない** |
| 要判断通知 | `#consult`（1回トライ後も未解決／Gmail再同意要。流れ: `docs/incident-flow.md`） |
| 終了報告 | **常に `#ops`**（成功も異常も。チャット／`#report` なし） |

## 1. 役割

- やること:
  - WeStudy 週次: `jarvis_westudy_weekly_check.py` 等で成功／Fail を確認
  - LINE オプチャ（**Mac 21:45**）: 健全性数値化＋異常時は既知復旧を**1回**
  - **Gmail token（Mac）**: スコープ不足・refresh 欠如を検知し `#ops` に載せる（estate send 欠落時は `reauth_estate_gmail_send.py` を案内）
  - 成功なら `#ops` に修正済、ダメなら `#ops` 未解決＋`#consult`
- やらないこと:
  - 815 の返信提案
  - 構造限界（Square 401・削除済みスレ）を無理に「直した」ことにする
  - YAML 大量追記・QR／**Gmail ブラウザ再同意**を無確認で進める
  - WeStudy 週次の自動再実行
  - `#report` やチャットへの定時報告

## 2. 動き出す合図

- [ ] 人が頼む（手動・`workflow_dispatch`）
- [x] **時間（本線）: 毎週日曜 21:00 JST — GitHub Actions `ops-health-315.yml`**
- [x] **時間（Mac補完）: 毎週日曜 21:45 JST — launchd `--remediate-once`**
- [x] 何かが届いたら（WeStudy 週次 GHA Fail 通知等 → 手動または次回定時）

旧: launchd 日曜 09:15 は廃止（21:45 に置換）。

## 3. 実行権限

| 方法 | 使う？ | 内容 |
|---|---|---|
| チャット・検索 | ○ | ログ・MD 件数 |
| 外部連携 | ○ | `gh`（週次結果）・Slack Webhook |
| CLI | ○ | `jarvis_ops_health_315.py`（GHAは `--cloud`／Macは `--remediate-once`） |
| ブラウザ | △ | 必要時のみ |
| 画面操作 | △ | QR は人がスキャン |

**人が確かめる**: QR 再ログイン、**Gmail ブラウザ再同意**（`reauth_estate_gmail_send.py` 等）、YAML 大量追記、構造限界の受容判断、WeStudy 再実行。

## 4. 報告先（具体）

| 種別 | 行き先 | 手段 |
|---|---|---|
| 定期・結果（本線・Mac） | Slack **`#ops`** | `jarvis_slack_webhook_post.py --channel ops` |
| 要判断（1回トライ後未解決） | Slack **`#consult`** | 同スクリプト `--channel consult` |
| 出さない | `#report`・FlowForge「チャットに報告」 | 業務報告と混ぜない |

## 5. 成果物の置き場

- スクリプト: `scripts/jarvis_ops_health_315.py` / `jarvis_westudy_weekly_check.py` / `jarvis_gmail_token_health.py` / `jarvis_openchat_recover_worker.py`
- launchd: `launchd/install_ops_health_315_launchd.sh`（Sun 21:45）
- ルール: `jarvis-openchat-thread-health.mdc` / `jarvis-westudy-weekly-watch.mdc`
- Gmail: `docs/GCP_OAuth本番移行_Jarvis_20260826.md` / `reauth_estate_gmail_send.py`
- コマンド正本: `docs/運用コマンド一覧.md`
- ログ: このフォルダ `logs/` ／ `~/Library/Logs/jarvis_ops_health_315/`

## 6. 作業手順（チェックリスト）

1. GHA 日曜21:00: `--cloud --post` → `#ops`
2. Mac 日曜21:45: `--remediate-once --post` → 異常なら1回トライ→再点検→`#ops`
3. 未解決なら `#consult`
4. QR や大量YAMLが必要なら人が対応

### 一括

```bash
# GHA本線と同じ（cloud）
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
~/selenium_env/venv/bin/python scripts/jarvis_ops_health_315.py --cloud --post --mark-checked

# Mac補完（1回トライ）
~/selenium_env/venv/bin/python scripts/jarvis_ops_health_315.py --remediate-once --post --mark-checked

# 安全確認（投稿・復旧ともしない）
~/selenium_env/venv/bin/python scripts/jarvis_ops_health_315.py --remediate-once --dry-run
```

停止: `JARVIS_OPS_HEALTH_315_DISABLE=1`

## 7. 改善ログ

| 日付 | 変更 |
|---|---|
| 2026-10-09 | ハブ初期化・候補として作成（案A: 週次取込＋オプチャ統合） |
| 2026-10-09 | 3桁化（旧20_ → 315）。ビルダー部門「品質・タスク運用管理室」配下へ |
| 2026-10-11 | 下準備プラン1体目として具体化。`jarvis_ops_health_315.py` → Slack `#ops` 報告1通 |
| 2026-10-11 | Phase H: launchd 日曜 09:15（のち本線外し） |
| 2026-10-11 | **本線＝GHA 日曜21:00**。報告＝`#ops` のみ具体化。`--cloud`。状態＝運用確認 |
| 2026-10-11 | FlowForgeきっかけ／報告確定＋「エージェントへの指示」生成・具体化表を追記 |
| 2026-10-11 | 伴走再開: `PROGRESS.md`・GHA手動検証／Mac補完方針の docs。状態は運用確認のまま |
| 2026-10-11 | **検知→1回トライ→結果**: `--remediate-once`＋launchd 日曜21:45。パートナー確認依存をやめる |
| 2026-10-15 | **Gmail token モニター**を役割に追加（Mac 点検・`#ops`／欠落時 `#consult`。自動再同意なし） |
