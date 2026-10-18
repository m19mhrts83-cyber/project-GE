# Slack 書き出し — FRIDAY／Jarvis／AI社員（2026-10-18）

社員 `CLAUDE.md` §報告先・FRIDAY キット・ハブ指示から参照する **1節の正本**。

## どの ch に書くか

| ch | いつ書く | 誰向け |
|---|---|---|
| **`#report`** | 完了・定型サマリ・「動いている」生存確認 | 松野が流し見 |
| **`#consult`** | 要判断・迷い・Yes/No・次の一手が人／他ツール | 松野の確認トレイ |
| **`#ops`** | 障害・失敗・認証切れ・枠切れ・健全性アラート | すぐ手当て |

| 実行者 | 残すもの |
|---|---|
| **Jarvis（Cursor）** | 実装完了・ゲート結果・要判断・FRIDAY からの引き継ぎ要約 |
| **FRIDAY（GenCode）** | Jarvis／松野と共有すべき完了・要判断（チャットだけに閉じない） |
| **AI社員（定期／イベント）** | 各 `CLAUDE.md` の報告先どおり（同じ3ch） |

壁打ち・長考は Grok チャンネル可。**残す報告は Slack**（Drive は Mac 実行手渡し用・併用）。

## 先頭1行（必須）

番号＋短い役割語。例:

- `【報告】211 返信案内下書き・朝便`
- `【相談】311 送信前品質`
- `【ops】315 連携健全性`

詳細: ハブ [`CLAUDE.md`](./CLAUDE.md)「Slack 書き出し」· `.cursor/rules/jarvis-agent-team-slack-report.mdc`

## `#consult` 末尾（必須 · 次の担当）

自動実行ではない。松野が読んで橋渡しする。

```
次: Grokで続行 | Jarvisに依頼 | 人判断のみ
担当メモ: （未配線・自動化できてない点があれば1行）
橋渡し: 松野が了承したら、上記の担当へ一声（当面は人が橋）
```

| `次:` | 了承後 |
|---|---|
| `Grokで続行` | Grok メイン／部長へ一声 |
| `Jarvisに依頼` | Cursor（Jarvis）。枠切れなら Claude Code 等 |
| `人判断のみ` | 実行依頼を出さない |

正本の読み方: [`36_Slack_consult手渡し_次の担当_20261018.md`](./36_Slack_consult手渡し_次の担当_20261018.md)

## 投稿の手段

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
~/selenium_env/venv/bin/python scripts/jarvis_slack_webhook_post.py \
  --channel report --text '【報告】…'
# consult / ops も同様（--channel consult|ops）
```

秘密・Webhook URL・トークンは本文に書かない。

## Jarvis が読む側

投稿後、Cursor セッションで差分に気づく: [`37_`](./37_Slackハブ_Jarvis読取_20261018.md) · `jarvis-slack-hub-watch.mdc`

## 社員 CLAUDE への載せ方

各社員の「報告先」節に、次を1ブロック貼る（または本 MD へリンク）:

```markdown
### Slack 書き出し（FRIDAY／Jarvis 共通）
ch・末尾型の正本: [`38_Slack書き出し_FRIDAY_Jarvis_20261018.md`](../../38_Slack書き出し_FRIDAY_Jarvis_20261018.md)
`#consult` は末尾「次の担当」3行必須（[`36_`](../../36_Slack_consult手渡し_次の担当_20261018.md)）。
```

（パス深さはフォルダ位置に合わせる。）
