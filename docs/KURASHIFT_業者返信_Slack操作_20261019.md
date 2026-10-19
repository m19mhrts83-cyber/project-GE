# 地場業者返信 — Slack 操作（2026-10-19）

Gmail 一覧から拾いにくい業者返信を、**Slack `#consult` で受信文＋草案を見てボタン操作**する。

## 調査結論（コスパ優先）

| 方式 | できること | 本線？ |
|---|---|---|
| **`action_id` + 既存 `/api/slack/consult-action`** | アプリ内で送信／返信なし／編集モーダル。Signing Secret 再利用・新エンドポイント不要 | **本線** |
| Bot `chat.postMessage`（`SLACK_BOT_TOKEN`） | interactive ボタンが確実に動く・`views.open` / `chat.update` | **投稿本線**（無いとき Webhook） |
| Incoming Webhook + `button.url` | ブラウザで署名付き URL（Interactivity 不要） | **フォールバック**（`--url-buttons`） |

出典: [Handling user interaction](https://docs.slack.dev/interactivity/handling-user-interaction/) · [Modal views](https://docs.slack.dev/reference/views/modal-views/) · [chat.postMessage](https://docs.slack.dev/reference/methods/chat.postMessage)

### なぜこれが安い／効率的か

1. **新 Slack App を増やさない** — 物件ゲートと同じ Interactivity URL（`consult-action`）に `vr:send|edit|skip:…` を足すだけ
2. **署名 URL は保険** — context と `--url-buttons` で Signing 未設定でも運用継続
3. **Bot が無くても**：同一 App の Webhook へ `action_id` 投稿は試せる。ダメなら URL モード

## Slack App 設定（1回だけ）

| 項目 | 値 |
|---|---|
| Interactivity Request URL | `https://jarvis-dashboard-amber.vercel.app/api/slack/consult-action` |
| Signing Secret | Vercel / `.env` の `SLACK_SIGNING_SECRET` |
| Bot Token Scopes（推奨） | `chat:write` · Interactivity 有効（`views.open` 用） |

## 方針（4点）

| 柱 | 内容 |
|---|---|
| **入口** | estate Gmail → `jarvis_kurashift_vendor_reply_triage.py --push` → Supabase `triage_items` → Slack `#consult` |
| **確認** | Slack ボタン／モーダル送信＝松野了承（`jarvis-outbound-confirm` の専用フロー） |
| **履歴** | triage `status`（sent/skipped）＋ `payload.slack_vr_*`。YAML は Mac `vendor_catchup` |
| **停止** | `JARVIS_VENDOR_REPLY_SLACK_DISABLE=1`／投稿経路未設定 |

## エージェント連携（途切れない流れ）

```
estate 受信
  → Jarvis（朝バンドル／明示） triage --push --slack
  → Slack #consult（Bot postMessage または Webhook）
  → 松野: この草案で送信 / 編集して送信 / 返信なし
  → consult-action（block_actions）→ Gmail estate 送信 or skip
  → 元メッセージを ✅ に置換（response_url / chat.update）
  → Mac vendor_catchup → YAML
  → Grok S2 は初回開拓のみ（返信レーンは触らない）
```

| 誰 | 役割 |
|---|---|
| **Jarvis** | triage・Slack 投稿・Interactivity 処理・送信 API |
| **111** | 地場は Slack 業者返信カード（パートナー報告と混同しない） |
| **516** | due／stall と並び、返信カードの見守り（件数のみ） |
| **Grok S2** | A'-v2／nurture 送信のみ。返信草案の改変・送信はしない |

## コマンド

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_vendor_reply_triage.py \
  --push --mark-inbound-replied --slack
# 既定: action_id ボタン + Bot 優先
~/selenium_env/venv/bin/python scripts/jarvis_vendor_reply_slack_post.py --from-triage --dry-run
# フォールバック（ブラウザ URL）
~/selenium_env/venv/bin/python scripts/jarvis_vendor_reply_slack_post.py --from-triage --url-buttons
```

## 秘密

| 変数 | 用途 |
|---|---|
| `SLACK_BOT_TOKEN` | `#consult` へ `chat.postMessage`（本線）・`views.open` |
| `SLACK_SIGNING_SECRET` | Interactivity 検証（consult-action 既存） |
| `SLACK_WEBHOOK_AI_TEAM_CONSULT` | Bot 無し時の投稿 |
| `SLACK_CONSULT_CHANNEL_ID` | 任意上書き（既定 `C0C7R0UF3MM`） |
| `PROPERTY_GATE_ACTION_TOKEN` | 予備 URL 署名（物件ゲートと共用） |
| `VENDOR_REPLY_ACTION_TOKEN` | 任意上書き |
| `JARVIS_DASHBOARD_URL` | 予備 URL オリジン |

## API

| 操作 | 経路 |
|---|---|
| 草案どおり送信 | Slack `action_id=vendor_reply_send` → consult-action |
| 編集して送信 | `vendor_reply_edit` → `views.open` → modal submit |
| 返信なし | `vendor_reply_skip` |
| URL 予備 | `GET /api/g/vr/{send\|edit\|skip}/{id}?s=` |

## 関連

- Dashboard 下書き: `docs/Jarvis_Dashboard_業者返信下書き.md`
- テンプレ: `config/kurashift_re_vendor_reply_template.yaml`
- 物件ゲート（同型 consult-action）: `docs/AIエージェントチーム/25_Hawk向け_物件進行ゲート_Slackコンサル共有_20261014.md`
