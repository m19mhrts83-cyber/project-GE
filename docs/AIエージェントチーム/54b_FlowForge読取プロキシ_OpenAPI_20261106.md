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
  version: "1.0.0"
  description: Read-only FlowForge (AI Automation) flow JSON via share API.
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
components:
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

1. [chatgpt.com/plugins](https://chatgpt.com/plugins) → **追加** → **カスタム MCP サーバー**
2. 名前: `FlowForge Jarvis MCP`（任意）
3. URL: `https://jarvis-dashboard-amber.vercel.app/api/flowforge/mcp`
4. Authentication: API Key / Bearer → `.env.jarvis_private` の `FLOWFORGE_READ_PROXY_KEY`
5. リスク確認 → 作成 → インストール
6. 既存プラグイン **FlowForge読取（Jarvis）** と併用可（スキル＋MCP）

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
