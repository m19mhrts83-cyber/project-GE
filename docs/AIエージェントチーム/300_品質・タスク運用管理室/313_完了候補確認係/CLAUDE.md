# Todoist完了候補確認（313）

**作業を始めたら、まず [`PROGRESS.md`](./PROGRESS.md) を読む**（続き・運用格上げがここにある）。

ビルダー「物件と連絡の見守り隊」由来。Todoist の完了候補を仕分けし、**確認のみは自動クローズ**、**要判断だけ人に残す**。  
**Todoist完了の本線は313**（起票は312）。作業フロー正本: [`flow.md`](./flow.md)

## AIオートメーション（作業フロー）

- **FlowForge（開く）**: [flow_6s1nyBIKzluSsdgR-hs9IolD](https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_6s1nyBIKzluSsdgR-hs9IolD)
- 一覧・進捗: [`15_FlowForge全体系_進捗_20261010.md`](../../15_FlowForge全体系_進捗_20261010.md)
- 設計の流れ図: [`flow.md`](./flow.md)（微修正はここを見て人が直す）
- Phase1: [`docs/phase1-l1-digest.md`](./docs/phase1-l1-digest.md)
- CLI: `scripts/jarvis_todoist_313_digest.py`（完了候補）／`scripts/jarvis_todoist_313_overdue.py`（期日超過の整理）
- Cursor skill: `todoist-batch-sweep`（`.cursor/skills/todoist-batch-sweep/`）
- Cursor コマンド: `/todoist-batch`（掃除・並列）／入口俯瞰は `/todoist`
- Cursor ルール: `jarvis-todoist-batch-sweep.mdc` / `jarvis-todoist-owner-confirm.mdc` / `jarvis-chat-open-complete-313.mdc`
- 起票側: [`312_Todoist起票整理係`](../312_Todoist起票整理係/CLAUDE.md)

## 0. 期日超過の整理（2026-10-22〜）

- 毎日20:00の2通目。**期限が今日より前**のタスクを上位**5件**に順位づけし、新期日案を `#consult` へ（完了候補とは**別投稿**）
- 番号は **📅N**（完了候補の **✅N** と区別）。返信「リスケ 📅3,📅5」
- 期日は了承後だけ動かす（`--apply --select 📅N`）。コメント必須
- Slack返信拾い: `scripts/jarvis_todoist_313_slack_ingest.py`（✅→close／📅→リスケ）
- 期限なしは対象外。完了（close）は本体フロー（下記）

## 1. 役割

- **やること**
  - 完了相当タスクを **確認のみ / 要オーナー判断** に分類
  - 確認のみ: オーナー確認経由で `complete-task`（Jarvis／同等CLI）
  - 要判断: オーナー確認列に残し、Slack `#consult` またはチャットで1行質問
  - 並列バッチ時は末尾1ブロックで報告（都度往復しない）
  - **処置・列移動・完了のたびに Todoist コメントへサマリ＋アウトプットを残す**（下節・必須）
- **やらないこと**
  - 了承なしの対外送信・秘密の再掲
  - 要判断・金・解約・対外を「確認のみ」扱いして close
  - オーナー確認列を飛ばした close（確認のみも一度は経由）
  - **コメント無しの close／列移動**（チャット報告だけでは不足）

## 2. 動き出す合図

- 目安: 実装・会話で完了相当／Todoist掃除・並列モード依頼
- [x] 人が頼む（`/todoist-batch`・「Todoist掃除」「確認だけで消せるものは完了」「閉じて N」）
- [x] ダイジェスト（`jarvis_todoist_313_digest.py` → `#consult`）
- [x] 時間（**毎日20:00** launchd `com.matsunoma.jarvis.todoist-313-digest` → L1 `#consult`。自動closeなし＝ソフト運用）
- [x] 何かが届いたら（hawk `owner_confirm` / `done` → スキャン合流）
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
| `#report` | 確認のみ完了一覧（先頭 `【報告】313 完了候補確認`） |
| `#consult` | 要判断／期日超過（先頭 `【相談】313 完了候補確認`。Webhook表示名も `313 完了候補確認`） |
| `#ops` | API失敗・二重起票疑い（`【ops】313 完了候補確認`） |

番号体系（スレ返信の取り違え防止）:

| 投稿 | 記号 | 返信例 | ボタン | 上限 |
|---|---|---|---|---|
| 完了候補 | **✅N** | `閉じて ✅1,✅3` ／ `✅1,3` | **完了する** | 最大5 |
| 期日超過 | **📅N** | `リスケ 📅2,📅4` ／ `📅2,4` | **→MM-DD へ延期** | 最大5 |

### Slack ボタン（L2・2026-10-22〜）

- 本線: Bot `chat.postMessage` ＋ Block Kit（`action_id` → `/api/slack/consult-action`）
- 予備: 署名付き URL（`/api/g/t313/close|reschedule/{task_id}`・開いただけでは実行せず確認画面）
- Todoist タイトルリンクは **詳細確認のみ**（押しても完了／延期しない）
- 秘密: `PROPERTY_GATE_ACTION_TOKEN`（署名）／`SLACK_BOT_TOKEN`（Bot投稿）／`TODOIST_API_TOKEN`（Vercel 実行）
- ヘルパー: `scripts/jarvis_todoist_313_slack_blocks.py`

`#consult` 末尾: `次: …` ＋ `担当メモ` ＋ `橋渡し`  
正本: [`38_Slack書き出し_FRIDAY_Jarvis_20261018.md`](../../38_Slack書き出し_FRIDAY_Jarvis_20261018.md) · [`36_`](../../36_Slack_consult手渡し_次の担当_20261018.md)

## 5. コメント必須（Jarvis ルールと同型）

バッチでも単件でも、**やったことは Todoist コメントに残して後から辿れるようにする**。  
チャット／Slack の報告は要約。証跡の正本はタスクコメント。  
正本: `.cursor/rules/jarvis-todoist-owner-confirm.mdc`「サマリ・アウトプットリンク」。

```
【Jarvis】
サマリ: （何を確認したか／なぜ閉じるか・残すか・1〜3行）
アウトプット:
- [表示名](https://…)
```

| とき | 必須？ |
|---|---|
| オーナー確認へ移動 | **必須**（何を見て了承するか） |
| 確認のみ `complete-task` | **必須**（先頭 `【Jarvis】タスク完了したよ（確認のみクローズ）` ＋サマリ＋アウトプット） |
| 通常完了（人了承後） | **必須**（先頭 `【Jarvis】タスク完了したよ`） |
| 処置・事実確認の途中報告 | **必須**（クローズしないときもコメント） |
| 秘密・トークン | **禁止** |

## 6. 成果物の置き場

- このフォルダ: `logs/`
- 外部正本: Todoist（コメント＋セクション）／`~/git-repos` のルール・skill

## 7. 作業手順（チェックリスト）

1. 対象タスクを読む（オーナー確認列／quick／表確認／要Jarvis連携）
2. **確認のみ / 要判断 / 除外** に分類
3. 各件に **コメント（サマリ＋アウトプット）** を先に（または complete と同梱）
4. 確認のみ: オーナー確認経由 → 定型コメント → `complete-task`
5. 要判断: オーナー確認に残し、聞きたいこと1行をコメント＋報告ブロック
6. バッチなら末尾1ブロックで報告（Slack `#report`／`#consult`）

### CLI

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
# L1ダイジェスト（#consult）
~/selenium_env/venv/bin/python scripts/jarvis_todoist_313_digest.py --dry-run
~/selenium_env/venv/bin/python scripts/jarvis_todoist_313_digest.py
# 確認のみ一括 close
~/selenium_env/venv/bin/python scripts/jarvis_todoist_313_digest.py --apply --auto-close-confirm
# 要判断（了承後・✅番号）
TODOIST_313_AUTHOR=FRIDAY ~/selenium_env/venv/bin/python scripts/jarvis_todoist_313_digest.py --apply --select '✅1'
# 期日超過（了承後・📅番号）
~/selenium_env/venv/bin/python scripts/jarvis_todoist_313_overdue.py --apply --select '📅3,📅5'
# Slack返信拾い（クラウド）
python3 scripts/jarvis_todoist_313_slack_ingest.py --dry-run
# FRIDAY が実行する時は TODOIST_313_AUTHOR=FRIDAY（先頭が【FRIDAY】。既定は Jarvis）

~/selenium_env/venv/bin/python scripts/jarvis_todoist_api.py update-status \
  --task-id … --lane apps --status オーナー確認
~/selenium_env/venv/bin/python scripts/jarvis_todoist_api.py complete-task \
  --lane apps --task-id … \
  --comment '【Jarvis】タスク完了したよ（確認のみクローズ）
サマリ: …
アウトプット:
- [表示](https://…)'
```

## 8. 改善ログ

| 日付 | 変更 |
|---|---|
| 2026-10-09 | ビルダー構成に合わせ候補フォルダ作成（ID 313） |
| 2026-10-19 | 確認のみクローズ／並列バッチ方針を本係の正本に具体化。Cursor skill・ルールと同期 |
| 2026-10-19 | 「コメント必須」節を独立。`/todoist-batch` 合図・チャットだけでは不足を明記 |
| 2026-10-19 | コメント先頭に書き手識別 `【Jarvis】` 必須（FRIDAY=`【FRIDAY】`・ホーク=`【ホーク】`） |
| 2026-10-21 | 312同型: flow本線・`313_digest`・運用格上げA〜E・`jarvis-chat-open-complete-313.mdc` |
| 2026-10-21 | 名称を **Todoist完了候補確認** に統一。Slack整形（件ごと空行）・タイトル＝Todoistリンク。**毎日20:00** のL1をlaunchd本線に |
| 2026-10-22 | Slackに **313番号＋役割語**。完了✅／期日📅で記号区別・各最大5件・別投稿。`313_slack_ingest` で番号返信を拾う |
| 2026-10-22 | L2ボタン: 完了／提案日へ延期（Block Kit＋`/api/g/t313`）。タイトルリンクは詳細のみ |
