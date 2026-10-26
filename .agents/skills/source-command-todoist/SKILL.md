---
name: "source-command-todoist"
description: "Migrated source command `todoist`"
---

# source-command-todoist

Use this skill when the user asks to run the migrated source command `todoist`.

## Command Template

# /todoist — Todoist 入口（起票・俯瞰）

人またはエージェントが Todoist を進めるときの **入口コマンド**。識別用。

## 振り分け

| 意図 | やること |
|---|---|
| 起票候補・宿題の整理 | **312 Todoist起票整理係**（`docs/AIエージェントチーム/300_品質・タスク運用管理室/312_Todoist起票整理係/CLAUDE.md`） |
| 掃除・確認のみ完了・並列バッチ | **`/todoist-batch`** へ（313 完了候補確認係＋ skill `todoist-batch-sweep`） |
| 単件の列移動・コメント返信 | `jarvis-todoist-owner-confirm.mdc` どおり CLI |

## 必須（毎回）

- 起票・オーナー確認移動・完了・処置は **Todoist コメントにサマリ＋アウトプット**（チャットだけでは不足）
- コメント1行目先頭に **`【Jarvis】`** を必ず付ける（FRIDAY は `【FRIDAY】`・ホークは `【ホーク】`）
- 無言自動起票しない（候補→了承→create）
- 対外送信・振込・解約・課金は人了承

## 報告

最後に1ブロック。Slack は `#report`／要判断は `#consult`。
