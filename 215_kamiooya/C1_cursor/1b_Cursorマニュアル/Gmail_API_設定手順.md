# Gmail API 設定手順（やり取り連携用）

`gmail_to_yoritoori.py` で Gmail のメールをやり取りフォルダに自動追記するために必要な設定です。  
**添付ファイル**も該当フォルダ内の「添付」サブフォルダに自動保存されます。

---

## 1. Google Cloud Console でプロジェクト作成

1. [Google Cloud Console](https://console.cloud.google.com/) にアクセス
2. プロジェクトを選択、または「新しいプロジェクト」を作成
3. プロジェクト名は任意（例: `yoritoori-gmail`）

---

## 2. Gmail API を有効化

1. 左メニュー「API とサービス」→「ライブラリ」
2. 「Gmail API」を検索して選択
3. 「有効にする」をクリック

---

## 3. OAuth 2.0 認証情報の作成

1. 「API とサービス」→「認証情報」
2. 「認証情報を作成」→「OAuth クライアント ID」
3. 初回は「同意画面の構成」が求められる場合あり
   - ユーザータイプ: **外部**（個人利用なら外部でOK）
   - アプリ名など必要項目を入力して保存
4. アプリケーションの種類: **デスクトップアプリ**
5. 名前: 任意（例: `yoritoori-local`）
6. 「作成」→ **credentials.json** がダウンロードされる
7. `credentials.json` を `C1_cursor/1b_Cursorマニュアル/` に配置

---

## 4. 初回認可（token.json の作成）

1. このフォルダで `python gmail_to_yoritoori.py` を実行（または `.venv_gmail/bin/python gmail_to_yoritoori.py`）
2. 初回はブラウザが開き、Google アカウントでのログインを求められる
3. 「このアプリは確認されていません」と出たら「詳細」→「〇〇（安全ではないページ）に移動」をクリック
4. アクセスを許可
5. 成功すると `token.json` が同じフォルダに作成される
6. 以降はこの token で自動的にAPIアクセスが可能（期限切れ時は再認可が必要）

---

## 5. 環境変数・パス（任意）

`.env` には以下を追加可能（省略時はデフォルトパスを使用）:

```
GMAIL_CREDENTIALS_PATH=./credentials.json
GMAIL_TOKEN_PATH=./token.json
CONTACT_LIST_PATH=../C2_ルーティン作業/26_パートナー社への相談/000_共通/連絡先一覧.yaml
YORITOORI_BASE_PATH=../C2_ルーティン作業/26_パートナー社への相談
```

スクリプトは相対パスで `連絡先一覧.yaml` と各フォルダを解決します。OneDrive のパスが長い場合は絶対パス指定も可能です。

---

## 6. セキュリティ注意

- `credentials.json` と `token.json` は **`.gitignore` に追加**し、Git にコミットしない
- これらは第三者に漏れると Gmail にアクセスされるため、厳重に管理する
