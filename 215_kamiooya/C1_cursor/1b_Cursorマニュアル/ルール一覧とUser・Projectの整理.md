# 現在のルール一覧と User / Project の整理

現在、プロジェクトごとの `.cursor/rules/` に置いているルールを一覧にし、**User Rules（ユーザールール）に寄せるか、Project Rules（プロジェクト側）に残すか**の判定をまとめました。

---

## 一覧（現在どこにあるか）

| # | ルール名 | 内容（概要） | 置いている場所 |
|---|----------|--------------|----------------|
| 1 | **command-location** | コマンド・プロンプトの保存先を「500_Obsidian/.cursor/commands/」に統一。215 の .cursor/commands には保存しない。 | 215 のみ |
| 2 | **git-commit-habit** | 変更後にコミットを提案。215 版は「sync_to_git.sh + git add をエージェントが実行してから提案」。他は「提案＋メッセージ例」のみ。 | 215 / 500_Obsidian / DX互助会 / 300_AI（4箇所） |
| 3 | **gmail-mcp-chat** | Gmail MCP で検索・下書き・送信するときのツール優先と「この内容で送って」は send_email で新規送信する。 | 215 のみ |
| 4 | **gmail-token-troubleshooting** | Gmail token 期限切れ・GMAIL_TOKEN_B64 更新時に、いけともとパートナーやりとり両方への案内を追加する。 | 215 / DX互助会（2箇所） |
| 5 | **onedrive-connection** | OneDrive 接続エラー時はリトライせず止めて、ユーザーに「接続が切れています」と伝える。 | 215 のみ |
| 6 | **partner-email-check** | 「パートナーからのメールを確認して」→ gmail_to_yoritoori.py と imessage_to_yoritoori.py を実行（215 のパス・連絡先一覧）。 | 215 のみ |
| 7 | **partner-email-send** | パートナー宛メールは yoritoori_send.py のみ。4.送信下書き.txt と連絡先一覧を使い、送信用 MD/Excel は作らない。 | 215 のみ |
| 8 | **python-local-venv** | Python は git-repos/ProgramCode の venv を使う。215 用にパートナー送信・確認の実行例あり。 | 215 のみ |

※ 215 = 215_神・大家さん倶楽部、500 = 500_Obsidian、DX = DX互助会_共有フォルダ、300 = 300_AIリスキリング講座

---

## 判定：User に寄せる vs Project に残す

| # | ルール名 | 判定 | 理由 |
|---|----------|------|------|
| 1 | command-location | **User** | カレントプロジェクトに関係なく「コマンドはここに保存」と決めている運用。一箇所で効かせたい。 |
| 2 | git-commit-habit | **User（1本にまとめる）** | 「コミットは自分でする」は全プロジェクト共通。215 のときだけ「提案前に sync_to_git + git add を実行」と条件分岐で書けば User に一本化できる。 |
| 3 | gmail-mcp-chat | **User** | Gmail MCP はどのプロジェクトを開いていても同じ振る舞いにしたい。 |
| 4 | gmail-token-troubleshooting | **User** | token 更新の案内は 215 でも DX でも同じ内容。参照ドキュメントのパスを「215 のとき」「DX のとき」と書けばよい。 |
| 5 | onedrive-connection | **User** | OneDrive 接続切れの扱いはプロジェクトに依存しない。 |
| 6 | partner-email-check | **Project（215）** | 実行するスクリプト・連絡先・フォルダがすべて 215 の構成。215 を開いているときだけ効けばよい。 |
| 7 | partner-email-send | **Project（215）** | 同上。yoritoori_send.py と 4.送信下書き.txt、連絡先一覧は 215 固有。 |
| 8 | python-local-venv | **User** | 「ProgramCode の venv を使う」は全プロジェクト共通。215 の実行例は「215 でパートナー系のときはカレント 1b_Cursorマニュアル」と短く書ける。 |

---

## まとめ

- **User Rules に寄せる（6本）**  
  command-location, git-commit-habit（1本に統合）, gmail-mcp-chat, gmail-token-troubleshooting, onedrive-connection, python-local-venv
- **Project Rules（215）に残す（2本）**  
  partner-email-check, partner-email-send  

User に寄せたルールは、**Cursor Settings → Rules** の「User Rules」にテキストとして追加します（.mdc の frontmatter は使えないので、見出しと本文だけ貼る形になります）。  
移行後は、500_Obsidian / DX互助会 / 300_AI の `.cursor/rules/` から git-commit-habit（および DX の gmail-token-troubleshooting）を削除し、215 からは User に移した 6 本を削除して、215 には partner-email-check と partner-email-send だけ残す、という整理ができます。

---

## 移行実施済み（〜実施日）

- 上記 6 本を **User Rules**（Cursor の `aicontext.personalContext`）に統合して反映した。
- 統合テキストの控え: `user-rules-merged.txt`（同一フォルダ）。
- 215 の `.cursor/rules/` から該当 6 本を削除。**partner-email-check.mdc** と **partner-email-send.mdc** のみ Project に残した。
- 500_Obsidian / DX互助会 / 300_AI の重複（git-commit-habit、DX の gmail-token-troubleshooting）を削除した。
