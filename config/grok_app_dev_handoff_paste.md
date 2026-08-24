# アプリ開発 — Grok 反映（索引）

**更新**: 2026-08-24  
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

- 統括＝レビューと **Jarvis向けカード**（材料／実装）。実装は Jarvis
- 「やってみたい」→ 実装カード（リスク: 低|高）
- 低＝Jarvis 即実行可／高＝確認後
- 週次の提案は全部やらない（カード最大3）
- **受け渡し**: カード後に estate へ件名 `[Grok開発]`（朝取り込み）
- 朝要約: `scripts/jarvis_app_dev_cards_morning.py`（`jarvis_morning_mac_refresh` 内）

対象:
1. 神・大家さんQ&Aチャットボット
2. Jarvisダッシュボード
3. KURASHIFT

データ: Supabase `kamiooya-qa`（Q&A）／`jarvis-dashboard`（自分用）。3つ目PJは作らない。
