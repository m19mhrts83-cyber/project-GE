# Codex・Claude Code・Cursor 共通再開（2026-11-01）

## 松野さんが使う一言

Claude Code または Cursor に、次のように頼めばよい。

> Codexなどの作業の続きをしてほしい。案件名は「○○」。

案件名が分からないときは「直近のCodex引き継ぎを確認して」と添える。受取側は会話履歴だけに頼らず、ローカル受け渡し、案件の正本、実ファイルを確認してから続ける。

## 人が覚える入口

| 用途 | 参照先 |
|---|---|
| この運用の入口 | `/Users/matsunomasaharu2/git-repos/docs/AIエージェントチーム/53_Codex_Claude_Cursor共通再開_20261101.md` |
| Claude Code 宛て | `/Users/matsunomasaharu2/git-repos/agent-handoff/to_MissLemon/` |
| Cursor / Jarvis 宛て | `/Users/matsunomasaharu2/git-repos/agent-handoff/to_Jarvis/` |
| 詳細手順 | `/Users/matsunomasaharu2/git-repos/docs/AIエージェントチーム/51_ローカル受け渡し_20261026.md` |
| AIチーム共通ルール | `/Users/matsunomasaharu2/git-repos/docs/AIエージェントチーム/CLAUDE.md` |
| 短い共有 | Slack `#ai-hub` |

## 何をどこに残すか

1. **作業の正本**: 社員 `TASK.md` / `output/`、案件docs、コード、commit/PR。ここに結論・判断理由・検証結果・残作業を残す。
2. **受け取り口**: `agent-handoff/to_MissLemon/` と `to_Jarvis/`。正本への短い索引であり、成果物の唯一の保存先にはしない。
3. **通知**: Slack `#ai-hub`。作業内容を全文転載せず、案件名・現在地・受け取り口・次の担当だけを書く。
4. **期限・判断履歴**: Todoist。期限がある、人の判断が残る、または既存カードがある場合だけコメント・起票する。単なる完了共有では増やさない。

## Codexから両ツールへ渡す基準

次のいずれかなら、同じ `handoff_group_id` を持つメモをClaude Code宛てとCursor宛ての両方へ置く。

- 次の実行者をClaude CodeとCursorのどちらにするか未定
- 片方が実行し、もう片方も結果を把握しておく必要がある
- 松野さんが「両方へ共有」「他ツールでも続けられるように」と依頼した

元担当だけへ戻せばよい案件は、従来どおり該当する片方だけでよい。両宛てメモの本文は同じ正本を指し、詳細を二重更新しない。

## 受取側の動き

1. 自分宛てフォルダから、案件名・正本・`handoff_group_id` が一致する最新メモを1件選ぶ。
2. メモだけで完了や権限を推定せず、正本、worktree、git差分、commit/PR、検証結果を確認する。
3. 自分が続行する場合は `accepted`、正本へ反映して終えたら `done`、進められなければ `blocked` と理由を記録する。
4. もう片方にも同じIDのメモがある場合、受領状況を上書きせず、自分宛てメモだけ更新する。
5. 対外送信・振込・削除・課金変更・Todoist closeは、引き継ぎメモを新しい了承として扱わない。

## Codexプロジェクトの整理

- コードと共通資料を扱うCodexチャットは、原則としてローカルプロジェクト `/Users/matsunomasaharu2/git-repos` に所属させる。
- サイドバーは `コミュニケーション改善`、`KURASHIFTブラッシュアップ`、`AIエージェントチーム開発・運用`、`神大家運営相談` で見分ける。
- チャット本文は各チャット固有。別チャットへ残すべき内容は、上記の正本と引き継ぎへ保存する。
- Claudeの一時worktreeは別プロジェクト表示になり得るため、無理に統合せず、正本パスとcommit/PRで結ぶ。
- 追加の参照フォルダを持つ既存チャットをローカルプロジェクトへ移す前に、`git-repos` **プロジェクト側**のメニューから `Edit project（プロジェクトを編集）` → `Add folder（フォルダを追加）` で必要なフォルダを接続する。チャット側の「…」メニューには「プロジェクトへ移動」は表示されない。フォルダ追加後はCodex側で既存チャットの所属変更を再実行できる。確認前でも上記4区分と共通MDで再開できる。

## Slack `#ai-hub` の最小形

```text
【共有】4者共通再開・Codex引き継ぎ

案件: ○○
現在地: 実装済み／検証待ち など
受取: Claude Code・Cursor（同じ引き継ぎID）
次: 「Codexなどの作業の続きをして」で再開可
```

長いパス、秘密、ログ全文はSlackに載せない。
