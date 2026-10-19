# メール要対応 — Slack 操作（2026-10-19）

管理者／パートナーの **要返信・要処置メール** を、業者返信と同型で `#consult` から処理する。

## 方針（4点）

| 柱 | 内容 |
|---|---|
| **入口** | `triage_items`（GHA gmail triage / night_triage）の pending → Slack `#consult` |
| **確認** | ボタン／モーダル＝松野了承（`jarvis-outbound-confirm` の専用フロー） |
| **履歴** | triage `status`（sent / skipped / todoist）＋ `payload.slack_ma_*`／見送り学習は `sync_meta.mail_action_skip_mute` |
| **停止** | `JARVIS_MAIL_ACTION_SLACK_DISABLE=1`／投稿経路未設定 |

## バッチ投稿（件数・要約・2026-10-20）

| 項目 | 正 |
|---|---|
| **件数** | 1バッチあたり **スコア上位最大5件**（`--limit` / `JARVIS_MAIL_ACTION_LIMIT`）。残り pending は次バッチで再評価 |
| **並び** | 新しい順ではなく **対応優先スコア**（priority / kind / lane / 依頼シグナル / 下書き有無 / 物件定例ペナルティ / 鮮度） |
| **Slack形** | **ダイジェスト1本**（要旨一覧）＋ **コンパクトカード**（要旨＋ボタン。本文全文は貼らない） |
| **詳細** | Dashboard `/mail/{id}`（「詳細を見る」） |
| **要約** | **Plan A（抽出・LLMなし）**。負荷／品質が足りなければ Plan B（トップNのみ Flash Lite）→ それでも多いなら件数3へ |

スコアの上げ下げ（抜粋）: `priority=high`・`kind=mail`・partner・「ご確認／お願い／期限」等・下書きありを加点。物件紹介定例・skim・ノイズ件名を減点。  
投稿前除外（下書きが無いとき）: OTP／請求通知／申込完了／Apple Pay完了／販促・メルマガ件名など（運用で徐々に追加）。

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
- **返信する／Todoist追加**で連続カウント（streak）をリセット。`muted` の解除は明示 unmute のみ

実装: `sync_meta` キー `mail_action_skip_mute`（JSON 文字列）。閾値は `JARVIS_MAIL_ACTION_MUTE_THRESHOLD`（既定 2）。

## 合図（116・T1〜T5）

| ID | 内容 |
|---|---|
| T1 | 朝バンドル soft-fail |
| T2 | 平日 12:30 JST GHA `jarvis-mail-action-noon.yml` |
| T3 | `jarvis_night_triage` 末尾相乗り |
| T4 | 手動 `--from-triage` |
| T5 | 朝 `--health --notify-ops`（異常時 `#ops`） |

## コマンド

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
~/selenium_env/venv/bin/python scripts/jarvis_mail_action_slack_post.py --from-triage --dry-run
~/selenium_env/venv/bin/python scripts/jarvis_mail_action_slack_post.py --from-triage
# 強制 URL ボタン
~/selenium_env/venv/bin/python scripts/jarvis_mail_action_slack_post.py --from-triage --url-buttons
# 見送り学習
~/selenium_env/venv/bin/python scripts/jarvis_mail_action_mute.py --list
~/selenium_env/venv/bin/python scripts/jarvis_mail_action_mute.py --unmute 'from:addr@example.com'
~/selenium_env/venv/bin/python scripts/jarvis_mail_action_mute.py --health --notify-ops
```

## 秘密

| 変数 | 用途 |
|---|---|
| `SLACK_BOT_TOKEN` / `SLACK_SIGNING_SECRET` | 投稿・Interactivity（業者返信と共用） |
| `SLACK_WEBHOOK_AI_TEAM_CONSULT` | Bot 無し時 |
| `PROPERTY_GATE_ACTION_TOKEN` / `MAIL_ACTION_TOKEN` | 予備 URL 署名 |
| `TODOIST_API_TOKEN` | Dashboard からの Todoist 起票（Vercel） |
| `JARVIS_MAIL_ACTION_MUTE_THRESHOLD` | 見送り→ミュート閾値（既定 2） |
| `JARVIS_MAIL_ACTION_LIMIT` | バッチ最大件数（既定 5） |
| `JARVIS_MAIL_ACTION_SLACK_DISABLE` | 投稿停止 |
| `JARVIS_MAIL_ACTION_REPOST` | 既投稿でも再掲（任意） |

## 関連

- 社員: `docs/AIエージェントチーム/100_連絡・物件動向把握室/116_メール要対応係/`
- 業者返信同型: `docs/KURASHIFT_業者返信_Slack操作_20261019.md`（516）
- GenMail レーン推定: `scripts/jarvis_todoist_genmail_propose.py`
- 要フォロー: Todoist `[要フォロー][night_triage]`