# メール自動送信システム

MDファイルから件名・本文を読み取り、Excelファイルのメールアドレス一覧にBCCで一斉送信するシステムです。

## 📁 ファイル構成

```
C1_cursor/mail_automation/
├── README.md                      # このファイル
├── README_Gmail_API_Setup.md      # Gmail API設定ガイド
├── send_mail.py                   # メール送信スクリプト
├── requirements.txt               # Python依存パッケージ
├── credentials.json               # （旧）空室対策専用。現在は未使用。1b_Cursorマニュアルに統一済み
├── token.pickle                   # （旧）同上。現在は未使用
└── logs/                          # 送信ログ（自動生成）
    └── send_history.log
```

**認証について**  
空室対策メール送信も、パートナー・いけともと同じ **1b_Cursorマニュアル** の `credentials.json` と `token.json` を使用します。3日ごとのトークン自動更新の対象になるため、別途このフォルダに認証ファイルを置く必要はありません。従来の `mail_automation` 内の `credentials.json` / `token.pickle` は現在は使用していません（コード上はフォールバック用に残してあります）。

## 🚀 セットアップ手順

### 1. Pythonのインストール確認

```bash
python3 --version
```

Python 3.8以上がインストールされていることを確認してください。

### 2. 依存パッケージのインストール

```bash
cd "/Users/matsunomasaharu/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/C1_cursor/mail_automation"
pip3 install -r requirements.txt
```

### 3. Gmail APIの設定

空室対策メール送信では **1b_Cursorマニュアル** フォルダの `credentials.json` と `token.json` を使用します（パートナー・いけともと同じ認証。3日ごとのトークン自動更新の対象）。  
まだ 1b_Cursorマニュアルに認証を用意していない場合は、`README_Gmail_API_Setup.md` を参照して以下を完了してください：

1. Google Cloud Consoleでプロジェクト作成
2. Gmail APIを有効化
3. OAuth同意画面の設定
4. 認証情報（credentials.json）のダウンロードと **1b_Cursorマニュアル** への配置

## 📧 使い方

### 基本的な使い方

```bash
python3 send_mail.py \
  --md-file "パス/メール.md" \
  --excel-file "パス/送信先リスト.xlsx"
```

### 詳細なオプション指定

```bash
python3 send_mail.py \
  --md-file "C2_ルーティン作業/24_空室対策メール履歴/空室対策_Grandole志賀本通2_260129.md" \
  --excel-file "★各種リスト.xlsx" \
  --sheet-name "送信先一覧" \
  --email-column "メールアドレス"
```

### 本文全文のプレビュー表示

デフォルトでは本文の先頭300文字のみが表示されますが、全文を確認したい場合：

```bash
python3 send_mail.py \
  --md-file "メール.md" \
  --excel-file "送信先リスト.xlsx" \
  --full-preview
```

### 送信時刻を指定（スケジュール送信）

特定の時刻に送信したい場合、`--schedule` オプションを使用できます：

#### 今日または明日の特定時刻に送信

```bash
python3 send_mail.py \
  --md-file "メール.md" \
  --excel-file "送信先リスト.xlsx" \
  --schedule "14:30"
```

#### 日付と時刻を指定

```bash
python3 send_mail.py \
  --md-file "メール.md" \
  --excel-file "送信先リスト.xlsx" \
  --schedule "2026-01-30 14:30"
```

または：

```bash
python3 send_mail.py \
  --md-file "メール.md" \
  --excel-file "送信先リスト.xlsx" \
  --schedule "01/30 14:30"
```

#### 相対時刻で指定

```bash
# 30分後に送信
python3 send_mail.py \
  --md-file "メール.md" \
  --excel-file "送信先リスト.xlsx" \
  --schedule "30分後"

# 2時間後に送信
python3 send_mail.py \
  --md-file "メール.md" \
  --excel-file "送信先リスト.xlsx" \
  --schedule "2時間後"
```

### テスト実行（送信せずにプレビューのみ）

```bash
python3 send_mail.py \
  --md-file "メール.md" \
  --excel-file "送信先リスト.xlsx" \
  --dry-run
```

### Cursorチャットから実行

Cursorのチャットで以下のように指定すると、AIが自動的にコマンドを組み立てて実行します：

```
@空室対策_Grandole志賀本通2_260129.md と @送信先リスト.xlsx を使って、
14:30にメール送信してください
```

または：

```
@空室対策_Grandole志賀本通2_260129.md と @送信先リスト.xlsx を使って、
本文全文をプレビューしてからメール送信してください
```

## 📝 MDファイルの形式

MDファイルは以下の形式で作成してください：

```markdown
件名をここに書く

本文の1行目
本文の2行目
本文の3行目
...
```

- **1行目**: メールの件名
- **2行目以降**: メールの本文

例: `空室対策_Grandole志賀本通2_260129.md`

```markdown
【Grandole志賀本通II(名古屋市北区)】102号室(新規)入居募集のお願い

お世話になっております。
志賀本通駅近くのGrandole志賀本通IIオーナーの松野です。
...
```

## 📊 Excelファイルの形式

Excelファイルには、メールアドレスを含む列が必要です。

### 推奨形式

| 会社名 | 担当者 | メールアドレス | 備考 |
|--------|--------|----------------|------|
| A不動産 | 田中様 | tanaka@example.com | |
| B管理 | 鈴木様 | suzuki@example.com | |
| C仲介 | 佐藤様 | sato@example.com | |

### 自動検出

`--email-column` オプションを省略すると、以下の文字列を含む列を自動的に検出します：

- 「メール」
- 「email」
- 「mail」

### 手動指定

```bash
--email-column "メールアドレス"
```

## ⚙️ コマンドオプション

| オプション | 必須 | 説明 | デフォルト値 |
|-----------|------|------|-------------|
| `--md-file` | ✓ | MDファイルのパス | - |
| `--excel-file` | ✓ | Excelファイルのパス | - |
| `--sheet-name` |  | Excelのシート名 | 最初のシート |
| `--email-column` |  | メールアドレス列の名前 | 自動検出 |
| `--to-display` |  | TO欄に表示する文字列 | `undisclosed-recipients:;` |
| `--full-preview` |  | 本文を全文表示 | 先頭300文字のみ |
| `--schedule` |  | 送信時刻を指定 | 今すぐ送信 |
| `--dry-run` |  | 送信せずプレビューのみ | - |

### --schedule オプションの詳細

送信時刻を指定できます。以下のフォーマットに対応：

| フォーマット | 例 | 説明 |
|------------|-----|------|
| `HH:MM` | `14:30` | 今日の14:30（過去の場合は明日） |
| `YYYY-MM-DD HH:MM` | `2026-01-30 14:30` | 2026年1月30日 14:30 |
| `MM/DD HH:MM` | `01/30 14:30` | 1月30日 14:30（今年または来年） |
| `XX分後` | `30分後` | 現在時刻から30分後 |
| `XX時間後` | `2時間後` | 現在時刻から2時間後 |

## 🔒 セキュリティ

### 重要なファイルの管理

以下のファイルは機密情報を含むため、Git管理から除外してください：

```gitignore
# Gmail API認証情報
C1_cursor/mail_automation/credentials.json
C1_cursor/mail_automation/token.pickle
```

### 送信制限

Gmail APIには以下の送信制限があります：

- **個人アカウント**: 1日500通まで
- **Google Workspace**: 1日2,000通まで

## 📋 送信ログ

送信履歴は `logs/send_history.log` に自動的に記録されます。

ログ形式：
```
[2026-01-29 14:30:00] SUCCESS - 件名: 【Grandole志賀本通II】入居募集 - 送信先: 25件
[2026-01-29 15:45:00] FAILED - 件名: N/A - 送信先: 0件 - エラー: File not found
```

## 🛠 トラブルシューティング

### エラー: `credentials.json not found`

**原因**: Gmail APIの認証情報ファイルが見つかりません。

**解決方法**: 
1. `README_Gmail_API_Setup.md` を参照
2. Google Cloud Consoleで認証情報をダウンロード
3. `credentials.json` を `C1_cursor/mail_automation/` に配置

### エラー: `openpyxlがインストールされていません`

**原因**: 必要なPythonパッケージがインストールされていません。

**解決方法**:
```bash
pip3 install -r requirements.txt
```

### エラー: `Excelファイルが見つかりません`

**原因**: 指定したExcelファイルのパスが正しくありません。

**解決方法**:
- ファイルパスを確認してください
- 相対パスまたは絶対パスで正しく指定してください

### エラー: `シート 'XXX' が見つかりません`

**原因**: 指定したシート名が存在しません。

**解決方法**:
- Excelファイルを開いてシート名を確認してください
- `--sheet-name` オプションを省略すると最初のシートが使用されます

### エラー: `メールアドレスの列が見つかりません`

**原因**: メールアドレス列を自動検出できませんでした。

**解決方法**:
```bash
--email-column "列名"
```
でメールアドレス列の名前を明示的に指定してください。

### 認証画面が表示されない

**原因**: ブラウザのポップアップブロック

**解決方法**:
- ターミナルに表示されるURLをコピーして手動でブラウザで開く
- ブラウザのポップアップブロックを解除

## 💡 Cursorからの実行方法

Cursorのチャットで以下のようにプロンプトを送信すると、AIが自動的にスクリプトを実行します：

```
@空室対策_Grandole志賀本通2_260129.md と @★各種リスト.xlsx を使ってメール送信
```

または：

```
C1_cursor/mail_automation/send_mail.py を使って、
MDファイル: C2_ルーティン作業/24_空室対策メール履歴/空室対策_Grandole志賀本通2_260129.md
Excelファイル: ★各種リスト.xlsx
でメールを送信してください
```

## 📚 参考情報

- Gmail API公式ドキュメント: https://developers.google.com/gmail/api
- Python Quickstart: https://developers.google.com/gmail/api/quickstart/python
- openpyxlドキュメント: https://openpyxl.readthedocs.io/
