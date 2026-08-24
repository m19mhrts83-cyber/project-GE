# 家族コーチング — Grok 反映（索引）

**更新**: 2026-08-24  
**方針**: このファイル単体を Instructions に貼らない。各 Bot の paste 正本を説明欄へ。

## Grok「説明」欄に貼るファイル（正本）

| Bot（Grok UI 名） | ファイル | 貼り方 |
|---|---|---|
| **家族コーチ統括** | `config/grok_family_manager_grok_paste.md` | コードブロック全文を説明欄へ |
| **まどかコーチ** | `config/grok_madoka_coach_grok_paste.md` | 同上 |
| **たまきコーチ** | `config/grok_tamaki_coach_grok_paste.md` | 同上 |
| **さわコーチ** | `config/grok_sawa_coach_grok_paste.md` | 同上 |

- **名前・タイトル**は UI の短い欄（各 paste 末尾のプロフィール設定）
- チャットは当日の材料・司令用。恒久ルールは説明欄のみ
- **統括は Notion 自己読取**（貼付待ち禁止）。Instructions 差し替え後に再貼り

## チャンネル（方式C）

- 推奨名: **家族コーチングチーム**
- メンバー: 統括＋まどか／たまき／さわコーチ
- 松野は統括にだけ話す（または `@家族コーチ統括`）

## 何が自動で、何が手動か

| 層 | 誰 | いまの状態 | トリガー |
|---|---|---|---|
| **材料** | Jarvis（Mac） | スクリプトあり。**launchd 未設定**（日曜セッションで実行） | `jarvis_family_journal_weekly.py --pull --apply` |
| **評価** | Grok 統括＋専属3本 | Instructions 済み。**ルーティン ON**（ユーザー設定済） | 日曜 21:00 週次／水曜 7:30 マイルストーン（任意） |
| **手動バックアップ** | 松野 | ルーティン前でも可 | 下の定型チャット |

Grok は Journal 本文を Jarvis からチャットで受け取らない。Notion の **Journal週次** を統括が読む。

## Grok ルーティン（チャンネルに設定）

正本: `config/grok_family_routine_週次.md` ／ `config/grok_family_routine_マイルストーン.md`

| 名前 | 投稿先 | スケジュール（JST） | 貼るファイル |
|---|---|---|---|
| `家族コーチング · 週次` | 家族コーチングチーム | **毎週日曜 21:00**（設定済） | `grok_family_routine_週次.md` の「指示」フェンス |
| `家族コーチング · マイルストーン` | 同上 | **毎週水曜 7:30**（任意） | `grok_family_routine_マイルストーン.md` |

## 定型チャット（ルーティン前・手動）

| タイミング | 文 |
|---|---|
| 週次（家族会議後） | `@家族コーチ統括 【今週の材料】Notionの直近家族会議と Journal週次を読んでまとめ。必要なら専属に振って。` |
| マイルストーン | `@家族コーチ統括 【マイルストーン確認】Notionの到達目標だけ見て、今夜の親の一言を1つ。` |
| 初回フル | paste 末尾「初回フル」ブロック |

## Notion・材料

| 項目 | 場所 |
|---|---|
| 正本 YAML | `config/notion_family_coaching.yaml` |
| ハブ1 | **家族会議** |
| ハブ2 | **子供コーチング** |
| ハブ3 | **Journal週次**（Jarvis 週次） |
| Journal週次更新 | `scripts/jarvis_family_journal_weekly.py --pull --apply` |

## 混同しないレーン

| レーン | 誰 |
|---|---|
| 家族コーチング | 本索引の4 Bot |
| 不動産賃貸 | 部長／S1〜S7 |
| アプリ開発 | アプリ開発統括 |
| Gemini カール参謀 | Journal 日次（並走可） |

## 初回チェックリスト

1. 統括 Instructions を更新版で差し替え（Notion自己読取）
2. 専属3本は参照材料の1行追加を再貼り（任意だが推奨）
3. Notion が Grok ログインアカウントから見えること（読取OK済みならスキップ）
4. 初回フル文をチャンネルへ投下
5. Grok ルーティン「家族コーチング · 週次」を家族コーチングチームに作成（`config/grok_family_routine_週次.md`）
