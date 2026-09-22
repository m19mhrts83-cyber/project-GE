# Todoist Pro 試用 — 戻り手順（2026-09-21）

## 方針

- **試用中は構成を Beginner 圧縮のまま**（`layout: beginner_compressed`）。1レーン1PJ 正規化は phase1b タスクで別途。
- **課金アカウント**: `admin@livingsupport-matsu.co.jp`（松野 UI）。Jarvis 分身は API 専用・課金不要。
- **試用開始直後に Cancel plan** 推奨 → 7日間は Pro 機能を使え、期限後に自動課金されない（公式ヘルプどおり）。

## スナップショット（正）

| もの | パス |
|---|---|
| プロジェクト／セクション／状態 | `.jarvis_state/todoist_pro_trial_rollback_20260921.json` |
| yaml 控え | `.jarvis_state/todoist_projects.yaml.rollback_beginner_20260921` |
| 歪みログ | `.jarvis_state/todoist_beginner_distortions.json` |

## Beginner に戻すとき

1. Settings → Subscription → **Cancel plan**（未キャンセルなら）
2. 試用中に増やした個人プロジェクトが **6本以上**なら、Beginner に落ちると超過分は **view-only** → 不要分を archive／統合して 5本以内に戻す
3. Filter が 4本以上なら、Beginner の **3枠**に戻す（正: 要連携 / SecondBrain / パッと）
4. `config/todoist_projects.yaml` が変わっていたら  
   `cp .jarvis_state/todoist_projects.yaml.rollback_beginner_20260921 config/todoist_projects.yaml`
5. `whoami` で admin / Jarvis とも `premium_status` を確認

## 試用中にやってよい／やらない

| よい | やらない（戻しにくくなる） |
|---|---|
| Filter 追加・Calendar 確認・歪み直し | いきなり全レーンを別プロジェクトへ分割して yaml を本番化 |
| distortions JSON に追記 | Guest `PM_*` を量産して枠を埋める（判断後でも可） |

## 公式

- 試用開始: https://www.todoist.com/help/account-and-billing/plans/start-a-todoist-pro-trial-LAVIT1Xm3
- ダウングレード時: https://www.todoist.com/help/todoist/billing/what-happens-when-i-downgrade-my-plan-dOhlH9qQe
