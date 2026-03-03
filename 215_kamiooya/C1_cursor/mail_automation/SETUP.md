# セットアップガイド

このガイドに従って、メール自動送信システムをセットアップしてください。

## 📋 前提条件

- Python 3.8以上がインストールされていること
- インターネット接続があること
- Googleアカウント（Gmail）を持っていること

## 🚀 セットアップ手順

### ステップ1: 仮想環境の作成

macOSのHomebrewでインストールされたPythonは、システム保護のため直接パッケージをインストールできません。仮想環境を作成する必要があります。

ターミナルを開いて、以下のコマンドを実行してください：

```bash
cd "/Users/matsunomasaharu/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/C1_cursor/mail_automation"
```

次に、仮想環境を作成します：

```bash
python3 -m venv venv
```

### ステップ2: 仮想環境のアクティベート

仮想環境をアクティベートします：

```bash
source venv/bin/activate
```

アクティベートに成功すると、プロンプトの前に `(venv)` が表示されます：

```
(venv) MacBook-Air-3:mail_automation matsunomasaharu$
```

### ステップ3: 依存パッケージのインストール

仮想環境内でパッケージをインストールします：

```bash
pip install -r requirements.txt
```

インストールが完了すると、以下のパッケージがインストールされます：

- google-auth-oauthlib
- google-auth-httplib2
- google-api-python-client
- openpyxl

### ステップ4: Gmail APIの設定

`README_Gmail_API_Setup.md` を開いて、以下の手順を完了してください：

1. ✅ Google Cloud Consoleでプロジェクト作成
2. ✅ Gmail APIを有効化
3. ✅ OAuth同意画面の設定
4. ✅ 認証情報（`credentials.json`）のダウンロードと配置

`credentials.json` をこのディレクトリに配置してください：

```
C1_cursor/mail_automation/credentials.json
```

### ステップ5: メールアドレス一覧の準備

`メールアドレス一覧の準備方法.md` を参照して、送信先のExcelファイルを準備してください。

### ステップ6: テスト送信

`テスト手順.md` に従って、テスト送信を実行してください。

## 💻 使い方

### 仮想環境内でスクリプトを実行

毎回実行する際は、まず仮想環境をアクティベートする必要があります：

```bash
cd "/Users/matsunomasaharu/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/C1_cursor/mail_automation"
source venv/bin/activate
```

その後、スクリプトを実行します：

```bash
python send_mail.py \
  --md-file "パス/メール.md" \
  --excel-file "パス/送信先リスト.xlsx"
```

### 実行例

```bash
python send_mail.py \
  --md-file "../C2_ルーティン作業/24_空室対策メール履歴/空室対策_Grandole志賀本通2_260129.md" \
  --excel-file "../送信先メールアドレス一覧.xlsx"
```

### 仮想環境の終了

作業が終わったら、仮想環境を終了できます：

```bash
deactivate
```

## 📝 便利なエイリアスの設定（オプション）

毎回長いコマンドを入力するのが面倒な場合は、以下を `~/.bash_profile` または `~/.zshrc` に追加してください：

```bash
# メール送信システムのエイリアス
alias mail-activate='cd "/Users/matsunomasaharu/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/C1_cursor/mail_automation" && source venv/bin/activate'
```

その後、以下のコマンドでシェル設定を再読み込み：

```bash
source ~/.bash_profile  # または source ~/.zshrc
```

これで、次回から `mail-activate` と入力するだけで、ディレクトリ移動と仮想環境のアクティベートが一度にできます。

## 🔍 トラブルシューティング

### エラー: `externally-managed-environment`

このエラーは、Homebrewで管理されているPythonに直接パッケージをインストールしようとした場合に発生します。

**解決方法**: 必ず仮想環境を作成して、その中でパッケージをインストールしてください（上記のステップ1〜3）。

### エラー: `venv: command not found`

Pythonのvenvモジュールがインストールされていない可能性があります。

**解決方法**:
```bash
python3 -m ensurepip
python3 -m pip install --upgrade pip
```

### 仮想環境の削除と再作成

何か問題が発生した場合、仮想環境を削除して再作成できます：

```bash
cd "/Users/matsunomasaharu/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/C1_cursor/mail_automation"
rm -rf venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## ✅ セットアップ確認チェックリスト

セットアップが正しく完了したか、以下をチェックしてください：

- [ ] 仮想環境 `venv/` が作成された
- [ ] 仮想環境をアクティベートできる（`(venv)` がプロンプトに表示される）
- [ ] `pip list` で必要なパッケージが表示される
- [ ] `credentials.json` が配置されている
- [ ] メールアドレス一覧のExcelファイルが準備できている

すべてチェックできたら、`テスト手順.md` に進んでテスト送信を実行してください。

## 📞 次のステップ

1. ✅ セットアップ完了
2. → `テスト手順.md` でテスト送信
3. → 本番環境で使用開始

## 🔗 関連ドキュメント

- `README.md` - 基本的な使い方
- `README_Gmail_API_Setup.md` - Gmail API設定
- `メールアドレス一覧の準備方法.md` - Excelファイルの準備
- `テスト手順.md` - テスト送信手順
