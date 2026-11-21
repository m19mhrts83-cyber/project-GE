# 714保存済み議事録から312へ渡す契約

2026-11-22本人承認。新しいAI・DB・テーブルは追加しない。議事録本文・担当者・会議IDの実値は公開資料やテストへ入れない。

## 実行の順序

1. 既存714のscanで未処理を確認する（全ページ取得、家族会議・保存済みを除外）。
2. 既存エージェントが52_形式に整理するときに本人TODO候補を同時抽出し、Git対象外のJSONにする。
3. `curate prepare --file` で検証・保存する。抽出済み0件も明示する。これはNotion了承ではない。
4. 整理済み本文を見せてNotion保存了承を受けてから `apply --select N`。保存成功を会議ごと即時記録してからoutboxへ渡す。
5. 312は既存署名ボタンで1候補ずつ#consultへ。既存朝更新の `recover` は既知の未送信だけを回収する。
6. 起票／見送りを個別に選ぶ。Notion了承と起票了承は別。L1/L2は表示区分で、会議候補はどちらも個別了承が必須。
7. 登録直前にTodoistの未完了一覧を再取得して件名・期限を照合。照合失敗・一覧の途中打切りは登録しない。候補IDの排他と永久終端状態で再押下・完了後再登録・再提案を防ぐ。
8. Task IDを先に記録し、出典コメント・owner_decisions・#reportを残す。失敗・不明な結果は#ops。作成応答・コメント・通知が不明な場合は再送しない。

CLIの略称curateは `scripts/jarvis_meeting_minutes_curate.py`。認証は既存環境変数を読み、値をログへ出さない。

## prepare入力の最小形（すべて架空）

```json
{
  "meeting_id": "synthetic-meeting",
  "extracted": true,
  "body": "## ひとことで\n検証用\n## 決まったこと\n入力を確認する\n## ToDo\n担当・内容・期限を記載\n## 次回\n未定",
  "candidates": [{
    "todo": "Check synthetic input",
    "assignee": "matsuno",
    "evidence": "explicit owner assignment in source",
    "due_raw": "",
    "due_date": null,
    "lane": "ai_raimo"
  }]
}
```

担当原文と根拠を保持し、既知の本人表記だけを本人と扱う。不明な話者や省略名を推測して本人へ割り当てない。不明担当はheld。相対期限・年のない日付は、確認を得てdue_confirmed=trueにするまで日付を作らない。0件はcandidates=[]。

候補IDはv1・会議ID・NFKC/空白正規化した省略前TODO・担当のhash。表示番号・切詰めた件名・順序・期限をIDに使わない。714準備済み会議を既存digestが再抽出しない。他の312入口・collect/reflect・旧payloadは維持する。

## 状態と保管

- ローカル: `.jarvis_state/meeting_minutes_prepared/`、`meeting_minutes_curate.json`、`meeting_todo_outbox.json`。private_sync_pathsで非公開バックアップ。ローカルの実行はflock、JSONは権限600の一時ファイルからatomic置換。
- クラウド: 既存sync_metaの `meeting_todo:v1:<候補ID>`、valueはJSON文字列。insertは既存行を上書きしない。読んだupdated_atを条件に更新し、版を必ず進めて並行操作を排他。長い本文をURLの比較条件へ載せない。
- 状態: queued→posting→posted→creating→finishing→created。dismissedは永久終端。heldは投稿しない。owner_decisionsは候補ID単位で採否・出典・Todoist IDを記録する。
- 既存の件名14日抑制とは分離する。会議候補の登録・見送りは14日経過後も再提案しない。
- `JARVIS_MEETING_TODO_DISABLE=1` は候補投稿と新会議ボタン処理を停止（MacとDashboardの両環境）。714自体の停止は既存disableを使う。

## 失敗からの戻し

Notion保存前にattemptを記録する。応答不明・保存後のstate更新失敗は、Notionを会議IDで人が照合し、見つかったpage_id/notion_urlを既存savedへ補ってから再開する。自動でページを再作成しない。上限超過の本文など、API未実行が確認できる場合だけattemptを照合して解除する。

Notion保存済みで配送だけ失敗した会議は朝recoverで回収する。保存前会議や従来のsaved6件は自動配送対象にしない。posting/creating/finishingやuncertainのままは配送先/Task IDを確認して既存候補行を復旧する（秘密値や実データを公開CLIへ貼らない）。Task IDがあれば再作成しない。コメント・判断ログ・通知の部分失敗も再起票せず人が照合する。

## 検証と適用境界

初回の過去Notion保存済み6件は既存取得CLIで要約を読み、抽出だけを試した。合計18件、本人担当を機械的に確定できたもの0件、本人未確定として保留18件、候補0件の会議2件。これは保守的なAction Items/日本語アクション項目/ToDo表の抽出であり、本文全体のAIレビューでTODOがないと保証する結果ではない。原文・担当名は非公開の作業stateだけに保持した。

本番sync_meta更新・Slack実投稿・Todoist実起票・Notion作成・デプロイ・マージは実行していない。新経路の通し動作はモック検証で、実サービスの受入れは別了承後。FlowForgeの図は実行プログラムではなく運用定義。

## FlowForge

714: [共有](https://flowforge-259747770348.asia-northeast1.run.app/share/HI4KOYwORPb7ZG1d)、flow_q41qaFFwQ_pX4m6qg04oLb3H、7ノード/6辺。
312: [共有](https://flowforge-259747770348.asia-northeast1.run.app/share/vg-hTz_zTJwBGVMK)、flow_k3luzQfsGTzYu7-2q5fibdXd、11ノード/8辺。

2026-11-22、所有・鮮度確認→写し→明示操作→クラウド同期→共有API照合で両方verified=true。714は人が画面で作成した所有フローを整形。直接新規の下書きは所有登録403で共有できず、削除了承がないためローカルに残した。既存9フローの内容・欠落は0、開いていた315系は同期済み。旧下書きはregistryに登録しない。


## 本人表記の非公開設定（2026-11-22改訂中）

公開コードに本人名の正規表現は持たず、config/meeting_owner.private.json（ignore・private_paths/private_sync_paths登録済み）から読む。公開見本はconfig/meeting_owner.example.jsonで、呼び方の実値や会議IDは入れない。環境変数JARVIS_MEETING_OWNER_CONFIGで別の非公開パスも指定可能。

- owner_aliases: 確認済みの本人表記だけ。NFKC・大文字小文字・空白を正規化した完全一致で、似た名前を推測しない。
- other_aliases: 他人と確認できた担当表記だけ。候補はexcludedとして保持し、Slackへ出さない。
- meetings: 会議IDごとの担当表記→identity(owner/other)、confirmed=true、evidence(確認根拠)。確認済みの会議だけに適用。
- 私・自分などの一人称、役職、Speaker番号を全会議共通のaliasには登録できない。会議別の明示対応がなければ保留。複数担当は自動で本人だけを切り出さない。
- 内容からの本人推測（2026-11-22本人了承・緩めでよい）: 話者番号・一人称・役職は、整理AIが本文全体から本人と判断でき、根拠の引用があるときだけ候補に `owner_inference: {identity: owner, evidence: 引用}` を付ける。確認済みの会議別対応・他人表記が優先。名前付きの人には使わない。判定結果に basis=content_inference と根拠を残す。推測の本人候補も個別の了承（起票/見送り）は必須。根拠が弱いものは付けず保留。
- 会議別の対応（話者番号・誤記・他人）は非公開configの meetings に、判定・根拠の一言（evidence）・basis（owner_confirmed/content_inference）・手がかり（cues、最大5）を会議単位で保存する（add_meeting_mapping）。本人が了承した対応だけが対象で、自動では書かない・恒久基準にしない。他の会議へ広げず、次回の抽出では owner_hints（了承済みの本人側cues）を参考にするだけで、判定は会議ごとの対応か根拠付き owner_inference で行う。
- pending_aliasesなどの候補メモは判定に使わない。設定なしはpolicy_not_configured、破損・矛盾は停止。公開の旧正規表現へフォールバックしない。
- 判断理由と設定のfingerprintを候補に残す。queuedの本人判定は投稿前に現在設定で再確認。設定変更だけで保留候補を自動昇格・投稿しない。既投稿カードの見直し時は既存停止フラグで操作を止めて照合する。

今回の18件の旧保留理由は、未確認の名前表記12件、会議内話者番号と本人の対応不明3件、別の名前の明示担当3件。担当欄なし・一人称/役職だけ・複数担当は各0件。これらの本人/他人対応は本人確認中で、未確認の候補は有効にしない。原文・具体名・会議IDは非公開stateのみに保存する。
