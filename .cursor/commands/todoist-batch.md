# /todoist-batch — Todoist 掃除・並列バッチ

**313 完了候補確認係**＋ skill `todoist-batch-sweep` を起動する依頼コマンド。

## 既定テンプレ

```
【Todoist掃除・並列モード】
対象: apps / ai_raimo の quick・表確認・要Jarvis連携
件数: 最大5
やり方: 別処理で並列可。対外送信・振込・解約は除外
止め位置: オーナー確認まで（ただし確認のみはJarvis完了可）
報告: 最後に一覧1ブロックだけ
```

## 必須

- 各タスクに **コメント（サマリ＋アウトプット）**。確認のみ close は先頭 `タスク完了したよ（Jarvis・確認のみクローズ）`
- チャットは末尾1ブロックのみ（都度「いいですか？」しない）
- 正本: `.cursor/skills/todoist-batch-sweep/SKILL.md` · `313_完了候補確認係/CLAUDE.md`

入口俯瞰・起票は `/todoist`。
