# Obsidian 日次レビュー・双方向連携

- 更新: 2026-11-12
- 実装ブランチ: `codex/obsidian-bidirectional-20261112`
- 状態: コード準備済み。Supabase migration／Vercel Production／ChatGPT connector／Mac LaunchAgent／GAS triggerは未適用。

## 全体構成

```text
ChatGPT private tools
  ├─ 読取: search_vault_notes / get_vault_read_result / get_vault_note_excerpt
  │    → read-only Bearer key → Supabase短期要求箱
  │    ← Macから15秒間隔の外向きpoll → allowlist配下を読取 → 抜粋を返す
  └─ 書込: submit_daily_review（確定指示の後だけ）
       → submit Bearer key → obsidian_review_inbox（一時キュー）
       ← Mac poll → Documents Vaultへno-clobber保存
       → 既存OGD helper → Google Drive同期 → ack後にCloud本文消去

Mac poll heartbeat → Supabase状態
Google Apps Script（5分trigger）→ 認証付きDashboard監視API
  → stale/recovery状態遷移時だけSlack #opsへ通知
```

Vault正本は `~/Documents/500_Obsidian_r1`。Google DriveはOGD同期ハブ、iPhoneはその同期先。ChatGPT/DashboardからGoogle Driveを直接編集しない。

## ChatGPTからの読み取り

### 権限・範囲

- 新しいread-only MCP: `/api/obsidian-vault/mcp`。認証鍵は `OBSIDIAN_REVIEW_READ_KEY`。
- Mac poll/response鍵は `OBSIDIAN_VAULT_POLL_KEY`。保存submit鍵 `OBSIDIAN_REVIEW_SUBMIT_KEY`、レビューpoll鍵 `OBSIDIAN_REVIEW_POLL_KEY`、監視鍵 `OBSIDIAN_REVIEW_MONITOR_KEY` と用途を分ける。
- 初期の固定allowlist:
  - `01_Journaling/★Journal/`
  - `04_Permanent Note/`
- クライアントが任意パスや他フォルダを指定できない。symlink、hidden path、Vault外参照、非Markdownを拒否する。
- テーマ検索はMacでMarkdownを走査し、上位最大10件・最大2抜粋/ノート・短いsnippetだけ返す。単一日・7日・30日範囲も指定できる。検索語なしの日付検索も可能。走査は最大12,000ファイル・64MB/要求に制限する。
- 詳細取得は過去検索で返した相対パスを使う。見出し指定があれば該当セクション、無ければ最大3,200文字を返す。
- 返却結果に相対パス・日付・見出し・取得時刻を含める。全文Vaultのアップロードや意味検索indexは作らない。
- Queue request/resultは15分で失効し、Mac poll時または次の新規read request時に期限切れを掃除する。QueueのDBはRLS有効でservice_roleだけがアクセスする。
- 検索語と抜粋は応答中にSupabaseを通る。保存時以外の一時データであり、ログには本文・検索語・鍵を出さない。

### ChatGPT tool flow

1. `search_vault_notes` に検索語、または日付範囲（`from_date`/`to_date`、`days=7|30`）を渡す。
2. ツールから `request_id` が返ったら `get_vault_read_result` で結果を確認する。`pending` なら5秒程度後に再度確認する。Macが停止中なら完了と報告せず、応答待ち／期限切れと伝える。
3. 必要な原文箇所だけ `get_vault_note_excerpt` で取得する。結果のsource_pathを使い、出典を会話に付ける。

日次レビュー送信は既存の**別**tool `submit_daily_review` を維持する。ユーザーの「今日のレビューを確定」後だけ送る。受付応答は保存完了ではない。

## Mac worker・保存安全性

- 既存worker `scripts/jarvis_obsidian_review_inbox.py` がレビュー保存とVault read requestの両方を処理する。LaunchAgent installerは15秒間隔で登録する。
- 読取ロジックは `scripts/jarvis_obsidian_vault_reader.py`。Vault正本から直接read-only取得し、結果を一時queueへ返す。検索語やノート本文をMacログに出さない。
- レビュー保存は固定フォルダ `01_Journaling/★Journal/日次レビュー/`。既存ファイルに異なる本文があれば上書きしない。保存・OGD helper成功後だけackする。
- Google Drive APIのupload/patchは既存 `scripts/jarvis_obsidian_ogd_retag.py` 内でMacから実行する。Cloud APIにDrive tokenやDrive書込処理を持たせない。
- dry-runはCloud queueをclaimせず、Vault write・OGD同期・期限切れ削除をしない。

## Mac offlineのSlack通知

- Dashboardはreview/read pollの成功時刻を `obsidian_review_agent_status` に記録する。
- Apps Scriptは5分ごとに `/api/obsidian-review/monitor` を呼ぶ。最後のMac pollから5分を超えるとoffline、再度応答があればrecoveredと判定。
- 最初の監視呼出しから10分は起動猶予。Apps Scriptの実行遅延もあるため、通知目安はMac最終応答から約5〜10分＋GAS遅延。
- Slack `#ops` には状態遷移時のみ短い通知を送る。成功状態の定期投稿なし。同じ状態で通知を繰り返さない。
- Slack webhookはVercel環境変数 `SLACK_WEBHOOK_AI_TEAM_OPS` に置き、GASにはmonitor endpoint/keyだけを置く。
- Apps Script source: `apps-script/obsidian-review-watchdog/`。

## 実運用の記録

- 2026-11-10分: Macログに `saved and synced`、Vault内に生ログ・戦術レビューの2ファイルを確認済み。OGD helperとackまで成功。iPhone画面での表示は未確認。
- 2026-11-12分: 前回の読み取りdry-runでpendingなし、Vault内保存なし。依頼時点の「送信保留」と整合。ChatGPT側の送信履歴は確認していない。
- このブランチのread/monitor新規経路はまだdeploy・migration・connector設定・実データを用いた動作確認をしていない。

## 有効化に必要な作業

1. このbranchのコードをレビュー後にmerge/deployする。
2. Supabaseへ `apps/jarvis-dashboard/supabase/migrations/20261112_obsidian_vault_read_watchdog.sql` を適用する。
3. Vercel Productionに以下を設定する（値はGit・チャットへ書かない）。
   - `OBSIDIAN_REVIEW_READ_KEY`
   - `OBSIDIAN_VAULT_POLL_KEY`
   - `OBSIDIAN_REVIEW_MONITOR_KEY`
   - `SLACK_WEBHOOK_AI_TEAM_OPS`（既存設定が使える場合は再設定不要）
4. Macの `~/git-repos/.env.jarvis_private` に `OBSIDIAN_VAULT_POLL_KEY` を追加する。
5. mainへ反映後、**安定したrepo checkoutから** `launchd/install_obsidian_review_inbox_launchd.sh` を実行する。現在のLaunchAgentは一時worktreeを実行先にしているため、この手順で安定パスへ付け替える。
6. `apps-script/obsidian-review-watchdog/README.md` に従いGAS private projectを作り、Script Propertiesを設定してtriggerを登録する。
7. ChatGPTにread-only MCP endpoint `https://jarvis-dashboard-amber.vercel.app/api/obsidian-vault/mcp` を、Bearer `OBSIDIAN_REVIEW_READ_KEY` でprivate登録する。既存save toolとは別の接続として扱う。
8. 有効化後、許可範囲内の一件で出典付き検索→抜粋取得、offline/recoveryの一度ずつの通知を確認する。失敗時に成功扱いしない。

## 既知の制約

- Markdown全文を対象に毎回走査する初期実装。上限12,000 Markdown files・64MB/要求・2MB/ファイル。速度を実測し、遅くなった場合に限りSQLite FTS5を検討する。
- GSuite/GAS time triggerはbest-effortで、5分きっかりを保証しない。さらに早い通知が必要なら安定した外部monitorを別途選ぶ。
- Slack通知失敗時はstateを更新しないため次回monitorで再試行する。Slack成功後にDB更新だけ失敗したときは通知が重複する可能性がある。
- Mac offline時のread要求は15分で失効。検索結果の全文は返さず、固定サイズの抜粋だけ返す。
- ChatGPT toolから取得可能なのは現在の会話でユーザーが指定したログ／過去Vaultの許可範囲だけ。非表示のChatGPT会話履歴を自動取得する機能ではない。

## 関連実装

- API: `apps/jarvis-dashboard/app/api/obsidian-review/{submit,mcp,inbox,monitor}/`
- 読取API: `apps/jarvis-dashboard/app/api/obsidian-vault/{mcp,inbox}/`
- DB: `apps/jarvis-dashboard/supabase/migrations/20261110_obsidian_review_inbox.sql`, `20261112_obsidian_vault_read_watchdog.sql`
- Mac: `scripts/jarvis_obsidian_review_inbox.py`, `scripts/jarvis_obsidian_vault_reader.py`
- Watchdog: `apps-script/obsidian-review-watchdog/`
- submit schema: `docs/obsidian-review-submit-openapi.yaml`
