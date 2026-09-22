# Todoist Webhook 受信（Jarvis）

Phase5 任意。コメント了承（2026-09-22）どおり **Webhook から実装**。Calendar 同期は別タスク。

## できること（現状）

| 段階 | 内容 |
|---|---|
| **受信** | Todoist のイベント（完了・コメント・更新等）を HTTPS で受け、HMAC 検証後に `todoist_webhook_events` へ保存 |
| **未実装** | 受信後の自動処置（相手完了→オーナー確認等）。いまは会話駆動 CLI が本線 |

## エンドポイント

| 項目 | 値 |
|---|---|
| **Production** | `https://jarvis-dashboard-amber.vercel.app/api/todoist/webhook` |
| **GET** | 疎通（`secret_configured: true/false`） |
| **POST** | Todoist からの配信（HMAC 必須） |
| **秘密** | `TODOIST_APP_CLIENT_SECRET`（App Console の client_secret）。Vercel + `.env.jarvis_private` |

## セットアップ（人手・1回）

1. [Todoist App Console](https://developer.todoist.com/appconsole.html) でアプリ作成（個人用）。
2. **Webhook URL** に上記 Production URL を登録。購読イベント例: `item:completed`, `note:added`, `item:updated`（必要に応じて追加）。
3. **client_id / client_secret** を `.env.jarvis_private` の `TODOIST_APP_CLIENT_ID` / `TODOIST_APP_CLIENT_SECRET` に保存（チャット禁止）。
4. Jarvis: `scripts/jarvis_todoist_webhook_secret_sync.py` で Vercel へ投影 → Production 再デプロイ。
5. **OAuth（必須・トークン交換まで）**: リダイレクト URI は **パス付き**  
   `https://jarvis-dashboard-amber.vercel.app/api/todoist/oauth/callback`  
   コールバックは `code` → `access_token` 交換まで行う（交換しないと Webhook はユーザーに届かない）。  
   承認URL例: `https://app.todoist.com/oauth/authorize?client_id=…&scope=data:read_write&state=jarvis1&response_type=code&redirect_uri=（上記をURLエンコード）`  
   画面に「承認完了」と出たら OK（トークンは表示しない・API 本線は既存 `TODOIST_API_TOKEN`）。
6. DB: `apps/jarvis-dashboard/supabase/migrations/20260922_todoist_webhook_events.sql` を jarvis-dashboard PJ に適用済みであること。
7. 疎通: `curl -sS https://jarvis-dashboard-amber.vercel.app/api/todoist/webhook` → `secret_configured: true`（ミドルウェア除外済）。
8. Todoist でテスト完了／コメント → Supabase `todoist_webhook_events` に行が増えること。
9. 問題なければ `config/todoist_projects.yaml` の `integrations.webhook.enabled: true`。

## コード

- ルート: `apps/jarvis-dashboard/app/api/todoist/webhook/route.ts`
- 検証: `X-Todoist-Hmac-SHA256` = base64(HMAC-SHA256(client_secret, rawBody))
- 冪等: `X-Todoist-Delivery-Id` → `delivery_id` UNIQUE upsert

## 関連

- タスク: `[Todoist導入][phase5] Webhook受信（リアルタイム）`（`6hc2Gf5Wqx39GJCc`）
- Calendar: 別タスク `6hc2Gf8r75c2FfVc`（後回し）
- 会話駆動（Webhook 無しでも可）: `scripts/jarvis_todoist_conv_status_propose.py`
