# メール要対応係（116）

管理者／パートナーの **要返信・要処置メール** を Slack `#consult` で捌く係。  
ボタン: **返信する／見送り／Todoist追加**。業者返信（VR）は **516**。

## AIオートメーション（作業フロー）

- **FlowForge（開く）**: 未作成（第2段階）。当面の正は [`flow.md`](./flow.md)
- 一覧・進捗: [`15_FlowForge全体系_進捗_20261010.md`](../../15_FlowForge全体系_進捗_20261010.md)
- 設計正本: [`Jarvis_メール要対応_Slack操作_20261019.md`](../../../Jarvis_メール要対応_Slack操作_20261019.md)

## 1. 役割

- やること:
  - `triage_items` pending → **スコア上位5**をダイジェスト＋コンパクトカードで `#consult`（要旨は抽出・LLMなし）
  - 見送り連続学習の監視／unmute 案内
  - 障害・枠切れは `#ops`
- やらないこと:
  - 了承なしの Gmail 送信（ボタン＝了承）
  - 業者返信 VR（`re-vendor-*`）の処理（**516**）
  - 111 のパートナー `#report` 差分報告
  - 211 の管理会社定型下書き本線
  - GenMail MD 入口の代替（レーン推定のみ同系）

## 2. 動き出す合図（確定 2026-10-19・T1〜T5 すべて）

- [x] **T1 時間＋朝バンドル**: `jarvis_morning_mac_refresh` soft-fail で `--from-triage --limit 5`
- [x] **T2 時間（昼）**: 平日 12:30 JST GHA `jarvis-mail-action-noon.yml`
- [x] **T3 イベント**: `jarvis_night_triage` 成功後に相乗り投稿
- [x] **T4 人が頼む**: 「メール要対応出して」→ `jarvis_mail_action_slack_post.py --from-triage`
- [x] **T5 変化・失敗を見回る**: 朝バンドルで `--health --notify-ops`（異常時のみ `#ops`）

## 3. 実行権限

| 方法 | 使う？ | 内容 |
|---|---|---|
| CLI | ○ | `jarvis_mail_action_slack_post.py` / `jarvis_mail_action_mute.py` |
| launchd／朝バンドル | ○ | morning soft-fail（T1・T5） |
| GHA | ○ | noon（T2） |
| Slack Bot／Webhook | ○ | `#consult` 投稿・Interactivity は Dashboard |
| ブラウザ | × | |
| Cursor 会話 | △ | 手動依頼・unmute |

**秘密**: `.env.jarvis_private` のみ。値は MD に書かない。  
**人が確かめる（必須）**: Slack ボタン（返信本文・見送り・Todoist）。お金・外に出す・消す。

## 4. 報告先

| 種別 | 行き先 |
|---|---|
| 要判断カード | Slack `#consult`（本線） |
| 障害・健全性異常 | Slack `#ops` |
| 完了・生存 | 通常不要（カード自体が入口） |

書き出し例: `【ops】116 メール要対応 — 健全性`

### Slack 書き出し（FRIDAY／Jarvis 共通）

| ch | いつ |
|---|---|
| `#consult` | 要返信カード。末尾「次の担当」はボタンUIのため省略可 |
| `#ops` | 投稿失敗・pending過多・mute過多 |

正本: [`38_`](../../38_Slack書き出し_FRIDAY_Jarvis_20261018.md)

## 5–6. 成果物・手順

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
~/selenium_env/venv/bin/python scripts/jarvis_mail_action_slack_post.py --from-triage --dry-run
~/selenium_env/venv/bin/python scripts/jarvis_mail_action_slack_post.py --from-triage
~/selenium_env/venv/bin/python scripts/jarvis_mail_action_mute.py --list
~/selenium_env/venv/bin/python scripts/jarvis_mail_action_mute.py --unmute 'from:addr@example.com'
~/selenium_env/venv/bin/python scripts/jarvis_mail_action_mute.py --health --notify-ops
```

停止: `JARVIS_MAIL_ACTION_SLACK_DISABLE=1`

## 7. 改善ログ

| 日付 | 変更 |
|---|---|
| 2026-10-20 | スコア上位5・ダイジェスト＋抽出要約（Plan A）。本文全文は Dashboard。Slack出した件はGmail既読。見送りでカード削除。ダイジェストは残 pending で更新／残0で削除 |
| 2026-10-19 | 新設（設計中）。T1〜T5 確定。硬化（連続見送り・unmute CLI・Todoist GenMail型） |
