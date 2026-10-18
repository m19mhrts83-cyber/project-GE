# 完了候補確認係

ビルダー「物件と連絡の見守り隊」由来。Todoist の完了候補を仕分けし、**確認のみは自動クローズ**、**要判断だけ人に残す**。

## AIオートメーション（作業フロー）

- **FlowForge（開く）**: [flow_6s1nyBIKzluSsdgR-hs9IolD](https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_6s1nyBIKzluSsdgR-hs9IolD)
- 一覧・進捗: [`15_FlowForge全体系_進捗_20261010.md`](../../15_FlowForge全体系_進捗_20261010.md)
- 設計の流れ図（あれば）: [`flow.md`](./flow.md)
- Cursor skill: `todoist-batch-sweep`（`.cursor/skills/todoist-batch-sweep/`）
- Cursor ルール: `jarvis-todoist-batch-sweep.mdc` / `jarvis-todoist-owner-confirm.mdc`

## 1. 役割

- **やること**
  - 完了相当タスクを **確認のみ / 要オーナー判断** に分類
  - 確認のみ: オーナー確認経由で `complete-task`（Jarvis／同等CLI）
  - 要判断: オーナー確認列に残し、Slack `#consult` またはチャットで1行質問
  - 並列バッチ時は末尾1ブロックで報告（都度往復しない）
- **やらないこと**
  - 了承なしの対外送信・秘密の再掲
  - 要判断・金・解約・対外を「確認のみ」扱いして close
  - オーナー確認列を飛ばした close（確認のみも一度は経由）

## 2. 動き出す合図

- 目安: 実装・会話で完了相当／Todoist掃除・並列モード依頼
- [x] 人が頼む（「Todoist掃除」「確認だけで消せるものは完了」）
- [ ] 時間（将来: 週次でオーナー確認列を仕分け）
- [ ] 何かが届いたら（hawk `owner_confirm` / `done`）
- [x] 変化・失敗を見回ったら（表確認カード・要フォローの事実確認）

## 3. 実行権限

| 方法 | 使う？ | 内容 |
|---|---|---|
| チャット・検索 | ○ | 仕分け結果の報告 |
| 外部連携（API/MCP） | ○ | Todoist API（分身トークン） |
| CLI | ○ | `scripts/jarvis_todoist_api.py` |
| ブラウザ | △ | 画面照合（表確認） |
| 画面操作 | × | 送信・課金は人 |

**人が確かめる**: 外に出す・金・削除・方針選択・自信なし。

### 確認のみ（自動 close 可）

- `[表確認]` / UI確認で一致・不一致が1行で出た
- 件数・有無など yes/no の事実確認だけ
- launchd resume 等、観測可能な復旧で宿題が消える
- 正本 state で既完了と分かるフォローのクローズ（再生成リスクをコメントに書く）

### 要オーナー判断（残す）

- 「検討する」「どうする？」・要ボス
- 資金移動・返済・カード退会・年額切替
- 対外メール／LINE 送信
- 実装方針が複数／失敗リスクが高い／エージェントが自信なし

## 4. 報告先

| 種別 | 行き先 |
|---|---|
| 完了報告（確認のみ一括） | Slack `#report` または司令塔チャット |
| 要判断 | Slack `#consult` またはチャット「オーナー判断待ち」 |

### Slack 書き出し（FRIDAY／Jarvis 共通）

| ch | いつ |
|---|---|
| `#report` | 確認のみ完了一覧 |
| `#consult` | 要判断。末尾「次の担当」3行必須 |
| `#ops` | API失敗・二重起票疑い |

`#consult` 末尾: `次: Grokで続行 | Jarvisに依頼 | 人判断のみ` ＋ `担当メモ` ＋ `橋渡し`  
正本: [`38_Slack書き出し_FRIDAY_Jarvis_20261018.md`](../../38_Slack書き出し_FRIDAY_Jarvis_20261018.md) · [`36_`](../../36_Slack_consult手渡し_次の担当_20261018.md)

## 5. 成果物の置き場

- このフォルダ: `logs/`
- 外部正本: Todoist（コメント＋セクション）／`~/git-repos` のルール・skill

## 6. 作業手順（チェックリスト）

1. 対象タスクを読む（オーナー確認列／quick／表確認／要Jarvis連携）
2. **確認のみ / 要判断 / 除外** に分類
3. 確認のみ: コメント（先頭 `タスク完了したよ（Jarvis・確認のみクローズ）`）→ `complete-task`
4. 要判断: オーナー確認に残し、聞きたいこと1行をメモ
5. バッチなら末尾1ブロックで報告

### CLI

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
~/selenium_env/venv/bin/python scripts/jarvis_todoist_api.py update-status \
  --task-id … --lane apps --status オーナー確認
~/selenium_env/venv/bin/python scripts/jarvis_todoist_api.py complete-task \
  --lane apps --task-id … \
  --comment 'タスク完了したよ（Jarvis・確認のみクローズ）
サマリ: …
アウトプット:
- [表示](https://…)'
```

## 7. 改善ログ

| 日付 | 変更 |
|---|---|
| 2026-10-09 | ビルダー構成に合わせ候補フォルダ作成（ID 313） |
| 2026-10-19 | 確認のみクローズ／並列バッチ方針を本係の正本に具体化。Cursor skill・ルールと同期 |
