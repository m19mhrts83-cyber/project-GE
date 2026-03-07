# DX互助会 資料（GitHub Pages 用）

この `docs` フォルダは **GitHub Pages** で公開されています。  
HTML 資料を外部から閲覧・Notion でリンク共有するために使います。

## 公開 URL（例）

- **リポジトリ**: `https://github.com/m19mhrts83-cyber/project-GE`
- **資料一覧（トップ）**: `https://m19mhrts83-cyber.github.io/project-GE/`
- 各スライドは一覧ページのリンクから開けます。

## GitHub Pages の有効化（初回のみ）

1. GitHub でリポジトリ **project-GE** を開く
2. **Settings** → 左メニュー **Pages**
3. **Build and deployment** の **Source** で **Deploy from a branch** を選択
4. **Branch**: `main`、**Folder**: `/docs` を選び **Save**
5. 数分後、上記の URL でアクセスできるようになります。

## 資料の更新手順

1. Google Drive の「DX互助会_共有フォルダ」内の HTML を編集
2. 更新した HTML を **git-repos/docs**（リポジトリルートの `docs`）にコピー
3. `git add docs/` → `git commit` → `git push origin main`
4. GitHub Pages は自動で再デプロイされます（1〜2分程度）。

## Notion で共有するとき

- 共有用リンク: **https://m19mhrts83-cyber.github.io/project-GE/**
- Notion のページに上記 URL を貼ると、メンバーがブラウザで資料一覧を開けます。
