# Slack 書き出し — FRIDAY／Jarvis／AI社員（2026-10-18）

社員 `CLAUDE.md` §報告先・FRIDAY キット・ハブ指示から参照する **1節の正本**。

## どの ch に書くか

| ch | いつ書く | 誰向け |
|---|---|---|
| **`#ai-hub`** | Hawk／FRIDAY／Jarvis 同士の進捗・共有・手渡し。**Jarvisへの依頼・確認もここ** | **エージェント同士**（共有本線） |
| **`#report`** | 完了・定型サマリ・「動いている」生存確認。**松野への情報共有のみ**（判断・依頼は書かない） | 松野が流し見 |
| **`#consult`** | 松野の要判断・迷い・Yes/No（Jarvis宛の依頼は #ai-hub へ） | 松野の確認トレイ |
| **`#ops`** | 障害・失敗・認証切れ・枠切れ・健全性アラート **およびその是正結果** | すぐ手当て＋後から振り返り／他AI共有 |

| 実行者 | 残すもの |
|---|---|
| **Jarvis（Cursor）** | エージェント共有→`#ai-hub`。松野向け完了→`#report`。要判断→`#consult` |
| **FRIDAY（GenCode）** | Jarvisへの依頼・確認→`#ai-hub`。松野向け完了→`#report`。松野の要判断→`#consult`（チャットだけに閉じない） |
| **ホーク（Grok）** | エージェント同士の共有→`#ai-hub`（または `slack_report` channel: hub）。要ボス→`#consult` |
| **AI社員（定期／イベント）** | 各 `CLAUDE.md` の報告先どおり（人向けは従来3ch。横断共有は `#ai-hub` 可） |

壁打ち・長考は Grok チャンネル可。**残す報告は Slack**（Drive は Mac 実行手渡し用・併用）。  
`#ai-hub` に「決めて」と書かない。松野判断は `#consult`。

### `#ops` に是正結果を残す（必須 · 2026-10-18）

障害を直したら、アラートだけで終わらず **是正結果を `#ops` に1通**残す。他AI・後日の自分が同じ型を再利用できるようにする。

| 含める | 例 |
|---|---|
| 事象 | いつ・どの run／ログ・どう見えたか |
| 真因 | 取込失敗 vs push 競合 vs 点検誤報、など混同しやすい点を明示 |
| 是正 | 何を直したか（コミット／ファイル／手順） |
| 残 | 任意の人手（再実行など）。無ければ「残なし」 |
| 再利用メモ | 同型が来たときの見分け方 1〜3 行 |

書き出し例: `【ops】315 連携健全性 — 是正結果（振り返り用・共有）`  
正常時の長文定型は従来どおり出さない。**障害対応のクローズ報告だけは長め可。**

## レイアウト（iPhone 必須 · 2026-10-19）

見る端末はほぼ **iPhone Slack**。Webhook は平文のため、`#report` / `#consult` / `#ops` / `#ai-hub` すべてで守る。本日分・夕方・仲介返信パック・S1 関連も同じ。

| ルール | 内容 |
|---|---|
| 要ボス先頭 | 先頭に **📌要ボス** 最大3つ（無ければ「要ボス: なし」） |
| 1項目の長さ | スマホで **2行以内**。入れ子の箇条書き・（）内の長文は使わない |
| 管理情報 | 楽待ID・msg番号・時刻などは末尾 **参考** か **スレッド**へ |
| 変化なし | 変化なしの項目は1行にまとめる |
| 区切り | セクション間は空行、見出しは短い絵文字＋語句 |
| `#consult` 末尾 | 「次／担当メモ／橋渡し」3行は維持（[`36_`](./36_Slack_consult手渡し_次の担当_20261018.md)） |
| **FB 案内（Phase 0）** | `#report` / `#consult` は末尾に `FB: スレ返信で（先頭に 見栄え／内容／方針）`（Webhook 自動付与。[`40_`](./40_Slack報告FB_スレ拾い_20261020.md)） |
| 出さない | 深いネスト・docs 長パス・エラー長文・等幅の表 |

正本の詳細・意図OKイメージ: [`33_Slack日次集約`](./33_Slack日次集約_第1段階_20261017.md)「レイアウト」。  
**スマホ行長・空行・過去FBの統合草案**: [`41_Slackスマホレイアウト_草案_20261022.md`](./41_Slackスマホレイアウト_草案_20261022.md) · `.cursor/rules/jarvis-slack-mobile-layout.mdc`  
Grok 定型報告の入口: [`17_Grok定型報告_Slack_20261010.md`](./17_Grok定型報告_Slack_20261010.md)。

## 先頭1行（必須）

番号＋短い役割語／ツール名。例:

- `【共有】Jarvis アプリ開発 Drive取込完了`
- `【報告】211 返信案内下書き・朝便`
- `【相談】311 送信前品質`
- `【ops】315 連携健全性`

詳細: ハブ [`CLAUDE.md`](./CLAUDE.md)「Slack 書き出し」· `.cursor/rules/jarvis-agent-team-slack-report.mdc`

## `#consult` 末尾（必須 · 次の担当）

自動実行ではない。松野が読んで橋渡しする。

```
次: Grokで続行 | Jarvisに依頼 | Claude Codeで続行 | 人判断のみ
担当メモ: （未配線・自動化できてない点があれば1行）
橋渡し: 松野が了承したら、上記の担当へ一声（当面は人が橋）
```

| `次:` | 了承後 |
|---|---|
| `Grokで続行` | Grok メイン／部長へ一声 |
| `Jarvisに依頼` | Cursor（Jarvis）。枠切れなら Claude Code 等 |
| `Claude Codeで続行` | Claude Code（git `TASK.md`）。受け渡し [`43_`](43_Claude_Code参加_受け渡し_20261023.md) |
| `人判断のみ` | 実行依頼を出さない |

正本の読み方: [`36_Slack_consult手渡し_次の担当_20261018.md`](./36_Slack_consult手渡し_次の担当_20261018.md)

## 投稿の手段（Webhook 本線 · 2026-10-18）

**残す報告（`#ops` 是正結果・`#report`／`#consult`／`#ai-hub`）は Incoming Webhook を本線にする。**  
理由: Webhook 投稿は端末通知が入り、「何か来た」が分かる。Slack MCP の `slack_send_message` は読取向きで、通知が弱い／入らないことがある。

| 用途 | 正 |
|---|---|
| **投稿（本線）** | `scripts/jarvis_slack_webhook_post.py`（`SLACK_WEBHOOK_AI_TEAM_*`） |
| **読取** | Cursor Slack MCP（`slack_read_channel` 等） |
| **例外** | Webhook 未設定（Cloud Secrets 無し等）のときは MCP 投稿可。あるのに MCP だけで済ませない |

**本線は Incoming Webhook**（Bot 投稿 → プッシュ通知が出る）。  
Slack MCP の本人投稿は通知が出ないので、報告／ops／consult の第一選択にしない。

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
~/selenium_env/venv/bin/python scripts/jarvis_slack_webhook_post.py \
  --channel ops --username '315 連携健全性' \
  --text '【ops】315 連携健全性 — 是正結果（振り返り用・共有）
…'
# report / consult / hub / deal も同様（--channel report|consult|ops|hub|deal）
# hub の別名: --channel ai-hub
```

| チャンネル | env（`.env.jarvis_private`／Cloud Secrets） |
|---|---|
| `#report` | `SLACK_WEBHOOK_AI_TEAM_REPORT` |
| `#consult` | `SLACK_WEBHOOK_AI_TEAM_CONSULT` |
| `#ops` | `SLACK_WEBHOOK_AI_TEAM_OPS` |
| `#ai-hub` | `SLACK_WEBHOOK_AI_TEAM_HUB`（未設定時は REPORT フォールバック＋`【#ai-hub】`） |
| `#deal-active` | `SLACK_WEBHOOK_AI_TEAM_DEAL_ACTIVE` |

| 実行場所 | env の取り方 |
|---|---|
| Mac / Self-hosted | `.env.jarvis_private` を `source` |
| **Cloud Agent** | My Secrets の `SLACK_WEBHOOK_AI_TEAM_*`（`jarvis_cloud_secrets_prepare.py --slack-only --apply`） |

秘密・Webhook URL・トークンは本文に書かない。  
**Cloud Agent**: Secrets があれば Webhook。無いときは MCP で投稿してよい（可能なら Secrets／Mac Webhook も提案）。  
Cloud 詳細: [`docs/Jarvis_Cloud_Agent.md`](../../Jarvis_Cloud_Agent.md)「Slack Incoming Webhook」。

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
