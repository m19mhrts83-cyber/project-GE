# Slack `#consult` 手渡し — 次の担当（2026-10-18）

- 確定: 松野意向（Slack AI 協働相談）／実装着手同日
- 土台: [`17_Grok定型報告_Slack_20261010.md`](17_Grok定型報告_Slack_20261010.md) · [`20_PhaseK`](20_PhaseK_Grok報告Slackミックス_20261011.md)

## 結論（いま）

`#consult` は **自動実行のスイッチではない**。  
**松野の確認トレイ**。投稿の末尾に「次は誰の仕事か」を必ず書く。

| 松野の動き | 内容 |
|---|---|
| 読む | Slack `#consult` |
| 進める | **Grok 続行**／**Jarvis（Cursor）に一声**／**Claude Code で続行**／**人判断のみ** のどれか |
| まだしない | 絵文字リアクション自動拾い · Connect 他社 Bot |

## `#consult` 本文の末尾（必須・3行）

各行の **あいだは空行1つ**（見やすさ。Jarvis apply が正規化）。

```
次: Grokで続行 | Jarvisに依頼 | Claude Codeで続行 | 人判断のみ

担当メモ: （1行。未配線・自動化できてない点があればここ）

橋渡し: 松野が了承したら、上記の担当へ一声（当面は人が橋）
```

### 書き分け

| `次:` | 意味 | 了承後 |
|---|---|---|
| `Grokで続行` | 文案・方針・チャンネル内で足りる | Grok メイン／部長に「これで続けて」 |
| `Jarvisに依頼` | Mac 実行・秘密・対外ゲート・スクリプト | Cursor（Jarvis）に「これやって」。枠切れなら Claude Code 等（813） |
| `Claude Codeで続行` | リポ実装・点検・BCP 再開（git `TASK.md` 本線） | Claude Code に「これで続けて」。受け渡し: [`43_`](43_Claude_Code参加_受け渡し_20261023.md) |
| `人判断のみ` | 方針・金額・対外了承など人だけ | 実行依頼は出さない。決めたら別途 |

`担当メモ` には例えば:

- 「まだ Jarvis に頼めてない（手動のまま）」
- 「311 ゲートまで済・送信了承待ち」
- 「Todoist オーナー確認に既起票」

## inbox（`action: slack_report` · `channel: consult`）

```
---
action: slack_report
channel: consult
source: hawk
bot: ホークアイ（参謀）
kind: 要判断
title: （短い題）
---

（判断材料の要約）

次: Jarvisに依頼

担当メモ: Mac で ○○ を実行してほしい

橋渡し: 松野が了承したら Jarvis へ一声
```

Jarvis の `jarvis_grok_slack_report_apply.py` は、`channel: consult` で末尾に `次:` が無いとき **補完行**を付ける（忘却防止）。既存末尾も **次／担当メモ／橋渡しの間に空行**を正規化する。

## 将来（やらない・後回し）

| 段階 | 内容 |
|---|---|
| 第2 | `#consult` リンク集約・リマインド |
| 第3 | Slack リアクション／Yes-No で橋渡し短縮 |
| 以降 | ChatGPT 等 Connect（同じ末尾型を共有） |

## 入口・確認・履歴・停止

- 入口: Drive `10_inbox_from_grok/` · Grok paste（ホーク／部長）
- 確認: 松野が `#consult` を見て橋渡し
- 履歴: Slack スレ／必要なら Todoist
- 停止: 末尾型をやめるときは paste から本節を削除し、本 MD を `disabled` 相当で閉じる

## 関連

- paste: `config/grok_sanbo_bot_grok_paste.md` · `config/grok_realestate_bucho_grok_paste.md`
- フォーク: `config/grok_jarvisbox_fork_policy.md`
- 日次集約: [`33_`](33_Slack日次集約_第1段階_20261017.md)
- Jarvis が Slack 差分に気づく: [`37_`](37_Slackハブ_Jarvis読取_20261018.md) · `.cursor/rules/jarvis-slack-hub-watch.mdc`
