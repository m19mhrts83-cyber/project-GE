# Quiet Edge 運用

いびきレーザー治療の経過を Jarvis Dashboard「Quiet Edge」に長期保管する手順。

- 画面: `/quiet-edge`
- サイドバー: **からだ → Quiet Edge**（同グループに **仕事** `/performance/work`・**運動** `/performance/move`。いびき治療は Quiet Edge 専用）
- 正本 DB: Supabase `jarvis-dashboard`
  - Phase1: `vital_snore_daily` / `vital_treatment_events`
  - Phase2: `vital_daily`（Health）
  - Phase3: `vital_journal_daily` / `vital_context_notes`
  - Reviews: `vital_quiet_reviews`（`kind`: `ingest` | `monthly`）
- **診断アプリではない。** 医師に見せるための観察整理。

主観の本線は毎朝の点数入力ではなく、Obsidian `★Journal`（`config/dashboard_lanes.yaml` の `obsidian_journal`）を日付でバイタルと重ねる。欠落・急変には「何がありましたか？」で補完する。観察の主線は **月次レビュー**。

Health 日次（Phase 2・先に確立）: [`docs/Quiet_Edge_ヘルスケアショートカット手順.md`](Quiet_Edge_ヘルスケアショートカット手順.md)  
Journal（Phase 3）は Health 確立後に **launchd 日次同期**で定常化（下記「Phase 3」）。画面の Journal バンド・月次レビューが同データを参照する。

---

## 画面の並び（上から）

| # | ブロック | 説明 |
|---|---|---|
| 1 | **直近レビュー** | 最新の取込 Gemini レビュー（`vital_quiet_reviews` kind=`ingest`）。取込後もここに出る |
| 2 | 推移グラフ | いびきスコア／回数 |
| 3 | 取込・確認フォーム | AutoSnore OCR → 確認 → 取り込む |
| 4 | **月次レビュー** | 既定は**先月**（JST）。対象月の傾向・その前月比較・Journal・注意点（kind=`monthly`）。UI で先月／今月／前後切替可 |
| 5 | KPI・Health（睡眠・SpO2要約）・Journal（睡眠シグナル）・治療 | 経過サマリー。仕事／運動は別ページ |
| 6 | 補完 Ask / 横断 Review | 折りたたみ（必要なときだけ） |
| 7 | **ログ表** | 全記録（長いので末尾） |

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
7. **取り込む** を押す（保存後、**画面最上段**に取込レビューが自動表示）

同じ測定日なら、1枚ずつでも欠けた欄だけ埋まる（upsert）。

### 取込レビュー（自動・最上段）

保存直後に、次を踏まえた短い励ましメモが画面上部に出ます（診断ではない）。DB にも保存されます。

| 参照 | 内容 |
|---|---|
| いびき | 当日スコア／回数、前回比、直近平均、改善目標（≤10） |
| Health | 同日の睡眠・SpO2 等（ingest 済みなら） |
| Journal | 同日の睡眠シグナル／タグ |
| 補完メモ | 「何がありましたか？」の回答 |
| 治療 | 次のレーザー予定 |

Gemini が使えないときはルールベースのフォールバック文を出します。

### 月次レビュー（取込とログのあいだ）

既定の対象月は**先月**（例: 今日が 8/8 なら 2026-07）。画面で先月／今月／前後に切り替え可能。「レビューを作成」で対象月 vs その前月の比較・Journal・注意点をまとめます。日常の「毎日 Ask」よりこちらを優先。

---

## 記録日ルール

- **記録日 = 起床側の暦日**（スコア画面に出る日付）
- 回数画面の「木〜金の間」は **金** に寄せる
- 例: 8/6木 22:45 〜 8/7金 6:02 → `recorded_at = 2026-08-07`

---

## Phase 3（完了）— Journal 本線 + 欠落時の双方向補完

| 段階 | 内容 | 状態 |
|---|---|---|
| 3-MVP | ★Journal を日付キーでいびき・Health と重ね表示（`QuietEdgeJournalBand`） | 完了 |
| 3-Ask | 欠落・急変・Health食い違い・治療日メモ空 →「何がありましたか？」→ `vital_context_notes` | 完了 |
| 3-AI | 横断観察／取込／月次レビューに Journal・補完を注入（診断禁止） | 完了 |
| 任意スケール | 眠気・主観いびき 1〜5（Ask 内の折りたたみ。毎朝必須にしない） | 完了 |

### Journal 同期（Mac）

Vercel はローカル Disk を見ないため、★Journal 抜粋を Supabase に投影する。

```bash
cd ~/git-repos
/Users/matsunomasaharu2/selenium_env/venv/bin/python scripts/jarvis_quiet_edge_journal_sync.py
# 確認だけ
/Users/matsunomasaharu2/selenium_env/venv/bin/python scripts/jarvis_quiet_edge_journal_sync.py --dry-run --days 14
```

- パス: `config/dashboard_lanes.yaml` → `obsidian_journal`（または env `QUIET_EDGE_JOURNAL_DIR` / `JARVIS_LANES_OBSIDIAN_JOURNAL`）
- 秘密: `JARVIS_SUPABASE_URL` + Service Role（`.env.jarvis_private`）
- 画面: `/quiet-edge` の **Journal（睡眠シグナル）** バンド（`QuietEdgeJournalBand`）。取込レビュー・月次レビューも同日 Journal を参照
- sync は業務メモ全文ではなく、防衛線など睡眠関連を優先抽出（`sleep_signal` / `sleep_tags`）

### 定常化（本線: launchd 日次）

ユーザー操作は増やさない。Mac ログイン中なら毎朝自動で投影する。

```bash
# 初回だけ（または Mac 再セットアップ時）
~/git-repos/launchd/install_quiet_edge_journal_sync_launchd.sh
# 解除
~/git-repos/launchd/uninstall_quiet_edge_journal_sync_launchd.sh
```

- Label: `com.matsunoma.jarvis.quiet-edge-journal-sync`
- 時刻: **毎日 08:15**（ローカル）／直近60日 upsert
- ログ: `~/Library/Logs/jarvis_quiet_edge/`

補完: パートナー確認のついでに手動実行してもよい（launchd が止まっているときの保険）。画面に「まだ同期された Journal がありません」と出たら上記 sync を一度走らせる。

---

## 治療ステータス（日次・いびき記録）

グラフ上のマーク。取込フォームの「治療ステータス」で付けるほか、**完了セッションの日程からグラフ用に自動付与**する（当日＝照射日、直後＝+1〜+2日）。フォームで明示した値を優先。

| 値 | いつ付けるか | グラフ色 |
|---|---|---|
| 通常日 | ほとんどの日 | スコア茶／回数藍 |
| 治療当日 | レーザー照射日の睡眠測定 | 赤系＋薄い帯 |
| 治療直後 | 照射後の直近2日 | **マゼンタ系＋薄い帯**（当日と区別） |

---

## 治療スケジュール（回数・次回日）

- **総回数の目安**: 最大 **9回**（経過を見て判断。6回で終わってもよい）
- **正本テーブル**: `vital_treatment_events`
- **更新本線（推奨）**: アプリUI・Journal自動抽出は使わない。月1回程度、チャットで Jarvis に伝える → CLI で反映

伝える例:

- 「今日第4回終わった。次回（第5回）は9/5 15時」
- 「第5回を9月5日に予約した。スケジュール更新して」

Jarvis 実行コマンド:

```bash
cd ~/git-repos
# 一覧
/Users/matsunomasaharu2/selenium_env/venv/bin/python scripts/jarvis_quiet_edge_treatment.py --list

# 実施済み
/Users/matsunomasaharu2/selenium_env/venv/bin/python scripts/jarvis_quiet_edge_treatment.py \
  --done 4 --at 2026-08-08T15:00 --note "第4回完遂"

# 次回日程が決まったとき
/Users/matsunomasaharu2/selenium_env/venv/bin/python scripts/jarvis_quiet_edge_treatment.py \
  --schedule 5 --at 2026-09-05T15:00 --note "診察時に予約"
```

| status | 意味 |
|---|---|
| done | 実施済み |
| scheduled | 日程確定の次回以降 |
| planned | 枠のみ（日程未定） |
| cancelled | 中止 |

**作らないもの**: アプリ内の治療日入力フォーム、Journal からの日程自動読取（不安定・頻度に見合わない）。

---

## 手入力・修正

- スクショなしでもフォームから保存可
- 画面末尾のログ表の日付をクリックすると、上の確認フォームに載る
- 削除は取り消せないので注意

---

## デプロイ前チェック（Vercel）

| 変数 | 用途 |
|---|---|
| `GEMINI_API_KEY` | OCR・観察レビュー |
| `QUIET_EDGE_INGEST_SECRET` | Health ingest API |
| `JARVIS_SUPABASE_*` / Dashboard 用 Supabase | 既存どおり |

Redeploy 後、サイドバー **からだ → Quiet Edge**（仕事・運動は同グループの別項目）。

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
