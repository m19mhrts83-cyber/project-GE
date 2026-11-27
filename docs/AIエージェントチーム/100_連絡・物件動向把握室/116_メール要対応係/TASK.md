# TASK — 116 メール要対応係 フローv2の実装（B・C）

| 項目 | 値 |
|---|---|
| task_id | mail-action-116-flow-v2-20261115 |
| agent_id | 116 |
| executor | Claude Code（2026-11-15 松野さん「続きを進めて」） |
| status | review（B・C を実装し PR #426。マージ＝本番反映は松野さん了承後。フロー図の本人確認は後追い） |
| フロー正本 | [flow.md](./flow.md) v2（工程番号 01〜20） |

## 業務自動化・社員具体化の依頼

既存社員 116 メール要対応係（`docs/AIエージェントチーム/100_連絡・物件動向把握室/116_メール要対応係/`）の見直し。作り直さず、既存の `scripts/jarvis_mail_action_slack_post.py` と Dashboard `apps/jarvis-dashboard/lib/mailActionSlackAction.ts` に最小の追加をする。

## 目的・背景

- 松野さんはメールをほぼ見ない。ざっと見てスターを付けたもの＝タスク化（人が選んだもの）は、Claude 予定タスク「スター付きメール→Todoist起票」（平日 8:38・工程03）が担当。116 は AI がスコアで選んだものだけ（工程09〜15）。
- 今は 116 のカードで「後回し」を押すと、スター起票済みのメールが Todoist に二重に入りうる（工程15に確認がない）。
- ルール帳（`learned_rules.md`）が読めなかった回は警告だけで先へ進み、ルールなしで選んだ回と見分けがつかない（工程08）。

## 優先する確定事項と未確認事項

確定（2026-11-15 松野さん了承）:
- A: スター起票の報告は Slack コネクタで #report に1通（予定タスクの指示は書き換え済み。本 TASK の範囲外）。
- B: Gmail で スター付き（STARRED）または ラベル `Todoist済` のメールは 116 のカードに出さない。突き合わせの鍵は Gmail スレッドID（116 の Todoist 説明欄には `gmail_thread=<id>` を書いている。スター起票側はこの印も検索する形に直し済み）。
- C: ルール帳を読めなかった回は投稿を止めず、「ルール未適用」の印を付け、#ops に1行、判断ログにも残す。
- 116 の返信／見送り／後回し／Chatworkで返信ボタンは変えない（Slack 出口の原則で上書きしない）。

未確認（実装前に確かめる）:
- スター起票が使う Gmail コネクタのアカウントはどれか（116 は admin／estate／m19m の3箱。スレッドIDは箱ごと）。重なるのがどの箱かで B の効き方が変わる。
- `triage_items` に Gmail ラベルが残っているか（無い前提で、投稿直前に Gmail API で1回引く想定）。
- `jarvis_learned_rules.load_rulebook` が読めない時に返すもの（warnings の中身・ルール0件との区別）。
- 昼 GHA の予定実行が約8時間遅れて 20:26 頃に走る件で、`_kick-guard.yml` が二重投稿を止めているか。

## 開始トリガー

変更しない（T1 朝バンドル／T2 昼 Mac キック＋GHA／T3 night_triage 後／T4 本人依頼／T5 朝の健全性）。

## 各工程（変更する所だけ）

- **08 プログラム｜ルール帳・ミュート・送信者方針を取得**（`jarvis_mail_action_slack_post.py` `load_pending_from_supabase`）
  - ルール帳の読込失敗（ファイルが無い・形式エラーで確定ルールが読めない）を「ルール0件」と区別して `rules_unavailable=True` を持つ。
  - その回は投稿を続ける。ダイジェスト索引の末尾に「⚠ ルール未適用」1行。`#ops` に1行（既存の 6 時間クールダウンに乗せる）。投稿した各行の payload に `rules_unavailable: true` を残す（判断ログのトリガーが payload を写す）。
- **09 プログラム｜候補集め・除外**
  - 上位を選ぶ前（または選んだ候補だけ）に、行の `account` に対応する token で Gmail `messages.get(format=minimal)` を引き、`labelIds` に STARRED か `Todoist済` のラベルIDがあれば除外。理由 `starred_or_todoist_done` を stats に数える。
  - Gmail に繋がらない時は除外せずに出す（soft-fail・stats に `star_check_unavailable`）。116 のカードが減ることより、出ないことの方が害が大きいため。
  - 除外した行の status は変えない（pending のまま）。スター起票側が Todoist を作る。
- **15 プログラム｜ボタンを処理**（`mailActionSlackAction.ts` の todoist 分岐）
  - Todoist を作る前に、同じ `gmail_thread_id` の Gmail スレッドが STARRED／`Todoist済` か、Todoist に `gmail_thread=<id>` または `#all/<id>` を含む未完了タスクがあるかを確認。あれば作らず「スター起票で登録済みです」とカードを置き換え、status は `todoist`、payload に既存タスクの id/url を入れる。
  - 確認が失敗した時は今まで通り作る（二重は後で消せる・漏れは気づけない）。

## 接続・分岐・戻り先

- 03 →（B）→ 09：スター付き・Todoist済は除外。同時実行（8:38 のスター起票と昼の 116）でも、15 の作成直前の確認で二重を防ぐ。
- 08 →（C）→ 11／17：ルール未適用でも投稿へ進み、#ops にも出す。
- 20 → 08（次回開始時だけ）、06 → 07（本人が戻した時だけ）、15 → 09（後回しの期日到来・1日1回）は変えない。

## 判断ログとフィードバック

- 既存の owner_decisions トリガー（triage_items の status 変化）と unseen（平日21:00）を使う。新しい表は作らない。
- 「ルール未適用」の回は payload の印で数えられるようにする。B で除外した行は判断ではないので判断ログに書かない。

## 成果物・反映・報告

- 保存：triage_items.payload（`rules_unavailable`、15 で既存タスクに寄せた時の `todoist_task_id`）。
- 画面：Slack #consult のダイジェスト・カード、障害は #ops。
- 保存できたことと Slack に表示されたことは別に確かめる。

## 変更範囲・実装順序

1. 未確認4点を読むだけで確かめる（コード・GHA ログ・Gmail コネクタのアカウント）。
2. 08 の C（Python のみ・テスト追加）。
3. 09 の B（Python・Gmail minimal 取得、テストはモック）。
4. 15 の B（Dashboard TS）。
5. `116/CLAUDE.md` 改善ログ・`flow.md` を v2 に合わせて更新。追加の従量課金 API は使わない（Gmail/Todoist/Supabase の既存枠のみ）。

## 受け入れ条件・検証

- `--dry-run` で、スター付きのメールが候補から外れ、stats に件数が出る。Gmail に繋がらないモックでは外れずに出る。
- ルール帳を壊したモックで、投稿は出て、索引に「⚠ ルール未適用」、#ops 1行、payload に印。正常なルール帳では印が出ない。
- 15：スター起票済みのスレッドで「後回し」を押すと Todoist は増えず、既存タスクが返る。確認が失敗するモックでは従来通り作る。
- 既存テスト（`scripts/tests/test_mail_action_*`）が通る。

## 参考資料・安全ルール

- 引継ぎ：Mac の `agent-handoff/to_MissLemon/20261115-1055-claude-116-flow-review.md`（git 管理外・Codex 確認コメント含む）
- 116：CLAUDE.md・flow.md・learned_rules.md、`.github/workflows/jarvis-mail-action-noon.yml`
- 秘密は `.env.jarvis_private` と GHA Secrets のみ。値をログ・Slack・MD に出さない。
- メール送信・Gmail ラベル変更・削除はしない（116 は既読化だけを従来通り）。push・Vercel デプロイは松野さんの了承後、デプロイ時は変更点を報告。

## 最初の返答と完了報告

最初に、未確認4点の結果と、2〜4 のどれから作るかを短く返す。完了時は、変更内容・検証結果・未検証・次の一手を報告し、116 の CLAUDE.md 改善ログを更新する。設計・実装・本番稼働を混同しない。

## 実施結果（2026-11-15・Claude）

- 未確認4点: (1) スター起票の Gmail アカウントは未確認のまま。116 側は行の account ごとの箱でラベルを見るので、どの箱でも効く。(2) triage_items にラベルは無い → 投稿直前に Gmail `messages.get(format=minimal)` で確認。(3) `load_rulebook` は読めないとき空のルール＋警告だけを返し、0件と区別できなかった → `RuleBook.unavailable` を追加。(4) 昼 GHA の遅延実行は未確認（digest の同一セット防止で投稿は抑えられる見込み）。
- 08（C）: `jarvis_learned_rules.py` に `unavailable`。`jarvis_mail_action_slack_post.py` で、読めない回は続行しダイジェストに「⚠ ルール未適用」、payload `rules_unavailable`、#ops に🟡1行（sync_meta `mail_action_rules_unavailable_ops` で6時間に1回）。
- 09（B）: `filter_star_or_todoist_done`。STARRED か「Todoist済」なら外す。外れる分を見越して5件多めに並べる。Gmail に繋がらない時は外さない。停止は `JARVIS_MAIL_ACTION_STAR_CHECK=0`。
- 15（B）: Dashboard `lib/starTodoistGuard.ts`（判定は `lib/starLabels.ts`）。「後回し」でスター付き・Todoist済なら作らず、スター起票のタスクを探して寄せる（status=todoist・payload `todoist_by_star`）。確かめられない時は従来どおり作る。
- テスト: `scripts/tests/test_mail_action_star_and_rules.py`（13件）、既存 mail_action／learned_rules 全件 OK。Dashboard `tests/starLabels.test.mjs` 3件 OK、`tsc --noEmit` OK。`npm test` の失敗1件は外部へ繋ぐ既存テスト（flowforgeShareProxy live）で、変更前も同じ。
- 未検証: 本番の Gmail・Todoist・Slack での実動作（マージ・デプロイ後に昼の回で確認）。

## 追補（2026-11-27・松野さん了承・大佐 件127）判断ログのパートナー別・理由

- 目的: 見送り・Todoist・後回しを、パートナーと理由つきで判断ログに残し、ダッシュボードでパートナー別に引く。返信は従来どおり `5.やり取り.md`（変えない）。
- 確かめた形: owner_decisions には `partner`（名前）が全行に入っている。見送りの理由タグは `payload.reason_tags`（直近30日の見送り389件中19件）。Todoist・後で には理由の入口が無かった。
- 16 判断ログ（変更）: トリガーが `payload.partner_key`（送信元アドレス小文字。無ければ partner 名）を足す。理由は本人が押したタグだけ（`reason_tags`）。押さなければ無し。
- 15 ボタン（変更）: Todoist 登録後のカードに任意の理由タグ4つ（押さなくても進む）。押すと triage_items の `later_reason_tags` と、直近の判断行の `reason_tags` に入る。
- 画面: Dashboard `/mail/partners`（ログイン必須・公開しない）。送り手ごとの件数、押すと判断を新しい順に（見送り／Todoist／後で で絞り込み）。理由が無い判断は「理由なし」と出す。
- 過去分: 埋めない。`partner_key` が無い行は partner 名で束ねる。別案（未実施）: triage_items の `from_email` を判断行に結び付けて `partner_key` を後から埋める。
- 未検証: 本番 DB への migration 適用と、Slack ボタンの実機操作（マージ・適用後に確認）。
