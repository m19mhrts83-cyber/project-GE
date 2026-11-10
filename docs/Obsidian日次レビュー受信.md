# Obsidian 日次レビュー受信

目的: ChatGPTで「今日のレビューを確定」と伝えたとき、生ログと戦術レビューをMacローカルVaultへ渡し、既存OGD同期でiPhoneへ届ける。

## 構成

```text
ChatGPT Plus plugin（ChatGPT Site hosted MCP）: submit_daily_review
  → Dashboard Bearer API → Supabase obsidian_review_inbox（一時キュー）
  ← Mac LaunchAgent（60秒間隔、外向きHTTPS取得のみ）
  → 固定フォルダへ2件のMarkdownを重複防止付き保存
  → jarvis_obsidian_ogd_retag.py → 既存Google Drive Sync / OGD
  → 保存・同期成功後にAPIへack（キュー本文を消去）
```

Vaultの正本は `~/Documents/500_Obsidian_r1`。保存先は `01_Journaling/★Journal/日次レビュー/`。日付とreview UUID先頭8桁を使い、生ログと戦術レビューを別々のファイルにする。受信データからファイルパスを作ることはない。既存ファイルの内容が異なる場合は上書きせず、ackもしない。

Cloud側は一時キュー。本文は最大30日 pending とし、通常のMac取得時に期限切れ分を削除する。削除件数があればMacログへ警告する。ローカル保存と既存OGDアップロードが成功してからackし、ack時にCloud本文をnull化する。Drive同期は既存の認証・Vault・OGD設定を利用する。

## 変更ファイル

- Dashboard: `apps/jarvis-dashboard/app/api/obsidian-review/mcp/route.ts`（ChatGPTからのsubmit専用MCP）
- Dashboard: `apps/jarvis-dashboard/app/api/obsidian-review/submit/route.ts`（Bearer認証REST API。ChatGPT Site pluginから呼ぶ）
- Site plugin登録用の要求形式: `docs/obsidian-review-submit-openapi.yaml`
- Dashboard: `apps/jarvis-dashboard/app/api/obsidian-review/inbox/route.ts`（Macのpull/ack）
- DB: `apps/jarvis-dashboard/supabase/migrations/20261110_obsidian_review_inbox.sql`
- Mac: `scripts/jarvis_obsidian_review_inbox.py`
- LaunchAgent雛形: `launchd/obsidian_review_inbox_runner.sh`, `launchd/install_obsidian_review_inbox_launchd.sh`

## 本番設定状況

- Supabase migration `20261110_obsidian_review_inbox.sql` を2026-11-10に適用済み。キューは一時保管のみで、ack時にレビュー本文を消去する。
- `jarvis-dashboard` のAPIを本番へ反映済み。送信キーとMac取得キーは別々に生成し、Vercel ProductionとMacの `.env.jarvis_private` に設定済み。値は表示・記録しない。
- ChatGPT Site **Obsidian 日次レビュー**をowner-onlyで公開済み: <https://obsidian-daily-review.cherishedcatfish1.chatgpt.site>
- SiteのMCP pluginはChatGPTにインストール済み。公開後の `server/discover` と `tools/list` は成功し、ツールは `submit_daily_review` のみ。
- Mac LaunchAgent `com.matsunoma.jarvis.obsidian-review-inbox` は60秒間隔で稼働中。正本Vaultと既存Google Drive Syncの状態を確認し、認証付きdry-run取得も成功した。
- 実レビューを使ったVault/Drive書き込みはまだ行っていないため、iPhoneへの実到達までは未確認。初回の実運用で保存・同期ログを確認する。

## ChatGPTでの利用

新しいChatGPTチャットを開き、プラグイン **Obsidian 日次レビュー**を使える状態にして日次レビューを行う。レビューの最後に **「今日のレビューを確定」** と伝えると、会話で確認できる生ログと戦術レビューを `submit_daily_review` が送信する。今回プラグインを追加した既存チャットにはツール一覧が反映されない場合があるため、新しいチャットで開始する。

ChatGPTの返答は「受付済み」で、Vaultへの保存完了ではない。Macが起動・オンラインなら通常60秒以内にVaultへ2つのMarkdownを作成し、既存 `jarvis_obsidian_ogd_retag.py` 経由で同期した後にキューをackする。Macがsleep/offline中は復帰後に処理する。

## Macでの手動実行

```bash
cd ~/git-repos
set -a
source .env.jarvis_private
set +a
~/selenium_env/venv/bin/python scripts/jarvis_obsidian_review_inbox.py --dry-run
~/selenium_env/venv/bin/python scripts/jarvis_obsidian_review_inbox.py
```

`--dry-run` はpending IDと日付だけを表示し、Vaultファイル作成・期限切れキュー削除は行わない。LaunchAgentが稼働中の通常運用では手動実行しない。エラー調査時はログを確認してから、LaunchAgentを停止して手動実行する。

## 制約・運用

- ChatGPT Site plugin送信の応答は受付確認であり、Vault/Drive/iPhone保存完了を意味しない。Macのログで `saved and synced` を確認して完了扱いにする。
- Macがofflineまたはスリープ中は、起動後の次回ポーリングまで遅れる。
- ChatGPTに見えている会話内容だけが生ログ対象。サービス側にある非表示の会話履歴を取得する機能ではない。
- ChatGPT Plusの直接カスタムMCP接続はread/fetch権限まで。書込みアクションにはSites hosted plugin等のPlus対応経路を使う。APIルート側にはMCP実装もあるが、Business/Enterprise/Edu等でFull MCPが使える場合の選択肢。
- 受信payloadはレビュー本文を含む。Vaultが正本で、Cloudキューは一時保管。APIキーと本文をログ出力しない。
- LaunchAgentログは `~/Library/Logs/jarvis_obsidian_review/`。`saved and synced` はVault保存と既存OGD同期の両方が成功した記録。
