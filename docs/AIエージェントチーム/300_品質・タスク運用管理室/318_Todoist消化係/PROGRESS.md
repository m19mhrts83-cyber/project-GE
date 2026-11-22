# 318 PROGRESS

更新: 2026-11-23（①自律実行・既定オフ）

## 朝に松野さんが決めること（全部いまはオフ・未登録）

| # | 決めること | 有効にする方法 | 今 |
|---|---|---|---|
| 1 | 掲載: ②を /313/bulk、③を今週の9件に載せる | `--publish`（Supabase sync_meta に書く・画面に出る） | オフ（11/23 01:17 に1回だけ実地確認: /313/bulk に2件表示、313 の質問中1件は重複なし） |
| 2 | 送信: #consult 判断依頼・#ai-hub 終了報告 | `--send-slack` | オフ |
| 3 | コメント: 変化のあった件に【318】コメントを追記 | `--write-comments` | オフ |
| 4 | 10:30 移管: 313 の 0.5 を止めて 318 を定時に | [`移管手順_10時30分.md`](./移管手順_10時30分.md) の順番 | 担当 313・未登録 |
| 5 | ①自律実行: ① の件を AI が調査・資料確認・文面下書きまで進める | `--execute-auto`（材料出し）→ Claude Code が作業 → `--execute-auto --work-results …`（取り込み） | オフ（実装済み・実データは dry-run だけ） |

- 4 と 5 は一緒に決めるのがよい。5 を有効にしても、作業（2 段目）は Claude Code の実行が要る。launchd だけでは材料出しまでしか進まない
- 5 の範囲は「調査・資料確認・文面下書き」まで。許可範囲のコード修正・テスト・PR 作成は将来（今は申告されたら②へ止める）
- /313/bulk での 318 の件の推奨は「残す」のまま。完了・削除の推奨を出すか（Phase 2 から持ち越し）

## ①自律実行（ノード2-1・2-2）— 実装済み・PR レビュー待ち。既定オフ（`--execute-auto`）

- [x] 部品: `scripts/jarvis_todoist_318_work.py`。作業範囲は基準ファイルの `work_scope`（decision_id 付き・調査／資料確認／文面下書きだけ）。読めなければ ① を始めない（分類は続ける・部分成功）
- [x] 回し方（追加の有料 AI API なし。Phase 1 の packet → answers と同じ形）
  1. `run --execute-auto` → 2-2 を通った ① だけ `work/packet.json` に作業の材料（題・説明・直近コメント・やる予定・許可された作業・止める操作）
  2. この実行の Claude Code が材料を読んで作業し、`work/results.json` を書く（status: done／partial／needs_decision／needs_owner・summary・artifacts・remaining・actions_taken・requested_operations）
  3. `run --execute-auto --work-results .jarvis_state/todoist_318/work/results.json` → 2-2 → 成果物を `work/<task_id>/<run_id>/`（＋progress.json）へ。進捗・成果物・残作業を判断履歴 `work_318` へ
- [x] 2-2 始める前: 停止スイッチ・時間上限・1回5件 → 着手しない（hold）／承認待ち → 本人の回答が来るまで再実行しない／承認が要る語（送信・削除・支払・契約・マージ・デプロイ・依頼…）→ ②／本人操作 → ③／大規模 → 週次（「318: 大規模（週次で進め方を決める）」）
- [x] 2-2 取り込む直前: 範囲外の操作を申告 → 成果物を取り込まず②／承認が要る操作の申告・判断を求めた → ②（承認待ち）／本人操作 → ③／材料を出した後に内容が変わった・3日より古い・材料に無い → 使わない／今の内容が読めない → 取り込まず材料に残す／停止スイッチ・時間上限 → 残りは材料に残す（中断点）
- [x] Todoist は閉じない（この部品は Todoist に触らない）。結果待ちの間はコメントしない。取り込んだ回だけ【318】コメント（やり切った／途中／要判断／本人作業。`--write-comments` の時だけ）
- [x] dry-run: 材料（やる予定）までは出すが、成果物・判断履歴は作らない。dry-run で取り込んでも材料から外さない
- [x] テスト: `scripts/tests/test_todoist_318_auto_exec.py` 25 件（全体 1205 件 OK）

### 手動実行（2026-11-23 1:26・実データ・dry-run・読むだけ・state は scratch のコピー）

- `--execute-auto` だけ: 変化のあった 5 件はすべて②（ルール）→ 着手 0・材料 0
- 仕組みの確認として、AI 見直しの回答で 2 件を①にして実行（**確認用の回答で、本採用の判断ではない**）
  - 大規模の1件 → 週次へ（着手しない）
  - もう1件 → 材料 1 件（許可された作業は調査・資料確認・文面下書き）
- 成果物 0・書き込み Todoist 0・Slack 0・Supabase 0

## Phase 3 準備（コメント・10:30 の取り決め・① の予定）— マージ済み（#586）。有効化はしていない

- [x] 【318】コメント（node_format_log・node_comment）: `scripts/jarvis_todoist_318_comment.py`
  - 内部ログと判断履歴を保存できた本実行の後だけ・変化があって分類し直した件だけ。`--write-comments` を付けた時だけ（dry-run では書かない）
  - 中身: 処理状態（① 途中／② 要判断／③ 本人作業）・要約・成果物・残作業／必要な判断・末尾に `処理ID: <run_id>`。下書きは毎回 `runs/<run_id>.json` の `comment_draft`
  - 前回と同じ中身は書かない（処理ID を除いた指紋）。投稿前に Todoist のコメントを読み、同じ処理ID・同じ中身の【318】があれば書かない（読めなければ書かない）
  - 送る前に「送信中」を判断履歴へ保存（保存できなければ送らない）。応答不明（時間切れ・5xx・id なし）は照合待ち → 次の回に処理ID を探して、あれば投稿済み・無ければ同じ処理ID で再送・読めなければ待ったまま
  - はっきり失敗（4xx）は次の回に重複確認のうえ再送（3回で止めて人の確認待ち）。1 回 5 件まで
  - 317 の除外（webhook_handle・dispatch）を毎回確かめ、外れていたら書かない。書き口は POST /comments だけ（完了・削除・期限変更の口は無い）
- [x] 10:30 の取り決め: `scripts/jarvis_todoist_morning_slot.py`（朝枠の担当＝無ければ 313・朝枠ロック・313 の作業跡）。`run --trigger schedule` は担当が 318 の時だけ動く
- [x] launchd の雛形（未登録）: `launchd/com.matsunoma.jarvis.todoist-318.plist.template`・runner・install（`--yes` と担当 318 が要る）・uninstall
- [x] 移管手順（止める順番・戻し方）: [`移管手順_10時30分.md`](./移管手順_10時30分.md)。313 の予定タスクは変えていない
- [x] ① は実行しない。`planned_action`（executed=false・やる予定の内容・上限）を内部ログに記録。AI 見直しの回答に `plan` を書けばそれを使う
- [x] 直した点: 止まった・失敗した本実行のログしか無い時に「履歴が消えた」と誤って止まっていた（朝枠の見送りで毎回起きる）→ 履歴を書いた回（success／partial）だけ数える
- [x] テスト: `scripts/tests/test_todoist_318_phase3.py` 32 件

### 手動実行（2026-11-23 1:10・実データ・dry-run・Todoist と owner_decisions は読むだけ・state は scratch のコピー）

- `--trigger schedule`（担当 313 のまま）: Todoist を読まずに見送り（stopped・exit 0）
- 手動 dry-run: 確認 15（変化なし 10）／②5（大規模 3）→ success。コメント下書き 5 件、すべて 317 の除外に当たる
- 書き込み: Todoist 0・Slack 0・Supabase 0

## Phase 2（/313/bulk・週次・本人回答・通知）— 実装済み・PR レビュー待ち。載せる・送るは既定オフ

- [x] 本人回答の読み戻し（owner_decisions surface=todoist_313）。読めなければ安全停止。回答だけ変わった件は聞き直さない。再評価: 日を変える→その日／残す→14日後
- [x] ② → /313/bulk: `sync_meta.todoist_318_bulk_queue`（`--publish`）。`jarvis_todoist_cleanup_bulk.py` が混ぜる（3日より古いキュー・「残す」14日中・閉じた件・重複は出さない）。画面に「318 判断依頼」・期限・前回判断を表示。判断の記録は payload.label=`318判断依頼`・origin=`318`
- [x] ③ → 今週の9件: `sync_meta.todoist_318_weekly_handoff`（`--publish`）。`jarvis_todoist_weekly_pick.py` が候補に入れる（理由 `handoff_318`・+20点）
- [x] #consult 通知案（新しく待ちに入った件だけ・1回）と #ai-hub 終了報告案を `drafts/` に保存。`--send-slack` の時だけ送る。#consult は `--publish` で載っていない時は送らない
- [x] 313 との二重質問防止: 313 の 20:00 片付けが36時間以内に出した件は 318 が載せない／318 が載せた件（`bulk_queue.json` published=true）は 313 が出さない／313 の状態が読めない時は②を載せない（部分成功）
- [x] Phase 3 の前提: 317（`jarvis_todoist_webhook_handle.py`）は投稿者 uid でしか自分を除いておらず、本人トークンで書く【318】は人のコメントとして受領を返していた → 先頭【318】を処理済みにして返さない除外を追加（dispatch の報告・Phase B にも数えない）。有効化（318 がコメントを書く）はまだ
- [x] テスト: Phase 2 で 27 件追加（全体 1144 件 OK）、loopware の cleanupBulk テスト 1 件追加

### 手動実行（2026-11-23 0:54・実データ・Todoist と owner_decisions は読むだけ・載せない・送らない・state は scratch のコピー）

- 1回目: 確認 5／①0 ②4 ③1／本人回答 11件読込・回答取込 0／/313/bulk 待ち 3（313 で質問中 1 を除外）／週次へ 1 → success
- 2回目: 確認 10（変化なし 5）／①1 ②4 ③0／待ち 7・週次へ 1 → success
- 書き込み: Todoist 0・Slack 0・Supabase 0。既存の片付け材料・週次ピックの dry-run は従来どおり（318 のキーが無い）

## 朝に松野さんが決めること（Phase 2 の時点・上の表に統合済み）

- [ ] `--publish` を付けて /313/bulk と今週の9件に実際に載せるか（Supabase sync_meta への書き込み。画面に出る）
- [ ] `--send-slack` で #consult（判断依頼）と #ai-hub（終了報告）を送るか
- [ ] /313/bulk で 318 の件の推奨を「残す」にしている。完了・削除の推奨を出すかどうか


## Phase 1（読むだけ・手動）— 実装済み・PR レビュー待ち

- [x] 開始チェック: 停止スイッチ（`.jarvis_state/todoist_318/STOP` か `TODOIST_318_STOP=1`）・排他（`run.lock`、O_EXCL。他人のロックは外さない）・313 との重なり（作業ロック表の 313 running／10:15–11:30）・Todoist 接続・本人権限（`TODOIST_API_TOKEN_OWNER` で `/user`）
- [x] 1-1 基準: `config/todoist_318_criteria.yaml`。`adopted`（出典・decision_id 付き）だけが ① の根拠になる。`proposed` は ②③（実行しない側）への手がかりだけ。313 の「残す」記録（`todoist_313_judgments.json`）を `jarvis_todoist_313_judgment.is_kept/fingerprint` で再利用。無い・壊れているは安全停止
- [x] 1-2 抽出: 今日まで＋締切3日以内・担当が自分か未割当。v1 の全ページを辿り、途中で切れたら失敗（0件扱いにしない）
- [x] 1-3 変化なし: 項目ごとのハッシュ（題そのものは残さない）。【318】自身と 317 の受領の返し（【AIチーム】見たよ）は変化に数えない。コメント数（note_count）が前回と同じならコメントを読まない
- [x] 1-4 3分類: ルール → この実行の Claude Code が `--ai-answers` で見直し（追加の有料 API なし）
- [x] 内部ログ: `runs/<run_id>.json`（分類根拠・適用 decision_id・判断案・停止理由・次回再評価条件・処理日時・報告案）、`history.json`（本実行だけ更新）
- [x] テスト 35 件

### 313 の順位付けから直した点

1. 部分文字列の誤判定: 「高」「優先1」などを題の部分一致で加点していた（「高い」「優先10」「URL の中の語」でも当たる）→ ラベル完全一致・題の【】[] タグ・Todoist の優先度だけで見る。URL は除いてから語を見る
2. 同点集中: `min(超過日,60)` で古い件が同点になり、毎日同じ5件が先頭に来た → 段（締切・外との約束 → 今日の割り振り → ほかの期限切れ）→ 優先度 → 重要の印 → **最後に見た日が古い順** → 超過日数 → id
3. 読取の取りこぼし: 313 overdue は `/tasks?filter=overdue&limit=200`（v1 は filter を無視・1ページだけ）→ 全ページを辿り、上限なら失敗

### 手動実行（2026-11-23 0:36〜0:39・実データ・読むだけ・state は scratch のコピー）

- ドライ（ルールだけ）: 候補 67／確認 5／繰越 62／変化なし 0／① 0・② 4・③ 1 → 判定 success
- ドライ（AI 見直し後）: ① 0・② 1・③ 4 → success
- 本実行 2 回目: 確認 10（変化なし 5 をスキップ）／① 1・② 4・③ 0 → success
- 本実行 3 回目: 確認 15（変化なし 10、うち 10 件はコメントを読まずに判定）／② 5（大規模 3） → success
- Todoist 書き込み 0・Slack 0（ログの `writes` で確認）。ログ・履歴にタスク名なし

## Phase 2 へ持ち越す確認事項

- [x] 10:30 定時起動と 313 0.5 の分担（Phase 3 準備で朝枠の担当・ロックを取り決め。移管は未実施）
- [ ] `proposed` 基準（③本人操作の語・大規模の語）を採用するか。採用なら `adopted` と decision_id を付ける
- [ ] AI 分類を毎回 Claude Code で回すか（packet → answers の2段）。定期起動時の回し方
- [x] `/313/bulk` への登録方法と回答の取り込み先（Phase 2 で実装）
- [ ] 313 0.5 の【Miss Lemon】コメントも「変化あり」になる。0.5 と 318 の役割を分けたら除外するか
- [x] 317 が【318】コメントを処理しないこと（Phase 2 で除外を追加）
- [ ] 担当が他人の件を除いている。共有プロジェクトの扱いでよいか
