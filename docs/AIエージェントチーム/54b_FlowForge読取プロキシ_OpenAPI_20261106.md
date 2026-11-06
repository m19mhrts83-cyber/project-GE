# FlowForge 読み取りプロキシ — OpenAPI（ChatGPT Actions 用）

- 実装: `apps/jarvis-dashboard/app/api/flowforge/`
- 調査: [`54_FlowForge読み取りAPI調査_20261106.md`](./54_FlowForge読み取りAPI調査_20261106.md)
- **Production デプロイは松野承認後**。未承認のあいだはローカル／Preview のみ

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
    description: Production (after deploy approval)
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

## ChatGPT 登録手順（デプロイ後）

1. Custom GPT → Actions → Import 上記 OpenAPI
2. Authentication → API Key → Bearer、キーは Actions 側のみ
3. ユーザーは share URL（または「312のフロー見て」）を渡す
4. GPT が `resolve` / `share` を呼び、改善案を返す

## curl 例（値は出さない）

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
curl -sS -H "Authorization: Bearer $FLOWFORGE_READ_PROXY_KEY" \
  "http://localhost:3001/api/flowforge/resolve?agentId=312&summary=1"
```
