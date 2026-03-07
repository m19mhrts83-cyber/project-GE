# ProgramCode の Git 統合について

このフォルダは **project-GE（git-repos）に統合**されたプログラムコード用です。

- **編集場所**: ここ `git-repos/ProgramCode` を編集してください。
- **コミット**: git-repos のソース管理で、他のフォルダ（215 / DX / 500 / 300）と **1つのコミット** でまとめて push できます。
- **venv / venv_gmail**: ローカルで `python -m venv venv` や `venv_gmail` を作成して利用してください。.gitignore で除外済みです。

ワークスペースには **git-repos のみ** を追加すると、Git 管理が1つにまとまります。  
旧 `~/ProgramCode` をワークスペースから外すと、コミットが2つ出る状態は解消されます。
