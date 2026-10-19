# 地場業者返信 — Slack 操作（2026-10-19）

Gmail 一覧から拾いにくい業者返信を、**Slack `#consult` で受信文＋草案を見てボタン操作**する。

## 調査結論（Slack App でできること）

| 方式 | できること | 本線？ |
|---|---|---|
| **Incoming Webhook + Block Kit `button.url`** | 送信／編集／返信なしの3ボタン（ブラウザで署名付き URL） | **本線**（既存 Webhook で足りる） |
| Slack App Interactivity + `action_id` | アプリ内で完結・`response_url` でメッセージ更新 | 任意（`SLACK_SIGNING_SECRET` 既存の consult-action を拡張可） |
| `views.open` モーダル編集 | Slack 内テキスト編集 | Bot Token 必須 → **HTML 編集ページで代替** |

出典: [Handling user interaction](https://docs.slack.dev/interactivity/handling-user-interaction/) · [Modal views](https://docs.slack.dev/reference/views/modal-views/) · [chat.update](https://docs.slack.dev/reference/methods/chat.update)

## 方針（4点）

| 柱 | 内容 |
|---|---|
| **入口** | estate Gmail → `jarvis_kurashift_vendor_reply_triage.py --push` → Supabase `triage_items` → Slack `#consult` |
| **確認** | Slack ボタン＝松野了承。編集ページ送信も了承扱い（`jarvis-outbound-confirm` の例外に近い・専用フロー） |
| **履歴** | triage `status`（sent/skipped）＋ `payload.slack_vr_*`。YAML は Mac `vendor_catchup` |
| **停止** | `JARVIS_VENDOR_REPLY_SLACK_DISABLE=1`／Webhook 未設定／`approved` トークン無し |

## エージェント連携（途切れない流れ）

```
estate 受信
  → Jarvis（朝バンドル／明示） triage --push --slack
  → Slack #consult（111／516／ホークが見られる）
  → 松野: 送信 / 編集して送信 / 返信なし
  → Dashboard API（署名付き）→ Gmail estate 送信 or skip
  → Mac vendor_catchup → YAML
  → Grok S2 は初回開拓のみ（返信レーンは触らない）
```

| 誰 | 役割 |
|---|---|
| **Jarvis** | triage・Slack 投稿・署名 URL・送信 API |
| **111** | パートナー報告のついでに `#consult` 業者返信を見ない（地場は別レーン）。混乱防止のため本係は「地場は Slack 業者返信カード」と CLAUDE に書く |
| **516** | due／stall と並び、返信カードの見守り（件数のみ） |
| **Grok S2** | A'-v2／nurture 送信のみ。返信草案の改変・送信はしない |

## コマンド

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_vendor_reply_triage.py \
  --push --mark-inbound-replied --slack
~/selenium_env/venv/bin/python scripts/jarvis_vendor_reply_slack_post.py --from-triage --dry-run
```

## 秘密

| 変数 | 用途 |
|---|---|
| `SLACK_WEBHOOK_AI_TEAM_CONSULT` | 投稿先（無ければ REPORT フォールバック） |
| `PROPERTY_GATE_ACTION_TOKEN` | URL 署名（本線・物件ゲートと共用） |
| `VENDOR_REPLY_ACTION_TOKEN` | 任意上書き |
| `JARVIS_DASHBOARD_URL` | ボタン先オリジン |

## API

| 操作 | URL |
|---|---|
| 草案どおり送信 | `GET /api/g/vr/send/{triage_id}?s=` |
| 編集フォーム | `GET /api/g/vr/edit/{triage_id}?s=` → POST |
| 返信なし | `GET /api/g/vr/skip/{triage_id}?s=` |

## 関連

- Dashboard 下書き: `docs/Jarvis_Dashboard_業者返信下書き.md`
- テンプレ: `config/kurashift_re_vendor_reply_template.yaml`
- 物件ゲート（同型署名リンク）: `docs/AIエージェントチーム/25_Hawk向け_物件進行ゲート_Slackコンサル共有_20261014.md`
