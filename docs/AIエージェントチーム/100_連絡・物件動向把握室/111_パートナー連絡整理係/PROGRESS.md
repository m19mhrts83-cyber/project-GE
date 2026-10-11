# PROGRESS — パートナー連絡整理係（111）

作業再開時は **このファイル → `CLAUDE.md`** の順で読む。

## フェーズ区切り（2026-10-10）

| フェーズ | 状態 |
|---|---|
| **初版開発（本開発／初動）** | **完了** — Webhook／昼GHA／夜launchd／件数テンプレ Slack／links・reports |
| **運用確認** | **進行中** — Todoist タスクで区切り。レポート形・判断しやすさ・実走ログを見る |

### 運用確認で見るもの

1. 昼 11:50／夜 20:30 → `#report` が来る（**〜2026-10-18 は更新ゼロでも「出なかった」投稿**）
2. 冒頭に **番号 `111`** があり識別できるか
3. 更新あり日 → 件数と「見る」で次の行動が取れるか
4. 失敗時 → 失敗行と「次」が分かること
5. 10/19以降 → ゼロ日は再び静か（`JARVIS_PARTNER_111_REPORT_ZERO=1` で延長可）

### 効率・トークン（初版に入れた方針）

- **LLM 不使用**（取込＋件数テンプレのみ → Cursor／API トークンを食わない）
- 昼: Gmail∥Chatwork **並列**、Gmail `limit=25` / `newer_days=2`（朝 triage との二度取り軽減）
- 夜: 公式エクスポートは poll 新鮮なら **スキップ**、**ダッシュボードを開く**（抑止は env）
- 夜取りこぼし: screen-unlock＋朝バンドル soft-fail
- GHA: pip cache、timeout 20分
- フォルダ: `links.md`／`reports/`（Slack 控え）

任意の仕上げ（運用確認の外でも可）: flow HTML 図の実装同期。

---

## 2026-10-11（計画実装クローズ）

- `links.md`／`reports/` 追加。Slack 投稿時に控え保存
- 夜 runner でダッシュボード同梱（SKIP 既定オフ）
- 取りこぼし: `jarvis_screen_unlock_catchup` ＋ `jarvis_morning_mac_refresh`
- 後続競合は [`後続_競合棚卸し.md`](./後続_競合棚卸し.md)

## 2026-10-10（Phase 3・夜枠）

- `jarvis_partner_night_pipeline.py` ＋ launchd 20:30。当日1回ガード。

## 2026-10-10（Phase 2 完了・dry_run 緑）

- dry_run `38039937891` success。`ecb44f30`（Gmail token 展開）。

## 2026-10-10（Phase 1・Webhook）

- Incoming Webhook 3本・テストOK。`ec0536ff`
