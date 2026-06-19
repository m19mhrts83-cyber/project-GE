# tax_docs_tools

税理士提出用資料の後処理・ブラウザ自動化スクリプト置き場。

## ダウンロード後の後処理（ログインなし）

| スクリプト | 役割 |
|------------|------|
| `amex_statement_postprocess.py` | AMEX の Excel（既定名 `activity.xlsx` 等）／CSV／PDF を四半期フォルダへ移動・リネーム |
| `orix_repayment_pdf_postprocess.py` | オリックス銀行 **返済実績表 PDF** を読み、**表に載っている最新月**に合わせて `返済実績表_G1_….pdf` へコピー・命名（`requirements.txt` に `pypdf`） |
| `amex_activity_classify.py` | `preview` / `finalize` / `export-tagged`（費目あり行だけ残す） |
| `vpass_csv_classify.py` | Vpass CSV → 費目付き xlsx（AMEX と共通ルール） |
| `amex_himoku_rules.example.json` | 費目ルールのテンプレート（`exclude_row_substrings` / `himoku_rules`） |

## ブラウザ自動化（Playwright）

| スクリプト | 役割 |
|------------|------|
| `paypay_bank_statement.py` | PayPay銀行（法人）にログインし、指定期間の取引明細 PDF をダウンロード → リネーム・配置 |
| `minitech_statement.py` | ミニテック・オーナーマイページにログインし、送金のご案内 PDF をダウンロード → リネーム・配置 |
| `leaf_kurasapo_statement.py` | LEAF・くらさぽコネクトにログインし、送金明細書 PDF をダウンロード → リネーム・配置 |
| `mykomon_upload.py` | MyKomon（税理士共有フォルダ）にログインし、指定の分類フォルダへファイルをアップロード |
| `orix_bank_statement.py` | オリックス銀行にログインし、**法人契約**の返済実績表 PDF を期間指定でダウンロード |
| `amex_statement.py` | AMEX マイアカウントにログインし、全カード分の利用履歴 Excel（activity.xlsx）を期間指定でダウンロード |
| `tax_submit_paypay.py` | PayPay取得 → MyKomonアップロードの一括オーケストレーター |
| `tax_submit_minitech.py` | ミニテック取得 → MyKomon 02_賃貸収入 アップロードの一括オーケストレーター |
| `tax_submit_orix.py` | オリックス（法人）取得 → リネーム → MyKomon 05_借入金 アップロードの一括オーケストレーター |
| `tax_submit_amex.py` | AMEX取得 → 全カード結合 → 費目仕分け → MyKomon 07_クレカ アップロード（2段運用） |
| `mykomon_audit.py` | **【読み取り専用】** MyKomon を期間横断で走査し、毎月必須4種目（PayPay/ミニテック/オリックス/クレカ）の月次カバレッジを検証して抜け漏れを報告（年次・最終チェック用） |

### 初回セットアップ（ブラウザ自動化）

```bash
# selenium_env の venv に Playwright をインストール
~/selenium_env/venv/bin/pip install -r requirements.txt
~/selenium_env/venv/bin/playwright install chromium

# 認証情報を設定
cp .env.tax_docs.example .env.tax_docs
# .env.tax_docs を編集して PayPay / MyKomon / ミニテック / オリックス / AMEX の認証情報を入力
```

### 使い方

```bash
cd ~/git-repos/215_kamiooya/C1_cursor/tax_docs_tools
PY=~/selenium_env/venv/bin/python

# PayPay銀行 — 単月の明細 PDF を取得
$PY paypay_bank_statement.py \
  --start-date 2025-06-01 --end-date 2025-06-30 \
  --output-dir ".../00_元ファイル_サイト取得/PayPay銀行/" \
  --output-name "PayPay銀行明細_6月.pdf"

# MyKomon — ファイルを指定フォルダにアップロード
$PY mykomon_upload.py \
  --file ".../PayPay銀行明細_6月.pdf" \
  --year "2025年（令和7年）" --quarter "②4-6月" \
  --category "01_預金通帳のコピー"

# 一括実行（PayPay → MyKomon）
$PY tax_submit_paypay.py \
  --months 2025-06,2026-05 \
  --materials-root ".../2.経費,売上資料"

# ミニテック — 送金のご案内 PDF を取得
$PY minitech_statement.py \
  --months 2025-07,2025-08,2025-09 \
  --output-dir ".../00_元ファイル_サイト取得/ミニテック/"

# LEAF（くらさぽコネクト）— 送金明細書 PDF を取得（最新 1 件）
$PY leaf_kurasapo_statement.py \
  --latest \
  --output-dir ".../516_名古屋銀行/3.送信添付/" \
  --headless --no-pause

# 一括実行（ミニテック → MyKomon 02_賃貸収入）
$PY tax_submit_minitech.py \
  --months 2025-07,2025-08,2025-09 \
  --materials-root ".../2.経費,売上資料"

# オリックス銀行 — 返済実績表 PDF を取得（既定: 法人契約・期間指定）
$PY orix_bank_statement.py \
  --start-month 2025-06 --end-month 2025-06 \
  --group G1 \
  --output-dir ".../00_元ファイル_サイト取得/オリックス銀行_借入/"

# 一括実行（オリックス取得 → リネーム → MyKomon 05_借入金）
$PY tax_submit_orix.py \
  --start-month 2025-06 --end-month 2025-06 \
  --group G1 \
  --materials-root ".../2.経費,売上資料"

# AMEX — 利用履歴 Excel を取得（全カード・期間指定）
$PY amex_statement.py \
  --start-date 2025-06-01 --end-date 2025-06-30 \
  --output-dir ".../2025/6月/00_元ファイル_サイト取得/AMEX/"

# 一括実行（AMEX 欠落分 → 費目付与 → 空欄報告で停止＝フェーズA）
$PY tax_submit_amex.py \
  --periods missing-2025-06-2026-05 \
  --materials-root ".../2.経費,売上資料" \
  --headless

# 空欄確認後（フェーズB: export-tagged → MyKomon 07_クレカ/取引が全て経費のもの）
$PY tax_submit_amex.py \
  --periods missing-2025-06-2026-05 \
  --materials-root ".../2.経費,売上資料" \
  --finalize-upload \
  --headless

# MyKomon 抜け漏れチェック（年次・最終チェック / 読み取り専用）
#   5月決算のため毎年「6月〜翌5月」で確認する。
$PY mykomon_audit.py \
  --start-month 2025-06 --end-month 2026-05 \
  --headless
#   → カバレッジ表と欠落一覧をコンソールに出力し、
#     OneDrive の 2.経費,売上資料/_チェック/ にレポート(.md)を保存。
#     欠落分は上の tax_submit_* で再抽出する。
```

### MyKomon 抜け漏れチェックの運用（年次）

- **決算月は5月**。毎年「6月〜翌5月」の12ヶ月サイクルで `--start-month` / `--end-month` を渡す。
  - 2025年度: `--start-month 2025-06 --end-month 2026-05`
  - 2026年度: `--start-month 2026-06 --end-month 2027-05`（以降同様）
- 判定対象（毎月必須）: **PayPay銀行明細 / ミニテック送金のご案内 / オリックス返済実績表 / AMEX / Vpass**。
- 年度フォルダ（例: `2025年（令和7年）`）は暦年単位のため、6月〜翌5月は2フォルダにまたがる。期間からツール側が訪問先（年度×四半期）を自動算出する。
- ファイル名から月を解釈（単月 / 同年レンジ `7月〜9月` / 年跨ぎ `10月〜2026.3月` / Vpass `202510-202604`）。年がファイル名に無い場合は**フォルダの暦年**で補完する。
- レポートには「カバレッジ表」「欠落（再抽出コマンド併記）」「検出ファイル（系列別）」「その他ファイル（未分類）」を含む。命名が異なるファイル（例: `6月集金.pdf`）は未分類に出るので、内容に応じて系列設定 `match` を調整するか手動確認する。
- 種目・系列を変えたいときは内蔵設定を編集するか、`--config <JSON>` で上書きする。

### AMEX 提出の運用（2段）

1. **フェーズA**（`tax_submit_amex.py` 既定）: サイトから全カード分を取得 → 結合 → `amex_himoku_rules.json` で費目付与 → **空欄行を報告して停止**
2. 空欄行を確認し、必要ならルール JSON を追記
3. **フェーズB**（`--finalize-upload`）: `export-tagged` で費目あり行のみに絞り → MyKomon `07_クレジットカード明細/取引が全て経費のもの` へアップロード

チャットで確認しながら仕分けする手順（正本・業務メモ）:  
`50_税金…/2.経費,売上資料/税理士提出_手順書/手順_AMEX_費目仕分け_チャット運用.md`

運用コマンドの正本: `~/git-repos/docs/運用コマンド一覧.md` セクション 10。
