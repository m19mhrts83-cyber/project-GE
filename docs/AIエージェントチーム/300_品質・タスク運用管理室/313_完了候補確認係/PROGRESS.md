# 313 PROGRESS

更新: 2026-11-22

## 2026-11-22 空回り停止・状態時刻

- [x] 原因: 最終まとめ時刻（`todoist_313_digest.json` の `last_digest_at`）は旧 digest だけが書く。runner は片付け・外で済んだ候補に切り替え済みで、実行も Slack 送信も毎日成功していたが、この時刻は誰も更新していなかった
- [x] 修正: 送信成功時に `last_run_at`／`last_digest_at` を書く（失敗・dry-run では書かない）。`jarvis_todoist_313_judgment.stamp_run`
- [x] 「残す」記録（`--keep N`）と、内容が変わるまで再提示しない指紋照合。置き場は `.jarvis_state/todoist_313_judgments.json`（非公開・task_id と指紋のみ）
- [x] 連続日数: 片付けに「同じ候補を N 日連続」を1行。外で済んだ候補は state の `streak_line`
- [x] テスト `scripts/tests/test_todoist_313_judgment.py`
- [ ] Slack ボタンで「残す」を押せるようにする（現状は CLI `--keep`。ボタン化は別件）

## ループウェア実装（進行中→本線化）

- [x] 出口設計 docs／CLAUDE／flow
- [x] Slack「313 片付け」3択（済んだ／いつ優先／やめる）＋`owner_decisions` payload
- [x] `scripts/jarvis_todoist_313_cleanup.py`／runner 切替
- [x] 外で済んだ検知: `scripts/jarvis_todoist_313_done_elsewhere.py`
- [x] 段階0棚卸し: `scripts/jarvis_todoist_313_stage0_clear.py`（要確認は松野・applyは了承後）
- [x] drop アクション: `/api/g/t313/drop`＋Block Kit
- [x] loopware `/313`
- [ ] 段階0 apply で超過≤10（人了承）
- [ ] 段階3: 高信頼型のみ auto-close（`jarvis_loopware_stage3_rules.py` 草案）

## 既存

- ヘルパー: `jarvis_todoist_313_slack_blocks.py` ／ TS: `todoist313SlackAction.ts`
- 返信拾い: `scripts/jarvis_todoist_313_slack_ingest.py`（✅→close／📅→リスケ）
- launchd: `com.matsunoma.jarvis.todoist-313-digest` → cleanup 本線
