# Jarvisメール入口 × Todoistコメント — 2本立て設計（2026-09-21／気づき本線更新 2026-09-22）

## 方針（松野確定）

- **第一**: Todoist でタスク管理。必要なことは **コメント** で返す
- **2本立て**
  - **(A) チャット**: いま話している1件・対話履歴
  - **(B) バッチ入口**: かつては Jarvis Gmail の Todoist 通知。**2026-09-22 以降の気づき本線は Webhook**（下表）
- ホークに `TODOIST_API_TOKEN` は **渡さない**（維持）
- 正本は常に **Todoist**（メールは入口のひとつ＝保険）

## コメント気づきの優先（2026-09-22 確定）

```
松野が Todoist にコメント
        │
        ├─▶ Webhook（admin App OAuth）──▶ todoist_webhook_events
        │         │
        │         ▼
        │   jarvis_todoist_webhook_handle.py（会話中「書いた」／--reply）
        │
        ├─▶ jarvis@Gmail 通知メール ──【保険】未読キュー
        │
        └─▶ Todoist API コメント巡回 ──【保険】漏れ補完
```

| 経路 | 役割 | 進捗の印 |
|---|---|---|
| **Webhook（本線）** | リアルタイムで内容確認。共同編集者でなくても所有者側承認があれば届く | `todoist_webhook_events`／`processed_at` |
| **メール（保険）** | 通知漏れ・Webhook 停止時 | **未読 → 対応 → 既読** |
| **API 巡回（保険）** | 同上の穴埋め | state の `api_seen_comment_ids` |
| チャット (A) | いま話している1件 | 会話履歴 |

手順・疎通: `docs/Todoist_Webhook受信_20260922.md`  
メール保険スクリプト: `scripts/jarvis_todoist_comment_inbox.py`（`--mark-read` で既読化。既定は報告のみ）

※ Jarvis 分身は Free。枠対策で **第2メアドは作らない**（参加入れ替え／次段 Pro）。詳細: `docs/Todoist_タスク正本_設計_20260921.md`「Free 参加入れ替え」。

## Todoist とメール（調査結果・補助）

| 方向 | 内容 | Beginner |
|---|---|---|
| **メール → Todoist** | プロジェクトの転送用アドレスへ転送 → 新規タスク（件名＝タイトル、本文はコメント添付） | **可** |
| **メール → タスクコメント** | タスクの「メールでコメント追加」用アドレスへ転送 | **可** |
| **Todoist → メール送信** | 通知メール等。気づき本線ではない（保険） | 通知用途 |

手順: プロジェクト `⋯` → **Email tasks to this project**／タスク `⋯` → **Add comments via email**  
公式: https://www.todoist.com/help/articles/forward-emails-to-todoist-JPJ1V339

→ **ネイティブ転送**は「起票・コメント添付」向き。解釈・バッチ確認・ホーク橋は **Jarvis Gmail** 側（任意）。

## 推奨アーキテクチャ（全体・2本立て）

```
(A) Cursorチャット ──対話──▶ Jarvis ──▶ Todoistコメント／列
(B) 気づき: Webhook 本線 ＋（保険）jarvis@Gmail 未読 ＋ API 巡回
ホーク ──Drive inbox──▶ Jarvis apply（現行）
```

## 軽い運用ルール（案）

| 項目 | 案 |
|---|---|
| 日常の「書いた」 | `jarvis_todoist_webhook_handle.py`（必要なら `--reply`） |
| 許可 From（任意メールバッチ） | `admin@…` / `m19m…` / `matsuno.estate@…`（他は無視 or 隔離） |
| Todoist 通知メール | `from:todoist.com is:unread` は **保険キュー** |
| 不明点 | バッチ処理時にまとめて質問 → 松野回答後に再実行 |
| 秘密 | パスワード等はメールに書かない（従来どおり env） |

## 段階ロードマップ

1. **Phase 0**: 方針文書化・本タスクで追跡（本MD）
2. **Phase 1**: Todoist 通知メール到達＋ Gmail API 実証 ✅
3. **Phase 2**: **メール未読キュー＋既読化＋API保険** ✅（`jarvis_todoist_comment_inbox.py`）
4. **Phase 2b**: **Webhook 受信＋半自動 handle** ✅（2026-09-22・気づき本線へ昇格）
5. **Phase 3**: 不明点の一括確認フォーマット／自動処置ルール
6. **任意**: ホーク完了のメール控え（本線は Drive inbox）

## 制約

- Beginner の転送は可。Email Assist（AI整形）は Pro 以上
- 転送用アドレスは **秘密扱い**（相手に配らない）
- ホークに API を渡すと方針衝突 → やらない
- 枠対策の第2 Free Todoist は作らない（設計 MD）

## 検証結果（2026-09-21）

- 松野がコメント＋通知全員 → **jarvis@Gmail に Todoist 通知メール到達**（画面・API 両方で確認）
- 例: 「…2本立て設計 のタスクにコメントしました」（07:32 UTC）
- Gmail API: `token_jarvis.json` 発行済み（`scripts/jarvis_gmail_jarvis_token_auth.py`）
- 通知メール本文に `app.todoist.com/app/task/{id}#comment-{id}` あり → タスク解決可能
- → 当時はメール未読＝処理キュー。**2026-09-22 以降は Webhook 本線・メールは保険**

## Grok フォーク共有（誰が「見える」か）

| メンバー | 見えるか | 経路 |
|---|---|---|
| **Jarvis** | 本線 | Webhook · Todoist API ·（保険）Gmail API |
| **ホークアイ（参謀）** | **共有** | Drive outbox `target: hawk` · 参謀室／Jarvisボックス · Todoist `要ホーク` |
| **不動産賃貸部長** | **共有** | Drive `outbox_to_teams/re/` · Todoist |
| ほか統括・コーチ | 原則 Hawk 経由 | jarvis@ ログイン・API は渡さない |

正本: `config/grok_jarvisbox_fork_policy.md` · ホーク paste · 不動産部長 paste（Instructions 差替用 B1 あり）

## Todoist タスク

- `6hXhcF3365G4cQQc` — メール入口＋2本立て設計（Phase2 実装）
- `6hXfMMQGxc29gxhC` — コメント巡回（＝上記スクリプトの保険側）
- Webhook: `docs/Todoist_Webhook受信_20260922.md` 参照
