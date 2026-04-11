# tax_docs_tools

税理士提出用資料のうち、**手動でダウンロードしたあと**に効く小さなスクリプト置き場。

| スクリプト | 役割 |
|------------|------|
| `amex_statement_postprocess.py` | AMEX の Excel（既定名 `activity.xlsx` 等）／CSV／PDF を四半期フォルダへ移動・リネーム |
| `orix_repayment_pdf_postprocess.py` | オリックス銀行 **返済実績表 PDF** を読み、**表に載っている最新月**に合わせて `返済実績表_G1_….pdf` へコピー・命名（`requirements.txt` に `pypdf`） |
| `amex_activity_classify.py` | `preview` / `finalize` / `export-tagged`（費目あり行だけ残す） |
| `amex_himoku_rules.example.json` | 費目ルールのテンプレート（`exclude_row_substrings` / `himoku_rules`） |

チャットで確認しながら仕分けする手順（正本・業務メモ）:  
`50_税金…/2.経費,売上資料/税理士提出_手順書/手順_AMEX_費目仕分け_チャット運用.md`

運用コマンドの正本: `~/git-repos/docs/運用コマンド一覧.md` セクション 10。
