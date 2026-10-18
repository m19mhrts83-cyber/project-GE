# （AI社員名）

複数ツール（Claude Code / Cursor / Codex / ChatGPT Work 等）から同じフォルダを開いて使う指示書。  
直した運用知見は**このファイルに追記**する（チャットだけの修正にしない）。

## AIオートメーション（作業フロー）

- **FlowForge（開く）**: （`agents_registry.yaml` の `flowforge_url` をここに貼る）
- 一覧・進捗: [`15_FlowForge全体系_進捗_20261010.md`](../../15_FlowForge全体系_進捗_20261010.md)
- 設計の流れ図（あれば）: [`flow.md`](./flow.md)

## 1. 役割

- やること:
- やらないこと:

## 2. 動き出す合図（4種のいずれか）

- [ ] 人が頼む
- [ ] 時間（スケジュール）: （例: 毎朝9時）
- [ ] 何かが届いたら（イベント）:
- [ ] 変化・失敗を見回ったら:

## 3. 実行権限

| 方法 | 使う？ | 内容 |
|---|---|---|
| チャット・検索 | | |
| 外部連携（API/MCP） | | |
| CLI | | |
| ブラウザ | | |
| 画面操作 | | |

**秘密**: このフォルダの `.env`（キーは `.env.example`）。追加・変更は必ず `~/git-repos/.env.jarvis_private` にも同期。値は MD に書かない。  
**人が確かめる（必須）**: お金・外に出す・消す。その他:

## 4. 報告先

| 種別 | 行き先 |
|---|---|
| 完了報告 | Slack `#report`（障害は `#ops`） |
| 要判断・相談 | Slack `#consult` |
| Webhook（秘密） | env キー名のみ記す（URLは書かない）: `SLACK_WEBHOOK_…` |

**書き出し**: 最初の1行に **`【報告】NNN 短い役割語`**（番号＋何をするか。「係」不要）。例: `【報告】211 返信案内下書き・朝便`。

### Slack 書き出し（FRIDAY／Jarvis 共通）

| ch | いつ |
|---|---|
| `#report` | 完了・定型・生存確認 |
| `#consult` | 要判断。末尾「次の担当」3行必須 |
| `#ops` | 障害・失敗・枠切れ |

`#consult` 末尾:

```
次: Grokで続行 | Jarvisに依頼 | 人判断のみ
担当メモ: …
橋渡し: 松野が了承したら、上記の担当へ一声（当面は人が橋）
```

正本: [`38_Slack書き出し_FRIDAY_Jarvis_20261018.md`](../38_Slack書き出し_FRIDAY_Jarvis_20261018.md) · [`36_`](../36_Slack_consult手渡し_次の担当_20261018.md) · ハブ `CLAUDE.md` · `.cursor/rules/jarvis-agent-team-slack-report.mdc`

## 5. 成果物の置き場

- 依頼・完了条件: [`TASK.md`](./TASK.md)（作業のたびに更新）
- 入力: `input/`（または外部パスを TASK に記す）
- 成果: `output/`（大きいものは Drive／OneDrive 正本＋パスメモ）
- 検証: `tests/`
- 設定: `config/`（秘密の値は置かない）
- 履歴: `logs/`
- 外部正本: （OneDrive / Drive / git-repos パス）
- 規格: [`30_共通Agentフォルダ規格_BCP`](../30_共通Agentフォルダ規格_BCP_20261017.md)

## 6. 作業手順（チェックリスト）

1. `TASK.md` に依頼・完了条件・executor を書く（status=running）
2. `input/` を確認して処理する
3. 成果を `output/`（または外部正本）へ。`tests/` を通す
4. 報告を Slack に送る。`TASK.md` を done／failed に更新

## 状態（作成・status変更時）

フォルダ名は変えない。`agents_registry.yaml` の `status` を直したあと:

```bash
cd ~/git-repos && ~/selenium_env/venv/bin/python scripts/jarvis_agent_team_status_sync.py
```

→ このフォルダに `00_🟢運用.md` 等（設計中以上）＋親部門の `00_状態ボード.md` が同期される。  
詳細: ハブ [`CLAUDE.md`](../../CLAUDE.md) / [`22_運用状態の識別`](../../22_運用状態の識別_20261011.md)

## 7. 改善ログ

| 日付 | 変更 |
|---|---|
| | |
