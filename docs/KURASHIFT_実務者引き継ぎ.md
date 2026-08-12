# KURASHIFT 実務者引き継ぎ（2026-08-13）

次の実務者（自分／Jarvis／人間）が **止まらず再開**するための正本。  
プランファイルが複数あるため、**この1枚を入口**にする。

本番: https://jarvis-trade-desk.vercel.app/  
リポ: `~/git-repos`（アプリ `apps/trade-desk`）  
DB: Supabase **`jarvis-dashboard`**（`JARVIS_SUPABASE_*`）

---

## 1. プラン地図（どれが生きているか）

| プランファイル | 役割 | 状態 |
|---|---|---|
| [`ライフプランhq再整理_c37d6392.plan.md`](~/.cursor/plans/ライフプランhq再整理_c37d6392.plan.md) | **本線**（①②③の骨格） | 大半完了。残は③-A〜D実装・verification・Lab立花 |
| [`kurashift実務検証_fbf4058e.plan.md`](~/.cursor/plans/kurashift実務検証_fbf4058e.plan.md) | Sprint1検証＋Sprint2買い進めOS | **To-do 完了**。成果は本番＋DBに反映済 |
| [`kurashift改善プラン_86acd2ee.plan.md`](~/.cursor/plans/kurashift改善プラン_86acd2ee.plan.md) | QAゲート仕様 | Phase A 実装済（frontmatter は要同期）。Phase B/C は未 |
| [`kurashift_hq_overview_e49b0cea.plan.md`](~/.cursor/plans/kurashift_hq_overview_e49b0cea.plan.md) | HQ俯瞰 | **完了** |
| [`trade_desk_方向再編_9c87a14e.plan.md`](~/.cursor/plans/trade_desk_方向再編_9c87a14e.plan.md) | 旧議論 | **cancelled（吸収済み）**。再開しない |

---

## 2. いま動いているもの（DONE）

- ホーム: データ鮮度（`sync_meta`）／いまやること／一部未取得
- ②: `/lifeplan` 年次・Zaim本番 confirm／`/tax` 手動取込・ドラフト
- ③: CF月50万 KPI、Bridge 19CF、loan-tracker リンク
- ③-A: 個人 YTD（Zaim 19系）＋法人カテゴリ参考表示（合算は未承認）
- ③-B: `/realestate/deals` 千三つ、メール候補、WeStudy助言、運営経緯
- ③-C: `/realestate/properties` 号室一覧（Phase1）
- ③-D: `/realestate/finance-pack` チェックリスト骨格
- 買い進め Excel: ingest（7版）／STEP3 export（OneDrive `05_…/exports/`）
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
| `re_sync_loan_tracker` | `jarvis_kurashift_loan_tracker_sync.py` | **現状は意図的に失敗**（未配線） |

ワーカー起動:

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_job_worker.py --once
```

コマンド正本: `docs/運用コマンド一覧.md` §7.6

---

## 3. 残バックログ（優先順・次の実務者がやる順）

### P0（信頼・日次で触る）

1. **ソニー週次フル成功** — 日中に  
   `python scripts/jarvis_portfolio_weekly.py --force`  
   （深夜はサービス時間外。検出は実装済）
2. **ダッシュボードPW** — 既に Rotate 済。正本は `.env.jarvis_private` のみ

### P1（③を実務レベルへ）

3. **loan-tracker 本接続** — Discover 済（データは estate Drive の専用ファイル。画面からは ID が取れない）。投影表は作成済。残は JSON パス or Drive OAuth or ログイン済み `/api/data`
4. **③-A 個人YTD** — ✅ Zaim カテゴリ年次
5. **③-A 法人＋合算** — ✅ 顧客承認により合算 KPI に投入（2026-08-13）
6. **メール候補** — ✅ スコア5以上を内見（詳細取り寄せ〜日程調整）

### P2（拡張）

7. 健美家／楽待（Sprint3）
8. `/realestate/properties` — ✅ Phase1 一覧（号室）。編集・loan突合は残
9. `/realestate/finance-pack` — ✅ チェックリスト骨格。PDF/状態保存は残
10. Excel STEP3 **完全互換** export（現状は骨格）
11. Lab 立花実弾（口座・鍵後）
12. 本線プランの verification-with-user（ユーザー同席）

---

## 4. 境界（絶対に崩さない）

- 未承認の実弾売買・自動振替・弥生本登録・Zaim本番（confirm なし）は禁止
- 秘密は `.env.jarvis_private` のみ（チャット・Git・ジョブログに値を出さない）
- Supabase Free は `kamiooya-qa` と `jarvis-dashboard` の2本まで
- ローン正本は [借入残高トラッカー](https://loan-tracker-plum.vercel.app/)（Google: **estate**）。KURASHIFT は読取投影のみ
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
