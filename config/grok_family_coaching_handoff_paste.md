# 家族コーチング — Grok 反映（索引）

**更新**: 2026-08-23  
**方針**: このファイル単体を Instructions に貼らない。各 Bot の paste 正本を説明欄へ。

## Grok「説明」欄に貼るファイル（正本）

| Bot（Grok UI 名） | ファイル | 貼り方 |
|---|---|---|
| **家族コーチ統括** | `config/grok_family_manager_grok_paste.md` | コードブロック（`` ``` `` 〜 `` ``` ``）**全文**を説明欄へ |
| **まどかコーチ** | `config/grok_madoka_coach_grok_paste.md` | 同上 |
| **たまきコーチ** | `config/grok_tamaki_coach_grok_paste.md` | 同上 |
| **さわコーチ** | `config/grok_sawa_coach_grok_paste.md` | 同上 |

- **名前・タイトル**は UI の短い欄（各 paste 末尾のプロフィール設定）
- チャットは当日の材料・司令用。恒久ルールは説明欄のみ

## チャンネル（方式C）

- 推奨名: **家族コーチングチーム**
- メンバー: 統括＋まどか／たまき／さわコーチ
- 松野は統括にだけ話す（または `@家族コーチ統括`）

## Notion・材料

| 項目 | 場所 |
|---|---|
| ページ／ソース定義 | `config/notion_family_coaching.yaml` |
| トークン | `.env.jarvis_private` の `NOTION_API_TOKEN` または `NOTION_FAMILY_API_TOKEN` |
| 接続確認 | `scripts/jarvis_notion_api.py [--token-env NOTION_FAMILY_API_TOKEN] family-probe` |
| 棚卸し | `… get-page` |

参照する内容: 家族会議、塾説明、先生面談、面談相談メモ。

## 混同しないレーン

| レーン | 誰 |
|---|---|
| 家族コーチング | 本索引の4 Bot |
| 不動産賃貸 | 部長／物件調査／業者開拓 |
| Gemini カール参謀 | Journal 日次（並走可） |
| 水田塾メール | OneDrive 215（送受信）。Notionは面談メモ |

## 初回チェックリスト

1. 上記4 Bot を Grok で作成し、説明欄に paste を貼る
2. チャンネル「家族コーチングチーム」に4 Bot を追加
3. Notion ページを Integration に接続（または `NOTION_FAMILY_API_TOKEN` 設定）
4. Jarvis が材料抽出 → 統括に「本日の材料」貼付 → 振り分けテスト
