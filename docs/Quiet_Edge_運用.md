# Quiet Edge 運用

いびきレーザー治療の経過を Jarvis Dashboard「Quiet Edge」に長期保管する手順。

- 画面: `/quiet-edge`
- 正本 DB: Supabase `jarvis-dashboard`
  - Phase1: `vital_snore_daily` / `vital_treatment_events`
  - Phase2: `vital_daily`（Health）
  - Phase3: `vital_journal_daily` / `vital_context_notes`
- **診断アプリではない。** 医師に見せるための観察整理。

主観の本線は毎朝の点数入力ではなく、Obsidian `★Journal`（`config/dashboard_lanes.yaml` の `obsidian_journal`）を日付でバイタルと重ねる。欠落・急変には「何がありましたか？」で補完する。

Health 日次: [`docs/Quiet_Edge_ヘルスケアショートカット手順.md`](Quiet_Edge_ヘルスケアショートカット手順.md)

---

## 毎朝の取込（1日2枚）

AutoSnore から次の **2画面** をスクリーンショットする。

| 枚 | 画面 | 取り出す項目 |
|---|---|---|
| A | 履歴 → **イビガースコア** | 日付・スコア・睡眠時間帯 |
| B | ホーム（検出円）→ **回数** | 検出回数（平均比は参考） |

### 手順

1. AutoSnore で昨夜の結果を開く
2. イビガースコア画面をスクショ
3. 検出回数画面をスクショ
4. Jarvis Dashboard → Quiet Edge → 「AutoSnore スクショ」に **2枚同時**（または1枚ずつ）アップロード
5. フォームに入った日付・スコア・回数・睡眠帯を目視確認
6. 治療当日／直後ならステータスを変更
7. **取り込む** を押す（保存後、取込レビューが自動表示）

同じ測定日なら、1枚ずつでも欠けた欄だけ埋まる（upsert）。

### 取込レビュー（自動）

保存直後に、次を踏まえた短い励ましメモが出ます（診断ではない）。

| 参照 | 内容 |
|---|---|
| いびき | 当日スコア／回数、前回比、直近平均、改善目標（≤10） |
| Health | 同日の睡眠・SpO2 等（ingest 済みなら） |
| Journal | 同日 ★Journal 抜粋の有無 |
| 補完メモ | 「何がありましたか？」の回答 |
| 治療 | 次のレーザー予定 |

Gemini が使えないときはルールベースのフォールバック文を出します。長い観察整理は画面下の「レビューを生成」を使用。

---

## 記録日ルール

- **記録日 = 起床側の暦日**（スコア画面に出る日付）
- 回数画面の「木〜金の間」は **金** に寄せる
- 例: 8/6木 22:45 〜 8/7金 6:02 → `recorded_at = 2026-08-07`

---

## Phase 3: Journal 同期（Mac）

Vercel はローカル Disk を見ないため、★Journal 抜粋を Supabase に投影する。

```bash
cd ~/git-repos
/Users/matsunomasaharu2/selenium_env/venv/bin/python scripts/jarvis_quiet_edge_journal_sync.py
# 確認だけ
/Users/matsunomasaharu2/selenium_env/venv/bin/python scripts/jarvis_quiet_edge_journal_sync.py --dry-run --days 14
```

- パス: `config/dashboard_lanes.yaml` → `obsidian_journal`（または env `QUIET_EDGE_JOURNAL_DIR` / `JARVIS_LANES_OBSIDIAN_JOURNAL`）
- 秘密: `JARVIS_SUPABASE_URL` + Service Role（`.env.jarvis_private`）
- 画面: **睡眠シグナル**（夜の防衛線・タグ）といびき日次のジョイン、Ask、観察レビュー
- sync は業務メモ全文ではなく、防衛線など睡眠関連を優先抽出（`sleep_signal` / `sleep_tags`）

推奨: パートナー確認のついで、または launchd で日次1回。

---

## 治療ステータス

| 値 | いつ付けるか |
|---|---|
| 通常日 | ほとんどの日 |
| 治療当日 | レーザー照射日の睡眠測定 |
| 治療直後 | 照射後数日（目安 1〜3 日。迷ったら通常日） |

スケジュール本体は `vital_treatment_events`（タイムライン表示）。変更は Jarvis／SQL で行う。

---

## 手入力・修正

- スクショなしでもフォームから保存可
- 表の日付をクリックするとフォームに載る
- 削除は取り消せないので注意

---

## デプロイ前チェック（Vercel）

| 変数 | 用途 |
|---|---|
| `GEMINI_API_KEY` | OCR・観察レビュー |
| `QUIET_EDGE_INGEST_SECRET` | Health ingest API |
| `JARVIS_SUPABASE_*` / Dashboard 用 Supabase | 既存どおり |

Redeploy 後、サイドバー **からだ → Quiet Edge**。

---

## トラブル

| 症状 | 確認 |
|---|---|
| OCR 失敗 | `GEMINI_API_KEY`（Vercel / ローカル `.env.local`） |
| スコアだけ／回数だけ | もう1枚を追加アップロードして同じ日で保存 |
| Journal が空 | Mac で sync スクリプト実行。Drive パス・Service Role |
| Health が空 | Shortcuts → ingest。秘密ヘッダと Vercel env |
| データが見えない | ログイン済みか。テーブル未作成なら migration 適用 |

画像ファイル自体は DB に保存しない（数値のみ）。Journal は抜粋のみ（全文は Obsidian 正本）。
