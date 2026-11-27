# Todoist消化係（318・仮）

**作業を始めたら、まず [`PROGRESS.md`](./PROGRESS.md) を読む**（どの Phase まで出来ているか・持ち越しがここにある）。

Todoist の未完了タスクを優先順に拾い、前回から変わっていない件は飛ばし、①AIのみ／②松野さんの判断／③本人操作に仕分ける。
② は `/313/bulk` で判断してもらい（本人回答は翌回に読み戻して再判定）、③ は 312「今週の9件」へ渡す（Phase 2・**載せる／送るはフラグを付けた時だけ**）。
Phase 3 準備として【318】コメント（`--write-comments`）と 10:30 の定時（313 0.5 との排他）を用意し、**2026-11-23 に 10:30 の枠を 313 から 318 へ移管済み**（松野さん了承。launchd 登録・担当 318・フラグ `--publish --send-slack --write-comments --execute-auto`。313 予定タスクは 2・3 段目に差し替え）。
① の自律実行（ノード2-1・2-2）は `--execute-auto` の時だけ。範囲は調査・資料確認・文面下書きまでで、成果物は内部（`work/`）に保存する。
**有効にするかは松野さんが決める**（[`PROGRESS.md`](./PROGRESS.md) の先頭の表）。

- 状態: **設計中**（registry の status は変えない。昇格は松野さんの了承後）
- 設計の正本: FlowForge [flow_HMy15MUxWiSpw5QgAPYa_8e4](https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_HMy15MUxWiSpw5QgAPYa_8e4)（承認済み 15 ノード・11 接続）。各ノードの説明文が仕様。読み方は [`flow.md`](./flow.md)
- 仕様を変えたい時は独断で変えない。300 ラス隊長に相談する
- 実装: `scripts/jarvis_todoist_318_triage.py`（本体）・`scripts/jarvis_todoist_318_handoff.py`（Phase 2 の部品）・`scripts/jarvis_todoist_318_comment.py`（【318】コメント）・`scripts/jarvis_todoist_morning_slot.py`（朝枠の排他）／基準: `config/todoist_318_criteria.yaml`／テスト: `scripts/tests/test_todoist_318_triage.py`・`test_todoist_318_phase2.py`・`test_todoist_318_phase3.py`
- 10:30 の移管: [`移管手順_10時30分.md`](./移管手順_10時30分.md)（止める順番・戻し方。launchd は 2026-11-23 登録済み）
- 関係: 起票は [312](../312_Todoist起票整理係/CLAUDE.md)、済み・やめるの週の整理（金曜）は [313](../313_完了候補確認係/CLAUDE.md)、コメント起動は [317](../317_コメント起動係/CLAUDE.md)

## 1. 役割

- **やること（Phase 1・いま動くもの）**
  - 開始チェック: 停止スイッチ・排他（ロックファイル）・313 との重なり・Todoist 接続・本人権限
  - 1-1 採用済み基準（`config/todoist_318_criteria.yaml` の `adopted`）と判断履歴（313 の「残す」記録・318 の履歴）を読む。読めなければ安全停止
  - 1-2 対象の抽出と並べ替え（今日まで＋締切が近い・担当が自分か未割当）。読取失敗は0件扱いにせず失敗終了
  - 1-3 前回から変化なしの除外（題・説明・期限・締切・優先度・ラベル・コメント・本人回答・親子の依存）
  - 1-4 3分類と根拠。**②は影響が大きい・お金・対外送信・削除・取り返せない・舵取りの印がある時だけ**。印が無い実務的で戻せる物は①（既定・`config/todoist_318_criteria.yaml` の `R1-DEFAULT-62`＝62_「聞く基準」・2026-11-27）。既定の基準が読めない時は従来どおり②。大規模は印だけ付けて既存タスクのまま
  - 内部ログ（`.jarvis_state/todoist_318/`・git 管理外）に分類根拠・採用基準・判断案・停止理由・次回再評価条件・処理日時と「報告案」を保存
- **やること（Phase 2・既定は案の保存まで）**
  - 本人回答の読み戻し: owner_decisions（surface=`todoist_313`・target_type=`todoist_task`。/313/bulk と旧 20:00 のボタン）の最新を毎回読む。読めなければ安全停止（`--owner-answers skip` を明示した時だけ読まない）
    - 回答だけが変わった件は「回答取込」として聞き直さない。再評価は「日を変える」→その日、「残す」→14日後、ほかの項目が後から変わった時
  - ② → `/313/bulk`: 回答待ちの ② を CleanupCard と同じ形で `sync_meta.todoist_318_bulk_queue` に置く（`--publish` の時だけ）。既存の `jarvis_todoist_cleanup_bulk.py`（GHA 30分ごと）が画面の材料に混ぜる。選んだ結果は既存どおり owner_decisions に残り、完了・削除・日を変えるは既存の reflect が反映する
  - ③ → 312「今週の9件」: `sync_meta.todoist_318_weekly_handoff`（`--publish` の時だけ）。週次ピックが候補に入れ、理由「318: 本人の操作が要る」を付ける（🤖 の件でも入る）
    - 週次側で判断の重さを付ける（2026-11-23）: ③（本人の操作）は「すぐ決まる」の手がかり、大規模（週次へ）は「じっくり」の手がかり（`config/todoist_weekly_weight.yaml`）。じっくりは週1件・火金の枠、すぐ決まるは月→水→金に前倒し
  - 通知・報告の案: `#consult`（新しく待ちに入った件だけ・1回だけ）と `#ai-hub`（終了報告）。`drafts/` に保存。**送るのは `--send-slack` の時だけ**。`#consult` は `--publish` で画面に載っていない時は送らない
  - 313 との分担（2026-11-24〜）: 318＝やり切る・判断を聞く、313＝金曜の「週の整理」（済みました・やめる提案）だけ。313 の毎晩 20:00 片付けは停止
  - 313 との二重質問の防止（同じタスクは片方だけ）: 313 の週の整理が /313/bulk に載せた件（`.jarvis_state/todoist_313_weekly.json` の `b_ids`・8日以内）と、旧 20:00 片付けが36時間以内に出した件は 318 が載せない。318 が載せた件（`bulk_queue.json` の published=true）は 313 の片付けが出さない。313 の状態が読めない時は ② を載せない（部分成功）
- **やること（Phase 3 準備・既定はオフ）**
  - 【318】コメント（`--write-comments` の本実行だけ）: 内部ログと判断履歴を保存できた後、変化があって分類し直した件だけに追記する
    - 中身: 先頭【318】＋処理状態（① 途中／② 要判断／③ 本人作業）・要約・成果物・残作業／必要な判断・末尾 `処理ID: <run_id>`。下書きは毎回 `runs/<run_id>.json` の `comment_draft`
    - 前回と同じ中身は書かない。投稿前に Todoist のコメントを読み、同じ処理ID・同じ中身があれば書かない（読めなければ書かない）
    - 送る前に「送信中」を判断履歴（`comment_318`）へ保存。応答不明は照合待ち → 次の回に処理ID を探してから（見つからなければ同じ処理ID で）再送。4xx は 3 回まで
    - 317 の除外（【318】を処理しない）を毎回確かめ、外れていたら書かない。1 回 25 件まで（`POST_CAP`）
  - 朝枠（10:30）の排他: `.jarvis_state/todoist_morning_owner.json`（無ければ担当 313）と朝枠ロック。`--trigger schedule` は担当が 318 の時だけ動き、313 の作業跡（`/tmp/t313_pending.json` 90 分以内）があれば始めない
  - `--execute-auto` が無い時、① は実行しない。`planned_action`（executed=false・やる予定の内容・上限）を内部ログに残す。AI 見直しの回答に `plan` を書けばそれを使う
- **やること（①自律実行・既定はオフ。`--execute-auto` の時だけ）**
  - 作業範囲は `config/todoist_318_criteria.yaml` の `work_scope`（decision_id 付き）: 調査・資料確認・文面下書き。読めなければ始めない
  - 回し方（追加の有料 AI API なし）: `run --execute-auto` → `work/packet.json`（材料）→ この実行の Claude Code が作業して `work/results.json` → `run --execute-auto --work-results …` で取り込み
  - 2-2 始める前: 停止スイッチ・時間上限（①の作業は60分・`WORK_MAX_MINUTES`）・1回15件なら着手しない／承認待ちは本人の回答まで再実行しない／承認が要る語は②・本人操作は③・大規模は週次へ
  - 2-2 取り込む直前: 範囲外の操作の申告・承認が要る操作の申告は②（成果物は取り込まない）、本人操作は③。内容が変わった・3日より古い・材料に無い結果は使わない。停止スイッチ・時間上限なら残りは材料に残す
  - 成果物は `work/<task_id>/<run_id>/`（＋`progress.json`）。進捗・残作業は判断履歴 `work_318`。Todoist は閉じない。コメントは取り込んだ回だけ（`--write-comments`）
- **やらないこと（Phase 1）**
  - Todoist への書き込み一切（完了・削除・期限変更は今後も作らない。コメントは Phase 3 準備で `--write-comments` の時だけ）
  - Slack 送信（#consult・#ai-hub とも「案」の保存だけ）、`/313/bulk` への登録
  - ① の自律実行（`--execute-auto` の時だけ。コード修正・テスト・PR 作成は将来）、他エージェントへの新規依頼
  - 定期起動の新規登録（10:30 の launchd は 2026-11-23 登録済み。GHA・cloud 予定タスクの追加はしない）。313 の 0.5 は止め、予定タスクを 318 の 2・3 段目に差し替え済み（戻し方は移管手順 §4）
  - 外部送信・削除・支払い・契約・マージ・デプロイ

## 2. 動き出す合図

- [x] 人が頼む（手動実行だけ。Phase 1）
- [ ] 時間（毎朝 10:30。**2026-11-23 登録済み**。雛形 `launchd/com.matsunoma.jarvis.todoist-318.plist.template`・取り決め `jarvis_todoist_morning_slot.py` は用意済み。移管の結果・戻し方は [`移管手順_10時30分.md`](./移管手順_10時30分.md)）

## 3. 実行権限

| 方法 | 使う？ | 内容 |
|---|---|---|
| 外部連携（API） | ○（読むだけ＋コメント追記） | Todoist API v1 を GET。`--write-comments` の時だけ POST /comments（【318】で始まるものだけ）。`TODOIST_API_TOKEN_OWNER`（本人権限）。分身トークンでは読まない |
| CLI | ○ | `scripts/jarvis_todoist_318_triage.py` |
| Slack | × | Phase 1 は送らない |
| 画面操作 | × | |

秘密は `.env.jarvis_private`。値を表示・記録しない。

## 4. 報告

- Phase 1 は **報告案を内部ログ（`runs/<run_id>.json` の `report_draft`）に置くだけ**。件数と ①②③ の内訳だけでタスク名は書かない
- Phase 2 以降の出口（フロー end ノード）: 既存の送信承認ルールで許された時だけ所定 Slack に1通。313 と二重に報告しない

## 5. 使い方（Mac）

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
PY=~/selenium_env/venv/bin/python
$PY scripts/jarvis_todoist_318_triage.py run --dry-run      # 履歴は更新しない（内部ログは残す）
$PY scripts/jarvis_todoist_318_triage.py run                # 履歴も更新（Todoist は読むだけ・載せない・送らない）
$PY scripts/jarvis_todoist_318_triage.py run --publish      # ②③を /313/bulk・週次へ載せる（Supabase sync_meta に書く。松野さん了承後）
$PY scripts/jarvis_todoist_318_triage.py run --publish --send-slack  # ＋#consult 通知・#ai-hub 報告（松野さん了承後）
$PY scripts/jarvis_todoist_318_triage.py run --write-comments   # ＋変化のあった件に【318】コメント（松野さん了承後）
$PY scripts/jarvis_todoist_318_triage.py run --execute-auto      # ①: 作業の材料を work/packet.json に出す（松野さん了承後）
$PY scripts/jarvis_todoist_318_triage.py run --execute-auto --work-results .jarvis_state/todoist_318/work/results.json  # ①: Claude Code の結果を取り込む
$PY scripts/jarvis_todoist_318_triage.py run --trigger schedule  # 定時用（朝枠の担当が 318 の時だけ動く。launchd の runner が使う）
$PY scripts/jarvis_todoist_morning_slot.py status            # 朝枠の担当・ロック・313 の作業跡
$PY scripts/jarvis_todoist_318_triage.py status             # ロック・停止スイッチ・直近の報告案
$PY scripts/jarvis_todoist_318_triage.py unlock --force     # 異常終了で残ったロックを外す（実行中でないと確かめてから）
touch .jarvis_state/todoist_318/STOP                         # 停止スイッチ（消すと解除）。環境変数 TODOIST_318_STOP=1 でも可
```

- 最大 90 分・処理 15 件（`MAX_MINUTES`／`MAX_TASKS`・引数で増やせない）。①の作業に新しく着手するのは 60 分まで（`WORK_MAX_MINUTES`）。コメントを読むのは 1 回 30 件まで（残りは繰越）
- 古い物の拾い: 毎回、期限（先の日）か締切があり30日以上変化がない物 3 件と、期限なしで作成から30日以上の物 3 件を、最後に見た日が古い順に拾う（`pick_old`・上限15件には数えない・一巡する）
- 済み検出（`scripts/jarvis_todoist_318_done.py`・既定オン・`--no-detect-done` で止める・読むだけ・追加のAI APIなし）: 今回見直した件・古い物の拾い・②で回答がなく止まっている物（7日ごと）に、Gmail（自分が送ったメール）・Slack ハブ（各ボットの報告）・GitHub（マージ済みPR）の根拠を探す。題の特徴語の半分以上（最低2つ）が完了の手がかりの近くにある時だけ「済みらしい」。待ちの一覧・318 自身の投稿は根拠にしない。根拠があれば【318】済みらしい コメント（根拠リンクつき・`--write-comments` の時だけ）と、大佐向けの一覧 `.jarvis_state/todoist_318/done_likely.md`／`.json`（題を含むので非公開）を出す。**318 は close しない**（Todoist の close は 62_ の了承事項）。閉じるのは大佐（000・水・土 8:30）で、一覧を見て明らかに終わった物だけ完了にして事後報告、迷う物は松野さん。読み口が使えなかった時は「根拠なし」にせず、報告に「読めなかった読み口」と出す
- 10:15–11:30 は 313 0.5 の時間帯なので止まる（重ならないと確かめた時だけ `--allow-313-window`）
- worktree から本番の state を読む時は `--state-dir ~/git-repos/.jarvis_state`

### AI 分類（この実行の Claude Code で見直す・追加の有料 API なし）

1. `run --dry-run --emit-packet` → `.jarvis_state/todoist_318/packet.json`（題・説明・直近コメント・ルールの結果。非公開の置き場だけ）
2. Claude Code が読んで `answers.json` を書く: `{task_id: {category: "1"|"2"|"3", reason: "…", snapshot_id: packet の値, large: bool}}`
3. `run --ai-answers .jarvis_state/todoist_318/answers.json`
- AI は ②③（実行しない側）へはいつでも動かせる。① にできるのは採用済み②基準に当たらない件だけ。内容が変わって snapshot_id が違う回答は使わない
- ログには `classified_by`（rule / ai(claude_code)）と `rule_category`（ルールの結果）を両方残す

## 6. 判定

| 結果 | いつ |
|---|---|
| success | 対象が「分類済み・変化なしスキップ・313 で残す済・繰越」のどれかに到達し、内部ログを保存できた（0件・上限で繰越も成功） |
| partial | 一部のコメントが読めず保留にした等、未解決のエラーが残った |
| failed | 読取不可・権限不足・排他異常・基準/履歴が読めない・内部ログの保存失敗 |
| stopped | 停止スイッチによる正常停止（別記） |

終了コード: success/stopped=0、partial=1、failed=2。

## 7. 改善ログ

| 日付 | 変更 |
|---|---|
| 2026-11-22 | FlowForge でフロー設計（たたき台→承認済み 15 ノード） |
| 2026-11-23 | Phase 1 実装（読むだけ・抽出・変化なし除外・3分類・内部ログ・手動実行）。社員フォルダ作成。313 の順位付けの部分一致・同点集中・読取の取りこぼしを直して再利用 |
| 2026-11-23 | Phase 2 実装（②→/313/bulk・③→今週の9件・本人回答の読み戻し・#consult／#ai-hub の案・313 との二重質問防止・317 の【318】除外）。載せる・送るは既定オフ（`--publish`／`--send-slack`）。松野さん「設計書どおりなら都度承認なしで進めてよい」 |
| 2026-11-23 | ①自律実行（ノード2-1・2-2）を既定オフで実装（`--execute-auto`・材料出し → Claude Code → 取り込み・範囲は調査／資料確認／文面下書き・承認が要る操作は②・本人操作は③・大規模は週次）。#586 マージ後、`--publish` の実地確認は 01:17 に済み |
| 2026-11-23 | Phase 3 準備（【318】コメント `--write-comments`・重複確認と応答不明の照合／10:30 の雛形と 313 0.5 との朝枠の排他・移管手順／① のやる予定を記録）。全部既定オフ・launchd 未登録・313 の予定タスクは変えない。止まった回のログで「履歴が消えた」と誤停止する不具合も修正 |
| 2026-11-26 | Slack 表示名は 300 ラス隊長（項目48の方針）。#consult・#ai-hub の投稿に `--username` を渡す（本文・送る条件は変えない） |
| 2026-11-27 | 分類基準を 62_「聞く基準」へ（ラス隊長決定・大佐案 件119の1）: ②は影響が大きい／お金／対外送信／削除／取り返せない／舵取りの印がある時だけ。印が無い物は①（既定 `R1-DEFAULT-62`・decision_id D-20261127-62-ask-criteria）。②語に経営・投資・融資・借入・売却・購入・発注等を追加。①の実行は従来どおり `--execute-auto`・承認が要る語は始める前の確認で②へ。|
| 2026-11-27 | 件119の2〜5: 1日の上限 5→15 件・1回 60→90 分・①の作業着手は60分まで（定数化）／古い物を毎回拾う（30日以上変化なし3件＋期限なし古い3件）／② で止まっている物は7日ごとに済み検出だけ当て直す／済み検出（Gmail・Slack・GitHub の根拠つき「済みらしい」コメントと大佐向けの一覧。318 は閉じない） |
