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

## 編集用の読み取りと修正文の待ち箱（2026-11-21）

松野さんが修正文をコピーして貼る作業をなくすための追加。FlowForge には書き込み口が無いので、
**FlowForge 画面の AIアシスタントへ、Mac のプログラムが代わりに入力する**形にした。

### 流れ（番号は会話と対応）

| # | 主体 | 実行者／道具 | 作業 |
|---|---|---|---|
| 1 | AI | ChatGPT＋MCP `resolve_flowforge_flow`（`view=edit`） | フローを読む（ノードの ID・種別・タイトル・説明・所属サブフロー、矢印、つながっていないノード） |
| 2 | AI | ChatGPT | 図・改訂案 → 修正文（1文1操作・実際のタイトルで名指し・1回4項目程度） |
| 3 | 人間 | 松野さん（ChatGPT のチャット） | 修正文を読み「これで反映して」と言う |
| 4 | AI | ChatGPT＋MCP `queue_flowforge_edit` | 了承済みの修正文を待ち箱（Supabase `flowforge_edit_queue`）へ置く |
| 5 | プログラム | Mac `scripts/jarvis_flowforge_assistant_paste.py --queue-once` | 待ち箱から拾い、置き場の Chrome で AIアシスタントへ入力・送信、返事と前後のノード数を書き戻す |
| 6 | 外部サービス | FlowForge の AIアシスタント | フローを書き換える |
| 7 | AI | ChatGPT＋MCP `get_flowforge_edit_status` → `view=edit` で読み直し | 狙いどおりか照合。ずれていれば 2 へ戻る（今回の取り直し） |

- 5 は AI を呼ばない。Mac が起きていて、Chrome が開いている時だけ動く
- 5 を自動で回す仕組み（launchd）は未設定。今は手で `--queue-once` を実行する
- 7 の読み直しは共有リンク経由。共有リンクが編集の最新を映すかは未確認（映さない場合は共有リンクの発行し直しが要る）

### 置き場の決まり

- **FlowForge の編集は「Chrome の既定プロフィール」だけで行う**（2026-11-21 松野さん）。
  FlowForge は最初に保存したブラウザを持ち主として扱うため
- 持ち主でないブラウザで `/flows/flow_…` を開かない。同じ ID の空の「新しいフロー」がそのブラウザに作られる
  （プログラムは先に保存内容を確かめ、持ち主でなければ編集画面を開かずに止める）
- Cursor のブラウザにある元のフローは、移し終わるまで消さない
- 移し方: 元のブラウザで「フローを共有」→ 共有 URL を Chrome の既定プロフィールで開く →
  上部の「このフローを自分の作業用にコピー」。ID が変わるので registry を付け替える。
  「みんなのフローに載せる」は押さなくてよい
- Chrome の「表示 > デベロッパー > Apple Events からの JavaScript を許可」がオンであること

### 道具（MCP）

| Tool | 用途 |
|---|---|
| `resolve_flowforge_flow` | `view`: `summary`（既定）／`edit`（修正文づくり・照合用）／`full` |
| `queue_flowforge_edit` | `agentId`・`instructions`・`confirmedByUser=true`。2000文字・箇条書き6項目まで。待ち5件で満杯 |
| `get_flowforge_edit_status` | `id` → `queued`／`running`／`sent`／`error` と AIアシスタントの返事 |

待ち箱の表は `apps/jarvis-dashboard/supabase/migrations/20261121_flowforge_edit_queue.sql`（適用が要る）。
ChatGPT 側は、道具が増えたあとプラグイン「FlowForge Jarvis MCP」をつなぎ直す。

### Mac 側のコマンド

```bash
cd ~/git-repos && ~/selenium_env/venv/bin/python scripts/jarvis_flowforge_assistant_paste.py --agent 311 --check
cd ~/git-repos && ~/selenium_env/venv/bin/python scripts/jarvis_flowforge_assistant_paste.py --queue-list
cd ~/git-repos && ~/selenium_env/venv/bin/python scripts/jarvis_flowforge_assistant_paste.py --queue-once
```

### 検証（2026-11-21）

- 済: 311 のコピーを Chrome の既定プロフィールに作成（中身は元と一致）。確認モード・入力だけ・送信
  （編集を伴わない質問）・返事の取り込み・前後比較
- 未: 実際の修正文での書き換え、待ち箱を通した一連の流れ（表の適用とデプロイの後）、311 の registry 付け替え

## curl 例（値は出さない）

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
curl -sS -H "Authorization: Bearer $FLOWFORGE_READ_PROXY_KEY" \
  "http://localhost:3001/api/flowforge/resolve?agentId=312&summary=1"
```
