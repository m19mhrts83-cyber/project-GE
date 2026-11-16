# 1Password 試行：comm-hub-backup を op run で動かす（手順書）

作成: 2026-11-15 Claude（チャット）／依頼者: 松野さん  
実行: Claude Code（この Mac 上）／経緯: Todoist「【相談】パスワード管理・.env の 1Password 移行判断」(id 6j2JJ7V7x3vPJJpv)  
まとめ: Claude Docs https://claude.ai/artifact/RW3voYABmSA5715m9K6hsj

## 目的

launchd の無人実行が、`.env.jarvis_private` の代わりに 1Password（Service Account ＋ `op run`）から秘密を読んでも**止まらずに動くか**を、1つの係で確かめる。

## 済んでいること（松野さん、11/14〜15）

- 1Password Individual（体験 11/28 まで）、Mac アプリ・CLI（`op`、.pkg で /usr/local/bin）導入済み
- 保管庫：「個人」「エージェント」「銀行・カード」
- Service Account `jarvis-agents`：**「エージェント」保管庫のみ・読み取り**。Environments へのアクセスなし。トークンは松野さんの「個人」保管庫にある

## 対象

- launchd: `launchd/comm_hub_backup_runner.sh`（毎日 13:40／21:10。GHA が止まったときだけ代走する台帳取り込みの予備）
- 本体: `scripts/jarvis_comm_hub_backup.py`
- 使う秘密（候補）: `JARVIS_SUPABASE_URL`／`JARVIS_SUPABASE_SECRET_KEY`（または `JARVIS_SUPABASE_SERVICE_ROLE_KEY`）／`GEMINI_API_KEY`／`MS_GRAPH_REFRESH_TOKEN`。`GMAIL_ADMIN_TOKEN_PATH` はファイルなので今回は対象外

## 守ること（厳守）

1. **秘密の値を画面・ログ・チャット・Slack・Todoist・git に出さない**（キー名だけ扱う）
2. Service Account のトークンは、**松野さんがターミナルで自分で入力**する（Claude Code は値を見ない）
3. 元の runner と plist は**そのまま残す**。新しい版を並べて置き、いつでも戻せるようにする
4. 「銀行・カード」保管庫には触れない
5. git commit は可、push は松野さんの了承後

## 手順

1. 確認：`op --version`、`op vault list`（Touch ID）で「エージェント」保管庫が見えること
2. **MS Graph トークンの扱いを先に調べる**：`MS_GRAPH_REFRESH_TOKEN` が実行のたびに更新・書き戻しされるか（`JARVIS_MS_GRAPH_USE_SYNC_META` の意味も確認）。書き戻しが要るなら、今回は 1Password に移さず `.env` のまま残す
3. 秘密を「エージェント」保管庫へ入れる：松野さんの Touch ID セッションで、`.env.jarvis_private` から対象キーの値を読み、値を表示せずに `op item create` で作る（1キー＝1項目、タイトルはキー名）
4. Service Account トークンをキーチェーンへ：松野さんに次を実行してもらう（値は松野さんが 1Password からコピーして貼る）  
   `security add-generic-password -a "$USER" -s "op-sa-jarvis-agents" -w`  
   読むとき：`security find-generic-password -a "$USER" -s "op-sa-jarvis-agents" -w`
5. 参照ファイルを作る：`config/op/comm_hub_backup.env`（中身は `KEY=op://<保管庫ID>/<項目>/<フィールド>` だけ。値は書かない）
6. 新しい runner：`launchd/comm_hub_backup_runner_op.sh`  
   - これまでどおり `.env.jarvis_private` を読んだうえで、`OP_SERVICE_ACCOUNT_TOKEN` をキーチェーンから読み、`op run --env-file=config/op/comm_hub_backup.env -- "$PY" scripts/jarvis_comm_hub_backup.py` で実行（対象キーは 1Password の値で上書きされる）  
   - ログには値を出さない（`op run` の既定のマスクを有効のまま）
7. 手で1回実行して成功を確認 → `op service-account ratelimit` で使用回数を確認
8. launchd を新しい runner に切り替え（元の plist は `*.bak` で保存）。`launchctl` で読み直し
9. 次の 13:40／21:10 の2回を見て判定

## 合格の条件（4つ）

1. 承認待ち（Touch ID など）で止まらずに、2回とも exit 0
2. ログ・Slack に秘密の値が出ていない
3. `op service-account ratelimit` の回数が想定内（1日 1,000 回の上限に対して十分少ない）
4. 画面ロック中・再起動後も動く（どちらかで1回は確認）

## 戻し方

元の plist を戻して `launchctl` で読み直すだけ（`.env.jarvis_private` は消していないので、すぐ元どおり）。

## 報告

- Todoist（id 6j2JJ7V7x3vPJJpv）にコメント：`【試行結果】` ＋ 合格条件4つの結果、変えたファイル一覧
- Slack `#ai-hub`：`【報告】comm-hub-backup 1Password 試行` を短く（値は書かない）
- この手順書の末尾に「結果」を追記

## 結果（途中経過 2026-11-15 01:34 Claude Code）

- 手順1：`op` 2.42.0。Touch ID で「エージェント」保管庫が見えた
- 手順2：`MS_GRAPH_REFRESH_TOKEN` は実行のたびに回転し、`~/.jarvis_state/ms_graph_new_refresh.env`（と任意で sync_meta）へ書き戻す（`scripts/jarvis_onedrive_graph.py` `refresh_access_token`）。`JARVIS_MS_GRAPH_USE_SYNC_META=1` は Supabase の sync_meta にも保存する印。→ **1Password に移さず `.env` に残す**
- 実際に使う秘密を調べ直した：comm-hub-backup が読むのは `JARVIS_SUPABASE_URL`／`JARVIS_SUPABASE_SERVICE_ROLE_KEY`／`SLACK_WEBHOOK_AI_TEAM_HUB`／`SLACK_WEBHOOK_AI_TEAM_OPS`。`GEMINI_API_KEY` は使っていないので外した
- 手順3：上の4項目を「エージェント」保管庫に作成（`scripts/jarvis_op_seed_items.py`。値は一時ファイル経由で表示なし）。`.env` の値と一致を確認
- 手順4：松野さんがキーチェーン `op-sa-jarvis-agents` に登録（1回目はクリップボードが別の文章だったので、`ops_` で始まるときだけ登録する1行でやり直し）。SA で見える保管庫は「エージェント」だけ
- 手順5・6：`config/op/comm_hub_backup.env`（参照だけ）・`launchd/comm_hub_backup_runner_op.sh`（移したキーは `.env` 側を unset してから `op run`）
- 手順7：手で `--dry-run` と本番1回、どちらも exit 0。`op service-account ratelimit`：token read 1/1000（1時間）、account 1/1000（1日）
- 手順8：`~/Library/LaunchAgents/com.matsunoma.jarvis.comm-hub-backup.plist` を新 runner に変更（元は同じ場所の `.plist.bak`）。`launchctl bootout`→`bootstrap` で読み直し、`kickstart` でも exit 0
- 実行場所の注意：launchd は `~/git-repos-ops/comm-hub`（detached worktree）を見る。新 runner と参照ファイルはそこへ未追跡ファイルとして置いた。main に入ったら worktree を進めれば同じ中身になる
- ログ・launchd.out/err に秘密の値が無いことを照合済み

合格条件の判定（11/15 13:40／21:10 待ち）

1. 承認待ちで止まらず2回 exit 0：未（手動・kickstart では OK）
2. ログ・Slack に値が出ない：今のところ OK
3. ratelimit が想定内：OK（1回あたり read 1）
4. 画面ロック中・再起動後も動く：未

### 結果（11/16 313 Miss Lemon 判定）

1. 承認待ちで止まらず2回 exit 0：**OK**（`backup_20261115_134005.log`・`backup_20261115_211005.log` とも `via=1password`・`end exit=0`）
2. ログ・Slack に値が出ない：**OK**（2回分のログと launchd.out を鍵の形で照合し、該当なし。launchd.err の最終更新は試行前の 11/14 21:10）
3. ratelimit が想定内：**OK**（11/16 10:3x 時点 token read 0/1000・account 0/1000。1時間窓のため実行時以外は0）
4. 画面ロック中・再起動後も動く：**未**（pmset ログでは 13:30 に画面ON、21:10 前後に画面OFFの記録なし → ロック中の実行は未確認）

判定: 1〜3 は合格。plist は戻さない。4 は次に画面ロック中・再起動後の回を1回見てから本移行を決める。
