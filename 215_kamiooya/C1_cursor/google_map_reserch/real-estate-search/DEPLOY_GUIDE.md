# 🚀 GitHub Pages デプロイガイド

このガイドに従って、不動産賃貸管理会社検索サイトをGitHub Pagesで公開できます。

## 📦 必要なファイル

以下の4つのファイルをGitHubリポジトリにアップロードしてください：

1. `index.html` - メインHTMLファイル
2. `style.css` - スタイルシート
3. `app.js` - JavaScript（検索ロジック）
4. `README.md` - プロジェクト説明（オプション）

## 🔧 デプロイ手順

### ステップ1: ファイルをGitHubにアップロード

1. **GitHubリポジトリにアクセス**
   - https://github.com/m19mhrts83-cyber/project-GE

2. **既存ファイルの確認**
   - リポジトリに既にファイルがある場合は、削除するか上書きしてください

3. **ファイルをアップロード**
   - 「Add file」ボタンをクリック
   - 「Upload files」を選択
   - 4つのファイル（index.html, style.css, app.js, README.md）をドラッグ&ドロップ
   - またはZIPファイル（real-estate-search.zip）を展開してアップロード

4. **コミット**
   - Commit message: "feat: 不動産賃貸管理会社検索サイトを追加"
   - 「Commit changes」ボタンをクリック

### ステップ2: GitHub Pagesを有効化

1. **Settings（設定）にアクセス**
   - リポジトリページ上部の「Settings」タブをクリック

2. **Pagesセクションに移動**
   - 左サイドバーから「Pages」をクリック

3. **ソースを設定**
   - **Source**: "Deploy from a branch" を選択
   - **Branch**: "main" を選択
   - **Folder**: "/ (root)" を選択
   - 「Save」ボタンをクリック

4. **デプロイを待つ**
   - 数分待つとデプロイが完了します
   - ページをリロードすると、公開URLが表示されます

### ステップ3: 公開URLを確認

デプロイが完了すると、以下のようなURLでアクセスできます：

```
https://m19mhrts83-cyber.github.io/project-GE/
```

## 🔒 セキュリティ設定（重要！）

公開後、Google Maps API Keyに制限を設定してください：

1. **Google Cloud Consoleにアクセス**
   - https://console.cloud.google.com/

2. **API Keyの制限を設定**
   - 「APIとサービス」→「認証情報」
   - API Keyを選択
   - 「アプリケーションの制限」→「HTTPリファラー」を選択
   - 「ウェブサイトの制限」に以下を追加：
     ```
     https://m19mhrts83-cyber.github.io/project-GE/*
     ```
   - 「保存」をクリック

## 📝 カスタムドメイン（オプション）

独自ドメインを使用したい場合：

1. **ドメインを用意**
   - お名前.com、ムームードメインなどで取得

2. **GitHub Pagesで設定**
   - Settings → Pages → Custom domain
   - ドメイン名を入力（例: real-estate-search.example.com）

3. **DNSレコードを設定**
   - Aレコードまたは CNAMEレコードを設定
   - 詳細: https://docs.github.com/ja/pages/configuring-a-custom-domain-for-your-github-pages-site

## 🔄 更新方法

ファイルを更新したい場合：

1. GitHubリポジトリでファイルを直接編集
2. または新しいファイルをアップロード（上書き）
3. 数分後に自動的に反映されます

## ⚠️ トラブルシューティング

### サイトが表示されない
- GitHub Pagesの設定を確認
- ブランチが "main" になっているか確認
- 数分待ってからアクセス

### 404エラーが出る
- ファイル名が正確か確認（大文字小文字も区別されます）
- index.html がルートディレクトリにあるか確認

### APIが動作しない
- Google Maps API Keyが正しく入力されているか確認
- API Keyの制限設定を確認
- ブラウザのコンソールでエラーを確認

## 📞 サポート

問題が解決しない場合は、以下を確認してください：

- GitHub Pagesのドキュメント: https://docs.github.com/ja/pages
- Google Maps Platform: https://developers.google.com/maps/documentation

## 🎉 完成！

すべての手順が完了したら、以下のURLでサイトにアクセスできます：

**🌐 公開URL: https://m19mhrts83-cyber.github.io/project-GE/**

おめでとうございます！🎊
