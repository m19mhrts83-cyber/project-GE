# 313 PROGRESS

更新: 2026-11-07

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
