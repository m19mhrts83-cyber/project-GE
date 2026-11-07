# 業務品質監査係（314）

**作業を始めたら、まず直近の `output/*_週次レビュー.md` を読む**（先週の持ち越し・人の対応待ちがここにある）。

ビルダー「物件と連絡の見守り隊」由来。**今週作った仕組み・プログラムを週1回レビューし、問題を直して PR にする**。担当は **Miss Lemon（Claude Code）**。  
初回の手動レビュー: [`46_週次レビュー_20261023.md`](../../46_週次レビュー_20261023.md)（この型を毎週回す）

## AIオートメーション（作業フロー）

- **FlowForge（開く）**: [flow_AzrNV2o5gb9M2JMFxeX5aZSa](https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_AzrNV2o5gb9M2JMFxeX5aZSa)
- 流れ図: [`flow.md`](./flow.md)
- 機械チェック CLI: `scripts/jarvis_weekly_review_314.py`（AI なし）
- launchd: `launchd/install_weekly_review_314_launchd.sh`（土曜 9:00）
- Claude 定期タスク: `weekly-review-314`（土曜 9:30・Claude デスクトップ。`~/.claude/scheduled-tasks/weekly-review-314/SKILL.md`）

## 1. 役割（3R の Role＝点検者）

- やること: 今週 main に入った変更を **点検者** の目でレビューし、壊れている・ムダが多い・危ないものを直す。直せないものは理由つきで提案に回す
- やらないこと: PR のマージ、対外送信、Slack 投稿（機械チェック側が済ませる）、秘密の表示・再掲、`agents_registry` の status 変更、Todoist close、**今週の変更と無関係な大改修**

## 2. 動き出す合図（トリガー＝決まった時刻）

| 時刻（JST） | 誰 | 何 |
|---|---|---|
| 土曜 9:00 | launchd（Mac） | 機械チェック → `.jarvis_state/weekly_review_314/facts_YYYYMMDD.md`＋`latest.json`、Slack（要確認あり `#ops`／なし `#report`） |
| 土曜 9:30 | Claude 定期タスク（Miss Lemon） | 事実ファイル＋今週の差分を読んでレビュー → 修正 PR＋`output/YYYYMMDD_週次レビュー.md` |
| 手動 | 人 | 「314 週次レビューやって」でいつでも同じ手順 |

Claude デスクトップが閉じていると 9:30 の回は次の起動時に走る。定期実行の本線は launchd（家ルール）。Claude は判断の補助。

## 3. 実行権限

| 方法 | 使う？ | 内容 |
|---|---|---|
| ファイル読取・git・gh（読取） | ○ | 差分・GHA 履歴・ログ |
| コード修正 | ○ | **専用 worktree／ブランチ**で。main を直接触らない |
| PR 作成 | ○ | 1 週 1 PR。マージは人 |
| テスト・ビルド | ○ | `scripts/tests`、該当アプリの `npm run build` |
| 外部 API（読取） | △ | Supabase／Slack／Todoist は**読むだけ**。書込みは修正対象のスクリプト経由のテストに限る |
| Slack 投稿・対外送信・削除・課金 | × | 人 |

## 4. 報告先

| 種別 | 行き先 |
|---|---|
| 機械チェック結果 | Slack `#ops`／`#report`（launchd が自動） |
| レビュー本体 | `output/YYYYMMDD_週次レビュー.md`＋PR 本文 |
| 人の対応が要るもの | レビュー MD の「人の対応待ち」に1行ずつ（次週も持ち越して消えるまで載せる） |
| `#ai-hub` 用の下書き | 定期タスクの最終メッセージに書く（投稿しない。松野が確認して `jarvis_slack_webhook_post.py --channel hub`） |

## 5. レビューの観点（毎週同じ物差し）

0. **危険・秘密**: 確認なしの送信・削除・送金、無限ループや連投。トークン・パスワード・Webhook URL のコミット
1. **動いているか**: GHA 失敗、launchd の繰り返しエラー、テスト
2. **AI 使用量**: 今週増えた AI 呼び出し。常時 ON か、回数上限・重複起動ガードがあるか。ルールで置き換えられないか
3. **時刻の実効性**: cron の予定と実行時刻のずれ。時刻が大事なジョブを GHA schedule に載せていないか
4. **冗長経路の正しさ**: GHA／Vercel 側に Mac 前提（固定パス・ローカル state）が残っていないか
5. **二重処理・連投**: 同じ Slack 投稿・同じ Ack・同じ AI 起動が繰り返されないか
6. **最小権限・秘密**: 不要な鍵を渡していないか、値をログに出していないか
7. **docs との一致**: 社員 `CLAUDE.md`／`運用コマンド一覧`／`43_`／ハブ `CLAUDE.md` と実装が食い違っていないか
8. **#ops の開きっぱなし**: 直近7日の `#ops`（`C0C88A6CWQH`）で是正結果が書かれていない障害が無いか（Slack は読むだけ。読めない回はその旨を MD に書く）
9. **鮮度（静かな停止）**: `.jarvis_state/freshness_watch.json` の stale が続いていないか。新しい定期成果物を足した週は `config/freshness_slo.yaml` にも 1 行足したか

## 6. 作業手順（Request）

1. 直近の `output/*_週次レビュー.md` を読み、持ち越しを把握
2. `.jarvis_state/weekly_review_314/latest.json`（無ければ `scripts/jarvis_weekly_review_314.py --dry-run`）を読む
3. `git log origin/main --since=7.days` から **仕組みの追加・変更コミット**（feat／fix／workflow／launchd）を選び、差分を読む。docs だけのコミットは流し読み
4. §5 の観点で問題を探す。**機械チェックの要確認は「今週の変更が原因か／前からあるか／人の対応か」に仕分け**
5. 直す: 小さく確実なものから **最大 5 件**。各修正にテストか実行確認をつける
6. `output/YYYYMMDD_週次レビュー.md` を書く（型は §7）。関係する社員 `CLAUDE.md`／docs も同じ PR で直す
7. ブランチ push → PR（タイトル `review(314): 週次レビュー YYYY-MM-DD`）。マージはしない

### 6.1 松野さんの判断ログから直す（2026-11-07〜、11-08 改訂）

松野さんが社員の提案（下書き・未返信判定・起票案・完了候補・S9）にどう判断したかは共有DB（Supabase）に毎回残る。週次レビューで毎回これを読む。**この節が手順の正本**（定期タスク `weekly-review-314` の手順5.5は「CLAUDE.md §6.1 のとおり」とだけ書く）。

| 表 | 何が入るか |
|---|---|
| `owner_decisions` | triage（DB トリガー）、Slack ボタンの 312/313・S9（`lib/ownerDecisionLog.ts`）、**Loopware 313**（`payload.kind=loopware`、理由タグは `payload.reason_tags`） |
| `task_loop_topics`／`task_loop_decisions` | **Loopware 312**（扱いを決める・拾い漏れ）。判断を変えた履歴は `history` |

週次スクリプトは**両方**を読み、片方が読めなければ「⚠ 読めなかった」と出す（黙って0件にしない）。

1. `~/selenium_env/venv/bin/python scripts/jarvis_owner_decisions_weekly.py --out <worktree>/docs/…/314_業務品質監査係/output/YYYYMMDD_判断ログ.md`
   - 出るもの: 今週と前週の **承認／修正／見送り**（件数・母数・率・前週比）、**共通パターン**（同じ理由タグ・見送り理由が2件以上。根拠 ID＝判断ログ ID・Todoist ID つき）、**改善台帳の効果**（`output/improvements.md` の「実装済」「効果測定中」の行の指標を今週の値と並べる）
   - 承認＝提案どおり、修正＝直して使った・延期・やめる、見送り＝提案を採らなかった（どれも違う・後でを含む）
2. 共通パターンから改善候補を **最大3件**。分類は「コード条件分岐／プロンプト／運用ルール／松野判断が必要」。**1件だけのものは一般化しない**（来週以降に重なったら候補）
3. 候補は `output/improvements.md` に `提案` で足す（ID・根拠ID・社員・指標・改善前の値・改善対象・想定効果）。既に Todoist／PR／別スレッドで扱っているものは足さない（二重起票・二重実装を避ける。番頭さんの停滞指摘・ホークの優先度整理と役割を重ねない）
4. **直すのは松野さんが `承認` にした行だけ**。実装・テストは担当（Jarvis／Miss Lemon）。§6 の「最大 5 件」に含める。直したら `実装済` と PR を書く
5. 翌週以降、`実装済`／`効果測定中` の行の数値を見て `効果あり`／`効果なし` に。効果なしなら原因と再改善案を新しい ID で `提案`。起票漏れ・誤完了・見送り率・再発もここで追う
6. 週次レビュー MD に「判断ログ」節を足し、`#ai-hub` 下書き（§4）は次の5段で書く。数字だけで終えない:
   - 今回の判断品質（件数・母数・承認／修正／見送り、前週比）
   - 共通パターン（2件以上のものだけ・根拠 ID）
   - 改善候補（最大3件・分類・想定効果）
   - 前回改善の効果（台帳の数値）
   - 要松野判断（承認してほしい改善 ID）
7. PR を作ったあと `--mark-reviewed` で読んだ `owner_decisions` の行に `review_week` を付ける（DB への書き込みはこれだけ。task_loop は読むだけ）

判断の記録と Todoist の実処置は別もの。Loopware の 313 画面は記録だけで、完了・期日変更・コメントは 313 の Slack ボタン／CLI が行う（`payload.todoist_applied=false`）。

AI 使用量の節約: 機械チェックで済む事実は集め直さない。要確認 0 件かつ仕組みのコミットが 0 件なら、MD に「変更なし・問題なし」と1行書いて終える。

## 7. レビュー MD の型

```
# 週次レビュー YYYY-MM-DD（314・Miss Lemon）
対象: 期間／コミット数
## 観点（§5 のうち今週見たもの）
## 結果と処置（表: 発見｜原因の区分｜処置）
## AI 使用量
## 人の対応待ち（持ち越し含む）
## 提案（今回は直さなかったもの・理由）
PR: <url>
```

## 8. 改善ログ

| 日付 | 変更 |
|---|---|
| 2026-10-09 | ビルダー構成に合わせ候補フォルダ作成（ID 314） |
| 2026-10-24 | 日曜の Claude 定期タスク `miss-lemon-weekly-review` を一時停止し、観点（危険・秘密・二重経路・#ops）と #ai-hub 下書きを本係へ統合 |
| 2026-10-24 | 2回目レビュー（`output/20261024_週次レビュー.md`）。Mac 側の繰り返しエラー5件を是正、GHA 定刻キック導入。ネットワーク一時エラー（DNS・オフライン中）は件数が多くても**ノイズとして扱い**、常駐の生存だけ確認する |
| 2026-10-24 | 週次レビューを定期化。機械チェック（launchd 土曜 9:00）＋Miss Lemon レビュー（Claude 定期タスク 9:30）。status 運用確認（松野了承） |
| 2026-10-31 | 3回目（`output/20261031_週次レビュー.md`）＋3か月バックログ（危険度順）。機械チェックの誤検知 2 件を修正（workflow のコメント行を依存に数えない・`scripts/tests` を AI 追加から除外）、**Gemini 呼び出し（`geminiReply`／`gemini.generate`／`GEMINI_API_KEY`）も AI 追加として拾う**ように。Supabase 402 のように1つの原因で多数の GHA が落ちた週は、系統ごとではなく原因ごとに1行にまとめて仕分ける |
| 2026-11-08 | 判断ログの週次を改訂（§6.1）: Loopware 312 の `task_loop_*` も読む、承認／修正／見送りを前週と比べる、同じ理由2件以上だけ共通パターンにする、改善台帳 `output/improvements.md` で提案→承認→実装→効果を追う。機械チェックはネット不通時に取り直し、Slack に出せなければ exit 2 と `latest.json` の `slack_posted:false` で残す。11/07 は fetch・gh・Slack が全部失敗したのに exit 0 だった |
| 2026-11-07 | 4回目（`output/20261107_週次レビュー.md`）。機械チェックの launchd ログは**前回の本番実行（`--post`）で読んだ位置から後だけ**数えるように（`.jarvis_state/weekly_review_314/log_offsets.json`。`--dry-run` は位置を動かさない）。各エラーに「最後に出たファイルの時刻」も付く。それでも件数だけで判断せず、**最後の発生を見てから**仕分ける |
