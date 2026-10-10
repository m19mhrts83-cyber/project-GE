# PROGRESS — パートナー連絡整理係（111）

作業再開時は **このファイル → `CLAUDE.md`** の順で読む。

## フェーズ区切り（2026-10-10）

| フェーズ | 状態 |
|---|---|
| **初版開発（本開発／初動）** | **完了** — Webhook／昼GHA／夜launchd／件数テンプレ Slack |
| **運用確認** | **進行中** — Todoist タスクで区切り。レポート形・判断しやすさ・実走ログを見る |

### 運用確認で見るもの

1. 昼 11:50 に更新がある日 → `#report` が判断しやすい文面か
2. 夜 20:30 → LINE 取込＋更新時投稿（Mac版LINEは終了）
3. 更新ゼロの日 → Slack が来ないこと
4. 失敗時 → 失敗行と「次」が分かること

### 効率・トークン（初版に入れた方針）

- **LLM 不使用**（取込＋件数テンプレのみ → Cursor／API トークンを食わない）
- 昼: Gmail∥Chatwork **並列**、Gmail `limit=25` / `newer_days=2`（朝 triage との二度取り軽減）
- 夜: 公式エクスポートは poll 新鮮なら **スキップ**、launchd は **ダッシュボード非表示**
- GHA: pip cache、timeout 20分

任意の仕上げ（運用確認の外でも可）: flow HTML 図の実装同期。

---

## 2026-10-10（Phase 3・夜枠）

- `jarvis_partner_night_pipeline.py` ＋ launchd 20:30。当日1回ガード。

## 2026-10-10（Phase 2 完了・dry_run 緑）

- dry_run `38039937891` success。`ecb44f30`（Gmail token 展開）。

## 2026-10-10（Phase 1・Webhook）

- Incoming Webhook 3本・テストOK。`ec0536ff`
