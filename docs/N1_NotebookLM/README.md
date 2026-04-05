# N1_NotebookLM（NotebookLM まわりのメモ）

このフォルダは **Cursor の `@docs/N1_NotebookLM` で参照**できるように、`project-GE` の `docs/` 配下に置いています。

## 同内容のミラー（215 ワークスペース）

OneDrive 上の **`215_神・大家さん倶楽部/N1_NotebookLM/`** と **常に同一内容**にする。

- **手動コピーは不要。** Cursor ルール [`.cursor/rules/n1-notebooklm-mirror.mdc`](../../.cursor/rules/n1-notebooklm-mirror.mdc) に従い、どちらかを編集したタスクの終わりにエージェントが `rsync` で双方向ミラーする。

## 含まれるファイル

| ファイル | 内容 |
|----------|------|
| [運用まとめ_会話からの記録.md](運用まとめ_会話からの記録.md) | 会話で固めた運用（ミラー・依頼/結果/自分の作業・MCP 境界）の要約 |
| [NotebookLM_MCP_インストール手順.md](NotebookLM_MCP_インストール手順.md) | `mcp.json`・ログイン・トラブルシュート |
| [NotebookLMとCursorでできること一覧.md](NotebookLMとCursorでできること一覧.md) | MCP 連携後にチャットで何ができるか |
| [CursorのまとめをNotebookLMのソースにする方法.md](CursorのまとめをNotebookLMのソースにする方法.md) | 貼り付け・アップロードでソース化 |
| [NotebookLM_マスタースタイル_cute-illustration.md](NotebookLM_マスタースタイル_cute-illustration.md) | **ゆるイラスト（cute）のマスター全文**—NotebookLM のソースにそのまま追加 |

## DX 勉強会スライド手順との関係

全体フローは [`.cursor/commands/dx-slides-from-outline.md`](../../.cursor/commands/dx-slides-from-outline.md) を正とし、本フォルダは **MCP・ソース登録の詳細**の参照先です。
