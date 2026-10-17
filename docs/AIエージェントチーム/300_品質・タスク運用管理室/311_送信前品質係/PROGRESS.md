# PROGRESS — 311 送信前品質係

作業を再開したら、まずこのファイルを読む。

## 2026-10-18

- 伴走開始（Cursor／Jarvis・ローカル実行型）
- 環境確認: Slack Webhook（report/consult/ops）既存
- **Phase 1 完了**: `scripts/jarvis_send_gate_311.py`（経路B・`--from-inbox` 経路A入口）
  - dry-run: Tcell LINE＝OK / Newtus＝OK / noreply To＝NG
  - Slack: OK→#report / 修正前の誤NG→#consult（1通）到達確認
- NG Slack文言をブラッシュアップ（要約／内訳／見方／次の一手）
- **Phase 2 完了**: 経路A inbox poll 定常
  - `--from-inbox`: 複数 MD・`README`/`example_*` スキップ・`processed/` 退避・`--limit`/`--keep-inbox`
  - launchd `com.matsunoma.jarvis.send-gate-311-inbox-poll`（900秒・RunAtLoad）
  - smoke: dry-run OK → `--post` 経路A→#report
  - 無効化: `JARVIS_SEND_GATE_311_POLL_DISABLE=1`
- **Phase 3 完了**: 上流キック
  - `--enqueue` / `enqueue_request()`
  - 211: 正本書込後に自動 enqueue
  - ホーク: `action: send_gate_311` → bucho poll → enqueue
  - 手順: `docs/phase3-upstream.md`
- 次: 運用観察（誤キック抑制・S9 定型の enqueue 追加は必要時）
