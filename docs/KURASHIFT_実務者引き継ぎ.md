# KURASHIFT 実務者引き継ぎ（2026-08-13）

次の実務者（自分／Jarvis／人間）が **止まらず再開**するための正本。  
プランファイルが複数あるため、**この1枚を入口**にする。

本番: https://jarvis-trade-desk.vercel.app/  
リポ: `~/git-repos`（アプリ `apps/trade-desk`）  
DB: Supabase **`jarvis-dashboard`**（`JARVIS_SUPABASE_*`）

### いま最初に読む（QA 2026-08-13）

| 文書 | 用途 |
|---|---|
| [`KURASHIFT_残ToDo一覧_タブ整理_20260813.md`](./KURASHIFT_残ToDo一覧_タブ整理_20260813.md) | **残 ToDo・生きている1 plan・アーカイブ索引（タブ整理の正）** |
| [`KURASHIFT_plan棚卸し_20260813.md`](./KURASHIFT_plan棚卸し_20260813.md) | plan 全本線の done/pending 棚卸し経緯 |
| [`KURASHIFT_通し検証ログ_20260813.md`](./KURASHIFT_通し検証ログ_20260813.md) | 通し検証（煙＋DB済／目視脇置き） |
| [`KURASHIFT_品質保証点検ログ_20260813.md`](./KURASHIFT_品質保証点検ログ_20260813.md) | Wave0 合否・P1/P2・実務者タスク順 |
| [`KURASHIFT_品質保証点検_実行プラン_20260813.md`](./KURASHIFT_品質保証点検_実行プラン_20260813.md) | Wave 定義・「満足」の定義 |

**QA 要約**: ③-A〜D 骨格は条件付き合格・**P0 なし**。本線全満足は未宣言（目視通し・V-2-UI・案件1件が残）。

**実務実装（同日）**: P1＋RE-1b＋買い進めCF年次プロット＋借入トラッカー導線を本番反映済。

**残 ToDo**: [`KURASHIFT_残ToDo一覧_タブ整理_20260813.md`](./KURASHIFT_残ToDo一覧_タブ整理_20260813.md) を正。Cursor は **生きている1本**（`kurashift残バックログ_20260813.plan.md`）だけ開く。旧本線 plan は `_archive/kurashift/`（タブは閉じてよい）。**2026-08-13: 本線6 ID 完了**（検証ログ参照）。

再開チェックリストから「verification-with-user（ユーザー同席）」は完了扱いで外してよい。

---

## 1. プラン地図（どれが生きているか）

| プラン | 役割 | 状態 |
|---|---|---|
| [`kurashift残バックログ_20260813.plan.md`](/Users/matsunomasaharu2/.cursor/plans/kurashift残バックログ_20260813.plan.md) | **生きている1本**（残6 todo → 2026-08-13 完了） | docs 残一覧と同期。plan frontmatter は手元で completed にしてよい |
| `~/.cursor/plans/_archive/kurashift/*`（9本） | 本線の経緯・完了履歴 | **ARCHIVED**（読取専用）。索引は残 ToDo 一覧 |

旧パス（HQ／買い進め／QA／改善／CFプロット／融資／実務検証／overview／trade_desk 方向再編）はすべてアーカイブへ移動済み。新しい作業の todo は生きている1本にだけ足す。

---

## 2. いま動いているもの（DONE）

- ホーム: データ鮮度（`sync_meta`）／いまやること／一部未取得
- ②: `/lifeplan` 年次・Zaim本番 confirm／`/tax` 手動取込・ドラフト
- 資金移動: `/money-ops` — **カード引落バッファ**プレイブック（2026-08-14）。正本 `docs/KURASHIFT_資金移動_カード引落バッファ_検討素案_20260814.md`。自動振込なし
- ③: CF月50万 KPI、Bridge 19CF、loan-tracker リンク、**レーンナビ A〜D**
- ③-A: `/realestate` — 個人／法人／合算 KPI、簡易 DSCR、YTD CF、B-RATE＋DSCR（**年計画バーは未**）
- ③-B: `/realestate/buy-plan`（長期年表・Focus）＋ `/realestate/deals`（千三つ実行）
- ③-C: `/realestate/properties` — 号室・RR合計 vs 月返済・合算金利・DSCR
- ③-D: `/realestate/finance-pack` — 物件／運転／フリー／教育 × 個人／法人、マイナ共通、コピーのみ（送信なし）
- loan-tracker: OneDrive `240_融資/loan_tracker_export/loans.json` → `jarvis_kurashift_loan_tracker_sync.py --apply` で投影（**二重入力しない**）
- B-RATE-4b: 残高加重合算金利（キャラメル目安 ≈2.55%）
- 買い進め Excel: ingest／STEP3 export
- 履歴: lifeplan `.numbers` + Zaim → `kurashift_lifeplan_*` / `kurashift_finance_*`
- Mac worker: 買い進め系ジョブ配線済（下表）

### ジョブ（アプリ → Mac worker）

| job_type | スクリプト | 危険度 |
|---|---|---|
| `buy_plan_ingest` | `jarvis_kurashift_buy_plan_ingest.py` | 低 |
| `buy_plan_export` | `jarvis_kurashift_buy_plan_export.py` | 低 |
| `re_mail_match` | `jarvis_kurashift_property_mail_match.py --apply` | 低（送信なし） |
| `re_deal_advice` | `jarvis_kurashift_deal_advice.py --apply` | 低 |
| `ops_consult_ingest` | `jarvis_kurashift_ops_consult_ingest.py` | 低 |
| `re_sync_loan_tracker` | `jarvis_kurashift_loan_tracker_sync.py` | **JSON 経路で接続済**（`LOAN_TRACKER_JSON_PATH` / `240_融資/loan_tracker_export/loans.json`）。estate でトラッカー画面投入後は export で上書き |

ワーカー起動:

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_job_worker.py --once
```

コマンド正本: `docs/運用コマンド一覧.md` §7.6

---

## 3. 残バックログ（優先順・次の実務者がやる順）

### P0（信頼・日次で触る）

1. **ソニー／アクサ週次** — 時間外は **skipped**（フル成功にはしない）。本線は日曜 **09:10**。  
   `python scripts/jarvis_portfolio_weekly.py --force`  
   （ソニー 9:00–17:30・バッチ後半、アクサは 5:00–8:00 メンテ）
2. **ダッシュボードPW** — 既に Rotate 済。正本は `.env.jarvis_private` のみ

### P1（③を実務レベルへ・QA後）

3. **ログイン補完** — QA ログ §5（数値目視・キャラメル 2.55%／DSCR）
4. **DOC 同期** — 検証プラン「いまの位置」を ③現行到達に（QA DOC-STALE-1）
5. **③-A 年計画 vs YTD** — Wave2 RE-1b（未）
6. **③-B 案件1件** — draft→内見通し（Wave2）
7. **P1 UX** — C の DSCR 注記／年表 action 日本語化（QA ログ）
8. **③-A 個人YTD** — ✅　**法人＋合算** — ✅　**メール候補** — ✅

### P2（拡張）

9. 健美家／楽待（Sprint3・任意）
10. 融資パック: localStorage 以外の案件保存・PDF
11. Excel STEP3 **完全互換** export（現状は骨格）
12. YAML↔`financePackCatalog.ts` ドリフト防止
13. Lab 立花実弾（口座・鍵後・明示解錠のみ。現状はゲート掲示のみ）

（旧「verification-with-user」は 2026-08-13 完了）

---

## 4. 境界（絶対に崩さない）

- 未承認の実弾売買・自動振替・弥生本登録・Zaim本番（confirm なし）は禁止
- 秘密は `.env.jarvis_private` のみ（チャット・Git・ジョブログに値を出さない）
- Supabase Free は `kamiooya-qa` と `jarvis-dashboard` の2本まで
- ローン正本は [借入残高トラッカー](https://loan-tracker-plum.vercel.app/)（Google: **estate**）を使い始めたら読取投影。**現状は未使用**（中身まとめ待ち）
- 物件問い合わせの対外送信は **送信前確認必須**

---

## 5. ログイン・アカウント

| 用途 | アカウント |
|---|---|
| KURASHIFT / Jarvis ダッシュボード | `JARVIS_DASHBOARD_LOGIN_EMAIL` |
| 物件メール主走査 | **admin** `token_livingsupport.json` |
| 物件メール補完・loan-tracker Google | **estate** |
| WeStudy スクレイプ知識 | admin Drive `215_神大家_WeStudyスクレイプ/` |

---

## 6. 再開チェックリスト（5分）

1. https://jarvis-trade-desk.vercel.app/ ログイン → 鮮度・③CFギャップ
2. `/realestate/deals` → ファネル件数・助言列
3. Mac: worker `--once` が動くか
4. `docs/KURASHIFT_検証プラン.md` 受け入れ表を見る
5. このファイルの §3 の先頭から着手

---

## 7. 関連ドキュメント

- `docs/Trade_Desk.md` — 製品ハブ
- `docs/KURASHIFT_不動産賃貸経営.md` — ③設計
- `docs/KURASHIFT_買い進めJob仕様.md` — 千三つ
- `docs/KURASHIFT_CF正規化メモ.md` — CF定義
- `docs/KURASHIFT_loan_tracker_Discover.md` — ローン同期ブロッカー
- `docs/KURASHIFT_検証プラン.md` — 受け入れ記録
- `docs/KURASHIFT_改善ロードマップ.md` — ロードマップ

---

## 8. 直近コミット（参照）

- `58feaed` docs Sprint2 受け入れ
- `43440ac` メール候補・助言・export
- `d911eda` Sprint2 骨格
- `12140b8` Sprint1 締め＋ソニー時間外
- `a3c2a04` QAゲート（鮮度・Zaim confirm・証憑手動）
