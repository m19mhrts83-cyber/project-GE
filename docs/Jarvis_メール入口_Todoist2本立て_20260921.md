# Jarvisメール入口 × Todoistコメント — 2本立て設計（下書き 2026-09-21）

## 方針（松野確定）

- **第一**: Todoist でタスク管理。必要なことは **コメント** で返す
- **2本立て**
  - **(A) チャット**: いま話している1件・対話履歴
  - **(B) メールバッチ**: Jarvis Gmail へ指示 → まとめて読取 → 確認／実行
- ホークに `TODOIST_API_TOKEN` は **渡さない**（維持）
- 正本は常に **Todoist**（メールは入口）

## Todoist とメール（調査結果）

| 方向 | 内容 | Beginner |
|---|---|---|
| **メール → Todoist** | プロジェクトの転送用アドレスへ転送 → 新規タスク（件名＝タイトル、本文はコメント添付） | **可** |
| **メール → タスクコメント** | タスクの「メールでコメント追加」用アドレスへ転送 | **可** |
| **Todoist → メール送信** | 通知メール等。Jarvis への「指示チャネル」としては弱い | 通知用途 |

手順: プロジェクト `⋯` → **Email tasks to this project**／タスク `⋯` → **Add comments via email**  
公式: https://www.todoist.com/help/articles/forward-emails-to-todoist-JPJ1V339

→ **ネイティブ転送**は「起票・コメント添付」向き。解釈・バッチ確認・ホーク橋は **Jarvis Gmail** 側。

## 推奨アーキテクチャ（コメント認識・2026-09-21 確定）

```
松野が Todoist にコメント（通知全員）
        │
        ▼
jarvis@Gmail ← 【本線】未読の Todoist 通知メール
        │  Jarvis が読む → チャット／処置
        │  対応済み → 既読（未読キューが進捗の正）
        ▼
Todoist API コメント巡回 ← 【保険】進行中／オーナー確認の新着
        │  メール漏れ・既読忘れの穴埋め
        │  本線で拾った comment_id は重複しない
```

| 経路 | 役割 | 進捗の印 |
|---|---|---|
| **メール（本線）** | 新着を確実に気づく | **未読 → 対応 → 既読** |
| **API 巡回（保険）** | 通知漏れの補完 | state の `api_seen_comment_ids` |
| チャット (A) | いま話している1件 | 会話履歴 |

スクリプト: `scripts/jarvis_todoist_comment_inbox.py`  
（`--mark-read` で未読メールを既読化。既定は報告のみ）

## 推奨アーキテクチャ（全体・2本立て）

```
(A) Cursorチャット ──対話──▶ Jarvis ──▶ Todoistコメント／列
(B) 松野コメント通知 → jarvis@Gmail（未読）──▶ Jarvis ──▶ 既読
    ＋ API保険巡回
ホーク ──Drive inbox──▶ Jarvis apply（現行）
```

## 軽い運用ルール（案）

| 項目 | 案 |
|---|---|
| 許可 From（任意バッチ） | `admin@…` / `m19m…` / `matsuno.estate@…`（他は無視 or 隔離） |
| Todoist 通知 | `from:todoist.com is:unread` を本線キューとする |
| 不明点 | バッチ処理時にまとめて質問 → 松野回答後に再実行 |
| 秘密 | パスワード等はメールに書かない（従来どおり env） |

## 段階ロードマップ

1. **Phase 0**: 方針文書化・本タスクで追跡（本MD）
2. **Phase 1**: Todoist 通知メール到達＋ Gmail API 実証 ✅
3. **Phase 2**: **メール未読キュー＋既読化＋API保険** ✅（`jarvis_todoist_comment_inbox.py`）
4. **Phase 3**: 不明点の一括確認フォーマット／自動処置ルール
5. **任意**: ホーク完了のメール控え（本線は Drive inbox）

## 制約

- Beginner の転送は可。Email Assist（AI整形）は Pro 以上
- 転送用アドレスは **秘密扱い**（相手に配らない）
- ホークに API を渡すと方針衝突 → やらない

## 検証結果（2026-09-21）

- 松野がコメント＋通知全員 → **jarvis@Gmail に Todoist 通知メール到達**（画面・API 両方で確認）
- 例: 「…2本立て設計 のタスクにコメントしました」（07:32 UTC）
- Gmail API: `token_jarvis.json` 発行済み（`scripts/jarvis_gmail_jarvis_token_auth.py`）
- 通知メール本文に `app.todoist.com/app/task/{id}#comment-{id}` あり → タスク解決可能
- → **メール未読＝処理キュー**が本線。API 巡回は保険

## Grok フォーク共有（誰が「見える」か）

| メンバー | 見えるか | 経路 |
|---|---|---|
| **Jarvis** | 本線 | Gmail API · Todoist API |
| **ホークアイ（参謀）** | **共有** | Drive outbox `target: hawk` · 参謀室／Jarvisボックス · Todoist `要ホーク` |
| **不動産賃貸部長** | **共有** | Drive `outbox_to_teams/re/` · Todoist |
| ほか統括・コーチ | 原則 Hawk 経由 | jarvis@ ログイン・API は渡さない |

正本: `config/grok_jarvisbox_fork_policy.md` · ホーク paste · 不動産部長 paste（Instructions 差替用 B1 あり）

## Todoist タスク

- `6hXhcF3365G4cQQc` — メール入口＋2本立て設計（Phase2 実装）
- `6hXfMMQGxc29gxhC` — コメント巡回（＝上記スクリプトの保険側）
