# フロー — 715 家族会議週次係

- 正本 CLI: `scripts/friday_family_meeting_weekly.py`
- 設定: `config/notion_family_coaching.yaml`（`automation`）／`config/notebooklm_studio.yaml`（`family_meeting_weekly`）
- 更新: 2026-10-19

## 文字1行

**松野さんが当日ページを複製 → 日曜21:30に「議事録MD → NLMソース → インフォ → Notionへインフォ→議事録の順」→ Slack報告。**

## Mermaid

```mermaid
flowchart TD
  S[日曜21:30 launchd] --> L{lock}
  L -->|取得済| X[終了]
  L -->|OK| P[Notion 当日ページ (YYYY/MM/DD) を探す]
  P -->|なし| OPS[#ops: 前週複製を依頼]
  P -->|あり| G[Genspark search 前後1日]
  G --> J[JST日付＋家族語彙＋時間帯で採点]
  J -->|候補なし| OPS
  J -->|採用| M[議事録MDをDriveへ]
  M --> N[NotebookLM 家族会議1ノートへソース追加]
  N --> I[Studio インフォ生成]
  I --> U[Notion file_upload]
  U --> A[ページ末尾へ インフォ → 議事録要約]
  A --> R[#report]
  N -->|失敗| RT[状態pending + #ops]
  I -->|失敗| RT
  RT --> RETRY[月曜07:00 --retry]
  RETRY --> M
```

## ステップ一覧

| # | 内容 | 方法 | 状態キー |
|---|---|---|---|
| 1 | 当日ページ検索 | Notion 子ページ `(YYYY/MM/DD)` | `notion.page_id` |
| 2 | 会議特定 | `gsk meeting search`＋採点 | `meeting_id` |
| 3 | MD 保存 | `13_家族会議_週次/議事録/` | `md_path` |
| 4 | NLM ソース追加 | `jarvis_notebooklm_add_source.py` | `source_added` |
| 5 | インフォ生成 | `jarvis_notebooklm_studio_run.py` | `infographic_png` |
| 6 | Notion 挿入 | `friday_notion_ops.py` | `notion_inserted` |
| 7 | 報告 | Slack webhook | `status` |

## 再実行の考え方

- `source_added` / `infographic_png` が立っていれば再生成しない
- Notion は見出し `週次インフォグラフィック（YYYY-MM-DD）` / `Genspark 議事録要約（YYYY-MM-DD）` の有無で判定
- 失敗時は `status: pending`。月曜07:00 `--retry` が拾う
