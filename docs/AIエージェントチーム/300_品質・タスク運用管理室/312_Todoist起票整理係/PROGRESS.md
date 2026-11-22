# 312 PROGRESS

更新: 2026-11-22

## 2026-11-22 状態ファイルの時刻

- 原因: `todoist_312_digest.json`（`last_digest_at`）は旧 `jarvis_todoist_312_digest.py`（10/21 で役目終了）だけが書いていた。本線は GHA（collect／reflect。状態は Supabase）なので、ローカルのこの時刻は止まって見えた。生存は 315-B が GHA の最終成功で見ている
- 修正: ローカルの週次（`jarvis_todoist_weekly_pick.py` の snapshot／reflect）が成功した回に `last_run_at`（snapshot は `last_digest_at` も）を書く。dry-run・失敗では書かない
- 未対応: GHA の collect は一時的な実行環境のため、ローカル state には書かない（書く必要もない。生存は GHA 実行履歴）

## ループウェア実装

- [x] 入口設計 docs／CLAUDE／flow／設計書コピー
- [x] Supabase `task_loop_*` migration（`20261107_task_loop.sql`）
- [x] `apps/loopware` `/312`（S05・シード3・localStorage＋API）
- [x] `prompts/proposal.md`
- [x] 拾い漏れスキャン `jarvis_todoist_312_miss_scan.py`／`/312?tab=misses`
- [ ] 本番 Vercel デプロイ＋Chrome 受け入れ確認（松野）

## 2026-11-09 — 入口を本物に（collect／reflect）

- 背景: Nody /312 のお題・判断20件がすべて見本。Slack の松野さんの発言を拾う入口、新しいお題の3案、決定→Todoist が無かった（確認メモはプロジェクト共有の 312_loopware_review.md）
- [x] `scripts/jarvis_todoist_312_collect.py` collect: #consult／#ai-hub／#report の松野さん本人の発言（AI が同名で出した報告は形で除外）→ 依頼／問いかけ／やりたい話をルールで判定 → 既存 Todoist と照合 → 3案（rule-v1）→ `task_loop_topics`（`source_ref`＝Slack リンク）→ #consult に1通
- [x] reflect: Nody で「既存タスクへ追記」「別タスクを作る」を選んだものだけ Todoist へ（`reflected_todoist_id`）。登録しない・見本は `-` 印
- [x] `.github/workflows/todoist-312-collect.yml`: collect 月・水・金 20:30 JST／reflect 30分ごと（7〜24時）
- [x] Nody: `/api/topics` で本物のお題を見本の前に並べる。★の案を最初から選ぶ。元の発言リンク
- [ ] migration `20261109_task_loop_source_ref.sql` を本番に適用（松野）
- [ ] 初回 collect の候補を松野さんが見て OK → 本運用
- 後回し: 3案を AI で作る（GHA に LLM キーが無いのでまず型）、拾い漏れの週1見直し、Slack 完結
- [ ] 段階3: 単純確定の Slack 完結（ログ十分後）

## 週の型：平日と土日祝の役割（松野さん 2026-11-12）
- 平日 = エージェント以外のタスク（松野さん自身の仕事）。土日祝 = エージェントでまだ自動化できていないところの自動化を進める日。
- 土日祝にはエージェント自動化タスクを2件置く。11/14(土) 58_承認案の実装、11/15(日) Gmail到着イベントの自動タスク化の設計。
- 週次ピック（scripts/jarvis_todoist_weekly_pick.py）は、土日の日付に置いた「[自律化]／自動化／エージェント作成」のタスクを候補にも日付消しにも入れない（`AGENT_RE`）。祝日は日付判定せず、土日同様に Todoist 側へ置く運用。

## Todoist片付けのまとめ判断（松野さん 2026-11-17）
スター付きメール由来のタスクが大量に入ったため、メールの判断デスクと同じ形でまとめて判断できるようにした（313 の出口側。Nody /313/bulk）。
1. GHA 30分ごと（`todoist-cleanup-bulk.yml`）が Todoist から「スター起票」ラベルの未完了を集め、おすすめ（完了／削除／残す）と理由を sync_meta.todoist_cleanup_snapshot に置く（プログラム）。
2. 松野さんが Nody /313/bulk で、1件ずつまたはチェックしてまとめて 完了／残す／削除／日を変える を選び「確定」（人間。選ばなかった物は何もしない）。
3. 判断を owner_decisions（surface=todoist_313, payload.bulk=true, 残す=defer）に記録。
4. 次の GHA 実行が Todoist に反映（完了=close／削除=delete／日=due_date）し、done 行（target_type=cleanup_apply）を足し、#consult に件数を報告。失敗は次回再試行。
- 「残す」は14日間候補から外す。日を変えたものはその日が来るまで外れる。
- 判断ログのおすすめ一致（payload.followed_suggest）で、おすすめ精度を週次レビューで見られる。
- 止める: リポジトリ変数 JARVIS_TODOIST_CLEANUP_DISABLE=1。loopware は merge で自動デプロイされない（デプロイは松野さんに伝えてから）。
