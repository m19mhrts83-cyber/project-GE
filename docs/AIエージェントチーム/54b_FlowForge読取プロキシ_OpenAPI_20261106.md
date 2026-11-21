# FlowForge 読み取りプロキシ — OpenAPI（ChatGPT Actions 用）

- 実装: `apps/jarvis-dashboard/app/api/flowforge/`
- 調査: [`54_FlowForge読み取りAPI調査_20261106.md`](./54_FlowForge読み取りAPI調査_20261106.md)
- **Production**: 2026-11-06 デプロイ済（`jarvis-dashboard` / `FLOWFORGE_READ_PROXY_KEY`）

## 認証

| 方式 | ヘッダ |
|---|---|
| Bearer | `Authorization: Bearer $FLOWFORGE_READ_PROXY_KEY` |
| 専用 | `x-flowforge-read-key: $FLOWFORGE_READ_PROXY_KEY` |

キーは `.env.jarvis_private` / Vercel Secret。チャット・GPT Instructions 本文に書かない（Actions の認証欄のみ）。

## エンドポイント

ベース（本番想定）: `https://jarvis-dashboard-amber.vercel.app`  
ローカル: `http://localhost:3001`

### 1. shareId 直指定

`GET /api/flowforge/share/{shareId}?summary=1`

### 2. URL / flowId / agentId 解決

`GET /api/flowforge/resolve?url=…`  
`GET /api/flowforge/resolve?flowId=flow_…`  
`GET /api/flowforge/resolve?agentId=312`  
`GET /api/flowforge/resolve?shareId=…`

`summary=1` でノード要約のみ（トークン節約）。

## OpenAPI 3.1（Actions 貼付用）

```yaml
openapi: 3.1.0
info:
  title: Jarvis FlowForge Read Proxy
  version: "1.1.0"
  description: FlowForge flow read, plus preview/apply (test flows only, unofficial). Read-only FlowForge (AI Automation) flow JSON via share API.
servers:
  - url: https://jarvis-dashboard-amber.vercel.app
    description: Production
paths:
  /api/flowforge/resolve:
    get:
      operationId: resolveFlowforgeFlow
      summary: Resolve share/flow/agent URL and return flow JSON
      parameters:
        - name: url
          in: query
          schema: { type: string }
          description: FlowForge share or edit URL
        - name: flowId
          in: query
          schema: { type: string }
        - name: agentId
          in: query
          schema: { type: string }
          description: e.g. 312
        - name: shareId
          in: query
          schema: { type: string }
        - name: summary
          in: query
          schema: { type: string, enum: ["1"] }
      responses:
        "200":
          description: Flow payload
        "401":
          description: Unauthorized
  /api/flowforge/share/{shareId}:
    get:
      operationId: getFlowforgeShare
      summary: Fetch flow by shareId
      parameters:
        - name: shareId
          in: path
          required: true
          schema: { type: string }
        - name: summary
          in: query
          schema: { type: string, enum: ["1"] }
      responses:
        "200":
          description: Flow payload
        "401":
          description: Unauthorized
  /api/flowforge/write/preview:
    post:
      operationId: previewFlowforgeChange
      summary: Preview a change to an allow-listed (test) flow. Writes nothing.
      description: >
        Returns a diff, baseUpdatedAt and confirmToken. Only flows in
        FLOWFORGE_WRITE_ALLOWED_FLOW_IDS are accepted (default: none).
      requestBody:
        required: true
        content:
          application/json:
            schema: { $ref: "#/components/schemas/ChangeRequest" }
      responses:
        "200": { description: Diff and confirmToken }
        "400": { description: Invalid change (unknown node, forbidden field, bad edge) }
        "403": { description: Flow not allow-listed / writes disabled }
  /api/flowforge/write/apply:
    post:
      operationId: applyFlowforgeChange
      summary: Write the previewed change (unofficial API). Call ONLY after Matsuno explicitly approves in the conversation.
      description: >
        apply は松野さんが会話で明示的に承認した後だけ呼ぶ。preview と同じ changes、
        preview の confirmToken と expectedUpdatedAt(=baseUpdatedAt) が必須。
        409 = preview 後にフローが変わった（preview からやり直す）。
        書き込み後に読み直して一致しなければ 502 verify_failed（成功とは扱わない）。
      requestBody:
        required: true
        content:
          application/json:
            schema:
              allOf:
                - { $ref: "#/components/schemas/ChangeRequest" }
                - type: object
                  required: [expectedUpdatedAt, confirmToken]
                  properties:
                    expectedUpdatedAt: { type: string }
                    confirmToken: { type: string }
      responses:
        "200": { description: Written and verified by re-reading }
        "409": { description: Stale updatedAt or token mismatch }
        "502": { description: Sync or verification failed (not a success) }
components:
  schemas:
    ChangeRequest:
      type: object
      required: [changes]
      properties:
        shareId: { type: string }
        url: { type: string }
        flowId: { type: string, description: "flow_… (must match the shared flow)" }
        changes:
          type: object
          additionalProperties: false
          properties:
            nodes:
              type: array
              items:
                type: object
                required: [id]
                additionalProperties: false
                properties:
                  id: { type: string }
                  title: { type: string }
                  description: { type: string }
            addEdges:
              type: array
              items:
                type: object
                required: [source, target]
                properties: { source: { type: string }, target: { type: string } }
            removeEdges:
              type: array
              items:
                type: object
                properties: { id: { type: string }, source: { type: string }, target: { type: string } }
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
security:
  - bearerAuth: []
```

## ChatGPT 登録手順（2026-11-06 更新）

**注意**: Plus アカウントでは **Custom GPT の新規作成は不可**（GPT 自体は 2026-12-11 廃止予定）。旧「Actions に OpenAPI 貼付」は使えない。代替は **Plugins**。

### 済（Jarvis 実施）

1. Plugin Creator（Work）で個人用プラグイン **「FlowForge読取（Jarvis）」** を作成・インストール済み
2. スキル指示（share URL / agentId / `summary=1`・読み取り専用・キー非再掲）を登録済み
3. 本番プロキシは稼働中（`FLOWFORGE_READ_PROXY_KEY`）

### 自動取得（カスタム MCP・2026-11-07）

実装: `GET|POST https://jarvis-dashboard-amber.vercel.app/api/flowforge/mcp`  
Auth: `Authorization: Bearer $FLOWFORGE_READ_PROXY_KEY`（REST プロキシと同じキー）  
Tool: `resolve_flowforge_flow`（`url` / `shareId` / `flowId` / `agentId`、既定 `summary=true`）

**ChatGPT への登録**

ChatGPT の「カスタム MCP」UIは **OAuth / 認証なし**のみ（Bearer 欄なし）。  
→ 登録 URL に `?key=` を埋め、認証は **認証なし** を選ぶ。

1. [chatgpt.com/plugins](https://chatgpt.com/plugins) → **追加** → **カスタム MCP サーバーを追加**
2. 名前: `FlowForge Jarvis MCP`
3. 説明: `FlowForge フロー読取（read-only）`
4. URL: `https://jarvis-dashboard-amber.vercel.app/api/flowforge/mcp?key=` + `FLOWFORGE_READ_PROXY_KEY`
5. 認証: **認証なし**
6. リスク確認にチェック → **プラグインとして作成** → インストール
7. 既存 **FlowForge読取（Jarvis）**（スキル）と併用可

curl / Jarvis 本線は従来どおり `Authorization: Bearer …`（`?key=` 不要）。

### チャッピー（ChatGPT）での使い方

| 渡し方 | できる？ | 例 |
|---|---|---|
| **FlowForge の share URL を貼る** | **はい**（MCP 接続後） | `https://flowforge-….run.app/share/xxxx` を貼って「設計改善して」 |
| **編集画面の `/flows/flow_…` URL** | はい（agent 登録の share に解決できるとき） | 312 の編集 URL |
| **「agentId 312 を見て」** | はい | `@FlowForge読取（Jarvis） agentId 312 を読んで改善案を` |
| **URL なし・MCP 未接続** | 不可（自動取得できない） | Jarvis に取ってもらい要約を貼る |

推奨プロンプト:

```
@FlowForge読取（Jarvis）
このフローを読んで、優先度順に設計改善案を出して。
https://flowforge-259747770348.asia-northeast1.run.app/share/tn9-F4fhdIgHVpRl
```

または:

```
@FlowForge読取（Jarvis） agentId 312 のフローを summary で読んで改善案を。
```

停止: `FLOWFORGE_READ_PROXY_DISABLE=1`

## curl 例（値は出さない）

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
curl -sS -H "Authorization: Bearer $FLOWFORGE_READ_PROXY_KEY" \
  "http://localhost:3001/api/flowforge/resolve?agentId=312&summary=1"
```

## 書き込み（試作・2026-11-21）

**位置づけ**: 方式B（松野さん決定 2026-11-21）。FlowForge の**公式な書き込み API は無い**。画面が使う非公式の保存 API（`POST /api/session` → `POST /api/flows/sync`）を使う試作。**テスト用フローだけ**で動かす。311 本線・旧デモ・他のフローには書かない。

### 注意（必ず読む）

- **非公式 API**: 予告なく変わる・止まる。第三者製品（ソース無し）で、**利用規約上のリスクは未確認**（規約は読めていない）。
- **ブラウザの編集は上書きされうる**: 編集の正本はブラウザの localStorage。画面は 2 秒後に「画面の内容が前回保存と違うとき」だけサーバへ送る（一方向）。サーバから読み戻す処理は JS 上に見当たらない。→ **この API で書いても、松野さんのブラウザの画面は変わらない**。ブラウザ側でそのフローを編集すると、古い内容でサーバを上書きする。
- **共有リンクが最新を指すか未確認**: 読み直しは共有 API 経由。スナップショットなら読み直しが一致せず `verify_failed`（書き込みは行われている可能性があるので `backupId` で確認／ロールバック）。
- 競合: サーバ側が updatedAt をどう扱うかは未確認。このプロキシ側で `expectedUpdatedAt` と確認トークンで守る。

### 仕組み（2段階）

| 段階 | 呼び方 | 内容 |
|---|---|---|
| preview | `POST /api/flowforge/write/preview` / MCP `preview_flowforge_change` | 現在のフローを取得 → 変更案を当てた差分と `confirmToken`・`baseUpdatedAt` を返す。**何も書かない** |
| apply | `POST /api/flowforge/write/apply` / MCP `apply_flowforge_change` | `confirmToken`＋`expectedUpdatedAt` 必須。ずれ→409。バックアップ→sync→読み直して一致確認。不一致は 502（成功と言わない） |
| rollback | `POST /api/flowforge/write/rollback`（`{shareId, backupId}`） | バックアップを書き戻す。管理用（MCP・OpenAPI には出さない） |

`confirmToken` = HMAC（フロー ID・元の内容ハッシュ・変更後の内容ハッシュ）。別の変更・元フローが変わった場合は一致しない。

変更できるもの（それ以外は 400）: ノードの `title` / `description`、接続（`addEdges` / `removeEdges`）。ノード種別・位置・新規ノード・削除は不可。存在しないノード、自己ループ、end からの接続、start への接続、重複接続は拒否。

### 設定（秘密は値を書かない）

| 名前 | 場所 | 内容 |
|---|---|---|
| `FLOWFORGE_WRITE_ALLOWED_FLOW_IDS` | `.env.jarvis_private` / Vercel env | 書き込み可の flow ID（カンマ区切り）。**既定は空＝全拒否** |
| `FLOWFORGE_ANON_ID` | 同上 | 画面の localStorage `flowforge:anon-id` の値。**松野さんが自分で設定**（エージェントはブラウザから抜かない）。ログ・応答に出さない |
| `FLOWFORGE_READ_PROXY_KEY` | 既存 | 認証と確認トークンの署名に使う（REST の書き込みはヘッダのみ。`?key=` 不可） |
| `FLOWFORGE_BACKUP_DIR` | 任意 | 既定は `.jarvis_state/flowforge_backups`（git 管理外）。Vercel は書き込み不可のため、**試作はローカル（`npm run dev`）で実行**が確実 |

### 止め方

1. `FLOWFORGE_WRITE_ALLOWED_FLOW_IDS` を空にする（書き込みだけ全拒否。読み取りは継続）
2. `FLOWFORGE_WRITE_DISABLE=1`（書き込み系を停止）／`FLOWFORGE_READ_PROXY_DISABLE=1`（読取も含め全停止）

### 戻し方

apply の応答（または失敗時の `backupId`）のファイルが `.jarvis_state/flowforge_backups/` にある。

```bash
curl -sS -X POST -H "Authorization: Bearer $FLOWFORGE_READ_PROXY_KEY" -H "Content-Type: application/json" \
  -d '{"shareId":"<テスト用 share>","backupId":"flow_…__2026-….json"}' \
  http://localhost:3001/api/flowforge/write/rollback
```

### ChatGPT からの使い方（チャッピー）

1. 「このフローを読んで修正案を」→ 既存の読取で現状把握
2. 修正案が固まったら `preview_flowforge_change`（shareId・changes）→ 差分を松野さんに見せる
3. **松野さんが「実行してよい」と明示した後だけ** `apply_flowforge_change`（同じ changes・`confirmToken`・`expectedUpdatedAt`）
4. 結果の `verified: true` を確認して報告。`409` は preview からやり直し、`verify_failed` は成功と言わず `backupId` を報告

### 実機テスト手順（松野さん準備後）

1. FlowForge でテスト用フローを新規作成し、「フローを共有」で share URL を作る
2. 松野さんが `FLOWFORGE_ANON_ID`（そのブラウザの値）と `FLOWFORGE_WRITE_ALLOWED_FLOW_IDS=<テスト用 flow_…>` を `.env.jarvis_private` に設定
3. `npm run dev` で起動し、preview → apply → 共有リンクで反映確認 → rollback を一巡
4. 確認すること: ①共有が最新を指すか ②ブラウザ画面に反映されるか（されない想定）③ブラウザ編集後に上書きされるか
