# 借入残高トラッカー — 項目確定版（2026-08-13）

アプリ URL: https://loan-tracker-plum.vercel.app/  
Google アカウント（正）: **estate** `matsuno.estate@gmail.com`

## 方針（変更なし）

- **正本** = 借入残高トラッカー（estate）
- KURASHIFT は **二重入力しない・読取投影のみ**（`kurashift_loan_tracker_loans`）
- トラッカーへの書込はしない
- Drive 勝手探索はしない（データ投入前）。投入後の第一候補は **JSON/CSV 書き出し → `LOAN_TRACKER_JSON_PATH`**

## Step0 確定フィールド（必須）

| 項目 | JSON / DB キー | なぜ |
|---|---|---|
| 物件／担保名 | `name` | ③-C 突合 |
| 名義（個人／法人） | `tags` に `個人`/`法人`、任意 `borrower` | 合算・融資パック |
| 銀行・支店 | `lender` | 融資パック・金利比較 |
| 残高 | `balance` → `balance_jpy` | CF・正味 |
| 金利（%） | `rate` → `rate_pct` | B-RATE-4 |
| 毎月返済（元利） | `monthlyPayment` → `monthly_payment_jpy` | 定常CF |
| 残期間／終了予定 | `payoffDate` → `payoff_date` | 借換え判断 |
| 団体信用生命の有無 | `groupCreditLife`（payload） | メモ |
| 更新日 | `asOf` / `synced_at` | 鮮度 |

任意: `principal`（当初借入額）・`startDate`（実行日）・`rateType`・`propertyId`（`grandole-i` 等）・`note`・返済表パス。

## 受け皿

| 役割 | 場所 |
|---|---|
| 投影表 | `kurashift_loan_tracker_loans` |
| 同期 | `re_sync_loan_tracker` → `scripts/jarvis_kurashift_loan_tracker_sync.py` |
| UI | `/realestate/properties` ローン投影・`/realestate` B-RATE-4 |
| 洗い出し表 | [`docs/KURASHIFT_loan_inventory.md`](KURASHIFT_loan_inventory.md) |
| JSON エクスポート（同期用） | OneDrive `240_融資/loan_tracker_export/loans.json`（`LOAN_TRACKER_JSON_PATH`） |

## 接続手順（定常）

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
# 1) トラッカー画面で更新したら JSON を export して loans.json を上書き（または同じパスへ保存）
# 2) 投影
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_loan_tracker_sync.py --dry-run
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_loan_tracker_sync.py --apply
```

`LOAN_TRACKER_JSON_PATH` が無い／ファイルが無いときだけ Drive・`/api/data` を試す（失敗時は blocker を返す）。

## 運用（正本）

- **更新タイミング**: 月末、または金利改定・繰上返済の直後
- **更新場所**: loan-tracker（estate）→ JSON を `240_融資/loan_tracker_export/loans.json` に保存 → `--apply`
- 初回シード（2026-08-13）: 洗い出し JSON を同パスに配置済み。トラッカー画面へ同じ3本を転記したら、以降は画面→JSON を正とする

## 現行 RE ローン（洗い出し確定・3本）

詳細・根拠パスは [`KURASHIFT_loan_inventory.md`](KURASHIFT_loan_inventory.md)。

1. GrandoleⅠ — オリックス・**法人** — 残高約 5,981 万・2.65%・月 262,928
2. GrandoleⅡ — オリックス・**個人** — 残高約 5,932 万・3.50%・月 300,746
3. キャラメル — 滋賀銀ジャストサポート（セゾンF）・**個人** — 残高約 4,450 万・2.55%・月 178,976（＋諸費用ローンは別行）
