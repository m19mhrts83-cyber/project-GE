# Slack Incoming Webhook 取得（AIエージェントチーム用）

所要: 約10〜15分。権限: Slack ワークスペースでアプリ追加ができること。

## 何のため？

プログラムが `#ai-hub` / `#report` / `#consult` / `#ops` に文章を投稿するための「投稿専用URL」です。  
URL 自体がパスワード扱いなので、チャットには貼らず、ローカルの秘密ファイルだけに書きます。

## 手順（画面遷移）

1. ブラウザで https://api.slack.com/apps を開く
2. **Create New App** → **From scratch**（既存 `Jarvis AI Team` があればそれを開く）
3. App Name 例: `Jarvis AI Team`／Workspace を自分のチームに選択 → **Create App**
4. 左メニュー **Incoming Webhooks** → **Activate Incoming Webhooks** を **On**
5. 下の **Add New Webhook to Workspace**
6. 投稿先チャンネルで **`#report`** を選び **Allow**
7. 表示された **Webhook URL**（`https://hooks.slack.com/services/...`）をコピー
8. 同じ画面で **Add New Webhook to Workspace** を繰り返し、`#consult` / `#ops` / **`#ai-hub`** 用も作る（チャンネルだけ変える）

## 保存先（チャットに貼らない）

Mac の `~/git-repos/.env.jarvis_private` に次を追記（値は自分の URL）:

```
SLACK_WEBHOOK_AI_TEAM_REPORT=https://hooks.slack.com/services/×××
SLACK_WEBHOOK_AI_TEAM_CONSULT=https://hooks.slack.com/services/×××
SLACK_WEBHOOK_AI_TEAM_OPS=https://hooks.slack.com/services/×××
SLACK_WEBHOOK_AI_TEAM_HUB=https://hooks.slack.com/services/×××
```

保存したらチャットで **「Webhook 保存した」** とだけ返事（URL は送らない）。  
`HUB` 未設定のあいだは `--channel hub` が `#report` へフォールバック（本文先頭に `【#ai-hub】`）。

## 消し方

- Slack: api.slack.com/apps → 当該アプリ → Incoming Webhooks で URL 削除、またはアプリ削除
- ローカル: 上記3行を `.env.jarvis_private` から削除

## うまくいかないとき

| 症状 | 確認 |
|---|---|
| チャンネルが一覧に出ない | 先に Slack で `#report` 等を作成／自分が参加 |
| 権限エラー | ワークスペース管理者にアプリ追加を依頼 |
| 投稿 403/invalid_token | URL のコピー漏れ・改行混入を確認 |
