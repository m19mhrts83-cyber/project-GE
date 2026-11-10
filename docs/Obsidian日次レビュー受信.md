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

## 初回有効化手順（未実施）

1. Migration `20261110_obsidian_review_inbox.sql` は2026-11-10にJarvis Supabaseへ適用済み。APIコードが本番反映される前にキュー表だけ作成済み。
2. 十分にランダムな別々のキーを2つ生成する。値はMacの `.env.jarvis_private`、Vercel Secret、ChatGPT Siteのserver-side secret設定だけに入れ、git・チャット・Siteの本文や画面側コードへ書かない。
   - `OBSIDIAN_REVIEW_SUBMIT_KEY`: ChatGPT Site pluginからqueueへsubmit
   - `OBSIDIAN_REVIEW_POLL_KEY`: MacポーラーのGET/ack
3. Vercel `jarvis-dashboard` のEnvironment Variablesに両キーを設定し、レビュー承認後に該当ブランチを本番へdeployする。既存FlowForge読取APIの権限・キーとは共有しない。
4. `.env.jarvis_private` に上記2変数を設定する（値を表示しない）。必要なら `OBSIDIAN_REVIEW_INBOX_URL` でDashboard base URLを上書きする。
5. ChatGPT Plusでは直接の外部MCP write connectorは使えないため、ChatGPT Sites上のprivate pluginにMCP toolを追加し、server-side secret `OBSIDIAN_REVIEW_SUBMIT_KEY` を使って `POST /api/obsidian-review/submit` を呼ぶ。OpenAI公式案内ではSitesはPlus/Proで利用可能だが、サイトの作成・公開とプラグイン接続は別手順。既存FlowForge read-only MCPとは別プラグインにする。
6. Site pluginの指示: `submit_daily_review` だけを公開し、「今日のレビューを確定」で日本時間の日付・会話で確認できる生ログ・確定した戦術レビューを送る。UUID v4を作成し、再試行には同じUUIDを使う。レスポンスが受付だけであることを明言し、Vault/Drive同期前に保存完了と案内しない。
7. 手動起動で受信→Vault→OGD→ackを確認し、その後 `launchd/install_obsidian_review_inbox_launchd.sh` を実行する。確認には試験用レビューを使い、iPhone側への到達も見る。

### ChatGPT Sitesでの作成依頼文

Site作成時に以下を使い、OpenAPIファイル `docs/obsidian-review-submit-openapi.yaml` もSiteのreference資料として渡す。キー値はSite作成チャットへ貼らず、SiteのEnvironment/Secrets UIで `OBSIDIAN_REVIEW_SUBMIT_KEY` として登録する。Siteがサーバー側SecretとしてAPIへ渡せない場合は、キーをブラウザ側・Site内容・ソース・URLへ移さず、設定を止める。

```text
このSiteを自分だけが使うprivate pluginとして仕上げてください。
MCP toolは submit_daily_review の1つだけにしてください。
実行条件は私が「今日のレビューを確定」と明示したときだけです。
toolは会話で確認できる生ログと確定した戦術レビューを分け、日本時間の日付とUUID v4を付け、次のAPIへPOSTしてください:
https://jarvis-dashboard-amber.vercel.app/api/obsidian-review/submit
OpenAPI: docs/obsidian-review-submit-openapi.yaml
Authorization: BearerはSiteのserver-side secret OBSIDIAN_REVIEW_SUBMIT_KEYから設定し、ブラウザ側コードやSite本文へ出さないでください。
リトライ時は同じreview_idを再利用してください。APIの202は受け付けただけです。MacのObsidian/Drive同期完了前に保存完了と表示しないでください。
読み取り・検索・編集・削除のtoolは追加しないでください。公開前にtoolの送信先、権限、secretの扱いを確認してください。
```

## Macでの手動実行

```bash
cd ~/git-repos
set -a
source .env.jarvis_private
set +a
~/selenium_env/venv/bin/python scripts/jarvis_obsidian_review_inbox.py --dry-run
~/selenium_env/venv/bin/python scripts/jarvis_obsidian_review_inbox.py
```

`--dry-run` はpending IDと日付だけを表示し、Vaultファイル作成・期限切れキュー削除は行わない。通常実行はVaultとDriveに書き込むため、運用開始時の人の確認後に行う。

## 制約・運用

- ChatGPT Site plugin送信の応答は受付確認であり、Vault/Drive/iPhone保存完了を意味しない。Macのログで `saved and synced` を確認して完了扱いにする。
- Macがofflineまたはスリープ中は、起動後の次回ポーリングまで遅れる。
- ChatGPTに見えている会話内容だけが生ログ対象。サービス側にある非表示の会話履歴を取得する機能ではない。
- ChatGPT Plusの直接カスタムMCP接続はread/fetch権限まで。書込みアクションにはSites hosted plugin等のPlus対応経路を使う。APIルート側にはMCP実装もあるが、Business/Enterprise/Edu等でFull MCPが使える場合の選択肢。
- 受信payloadはレビュー本文を含む。Vaultが正本で、Cloudキューは一時保管。APIキーと本文をログ出力しない。
- 本番DB migrationは2026-11-10適用済み。Vercel Secrets、デプロイ、LaunchAgent登録、ChatGPT Site接続は別途有効化が必要。
