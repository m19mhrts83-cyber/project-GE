# Todoist → admin Googleカレンダー同期（2026-09-22）

Phase5 任意。Webhook 完了後に実装。

## 方針

| 項目 | 正 |
|---|---|
| **予定正本** | admin Googleカレンダー（`token_calendar.json`） |
| **Todoist の役割** | due があり、ラベル **`@cal`** を付けたタスクだけ外部同期 |
| **方向** | Todoist → GC の **片方向**（GC を Todoist に戻さない） |
| **終日** | due が日付のみ → 終日予定 |
| **時刻付き** | due に時刻あり → 開始＋既定 60 分（yaml で変更可） |

入口: Todoist `@cal`＋due · 確認: dry-run → `--apply` · 履歴: `.jarvis_state/todoist_calendar_sync.json` · 停止: yaml `enabled: false` / `JARVIS_TODOIST_CALENDAR_SYNC_DISABLE=1`

## 使い方

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
# ラベル作成（初回）
~/selenium_env/venv/bin/python scripts/jarvis_todoist_calendar_sync.py --ensure-label
# 候補確認
~/selenium_env/venv/bin/python scripts/jarvis_todoist_calendar_sync.py --dry-run
# 反映
~/selenium_env/venv/bin/python scripts/jarvis_todoist_calendar_sync.py --apply
# 状態
~/selenium_env/venv/bin/python scripts/jarvis_todoist_integrations_status.py
```

Todoist 側: タスクに **期限**を付け、ラベル **`cal`** を付ける（Filter 例: `@cal`）。

## 挙動

1. 未完了かつ `@cal`＋due のタスクを列挙
2. 未同期 → GC に作成（extendedProperties に task_id）
3. due／タイトル変更 → patch 更新
4. `@cal` 外し・完了・due 削除 → GC イベント削除＋ state から除去

## 設定

`config/todoist_projects.yaml` → `integrations.calendar_sync`

| キー | 意味 |
|---|---|
| `enabled` | true で `--apply` 可 |
| `due_label` | 既定 `cal` |
| `default_duration_minutes` | 時刻付きの長さ（既定 60） |
| `calendar_id` | 既定 `primary`（admin） |

## 関連

- 認証: `215_kamiooya/.../google_calendar_create.py` / `token_calendar.json`
- Webhook: `docs/Todoist_Webhook受信_20260922.md`
- タスク: `6hc2Gf8r75c2FfVc`
