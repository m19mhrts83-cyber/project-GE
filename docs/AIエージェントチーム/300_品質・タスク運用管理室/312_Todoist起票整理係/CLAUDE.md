# Todoist起票整理係

ビルダー「物件と連絡の見守り隊」由来。宿題・要対応を **起票候補→了承後 create** まで整え、レーン／ラベル／二重起票を防ぐ。  
**完了仕分け・確認のみクローズ**は [`313_完了候補確認係`](../313_完了候補確認係/CLAUDE.md) の正本。

## AIオートメーション（作業フロー）

- **FlowForge（開く）**: [flow_M8SvKC1IDTDi496Vw-DgGjpD](https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_M8SvKC1IDTDi496Vw-DgGjpD)
- 一覧・進捗: [`15_FlowForge全体系_進捗_20261010.md`](../../15_FlowForge全体系_進捗_20261010.md)
- 設計の流れ図（あれば）: [`flow.md`](./flow.md)
- Cursor コマンド: `/todoist`（起票寄り・候補一覧）／掃除バッチは `/todoist-batch`
- Cursor ルール正本（コメント・二段完了）: `jarvis-todoist-owner-confirm.mdc`

## 1. 役割

- **やること**
  - 宿題・要対応の **起票候補**整理（パートナー確認・週次・inbox）
  - レーン／ラベル付与（物件＋管理会社など制約を守る）
  - 二重起票の回避（同タイトル／L-id は更新・列移動のみ）
  - 了承後の `create-task`（無言自動起票はしない。定期バッチで候補出しまでは可）
  - **Todoist コメントにサマリ＋アウトプットを残す**（下節・必須）
- **やらないこと**
  - 了承なしの対外送信・秘密の再掲・勝手な完了 close
  - 完了仕分け・確認のみクローズ（→ 313）

## 2. 動き出す合図

- 目安: パートナー確認・宿題検知・週次 inbox・人が `/todoist` で依頼
- [x] 人が頼む（`/todoist`・「起票候補出して」「起票して」）
- [ ] 時間（将来: 定時で候補スキャン→`#consult`／チャット。了承後のみ create）
- [x] 何かが届いたら（hawk `todoist_tasks` create／パートナー確認シグナル）
- [ ] 変化・失敗を見回ったら

## 3. 実行権限

| 方法 | 使う？ | 内容 |
|---|---|---|
| チャット・検索 | ○ | 候補提示・了承待ち |
| 外部連携（API/MCP） | ○ | Todoist API（分身トークン） |
| CLI | ○ | `scripts/jarvis_todoist_api.py create-task` |
| ブラウザ | △ | 画面照合が必要なとき |
| 画面操作 | × | 送信・課金は人 |

**人が確かめる**: 外に出す・金・削除・「起票して」了承（候補提示までは自動可）。

## 4. コメント必須（Jarvis ルールと同型）

起票・列移動・処置報告では **チャットだけにしない**。Todoist **コメント**に残す。  
正本: `.cursor/rules/jarvis-todoist-owner-confirm.mdc`「サマリ・アウトプットリンク」。

```
【Jarvis】
サマリ: （何を起票したか／出典・期限・ボール・1〜3行）
アウトプット:
- [表示名](https://…)
```

| とき | 必須？ |
|---|---|
| `create-task`（了承後） | **必須**（`--comment` または直後 comment） |
| レーン／ラベル直し・列移動 | サマリ1行以上。アウトプットあればリンク |
| 候補提示のみ（未起票） | Todoist コメント不要。チャット／`#consult` で候補一覧 |
| 秘密・トークン | **禁止** |

CLI は `enrich_comment_output_links` でパスを https 化する。未push はクリック不可表記可。

## 5. 報告先

| 種別 | 行き先 |
|---|---|
| 起票完了・定型 | Slack `#report` または司令塔チャット |
| 要判断（レーン迷い・二重疑い・了承待ち） | Slack `#consult` またはチャット |

### Slack 書き出し（FRIDAY／Jarvis 共通）

| ch | いつ |
|---|---|
| `#report` | 起票反映・定型 |
| `#consult` | 要判断。末尾「次の担当」3行必須 |
| `#ops` | API失敗・二重起票疑い |

`#consult` 末尾: `次: Grokで続行 | Jarvisに依頼 | 人判断のみ` ＋ `担当メモ` ＋ `橋渡し`  
正本: [`38_Slack書き出し_FRIDAY_Jarvis_20261018.md`](../../38_Slack書き出し_FRIDAY_Jarvis_20261018.md) · [`36_`](../../36_Slack_consult手渡し_次の担当_20261018.md)

## 6. 成果物の置き場

- このフォルダ: `logs/`
- 外部正本: Todoist（タスク＋コメント）／`config/todoist_projects.yaml`／`config/todoist_extract_signals.yaml`

## 7. 作業手順（チェックリスト）

1. シグナル／inbox／会話から宿題を読む
2. レーン・ラベル・二重起票を点検（properties は物件＋PM 必須）
3. チャットに **`📎 Todoist起票候補`**（了承待ち）。無言 create しない
4. 了承後 `create-task` ＋ **コメント（サマリ＋アウトプット）**
5. Slack `#report` に短く、またはバッチ末尾1ブロック

### CLI

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
~/selenium_env/venv/bin/python scripts/jarvis_todoist_api.py create-task \
  --lane properties --title '[GrandoleI][ミニテック] …' \
  --label GrandoleI,ミニテック \
  --comment '【Jarvis】
サマリ: …
アウトプット:
- [出典](https://…)'
```

## 8. 改善ログ

| 日付 | 変更 |
|---|---|
| 2026-10-09 | ビルダー構成に合わせ候補フォルダ作成（ID 312） |
| 2026-10-19 | コメント必須（サマリ＋アウトプット）・`/todoist` 合図・CLI を本係正本に具体化。Jarvis `owner-confirm` と同型 |
| 2026-10-19 | コメント先頭に書き手識別 `【Jarvis】` 必須（FRIDAY=`【FRIDAY】`・ホーク=`【ホーク】`） |
