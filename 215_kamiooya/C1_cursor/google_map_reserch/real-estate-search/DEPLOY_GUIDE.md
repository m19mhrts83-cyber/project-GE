# 🚀 GitHub Pages デプロイガイド

このガイドに従って、不動産賃貸管理会社検索サイトをGitHub Pagesで公開できます。

## 必要なファイル

以下を GitHub リポジトリ（project-GE）に含めてください：

1. `index.html` - 管理会社検索
2. `style.css` - スタイル
3. `app.js` - 管理会社検索ロジック
4. `shuhen-map.html` / `shuhen-map.js` - **周辺MAP 番号ピン**（別ページ）
5. `README.md` - プロジェクト説明（オプション）

周辺MAP: 公開後 `https://m19mhrts83-cyber.github.io/project-GE/shuhen-map.html`

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

## 🔒 セキュリティ設定（重要！）— 運営キー運用

`shuhen-map` 公開版は **会員にキー入力させない**（GitHub Actions が `GOOGLE_MAPS_BROWSER_KEY` を注入）。  
Maps JS のキーはページ上で見えるため、次の制限が必須です。詳細正本:

`215_kamiooya/.../AI×周辺MAP/運用手順_周辺MAP_MapsAPIキー_運営移管.md`

1. **Google Cloud Console** → API とサービス → 認証情報  
2. **アプリケーションの制限** → HTTP リファラー:
   ```
   https://m19mhrts83-cyber.github.io/project-GE/*
   ```
3. **API の制限**: Maps JavaScript / Places / Geocoding / Directions（必要なら Static）のみ  
4. **Directions API** を有効化（徒歩動線トグル用）  
5. **予算アラート** 50% / 90% / 100%、日次クォータ上限  
6. GitHub Secret `GOOGLE_MAPS_BROWSER_KEY` に制限済みキーを設定  

戻し（キー入力 UI あり）: タグ `shuhen-map-before-ops-key`
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
