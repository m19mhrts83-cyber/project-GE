# メール要対応 — Slack 操作（2026-10-19）

管理者／パートナーの **要返信・要処置メール** を、業者返信と同型で `#consult` から処理する。

## 方針（4点）

| 柱 | 内容 |
|---|---|
| **入口** | `triage_items`（GHA gmail triage / night_triage）の pending → Slack `#consult` |
| **確認** | ボタン／モーダル＝松野了承（`jarvis-outbound-confirm` の専用フロー） |
| **履歴** | triage `status`（sent / skipped / todoist）＋ `payload.slack_ma_*`／見送り学習は `sync_meta.mail_action_skip_mute` |
| **停止** | `JARVIS_MAIL_ACTION_SLACK_DISABLE=1`／投稿経路未設定 |

## バッチ投稿（件数・要約・2026-10-20／スレ縮約同日）

| 項目 | 正 |
|---|---|
| **件数** | 1バッチあたり **スコア上位最大5件**（`--limit` / `JARVIS_MAIL_ACTION_LIMIT`）。残り pending は次バッチで再評価 |
| **並び** | 新しい順ではなく **対応優先スコア**（priority / kind / lane / 依頼シグナル / 下書き有無 / 物件定例ペナルティ / 鮮度） |
| **Slack形（見るストレス低減）** | **本線ダイジェスト＝短索引のみ**（partner＋件名）。**案件の間は空行1つ**。**コンパクトカードはスレ**（要旨＋ボタン。下書き全文・本文全文は貼らない） |
| **再投稿防止** | (1) バッチ内で **同一 gmail_message_id**（`id` / `gha-*` 二重）や同一 partner+件名+日付 を1件に潰す (2) 直近6時間に **同一 id セット**のダイジェストがあればスキップ（`sync_meta.mail_action_slack_digest` ＋ローカル JSON）。強制は `JARVIS_MAIL_ACTION_REPOST=1` (3) 投稿印付け時に同一 gmail_id の姉妹 pending も `slack_ma_posted_at` |
| **スレ投稿** | Bot あり＋ダイジェストあり → カードを `thread_ts` 配下へ。Webhook のみ／`JARVIS_MAIL_ACTION_THREAD_CARDS=0` → 本線に短カード |
| **ボタン** | Bot＋Signing あり→アプリ内。**無い／Webhookのみ→署名URLボタン**（ブラウザ。見送りカード自動削除は Bot 投稿時のみ） |
| **Dashboard詳細** | 「詳細を見る」→ `/mail/{id}`。未ログイン時は `/login?next=/mail/...` → ログイン後に同じメールへ戻る |
| **ダイジェスト定義** | バッチ投稿時の **索引ヘッダ1通**（N件の partner／短い件名）。要旨・操作はスレの個別カード |
| **ダイジェスト同期** | 見送り／返信／Todoist のあと、同一バッチ（`payload.slack_ma_digest_ts`）の **残 pending だけで chat.update**（短索引）。残0なら **chat.delete** |
| **詳細** | Dashboard `/mail/{id}`（「詳細を見る」） |
| **要約** | **Plan A（抽出・LLMなし）**。カード要旨は目安280字まで。負荷／品質が足りなければ Plan B（トップNのみ Flash Lite）→ それでも多いなら件数3へ |
| **Gmail既読** | Slack ダイジェスト／カードに出した件は **Gmail 既読**（物件メール取込と同型）。`gmail_message_id` がある行のみ。`payload.gmail_read_on=slack_ma_digest`。失敗時は morning `jarvis_triage_gmail_read_catchup` が取りこぼしを埋める |

スコアの上げ下げ（抜粋）: `priority=high`・`kind=mail`・partner・「ご確認／お願い／期限」等・下書きありを加点。物件紹介定例・skim・ノイズ件名を減点。  
投稿前除外（下書きが無いとき）: OTP／請求通知／申込完了／Apple Pay完了／販促・メルマガ件名など（運用で徐々に追加）。  
**自分発信除外（2026-10-21）**: From が estate／admin／m19m／法人ドメイン、または estate 送信の BCC 控えが「相手から返信」誤ラベルされた本文は、Slack 投稿・Dashboard 未読の両方から除外。取込側（`gmail_to_yoritoori`）も From 自己は受信追記しない（SENT＝自分から送信が正）。  
**自分発信除外の強化（2026-10-28）**: GHA パートナー行（`gha-p-*`）は `from_email` が空のため本文で判定。冒頭が「〇〇様 お世話になっております。松野です。」型（`株式会社リビングサポート松の松野です` 含む）も自分発信として除外。先頭120字に「松野（真治）様／さま」があれば相手の声として除外しない（Python `looks_like_self_outbound_body` と TS `looksLikeSelfOutboundBody` を同期）。

## ボタン

| 操作 | 意味 |
|---|---|
| **返信する** | 草案モーダル（または URL フォーム）→ Gmail 送信。カードは「送信済み」に置換 |
| **見送り** | 返信不要として閉じる。**Slack カードはチャットから削除**（振り返り不要）。同一バッチのダイジェストも残件更新／残0なら削除。同一 From が閾値回続くと以降の Slack 通知からも除外 |
| **Todoist追加** | メール返信以外の手配（電話・ポータル・折り返し等）。カードは「登録済」に置換。ダイジェストは残件更新／残0なら削除 |

### 返信モーダル（2026-10-28）

| 欄・ボタン | 動き |
|---|---|
| **送信元** | estate／admin／m19m から選択。既定は受信したアカウント（不明なら estate）。受信と違う送信元を選ぶとスレッドは引き継がない（件名 Re: で新規） |
| **宛先** | `from_email`。無い行（パートナーやり取り md 由来）は本文中の最初の他者アドレスを候補表示。編集可 |
| **返信本文** | 直接修正できる |
| **誤字脱字チェック** | 指示不要のワンボタン。誤字・脱字・変換ミス・敬語の誤りだけ直し、直した箇所を一覧表示（Gemini） |
| **指示で見直し** | 「見直し指示」欄の内容で書き直す（Gemini） |
| **送信** | 選んだ送信元から送る。後回し（Todoist）由来なら Todoist も完了 |

点検は Slack の 3 秒制限のため「⏳ 点検中」を先に出し、結果を `views.update` で本文欄へ戻す（`after()`・`maxDuration=60`）。`GEMINI_API_KEY`（Vercel）が必要。  
GHA パートナートリアージは連絡先一覧の `emails` 先頭を `from_email` に入れる（返信先）。

### 後回し（Todoist）の拾い直し（2026-10-28）

| 項目 | 正 |
|---|---|
| **起票** | 「Todoist追加」で **期日＝2日後（JST）＋ラベル `返信待ち`** を付ける（期日なしで埋もれるのを防ぐ） |
| **再掲** | バッチ時に `status=todoist` の行を見て、Todoist タスクが未完了かつ **期日が今日以前** なら「⏰後回し」としてダイジェスト・カードに再掲（既定最大3件 `JARVIS_MAIL_ACTION_WAIT_LIMIT`、同じ行は1日1回） |
| **返信** | 同じカードの「返信する」で送信 → **Todoist タスクも自動で完了**（コメント付き） |
| **見送り** | 再掲カードで見送り → Todoist タスクも完了 |
| **先送り** | Todoist 側で期日を延ばす（313 の延期でも可）→ 期日まで再掲しない |
| **Todoist で完了済み** | 次回バッチで検知し、以後は拾わない（`payload.todoist_closed_at`） |
| **必要な秘密** | `TODOIST_API_TOKEN`（無ければ再掲だけスキップ） |

業者返信（`re-vendor-*`）は本レーン対象外（既存 VR カード）。

## 見送り学習（ベストプラクティス反映）

調査メモ（Gmail mute／Clean Email／Morning Zero）:

- 会話ミュートと送信者ミュートは別。再掲ノイズは **送信者スコープ**が効く
- ミュートは **削除しない**（可逆・スキップ Inbox 相当）
- 狭い鍵（`from:addr`）を優先。ドメイン一括は誤爆しやすいので当面しない
- 閾値を越えたら通知除外（既定 **2 回**連続見送り）
- **返信する／Todoist追加**で連続カウント（streak）をリセット。`muted` の解除は明示 unmute のみ

実装: `sync_meta` キー `mail_action_skip_mute`（JSON 文字列）。閾値は `JARVIS_MAIL_ACTION_MUTE_THRESHOLD`（既定 2）。

### Dashboard 共有（2026-10-21）

| 項目 | 正 |
|---|---|
| **共有** | Slack 見送り学習と同じ `mail_action_skip_mute` を Dashboard 未読でも読む |
| **除外先** | `/general`・`/partner` の未読一覧／1通フォーカス、ホーム「その他メール」 |
| **判断済み** | Slack／Dashboard で見送り・返信・Todoist にした行は `status` 更新＋ `revalidatePath` でフォーカス／ラジオ相当 UI から消える |
| **ミュート到達時** | 同 From の残 `pending` も `skipped`（`payload.mail_skip_mute_auto`）。unmute は `jarvis_mail_action_mute.py --unmute` |
| **Dashboard スキップ** | 連続見送りカウントも同じレジストリへ学習（Slack と双方向） |

## 合図（116・T1〜T5）

| ID | 内容 |
|---|---|
| T1 | 朝バンドル soft-fail |
| T2 | 平日 12:30 JST GHA `jarvis-mail-action-noon.yml` |
| T3 | `jarvis_night_triage` 末尾相乗り |
| T4 | 手動 `--from-triage` |
| T5 | 朝 `--health --notify-ops`（異常時 `#ops`）。同一種別アラートは6時間クールダウン（`sync_meta.mail_action_health_notify`。強制は `JARVIS_MAIL_ACTION_HEALTH_REPOST=1`） |

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
~/selenium_env/venv/bin/python scripts/jarvis_mail_action_mute.py --close-muted-pending
~/selenium_env/venv/bin/python scripts/jarvis_mail_action_mute.py --health --notify-ops
```

## 秘密

| 変数 | 用途 |
|---|---|
| `SLACK_BOT_TOKEN` / `SLACK_SIGNING_SECRET` | **アプリ内ボタン本線**（Mac・GitHub Secrets・Vercel の3箇所）。無いと URL ボタンに自動フォールバック。取得: `api.slack.com/apps` → **Jarvis AI Team**（Bot User OAuth + Signing Secret）。3先同期: `scripts/jarvis_slack_bot_secrets_sync.py` |
| `SLACK_WEBHOOK_AI_TEAM_CONSULT` | Bot 無し時の投稿（カード自動削除・モーダルは不可） |
| `PROPERTY_GATE_ACTION_TOKEN` / `MAIL_ACTION_TOKEN` | 予備 URL 署名 |
| `TODOIST_API_TOKEN` | Dashboard からの Todoist 起票（Vercel） |
| `JARVIS_MAIL_ACTION_MUTE_THRESHOLD` | 見送り→ミュート閾値（既定 2） |
| `JARVIS_MAIL_ACTION_LIMIT` | バッチ最大件数（既定 5） |
| `JARVIS_MAIL_ACTION_THREAD_CARDS` | `0` でカードのスレ投稿をオフ（本線に短カード） |
| `JARVIS_MAIL_ACTION_SLACK_DISABLE` | 投稿停止 |
| `JARVIS_MAIL_ACTION_GMAIL_READ_DISABLE` | Slack 投稿後の Gmail 既読をオフ |
| `JARVIS_MAIL_ACTION_REPOST` | 既投稿でも再掲（任意） |

## 関連

- 社員: `docs/AIエージェントチーム/100_連絡・物件動向把握室/116_メール要対応係/`
- 業者返信同型: `docs/KURASHIFT_業者返信_Slack操作_20261019.md`（516）
- GenMail レーン推定: `scripts/jarvis_todoist_genmail_propose.py`
- 要フォロー: Todoist `[要フォロー][night_triage]`