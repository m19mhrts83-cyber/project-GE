# 連携状況メモ（111・2026-10-10）

チャット⓪の詳細。値・URLは書かない。

| 連携 | 状態 | Phase 1 での使い方 |
|---|---|---|
| Gmail | Cursor MCP `plugin-gmail` / `user-gmail*` 接続済。本番取込は既存 **Gmail API**（admin） | 読取確認用。書込正本は既存 `yoritoori`／GHA |
| Chatwork | API トークンはローカル `.env` にあり | 既存取込スクリプト |
| OneDrive `5.やり取り.md` | Mac ローカルパスで読める | 正本突合 |
| Slack `#report` 等 | **Webhook 済**（2026-10-10・3本） | `jarvis_slack_webhook_post` / `jarvis_partner_slack_report` |
| Todoist | MCP 未認証。Jarvis API は別途可用 | Phase 2 以降（起票は案のみ） |
| Google Drive MCP | 未認証 | 不要（Drive 作業フォルダはローカル Sync） |

**この環境で難しいもの（後回し）**

- 夜枠 LINE（CHRLINE／QR）は **Mac 専用** → `jarvis_partner_night_pipeline.py` ＋ launchd 20:30。
- FlowForge 定義は設計同期済。実行ランナーは未接続前提。
