# FlowForge → Obsidian 日次レビュー保存連携 調査

- 調査日: 2026-11-10
- 範囲: ローカルリポジトリ、FlowForge読取API/MCP、Obsidian保存とGoogle Drive同期の既存経路
- 制約: 調査・設計のみ。実装・設定変更・ノート保存はしていない

## 結論

**FlowForge関連の既存APIはあるが、読み取り専用。ChatGPTからMarkdownを送ってObsidianに保存する既存Webhook/APIは確認できなかった。**

確認できたFlowForge APIは、共有フローを読む `GET /api/flowforge/resolve`、`GET /api/flowforge/share/{shareId}` とStreamable HTTP MCPの `resolve_flowforge_flow`。FlowForge上の共有APIをサーバー側から読む機能で、Markdownの受信・ファイル保存機能はない。現在のMCP登録ツール一覧も読み取りツール1件のみ。

よって、優先構成のうち `ChatGPT → 既存FlowForge API → Obsidian` はそのままでは成立しない。既存のVault・OGD同期は維持したまま、**Mac側に受信・検証・保存する小さな経路**を新設するのが現実的。実装承認後に設計を具体化する。

## 確認できた事実

### 1. FlowForgeのローカル資産と既存API

- FlowForge本体ソースはproject-GE内にない。ローカルにあるのは共有URL台帳、フロー読取スクリプト、ダッシュボード側の読取プロキシ/MCP。
- FlowForge共有APIの取得先は `GET https://flowforge-259747770348.asia-northeast1.run.app/api/shares/{shareId}`。プロキシはFlowForgeの `Origin` / `Referer` を付けて取得する。
- 読取プロキシの入口は次の通り。
  - `GET /api/flowforge/resolve?shareId=...|url=...|flowId=...|agentId=...`
  - `GET /api/flowforge/share/{shareId}`
  - `GET /api/flowforge/mcp`（認証付き疎通）と `POST /api/flowforge/mcp`（MCP JSON-RPC）
- 認証は `Authorization: Bearer` または `x-flowforge-read-key`。MCPでは互換用のクエリ認証も実装されている。**鍵の値は本報告に記載しない。**
- 実装はupstreamにGETだけを送り、フローJSONまたはノード要約を返す。MCPの公開ツールも `resolve_flowforge_flow` のみ。書込みメソッドや任意のFlowForge実行機能はない。
- 公開中のダッシュボードに認証なしでGETし、resolve/MCPともHTTP 401を確認。秘密値は送信していない。
- 2026-11-06の旧調査メモには「本番未デプロイ」とあるが、11-06追記のOpenAPI文書は「本番稼働中」と記載。今回のライブ401応答と整合するのは後者。なお、認証済みの実フロー取得までは本調査で再実行していない。

### 2. Webhook、受信形式、保存先

| 項目 | 確認結果 |
|---|---|
| FlowForgeからの受信用Webhook | リポジトリ内にObsidian保存用の既存エンドポイントは見つからず |
| 既存FlowForge APIの入力 | URL/shareId/flowId/agentId等の読取指定。上流は共有フローJSON |
| Markdown受信形式 | 既存API/MCPに定義なし |
| 読取プロキシの保存先 | なし。フローJSONを呼出元へ返す |
| Obsidianの保存先 | MacローカルVault `/Users/matsunomasaharu2/Documents/500_Obsidian_r1` |
| iPhone同期 | VaultのGoogle Drive Syncプラグインを利用。既存メモでは`autoPush`有効を確認済みだが、本調査では設定を開いたり変更したりしていない |

リポジトリには `scripts/jarvis_obsidian_ogd_retag.py` がある。これは既存Vaultのローカル文書をOGDプラグイン経由でGoogle Drive側に認識させ、iPhone Pull対象にする補助処理。FlowForgeからの受信口ではない。別のObsidian同期処理も存在するが、今回確認した範囲では日次レビューのChatGPT入力を受け取るAPIはない。

### 3. 関連フローの有無

- `15_FlowForge全体系_進捗_20261010.md` には「家族Journal週次材料係」のFlowForge定義が載っている。これは週次材料用であり、今回の「日次レビュー確定→生ログと戦術レビューを保存」と同じ機能だとは確認できない。
- 現行ローカルFlowForge台帳に載るagentIdで当該フローを特定できず、接続済み読取MCPで旧台帳のflow IDを引く試行も `share_not_found_for_agent` となった。週次フローの実体や入力・実行ノードは今回未確認。
- 現在の読取MCPはフロー定義を読む用途であり、フローを起動して結果を受け取るツールではない。

## ChatGPTからVaultへ保存する設計案

### 推奨案: Mac受信箱ポーラー

```text
ChatGPT「今日のレビューを確定」
  → ChatGPT側の専用送信アクション
  → 認証付きの一時保管API（レビュー本文を受け取る）
  → Mac側ポーラーが取得・検証
  → Vault内に生ログと戦術レビューを別Markdownで保存
  → 既存Google Drive Sync / OGD処理
  → iPhone
```

- ローカルVaultを唯一の編集正本とし、クラウドAPIは一時受け渡し箱に限定する。クラウド側からMacのファイルシステムへ直接アクセスさせない。
- ChatGPTからMacへ直接到達させる公開Webhookは避ける。Macから外向きに定期取得する形なら、ルーターのポート開放やVaultの外部公開をせずに済む。
- 受信は固定スキーマ（例: `id`, `date`, `raw_log`, `tactical_review`, `schema_version`）とし、Markdown本文を許可。APIキー認証、サイズ上限、ID重複排除、パス固定、Frontmatter/本文のサニタイズ、書込み先配下の検証を行う。
- `id`から決定的なファイル名を作り、重複受信で別ファイルや二重追記をしない。まずMac側のinboxへ一時保存し、検証成功後にVault内所定フォルダへatomic renameする。失敗・未取得・同期失敗はローカルログに残し、保存成功と表示しない。
- Vaultへの書込み後に既存OGDルートでDriveへ反映し、iPhone側で同期確認する。既存のDrive Sync設定やVault位置を移動・再設定しない。
- 認証・保管サービスの選定は未確定。すでに利用中の承認済み受け渡し基盤があるかを実装前に確認する。新たな有料サービスや外部保管を選ぶ場合は別途判断が必要。

### 代替案: FlowForgeに受信／起動Webhookが既存する場合

本リポジトリ・読取APIだけからは確認できない。FlowForge本体ソースがなく、認証済み編集画面や実行履歴を今回確認していないため、製品側に汎用Webhookノード・実行API・受信データ形式がある可能性は**未確認**。FlowForgeの実フロー画面またはベンダー仕様で確認できれば、既存機能を再利用できるか再評価する。

ただしFlowForgeから自宅MacのVaultへ直接書くには、Mac側への安全な到達経路と認証、再送・重複対策が別途必要。FlowForgeのWebhookが存在するだけでローカルVaultへ安全に届くとは限らない。

## 保存先の提案（未承認）

実装時はVault内に日次レビュー専用フォルダを定め、同じ日付・review IDで次の2ファイルを保存する案。

1. `YYYY-MM-DD_レビュー生ログ.md` — ChatGPTとのレビュー記録（必要な範囲の原文）
2. `YYYY-MM-DD_戦術レビュー.md` — 結論、勝ち筋/課題、次の一手などの構造化レビュー

正確なフォルダ、保持する会話範囲、日付の基準（日本時間）、追記か新規かは未決定。実装前に仕様化する。

## 未確認・残課題

- FlowForgeの認証済み実フローに、Webhook受信・HTTP実行・実行結果の取得機能があるか。
- 家族Journal週次材料フローの現行shareId・ノード定義・稼働状態。
- ChatGPT側の「今日のレビューを確定」を送信アクションへ結び付ける方法と、会話ログ全体をどの範囲で取得可能か。現行FlowForge MCPはこの保存処理に使えない。
- Mac側ポーラーの常時起動方法、通信・一時保管先、暗号化、保持期間、障害通知。
- Google Drive Syncの実際の同期完了とiPhoneでの到達確認。既存メモ上の設定事実は現況の同期成功を保証しない。

## 実装承認後の最小着手順

1. FlowForgeの実行系機能だけを読み取り確認し、既存再利用の可否を確定。
2. 日付・ファイル名・本文構造・重複/訂正・保持期間を決める。
3. 既存の認証済み受け渡し先の有無を確認し、Macポーラー方式を最小範囲で設計。
4. テスト用ノートでローカル保存→Drive反映→iPhone表示まで確認後、日次運用に移す。

## 参照

- [`54_FlowForge読み取りAPI調査_20261106.md`](AIエージェントチーム/54_FlowForge読み取りAPI調査_20261106.md)
- [`54b_FlowForge読取プロキシ_OpenAPI_20261106.md`](AIエージェントチーム/54b_FlowForge読取プロキシ_OpenAPI_20261106.md)
- [`15_FlowForge全体系_進捗_20261010.md`](AIエージェントチーム/15_FlowForge全体系_進捗_20261010.md)
- `apps/jarvis-dashboard/app/api/flowforge/`（読取API/MCP実装）
- `apps/jarvis-dashboard/lib/flowforgeShareProxy.ts`（認証・FlowForge読取）
- `scripts/jarvis_obsidian_ogd_retag.py`（既存Vault/OGD同期補助）

## 報告

調査結果のみを保存した。実装・設定変更・Vaultへのノート保存は未実施。次は実装承認後、FlowForgeの実行側機能の確認と受信経路の仕様確定から始める。
