# Phase 1 — L1ダイジェスト → #consult → 了承後 create

対象: 312 Todoist起票整理係  
所要目安: 1〜2時間（Jarvis側実装＋1回の通し確認）

## ゴール

「起票整理して」または材料ありのとき、**見るだけ**の候補一覧を Slack `#consult` に1通出し、松野が了承した番号だけ Todoist に `create-task` する（登録動線①）。

## 使うもの（新規アカウント不要）

| 道具 | 役割 | 補足 |
|---|---|---|
| Todoist API | タスク作成 | 既に `.env.jarvis_private` のトークン |
| Slack Incoming Webhook | `#consult` 投稿 | Webhook＝外部からチャンネルへ自動投稿するURL |
| 既存スクリプト | 候補抽出・create | `jarvis_todoist_sb_propose.py` / `jarvis_todoist_genmail_propose.py` / `jarvis_todoist_api.py` / `jarvis_slack_webhook_post.py` |

## 実装済み（2026-10-21）

- スクリプト: `scripts/jarvis_todoist_312_digest.py`
- state: `.jarvis_state/todoist_312_digest.json`
- 引数なし＝収集＋`#consult` 投稿 / `--dry-run`＝未投稿 / `--apply --select N`＝①create

## 通し確認

1. Slack `#consult` に「【相談】312 … L1ダイジェスト」がある ← **済**
2. 番号を決めて「起票して N」→ apply ← **運用時任意**（意図OK 2026-10-21。必須ゲートではない）
3. Todoist に1件増える ← 2のとき確認

## 運用格上げ（抄・正本は PROGRESS）

| 段階 | 開始目安 |
|---|---|
| A ルール常時 | **今（済）** |
| B ソフト（相乗りdigest） | **2026-10-22〜** |
| C 定時digest | 初回apply成功翌日 or **2026-10-28** |
| D 1.5b / E Phase2–3 | C安定1週後〜 |

## やらない（Phase 1外）

- L2 ボタンUI（→ Phase 2）
- 材料即時常駐（→ Phase 3）
- close（→ 313）
- ノイズ未確認での毎日自動 digest
