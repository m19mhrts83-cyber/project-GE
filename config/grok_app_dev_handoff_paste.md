# アプリ開発 — Grok 反映（索引）

**更新**: 2026-08-28  
**方針**: このファイル単体を Instructions に貼らない。

| Bot | ファイル |
|---|---|
| **アプリ開発統括** | `config/grok_app_dev_manager_grok_paste.md` |

| 用途 | ファイル |
|---|---|
| チャンネル・ルーティン | `config/grok_app_dev_routine_週次.md` |
| 設計 | `docs/Grok_アプリ開発統括_設計_20260824.md` |

チャンネル: **アプリ開発チーム**（当面は統括のみ）

## 運用の要点

- 統括＝レビューと **Jarvis向けカード**（材料／実装／表確認）。**PR は切らない**
- 「やってみたい」→ 実装カード（リスク: 低|高）
- **表確認（3アプリ）**: 裏（統括）→怪しさなら表確認（Jarvisがログインして画面確認）。PWは Drive に置かない
- **受け渡し**: カード後に estate へ件名 `[Grok開発]`
- 朝: 要約 → **キュー**（低=Cloud→PR／高=Issue／表確認=ui-check Issue）。自動マージなし
- 処置: GitHub で目視、または Jarvis に「委任して #N」
- スクリプト: `jarvis_app_dev_cards_morning.py` / `jarvis_app_dev_queue.py`

対象:
1. 神・大家さんQ&Aチャットボット
2. Jarvisダッシュボード
3. KURASHIFT

データ: Supabase `kamiooya-qa`（Q&A）／`jarvis-dashboard`（自分用）。3つ目PJは作らない。
