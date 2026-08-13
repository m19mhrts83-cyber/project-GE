# 融資提出パック（③-D）

KURASHIFT `/realestate/finance-pack` の業務正本。

## 目的

- 物件購入時の銀行提出書類を、常備＋案件で一か所に揃える
- **購入原資**として今後も使う **運転資金・フリーローン・教育ローン** も同じ枠で不足を見える化する
- 個人セット／法人セットを分離。**マイナンバーカードは共通**

## 商品タイプ

| type | 用途 |
|---|---|
| `property_purchase` | 物件本体（オリックス／滋賀等） |
| `working_capital` | 運転資金（名銀・信金・マル経等） |
| `free_loan` | フリーローン（使途確認書類が鍵） |
| `education_loan` | 教育ローン（名銀・住信SBI既存） |

## 名義

| ownership | 内容 |
|---|---|
| `common` | マイナ・免許・保険証・既存借入一覧 |
| `personal` | 源泉・個人確定申告・住民票など |
| `corporate` | 登記・定款・決算・代表者個人サブ枠 |

## フォルダ規約（OneDrive）

```
240_融資/finance_packs/{YYYYMM}_{物件or商品}_{銀行}/
  00_共通/
  01_個人/  または  01_法人/（代表者個人/）
  02_収入税務/
  03_既存借入/
  04_資産/
  05_物件または使途根拠/
  06_取引契約/
  07_銀行固有/
  08_送信控え/
```

実物の流用: `243_カードローン書類/`、`241_融資審査/`、過去の `10_【購入】物件購入,融資/`。

## カタログ正本

- YAML: [`config/kurashift_re_finance_doc_templates.yaml`](../config/kurashift_re_finance_doc_templates.yaml)
- アプリ写し: `apps/trade-desk/lib/financePackCatalog.ts`
- UI の状態（チェック）はブラウザ localStorage（端末ローカル）

## メール

画面の「メール下書きをコピー」は **送信しない**。対外送信は確認後のみ（`jarvis-outbound-confirm`）。

## 関連

- 合算金利: [`KURASHIFT_loan_tracker_Discover.md`](KURASHIFT_loan_tracker_Discover.md) §B-RATE-4
- 物件マスタ: `config/kurashift_re_property_master.yaml`
- 借入投影: `scripts/jarvis_kurashift_loan_tracker_sync.py`
