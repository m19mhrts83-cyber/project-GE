# ProgramCode の Git 統合について

このフォルダは **project-GE（git-repos）に統合**されたプログラムコード用です。

- **編集場所**: ここ `git-repos/ProgramCode` を編集してください。
- **コミット**: git-repos のソース管理で、他のフォルダ（215 / DX / 500 / 300）と **1つのコミット** でまとめて push できます。
- **venv**: `./venv/bin/python` — excel_to_md.py, pdf_to_md.py 用（`pip install -r requirements.txt` 済み）。
- **venv_gmail**: `./venv_gmail/bin/python` — Gmail API・やり取りスクリプト用（`pip install -r requirements_gmail.txt` 済み）。  
  いずれも .gitignore で除外されているためリポジトリには含まれません。再作成する場合は上記の requirements でインストールしてください。
- **Cursor ルール**: `.cursor/rules/python-local-venv.mdc` で、実行パスを `~/git-repos/ProgramCode/venv_gmail` および `~/git-repos/ProgramCode/venv` に合わせてあります。

ワークスペースには **git-repos のみ** を追加すると、Git 管理が1つにまとまります。  
旧 `~/ProgramCode` は削除して問題ありません（仮想環境はこのフォルダに同等で用意済みです）。
