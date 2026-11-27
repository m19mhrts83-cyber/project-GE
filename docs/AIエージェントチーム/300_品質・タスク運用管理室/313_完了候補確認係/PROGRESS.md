# 313 PROGRESS

更新: 2026-11-24

## 2026-11-24 週の整理に一本化（松野さん了承・Orca 項目50）

- [x] `scripts/jarvis_todoist_313_weekly.py`＋`config/todoist_313_weekly.yaml`（A 済みました・B やめる提案・`--undo`）
- [x] /313/bulk に「313 週の整理」の見出し・済み／やめる／残す（やめる＝完了扱い）。cleanup_bulk が `sync_meta.todoist_313_weekly_queue` を混ぜ、reflect は 313 カードを削除せず完了にする
- [x] runner: 金曜以外は何もしない。318 は 313 が載せた件（8日）を載せない。315-B は週1の監視に
- [x] 実データ下見 11/24: タスク229件 → A 0件／B 15件（うち「済み？」5件）
- [ ] 初回本番 2026-11-27（金）20:00 → 結果（A n／B n・閉じた件の誤り）を確かめる
- [ ] launchd 入れ替え（ラス隊長・Mac の `~/git-repos` を main に追従した後）:
  ```bash
  cd ~/git-repos && git pull --ff-only
  zsh launchd/install_jarvis_todoist_313_digest_launchd.sh   # 金曜 20:00（Weekday=5）で入れ直す
  plutil -p ~/Library/LaunchAgents/com.matsunoma.jarvis.todoist-313-digest.plist | grep -A3 StartCalendarInterval
  ```
  戻すとき: このPRを revert → 同じ install を流す（毎日 20:00 に戻る）。止めるだけなら `zsh launchd/uninstall_jarvis_todoist_313_digest_launchd.sh`

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
