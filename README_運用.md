# project-GE 一本化：Git 運用メモ

## 構成（2025年3月〜）

- **1 つの Git リポジトリ** = `~/git-repos`（ルートに `.git` がある）
- **リモート** = GitHub **project-GE**（https://github.com/m19mhrts83-cyber/project-GE）
- **中身** = 215 / DX / 500 / 300 をサブフォルダで管理
  - `215_kamiooya/` … 215 神・大家さん倶楽部
  - `dx_kyouyuu/` … DX互助会（定期実行・いけともAIニュース等）
  - `500_obsidian/` … 500 Obsidian
  - `300_ai/` … 300 AIリスキリング講座

## 日々の運用

1. **編集**  
   - 215: これまでどおり OneDrive「215_神・大家さん倶楽部」で編集し、必要に応じて rsync で `git-repos/215_kamiooya` に反映してもよい。  
     または `git-repos/215_kamiooya` を直接編集してもよい。
   - DX: **`git-repos/dx_kyouyuu`** を編集する（Google Drive の「DX互助会_共有フォルダ」は Git の作業ツリーではなくなった。定期実行は GitHub 上の project-GE を参照する想定）。
   - 500 / 300: `git-repos/500_obsidian`、`git-repos/300_ai` を編集。

2. **コミット・push**  
   - Cursor のワークスペースに **`~/git-repos`** を追加しておく。
   - ソース管理で変更を確認し、**メッセージを入力 → コミット → Push**。  
   - またはターミナルで:
     ```bash
     cd ~/git-repos
     git add -A
     git commit -m "ここにメッセージ"
     git push
     ```

3. **215 を OneDrive から同期する場合（従来の rsync）**  
   - 運用メモは `215_kamiooya/C1_cursor/運用メモ_ローカル本番とGitHub.md` にあり、rsync コマンド等は従来どおり。  
   - 同期先を **`~/git-repos/215_kamiooya`** にすれば、そのまま project-GE 用の 1 本のリポジトリに反映される。

## DX の定期実行（GitHub Actions 等）について

- これまで **DX-_-** リポジトリで定期実行していた場合は、**project-GE** 側のパスが変わっている（`dx_kyouyuu/` がトップに増えている）ため、  
  - GitHub Actions の `paths` やスクリプト内のパスを **project-GE** の構造（例: `dx_kyouyuu/.github/workflows/`、`dx_kyouyuu/03_outputs/ai_news_save/`）に合わせて変更する必要があります。
- 定期実行の設定は `dx_kyouyuu/.github/workflows/` に含めたまま project-GE に push 済みです。

## 旧リポジトリ（参考）

- **215** の旧 .git は `215_kamiooya/.git.bak.日付` に退避済み。不要なら削除してよい。
- **DX** の旧 .git は `dx_kyouyuu/.git.bak.日付` に退避済み。DX-_- リポジトリは今後は使わず、project-GE に一本化。
- Google Drive「DX互助会_共有フォルダ」内の **`.git` ファイル**（`gitdir: .../dx_kyouyuu` を指していたもの）は、今後は Git の作業ツリーとして使わない。削除してもよい（Git の管理は `git-repos` のみ）。
