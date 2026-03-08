# GitHub Pages で DX互助会資料（HTML）を公開する手順

HTML 資料を外部から閲覧できるようにし、Notion でリンクを共有するための手順です。

## 公開後のURL（Notion に貼るリンク）

- **資料一覧（トップ）**: https://m19mhrts83-cyber.github.io/project-GE/
- この1リンクを Notion に貼れば、メンバーがブラウザで各スライドを開けます。

## 初回のみ：GitHub Pages を有効にする

1. GitHub でリポジトリ **project-GE** を開く  
   https://github.com/m19mhrts83-cyber/project-GE
2. **Settings** → 左メニュー **Pages**
3. **Build and deployment** の **Source** で **Deploy from a branch** を選択
4. **Branch**: `main`、**Folder**: **/docs** を選び **Save**
5. 数分待つと、上記 URL でアクセスできるようになります。

## 資料の更新の流れ

- 共有フォルダ内の HTML を編集したら、**git-repos/docs**（リポジトリルートの `docs`）に同じファイルをコピーし、`git add docs/` → `commit` → `push` すると、GitHub Pages が自動で更新されます。
- 詳細はリポジトリ内 `docs/README.md` を参照。

## 参考

- 公開用ファイルは **git-repos/docs** にあります（`index.html` が一覧ページ、各 HTML がスライド）。
