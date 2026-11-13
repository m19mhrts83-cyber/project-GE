---
name: purchase-asset-evidence
description: >-
  不動産購入・融資・業者提出向けに、借入残債トラッカーと金融資産（銀行・保険・証券・外国債）の
  残高画面スクショを収集し、パートナー送信下書きにまとめる。
  Use when the user runs /purchase-asset-evidence, or asks for 金融資産スクショ、残債キャプチャ、
  資産証明、借入残高エビデンス、2,000万証明、購入時の必要書類（金融資産）、残高チェッカー画面保存。
---

# 購入時・金融資産／残債エビデンス収集

リリーフコミット専用ではない。**物件購入・融資・業者提出で「残債＋金融資産の画面証拠」が要るとき全般**で使う。

## 入口・確認・履歴・停止

| 柱 | 内容 |
|---|---|
| **入口** | 先方の必要書類一覧／パートナーフォルダ／`.env.jarvis_private`／`loans.json`／各社マイページ |
| **確認** | キャプチャ目視＋**対外送信は松野了承必須**（`jarvis-outbound-confirm`） |
| **履歴** | パートナー `5.やり取り.md`・必要なら Todoist コメント |
| **停止** | OTP不能・メンテ・名義不明・ログインID無しは **スキップして報告**。Zaim代用を先方向けに送らない |

## 呼び出し

- スラッシュ: **`/purchase-asset-evidence`**
- 言い回し例: 「金融資産のスクショ取って」「残債と資産証明まとめて」「購入書類の資産エビデンス」

最初に1行で確定（分かるなら省略可）:

- **宛先パートナー**（例: `P424_リリーフコミット`）または保存先パス
- **目的**（例: 金融資産2,000万以上＋借入残債）
- **同梱**（税務PDFなど既存添付があるか／今回はスクショのみか）
- **送信**（下書きのみ／了承後送信）

## 成果物の置き方

```
{パートナー}/3.送信添付/
  （既存の税務PDF等はそのまま）
  YYYY-MM-DD_金融資産スクショ/
    05_借入残債_残高トラッカー.png
    10_銀行_*.png
    20_保険_*.png
    30_証券_SBIインデックス_*.png
    31_証券_Bloomo_*.png
    40_外国債_あかつき_*.png
    _提出用一覧.txt
    _skip_内部用/          # 失敗・スキップ画面（送付しない）
  4.送信下書き.txt（親フォルダ正本＋ここへ同期可）
```

撮影日・名義が画面上で読めるページを優先。パスワード／OTP／口座フル番号はチャットに出さない。

## 実行順（止まず）

### 0. 出力フォルダ

`3.送信添付/YYYY-MM-DD_金融資産スクショ/` を作成（JST）。

### 1. 借入残債（先に1枚）

- 正本UI: https://loan-tracker-plum.vercel.app/（イマザン／残高チェッカー）
- ログインできないときは OneDrive `240_融資/loan_tracker_export/loans.json` を HTML→PNG で代替可（オーケストレータ本線）
- 銀行IBのローン明細は取らない（トラッカー1枚で足りる）

### 2. 銀行（ログイン可能分を全部）

秘密は `source .env.jarvis_private` のみ。OTP／合言葉は既存経路。失敗時だけ人手。

| 優先 | 口座 | キー目安 |
|---|---|---|
| 必須寄り | PayPay銀行（法人） | `PAYPAY_*` |
| 必須寄り | ドコモSMTB／第一生命NEOBANK | `SBI_NET_*` |
| 必須寄り | 滋賀銀行 IB | `SHIGA_IB_*`・`config/kurashift_ib_shiga.yaml` |
| できれば | Olive／SMBC銀行 | 銀行ログインIDが無いならスキップ明記 |
| できれば | 三菱UFJ | あんしんパス要ならスキップ |
| できれば | 京都銀行 IB | `KYOTO_IB_*`・契約なしエラーならスキップ |
| できれば | 名古屋銀行 | Web IBが無いならスキップ |

Zaim残高だけの代用スクショは**送付しない**。

### 3. 保険

| 対象 | 手段 |
|---|---|
| アクサ | `jarvis_axa_balance.py`（headed／debug PNG を提出名へ） |
| ソニー | お客さまWEB。停止中なら停止理由＋直近成功スクショ。捏造しない |
| プルデンシャル | マイページ可ならスクショ。不可なら `PRUDENTIAL_*_VALUE_JPY` メモ画像＋差し替え推奨と明記 |

### 4. 証券・外国債

| 対象 | 手段 |
|---|---|
| SBIインデックス（本線） | `jarvis_sbi_index_balance.py`。ログイン失敗時は週次Zaim由来の保有HTML→PNG可（出所を画面に書く） |
| Bloomo（補強） | `jarvis_mf_bloomo_balance.py` |
| あかつき外国債 | `215_kamiooya/.../finance` のあかつき残高スクリプト（OTPは「今回送信以降」） |

### 5. オーケストレータ（推奨）

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
OUT='…/3.送信添付/YYYY-MM-DD_金融資産スクショ'
~/selenium_env/venv/bin/python scripts/jarvis_purchase_asset_evidence.py \
  --out "$OUT" --only all
# 一部だけ: --only loan,paypay,sbi_net,axa,sbi_sec,bloomo,akatsuki,sony,prudential
```

終わったら `_capture_summary.json` と収集表をチャットへ。

### 6. 下書き（1通まとめが既定）

`4.送信下書き.txt` を更新:

- 税務等の既存添付＋金融資産スクショ＋借入残債を**1通**に書く
- 「別途送ります」は残さない（今回同梱する方針のとき）
- `README.md`・`5.やり取り.md` を同期追記

### 7. 送信プレビュー → 了承まで停止

チャットに To／件名／本文要点／添付一覧／下書きパス → 文面点検 → **「これで送ってOK？」**  
了承後のみ 311ゲート → `yoritoori_send.py`（`--via` は推測しない）。

## やらないこと

- 了承前の対外送信
- 秘密・OTPのチャット再掲
- あかつき／SBIの売買・設定変更
- 残債を銀行ごとに取り直す
- スキップ画面を提出用に混ぜる（`_skip_内部用/` へ）

## 追加リソース

- 口座別の既知の詰まり・代替: [reference.md](reference.md)
- 自動化ロードマップ: [reference.md](reference.md)「自動化」
