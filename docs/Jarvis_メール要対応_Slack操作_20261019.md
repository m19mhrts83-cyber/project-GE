# メール要対応 — Slack 操作（2026-10-19）

管理者／パートナーの **要返信・要処置メール** を、業者返信と同型で `#consult` から処理する。

## 方針（4点）

| 柱 | 内容 |
|---|---|
| **入口** | `triage_items`（GHA gmail triage / night_triage）の pending → Slack `#consult` |
| **確認** | ボタン／モーダル＝松野了承（`jarvis-outbound-confirm` の専用フロー） |
| **履歴** | triage `status`（sent / skipped / todoist）＋ `payload.slack_ma_*`／見送り学習は `sync_meta.mail_action_skip_mute` |
| **停止** | `JARVIS_MAIL_ACTION_SLACK_DISABLE=1`／投稿経路未設定 |

## ボタン

| 操作 | 意味 |
|---|---|
| **返信する** | 草案モーダル（または URL フォーム）→ Gmail 送信 |
| **見送り** | 返信不要として閉じる。同一 From が閾値回続くと **Slack 通知から除外**（削除しない） |
| **Todoist追加** | メール返信以外の手配（電話・ポータル・折り返し等）。GenMail と同系レーン推定 |

業者返信（`re-vendor-*`）は本レーン対象外（既存 VR カード）。

## 見送り学習（ベストプラクティス反映）

調査メモ（Gmail mute／Clean Email／Morning Zero）:

- 会話ミュートと送信者ミュートは別。再掲ノイズは **送信者スコープ**が効く
- ミュートは **削除しない**（可逆・スキップ Inbox 相当）
- 狭い鍵（`from:addr`）を優先。ドメイン一括は誤爆しやすいので当面しない
- 閾値を越えたら通知除外（既定 **2 回**連続見送り）

実装: `sync_meta` キー `mail_action_skip_mute`（JSON 文字列）。閾値は `JARVIS_MAIL_ACTION_MUTE_THRESHOLD`（既定 2）。

## コマンド

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
~/selenium_env/venv/bin/python scripts/jarvis_mail_action_slack_post.py --from-triage --dry-run
~/selenium_env/venv/bin/python scripts/jarvis_mail_action_slack_post.py --from-triage
# 強制 URL ボタン
~/selenium_env/venv/bin/python scripts/jarvis_mail_action_slack_post.py --from-triage --url-buttons
```

朝バンドル: `jarvis_morning_mac_refresh` が soft-fail で相乗り可。

## 秘密

| 変数 | 用途 |
|---|---|
| `SLACK_BOT_TOKEN` / `SLACK_SIGNING_SECRET` | 投稿・Interactivity（業者返信と共用） |
| `SLACK_WEBHOOK_AI_TEAM_CONSULT` | Bot 無し時 |
| `PROPERTY_GATE_ACTION_TOKEN` | 予備 URL 署名 |
| `TODOIST_API_TOKEN` | Dashboard からの Todoist 起票（Vercel） |
| `JARVIS_MAIL_ACTION_MUTE_THRESHOLD` | 見送り→ミュート閾値（既定 2） |
| `JARVIS_MAIL_ACTION_SLACK_DISABLE` | 投稿停止 |

## 関連

- 業者返信同型: `docs/KURASHIFT_業者返信_Slack操作_20261019.md`
- GenMail レーン推定: `scripts/jarvis_todoist_genmail_propose.py`
- Todoist タスク: 「メール自動返信システムの開発」
