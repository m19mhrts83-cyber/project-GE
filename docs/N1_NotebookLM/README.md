# N1_NotebookLM（NotebookLM まわりのメモ）

このフォルダは **Cursor の `@docs/N1_NotebookLM` で参照**できるように、`project-GE` の `docs/` 配下に置いています。

## 同内容のミラー（215 ワークスペース）

OneDrive 上の **`215_神・大家さん倶楽部/N1_NotebookLM/`** と **常に同一内容**にする。

- **手動コピーは不要。** Cursor ルール [`.cursor/rules/n1-notebooklm-mirror.mdc`](../../.cursor/rules/n1-notebooklm-mirror.mdc) に従い、どちらかを編集したタスクの終わりにエージェントが `rsync` で双方向ミラーする。

## NotebookLM に実際に上げるファイル（Drive 正）

admin Drive の **`200_NoteBookLM/`** が添付の正本。

| 用途 | パス |
|------|------|
| 共通スタイル（いけとも） | `200_NoteBookLM/00_ゼロイチマスタースタイル/` |
| ノート単位のソース | `200_NoteBookLM/01_…` / `02_…` / `03_…` 等 |

ルール: [`.cursor/rules/jarvis-notebooklm-drive-sources.mdc`](../../.cursor/rules/jarvis-notebooklm-drive-sources.mdc)  
スタイル本文を直したら、ミラー後に **ゼロイチフォルダへも反映**する。

## 含まれるファイル

| ファイル | 内容 |
|----------|------|
| [運用まとめ_会話からの記録.md](運用まとめ_会話からの記録.md) | 会話で固めた運用（ミラー・依頼/結果/自分の作業・MCP 境界）の要約 |
| [NotebookLM_MCP_インストール手順.md](NotebookLM_MCP_インストール手順.md) | `mcp.json`・ログイン・トラブルシュート |
| [NotebookLMとCursorでできること一覧.md](NotebookLMとCursorでできること一覧.md) | MCP 連携後にチャットで何ができるか |
| [CursorのまとめをNotebookLMのソースにする方法.md](CursorのまとめをNotebookLMのソースにする方法.md) | 貼り付け・アップロードでソース化 |
| [NotebookLM_マスタースタイル_cute-illustration.md](NotebookLM_マスタースタイル_cute-illustration.md) | **ゆるイラスト（cute）のマスター全文**—NotebookLM のソースにそのまま追加 |
| [いけともゆるキャラプロンプト.md](いけともゆるキャラプロンプト.md) | **いけとも用クイック参照**—cute-illustration 全文＋NotebookLM コピペ用プロンプト |
| [AI説明資料_後から直しやすい作り方.md](AI説明資料_後から直しやすい作り方.md) | **客先提出向け**—画像1枚スライドの限界と、オブジェクト型（Plus AI 等）への切り替え方針 |
| [運用_ゆるイラスト画像＋PPTテキスト重ね.md](運用_ゆるイラスト画像＋PPTテキスト重ね.md) | **いけともゆるキャラ本線**—文字なしイラスト＋PPTテキスト箱（PoC済み） |
| [検証_周辺MAP_地図下地AI配置.md](検証_周辺MAP_地図下地AI配置.md) | **周辺MAPチラシ**—Plus AI地図上配置は不採用／Canva本線維持（2026-07-27） |
| [PlusAI_加入価値まとめ_検証要約_20260727.md](PlusAI_加入価値まとめ_検証要約_20260727.md) | **Plus AI有料加入の要否**—本業（ゆる／MAP）だけでは非推奨の要約 |
| [Plus_AI_導入手順.md](Plus_AI_導入手順.md) | Plus AI のインストール・ブランドテンプレ・日常フロー |
| [プロンプト雛形_ブランドテンプレ前提.md](プロンプト雛形_ブランドテンプレ前提.md) | ワンスライドワンメッセージの表＋Plus AI／校正用プロンプト |
| [NotebookLM_編集可能PPTX変換手順.md](NotebookLM_編集可能PPTX変換手順.md) | NotebookLM PDF→編集可能 PPTX（系統B・つなぎ） |
| **`jarvis-self/`（OneDrive のみ・容量正本）** | 自分理解用 PDF/PNG。公開写しは `docs/jarvis-self/`。取込は `jarvis_materials_ingest_downloads.py` |

## DX 勉強会スライド手順との関係

全体フローは [`.cursor/commands/dx-slides-from-outline.md`](../../.cursor/commands/dx-slides-from-outline.md) を正とし、本フォルダは **MCP・ソース登録の詳細**の参照先です。

- **公開 HTML・ゆるイラスト中心**（DX勉強会など）: 従来どおり NotebookLM Studio → PNG → `*_cute.html`
- **ゆるキャラを保ちつつ PPT で直したい**: [運用_ゆるイラスト画像＋PPTテキスト重ね.md](運用_ゆるイラスト画像＋PPTテキスト重ね.md)
- **客先提出であとから直したい PPTX（オブジェクト本線）**: [AI説明資料_後から直しやすい作り方.md](AI説明資料_後から直しやすい作り方.md)（構成は NotebookLM、本番は Plus AI 等）
