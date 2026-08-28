# 家族コーチング — Grok 反映（索引）

**更新**: 2026-08-28  
**方針**: このファイル単体を Instructions に貼らない。各 Bot の paste 正本を説明欄へ。

## Obsidian 直読み・週次定型（運用の正 · 2026-08-28〜）

| 項目 | 正 |
|---|---|
| **Journal 正本** | Obsidian `★Journal`（admin Google Drive `500_Obsidian_r1`） |
| Journal 読取 | 統括が **Drive 自己読取**（金締＝土〜金。直下と `YYYY-MM/` 両方） |
| Notion 正本 | **家族会議**・塾／面談・子供別ページ（Journal 要約は使わない） |
| 参照順 | ①Drive ★Journal（金締） → ②Notion 家族会議 → ③必要なら子供別ページ |
| Jarvis | Obsidian 同期補助。Notion 投影は **フォールバック**（`jarvis_family_journal_weekly.py`） |
| 週次定型 | `@家族コーチ統括 【今週の材料】…`／ルーティン日曜 21:00 |
| マイルストーン定型 | `@家族コーチ統括 【マイルストーン確認】…`／ルーティン水曜 7:30（任意） |
| 初回 | paste 末尾「初回フル」ブロック（チャンネルへコピペ） |

## Grok「説明」欄に貼るファイル（正本）

| Bot（Grok UI 名） | ファイル | 貼り方 |
|---|---|---|
| **家族コーチ統括** | `config/grok_family_manager_grok_paste.md` | コードブロック全文を説明欄へ |
| **まどかコーチ** | `config/grok_madoka_coach_grok_paste.md` | 同上 |
| **たまきコーチ** | `config/grok_tamaki_coach_grok_paste.md` | 同上 |
| **さわコーチ** | `config/grok_sawa_coach_grok_paste.md` | 同上 |
| **ちかげアドバイザー** | `config/grok_chikage_advisor_grok_paste.md` | 同上（配偶者・夫婦コミュニケーション） |
| **空手アドバイザー** | `config/grok_karate_advisor_grok_paste.md` | 同上（空手ジャンル · Journal・遊愛会） |

- **名前・タイトル**は UI の短い欄（各 paste 末尾のプロフィール設定）
- チャットは当日の材料・司令用。恒久ルールは説明欄のみ
- **統括は Drive＋Notion 自己読取**（貼付待ち禁止）。Instructions 差し替え後に再貼り

## チャンネル（方式C）

- 推奨名: **家族コーチングチーム**
- メンバー: 統括＋まどか／たまき／さわ／**ちかげアドバイザー**／**空手アドバイザー**
- 松野は統括にだけ話す（または `@家族コーチ統括`）

## 何が自動で、何が手動か

| 層 | 誰 | いまの状態 | トリガー |
|---|---|---|---|
| **材料（Journal）** | iPhone Obsidian Push → Drive | 正本は Drive 上の ★Journal | 松野が日次入力・Push |
| **材料（会議・面談）** | Notion | 統括が自己読取 | 手動／会議後 |
| **評価** | Grok 統括＋専属5本 | Instructions 更新要。**ルーティン ON** | 日曜 21:00 週次 |
| **フォールバック** | Jarvis（Mac） | Notion Journal週次投影（任意・Drive NG 時） | launchd 日曜 08:00 |
| **手動バックアップ** | 松野 | ルーティン前でも可 | 下の定型チャット |

Grok は Journal 本文を Jarvis からチャットで受け取らない。**Drive の ★Journal** を統括が読む。

## Grok ルーティン（チャンネルに設定）

正本: `config/grok_family_routine_週次.md` ／ `config/grok_family_routine_マイルストーン.md`

| 名前 | 投稿先 | スケジュール（JST） | 貼るファイル |
|---|---|---|---|
| `家族コーチング · 週次` | 家族コーチングチーム | **毎週日曜 21:00**（設定済） | `grok_family_routine_週次.md` の「指示」フェンス |
| `家族コーチング · マイルストーン` | 同上 | **毎週水曜 7:30**（任意） | `grok_family_routine_マイルストーン.md` |

## 定型チャット（ルーティン前・手動）

| タイミング | 文 |
|---|---|
| 週次（家族会議後） | `@家族コーチ統括 【今週の材料】Drive の ★Journal（金締）と Notion 直近家族会議を読んでまとめ。必要なら専属に振って。` |
| マイルストーン | `@家族コーチ統括 【マイルストーン確認】Notionの到達目標だけ見て、今夜の親の一言を1つ。` |
| 初回フル | paste 末尾「初回フル」ブロック |
| 空手・稽古 | `@空手アドバイザー 【空手】Journal と遊愛会から今週の稽古・親子の次の1手。` |

## 材料の置き場

| 項目 | 場所 |
|---|---|
| 正本 YAML（Notion） | `config/notion_family_coaching.yaml` |
| 正本 YAML（Obsidian） | `config/kurashift_obsidian_artifacts.yaml` → `family_journal` |
| Journal（Drive） | `マイドライブ/500_Obsidian_r1/01_Journaling/★Journal/` |
| Notion ハブ1 | **家族会議** |
| Notion ハブ2 | **子供コーチング** |
| Notion レガシー | **Journal週次**（Drive NG 時のみ） |
| Notion 投影（任意） | `scripts/jarvis_family_journal_weekly.py --pull --apply` |

## Drive 許可（Grok Bot）

- **許可**: admin Google Drive のみ
- **禁止**: Downloads／OneDrive／iCloud／Desktop 全体／Media
- パスワード・API 鍵は Drive に置かない

## 混同しないレーン

| レーン | 誰 |
|---|---|
| 家族コーチング | 本索引の **6 Bot** |
| 不動産賃貸 | 部長／S1〜S7 |
| アプリ開発 | アプリ開発統括 |
| Gemini カール参謀 | Journal 日次（並走可） |

## 初回チェックリスト

1. 松野 → `@家族コーチ統括 JarvisBox の未処理（Obsidian直読み）を読んで実行して。`
2. 統括が `Drive読取:` / `Notion読取:` を返すことを確認
3. （任意）Instructions／週次ルーティン UI 貼付 — `00_松野向け_Grok_UI手順.md`
4. 2〜3週 Drive OK が続いたら Notion 投影 launchd 停止検討

## 松野向け Grok UI（JarvisBox 本線）

**通常**: 松野は統括に **「JarvisBox 見て」** とだけ伝える。統括が Drive で読んで実行する。

**任意（恒久化）**: Instructions／週次ルーティンの Grok UI 貼付は Bot 自身ではできない。余裕があれば松野が作業パックの 01・02 を UI に貼る。

| 入口 | 内容 |
|---|---|
| **JarvisBox** | `20_outbox_to_grok/` 未処理 → **統括が読む** |
| **作業パック** | `30_shared_working/2026-08-28_家族コーチ_Obsidian直読み/` |
| 統括向け | `00_統括向け_運用切替.md` |
| UI 貼付用（任意） | `01_統括_Instructions貼付用.md` / `02_ルーティン_週次_貼付用.md` |

松野が統括へ言う一言:

```
@家族コーチ統括 JarvisBox の未処理（Obsidian直読み）を読んで実行して。
```

## 運用開始時の期待優先（設計例）

材料が 2026-08-23 家族会議＋直近 ★Journal のときの正解イメージ:

1. **まどか**: 数学到達と「0.1%／1〜2分」の毎週確認（一発理解を求めない）。マリオット条件の親の言い方は短く具体
2. **たまき**: 算数など到達の意味を確認したうえで、開始時刻・後期自習→授業のリズムを1つ
3. **さわ**: 宿題は今夜 **1つだけ**（チャンネル既報と整合）
4. **マサハル**: 帰宅後ゾーンは **1ルールだけ**（例: 食後〜子ども就寝まで開発Bot触らない）
