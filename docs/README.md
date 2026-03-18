# DX互助会 資料（GitHub Pages 用）

この `docs` フォルダは **GitHub Pages** で公開されています。  
HTML 資料を外部から閲覧・Notion でリンク共有するために使います。

- **トップページ**（`index.html`）: 第1回・第2回・第3回…と分岐する一覧。第1回は外部サイト（dx-slides）、第2回は `2kai.html`（3本のスライド）、第3回は準備中。
- **神・大家さん倶楽部**: `260308_目黒さん面談_打ち合わせ用.html` — 目黒さん面談用の打ち合わせ資料（AI活用・法人サポートの選択肢など）。共有用に同じURLで公開可能。
- **神・大家さん倶楽部（採点ツール）**: `saiten_trial_and_production_flow.html` — 成果報告 AI 採点ツールの試行・本番運用の流れ（目黒さん向け）。画像は `採点自動化/image/` を参照。
- **今後の運用**: 第3回の資料ができたら、トップの「第3回」をリンクに差し替え、必要なら `3kai.html` を作成して同様にまとめる。

## 公開 URL（例）

- **リポジトリ**: `https://github.com/m19mhrts83-cyber/project-GE`
- **資料一覧（トップ）**: `https://m19mhrts83-cyber.github.io/project-GE/docs/`（※ ルート公開の場合は `/docs/` が必要）
- 各スライドは一覧ページのリンクから開けます。

### 目黒さん向け資料の直接URL（共有用）

- 打ち合わせ資料（3月）: `https://m19mhrts83-cyber.github.io/project-GE/docs/260308_目黒さん面談_打ち合わせ用.html`
- **試行・本番運用の流れ（採点ツール）**: `https://m19mhrts83-cyber.github.io/project-GE/docs/saiten_trial_and_production_flow.html`

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
