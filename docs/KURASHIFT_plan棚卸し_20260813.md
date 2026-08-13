# KURASHIFT plan 棚卸し結果（2026-08-13）

方針: 推奨順で全本線 plan を1周し、todo を **done / pending（未・部分の残）/ cancelled / 検証後バックログ** に同期した。  
入口: [`KURASHIFT_実務者引き継ぎ.md`](./KURASHIFT_実務者引き継ぎ.md)

---

## 回した順と判定

| # | プラン | 結果 |
|---|---|---|
| 1 | `ライフプランhq再整理_c37d6392` | **24 completed / 3 pending** |
| 2 | `買い進め長期レーン_77a6bd3e` | **6 completed / 1 pending**（検証後モードを追加） |
| 3 | `融資提出パック設計_74653333` | **5/5 completed** |
| 4 | `qa実行プラン整理_b3b4e68d` | **4 completed / 1 pending**（Wave2 を過大完了から戻した） |
| 5 | `kurashift改善プラン_86acd2ee` | **4 completed / 1 pending** |
| 6 | `kurashift実務検証_fbf4058e` | **9/9 completed**（突合OK） |
| — | `kurashift_hq_overview_e49b0cea` | **7/7 completed**（確認のみ） |
| — | `trade_desk_方向再編_9c87a14e` | **全 cancelled（吸収済）**・再開しない |

---

## いま残っている pending（本線）

### すぐ次（通し検証）

| ID | プラン | 内容 |
|---|---|---|
| `verification-with-user` | HQ再整理 | ①資産／②LP・税／③不動産の通し検証 |
| `wave2-re1` | QA実行 | V-2-UI（`/lifeplan` `/roi` `/tax`）・案件1件 draft→内見（RE-1bは済） |

### 検証後でもよい実装残

| ID | プラン | 内容 |
|---|---|---|
| `re-a-plan-revise` | HQ再整理 | 計画補正ジョブ（dry-run→承認→Numbers/DB） |
| **`buy-plan-revise-modes`** | 買い進め長期 | **年1実績反映／Excel改訂→運営相談モード**（現状は読取・評価のみ）。ユーザー指摘どおり検証後に追加 |
| `phase-c-diff` | 改善プラン | Next Action深化・健美家等・スマホ承認 |

### 本線と分離（Lab）

| ID | 内容 |
|---|---|
| `lab-tachibana-gated` | 立花 API・少額実弾 |

---

## #1 HQ で今回「到達」に上げたもの

- `re-a-plan-vs-actual-personal` … RE-1b 年計画 vs YTD バー
- `re-a-corporate-ingest` … 法人／合算 KPI
- `re-c-property-master` … 物件マスタ＋loan-tracker
- `re-d-finance-pack` … 融資パック

## #2 買い進めで今回閉じたもの

- `deals-slim` / `hub-tidy` / `docs-update` → completed  
- **新規** `buy-plan-revise-modes` → pending（検証後）

## ユーザーメモ（検証後）

買い進めプランは「現状プランの読込・評価」はできるが、次のモードは未対応:

1. **年1回ペースで実績をプランに反映**
2. **考えを変えて Excel を直し、運営に相談する**

→ `buy-plan-revise-modes` に登録済み。通し検証のあとに設計・実装する。

---

## 次の一手

1. ~~**通し検証**~~ → 煙＋DB完了（`docs/KURASHIFT_通し検証ログ_20260813.md`）。ログイン目視は脇置き  
2. ~~不動産 CF 年次プロット~~ → `/realestate/buy-plan` 実装・本番反映（2026-08-13）  
3. **残 ToDo の正本（タブ整理）**: [`KURASHIFT_残ToDo一覧_タブ整理_20260813.md`](./KURASHIFT_残ToDo一覧_タブ整理_20260813.md)  
4. 検証後に `buy-plan-revise-modes` と `re-a-plan-revise` を優先順位付け
