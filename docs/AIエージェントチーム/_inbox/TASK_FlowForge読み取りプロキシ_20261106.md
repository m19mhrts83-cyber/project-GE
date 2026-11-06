# TASK — FlowForge 読み取り専用プロキシ（ChatGPT 接続）

規格: [`30_共通Agentフォルダ規格_BCP`](../30_共通Agentフォルダ規格_BCP_20261017.md)  
調査正本: [`54_FlowForge読み取りAPI調査_20261106.md`](../54_FlowForge読み取りAPI調査_20261106.md)

| 項目 | 値 |
|---|---|
| task_id | flowforge-read-proxy-20261106 |
| agent_id | （横断・ハブ） |
| executor | codex（実装）／cursor（レビュー可） |
| status | queued |
| started_at | |
| finished_at | |

## Goal

ChatGPT（Custom GPT Actions）が、FlowForge の **share URL** または shareId を渡すだけで、作業フロー JSON（ノード・接続・説明）を取得できる読み取り専用エンドポイントを用意する。

## Background

- FlowForge 本体には既に `GET /api/shares/{shareId}` がある
- ただし `Origin` が FlowForge ドメイン以外だと **403 forbidden_origin**
- ChatGPT 直叩きは不可。project-GE 側の薄いプロキシが最短
- FlowForge **本体ソースは repo に無い**。本体改修はスコープ外

## Scope

### In

- 読み取り専用 HTTP API（JSON）
- shareId またはフル share URL の受理
- 任意: `flow_id` → `config/flowforge_share_urls.json` で share 解決
- API キー認証（Bearer または専用ヘッダ）
- 既存 CLI `scripts/jarvis_flowforge_share_fetch.py` と応答形を揃える
- OpenAPI 断片（ChatGPT Actions 登録用）を docs に残す
- 単体テスト（モック or dry fixture）

### Out

- FlowForge 本体の改修・デプロイ
- フロー編集・実行・書込 API
- 認証なし公開
- 本番デプロイ（**松野の事前承認が必要**。実装＋ローカル／Preview まで）

## Requirements

1. `GET`（推奨パス案）:
   - `/api/flowforge/share/{shareId}`
   - または `/api/flowforge/resolve?url=…` / `?flow_id=…`
2. 内部で FlowForge `GET /api/shares/{id}` を  
   `Origin: https://flowforge-259747770348.asia-northeast1.run.app` 付きで呼ぶ
3. 未認証 → 401。不正キー → 401/403
4. 上流 403/404 を透過または分かりやすい JSON エラーに
5. レスポンスに秘密（API キー・env）を含めない
6. キーは `.env.jarvis_private` 例: `FLOWFORGE_READ_PROXY_KEY`（値はドキュメントに書かない）
7. `jarvis-outbound-confirm` / デプロイ承認: Production 反映は別承認

## Acceptance Criteria

- [ ] ローカルまたは Preview で、正しいキー付き GET が 312 の share JSON を返す
- [ ] キー無しが拒否される
- [ ] ChatGPT Actions 用 OpenAPI（パス・ヘッダ・例）が docs にある
- [ ] `docs/運用コマンド一覧.md` にプロキシ節がある（または 54 からリンク）
- [ ] `tests/` または同等のチェックが通る
- [ ] Production デプロイは未実施、または松野承認済みと明記

## References

- 調査: `docs/AIエージェントチーム/54_FlowForge読み取りAPI調査_20261106.md`
- CLI: `scripts/jarvis_flowforge_share_fetch.py`
- share 一覧: `config/flowforge_share_urls.json`
- 312 例: share `tn9-F4fhdIgHVpRl` / flow `flow_M8SvKC1IDTDi496Vw-DgGjpD`
- 置き場候補: `apps/jarvis-dashboard`（自分用）

## Instructions（Codex）

1. 調査 MD と CLI を読む（重複実装しない）
2. 最小の Route Handler を追加（Dashboard 推奨）
3. env example にキー名だけ追記（値なし）
4. OpenAPI 断片を `docs/AIエージェントチーム/` または `apps/jarvis-dashboard/docs/` に書く
5. ローカル検証手順を TASK の成果物に残す
6. `#ai-hub` または完了報告に「デプロイ未／要承認」を明記

## Safety

- 読み取りのみ。POST で FlowForge を更新しない
- キーを Git／Slack／チャットに出さない
- Production デプロイ・対外公開はユーザー事前承認

## Output

- 実装差分（PR 可）
- OpenAPI 断片
- 検証ログ（ステータス・ノード数だけ。フロー全文は任意で `output/`）
- 推奨次アクション（ChatGPT Actions 登録手順 5 行以内）
