# ProgramCode ツール一覧

ワトソンくん（Cursor AI）と一緒に作成したツールの一覧です。
新しいツールを作成するたびにこのファイルを更新します。

---

## 変換ツール

### pdf_to_md.py
- **概要**: PDFファイルをMarkdown(.md)に変換する
- **機能**: テキスト抽出、テーブルのMarkdown変換、ページ区切り
- **作成日**: 2026-02-07

```bash
source ~/ProgramCode/venv/bin/activate && python3 ~/ProgramCode/pdf_to_md.py <PDFファイルパス>
source ~/ProgramCode/venv/bin/activate && python3 ~/ProgramCode/pdf_to_md.py <PDFファイルパス> -o <出力先ディレクトリ>
```

### excel_to_md.py
- **概要**: Excelファイル(.xlsx)をMarkdown(.md)に変換する
- **機能**: 全シート自動変換、シートごとに見出しで区切り、日付・数値の適切な文字列化
- **作成日**: 2026-02-07

```bash
source ~/ProgramCode/venv/bin/activate && python3 ~/ProgramCode/excel_to_md.py <Excelファイルパス>
source ~/ProgramCode/venv/bin/activate && python3 ~/ProgramCode/excel_to_md.py <Excelファイルパス> -o <出力先ディレクトリ>
```

---

## 過去のスクリプト（alfred_python/）

| ファイル名 | 概要 |
| --- | --- |
| chapro_population_only.py | 人口データ関連 |
| merge_westudy_csv.py | WeStudy CSV結合 |
| rosenka_final.py | 路線価関連 |
| westudy_forum_all.py | WeStudyフォーラム関連 |
| westudy_forum_test.py | WeStudyフォーラムテスト |

## 過去のスクリプト（old/）

| ファイル名 | 概要 |
| --- | --- |
| hazard_search.py | ハザード検索 |
| rosenka_hazard_safari.py | 路線価ハザード（Safari） |
| rosenka_iframe_check.py | 路線価iframe確認 |
| rosenka_input_test.py | 路線価入力テスト |
| rosenka_min.py | 路線価（最小版） |
| rosenka_search.py | 路線価検索 |
| rosenka_test.py | 路線価テスト |

---

## 環境情報

- **Python**: 3.13.7
- **仮想環境**: `~/ProgramCode/venv/`
- **依存ライブラリ**: `requirements.txt` 参照（pdfplumber, openpyxl）
