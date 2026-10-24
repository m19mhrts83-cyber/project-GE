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

## 6. 作業手順（Request）

1. 直近の `output/*_週次レビュー.md` を読み、持ち越しを把握
2. `.jarvis_state/weekly_review_314/latest.json`（無ければ `scripts/jarvis_weekly_review_314.py --dry-run`）を読む
3. `git log origin/main --since=7.days` から **仕組みの追加・変更コミット**（feat／fix／workflow／launchd）を選び、差分を読む。docs だけのコミットは流し読み
4. §5 の観点で問題を探す。**機械チェックの要確認は「今週の変更が原因か／前からあるか／人の対応か」に仕分け**
5. 直す: 小さく確実なものから **最大 5 件**。各修正にテストか実行確認をつける
6. `output/YYYYMMDD_週次レビュー.md` を書く（型は §7）。関係する社員 `CLAUDE.md`／docs も同じ PR で直す
7. ブランチ push → PR（タイトル `review(314): 週次レビュー YYYY-MM-DD`）。マージはしない

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
| 2026-10-24 | 週次レビューを定期化。機械チェック（launchd 土曜 9:00）＋Miss Lemon レビュー（Claude 定期タスク 9:30）。status 運用確認（松野了承） |
