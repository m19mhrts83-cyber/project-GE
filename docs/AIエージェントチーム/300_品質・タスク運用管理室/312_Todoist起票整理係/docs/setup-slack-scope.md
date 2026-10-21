# Slackアプリに「履歴の読み取り」権限を追加する（5分）

対象アプリ: **Jarvis AI Team**（Bot `B0CB1LCDRQR` / ワークスペース `aiwsnetwork.slack.com`）

なぜ必要か: いまのBotトークンは #consult のメッセージ履歴を読めない（`missing_scope`）。
返信をトリガーにするには、Bot に `channels:history` を付けて再インストールする必要がある。

## 手順

1. https://api.slack.com/apps を開く（Slackにログインした状態）
2. **Jarvis AI Team** をクリック
3. 左メニュー **OAuth & Permissions**
4. 「**Scopes**」→「**Bot Token Scopes**」で **Add an OAuth Scope** を押し、次を追加
   - `channels:history`（#consult の履歴を読む）
   - `chat:write` は既にある想定（無ければ追加）
5. ページ上部に戻り **Reinstall to Workspace** → **Allow**
6. 再インストール後の **Bot User OAuth Token**（`xoxb-…`）をコピー
7. コピーしたトークンを FRIDAY に渡す（チャットに貼らず、`~/git-repos/.env.jarvis_private` の `SLACK_BOT_TOKEN` を更新したい旨だけ伝える）

## 確認（FRIDAY がやる）

- `auth.test` が ok
- `conversations.history`（#consult）が ok
- 失敗時は `missing_scope` の文字列と必要な scope 名を返す

## 注意

- トークンはチャット・ドキュメント・Git に書かない（`.env.jarvis_private` のみ）
- 再インストールでトークンが変わるので、古い値は上書きする
- 権限追加は「読み取り」のみ。投稿権限は既存のまま
