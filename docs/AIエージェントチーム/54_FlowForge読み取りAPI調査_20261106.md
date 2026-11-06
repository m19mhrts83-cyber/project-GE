# FlowForge（AI Automation）読み取り API 調査

- 調査日: 2026-11-06
- 対象: `https://flowforge-259747770348.asia-northeast1.run.app`
- 目的: URL を ChatGPT／他エージェントに渡すだけでフロー定義を読み、改善検討できる状態
- 結論: **新規 API を FlowForge 本体に足す前に、既存 share API を使うのが最短**

## 役割分担（合意したい形）

| 層 | 役割 |
|---|---|
| FlowForge | 作業フローの正本（ノード・接続・指示） |
| ChatGPT（チャッピー） | フロー読取 → 設計・改善点の検討 |
| Codex / Cursor / Claude Code | 改善の実装・テスト・再検証 |

## 調査結果（事実）

### 1. 製品とソースの所在

- UI タイトルは **「AI Automation — 業務自動化フローを設計」**（社内呼称 FlowForge）
- `~/git-repos`（project-GE）内に **FlowForge 本体ソースは無い**
- Cloud Run 上の第三者／いけとも系プロダクト。本体改修は **ベンダー依頼 or ソース共有が必要**

### 2. 既存の読み取り API（既にある）

```http
GET /api/shares/{shareId}
Origin: https://flowforge-259747770348.asia-northeast1.run.app
# または Referer: …/share/{shareId}
```

| 条件 | 結果 |
|---|---|
| `Origin` / `Referer` が FlowForge ドメイン | **200** … フロー JSON |
| Origin なし / ChatGPT Origin | **403** `{"error":"forbidden_origin"}` |
| `GET /api/flows/{flowId}`（未認証） | **404**（編集用の公開読取は無し） |
| `/openapi.json` 等 | 404 |

検証例（312）:

- share: `tn9-F4fhdIgHVpRl`
- flow id: `flow_M8SvKC1IDTDi496Vw-DgGjpD`
- 応答: `{ "flow": { id, name, description, nodes, edges, createdAt, updatedAt, look } }`
- ノード種別例: `start` / `tool` / `claude` / `human` / `subflow` / `end`
- AI 向け指示は主に各ノード `data.description`（長文プロンプトは短い説明レベル）

共有 URL 正本: `config/flowforge_share_urls.json`  
（`/flows/…` 編集 URL ではなく **`/share/…` 閲覧専用**を使う）

### 3. ChatGPT 直アクセスは不可（現状）

- Custom GPT Actions が `Origin: https://chatgpt.com` 等で叩くと **403**
- ブラウザ連携（①）も接続環境次第で不可、との前提と一致
- **API を「ある」だけでは ChatGPT は読めない** → 認証付きプロキシ or ベンダー側の API キー対応が必要

### 4. ローカルエージェント（Codex／Cursor／Claude）は今すぐ可

`Origin` ヘッダを付けたサーバ側 fetch なら、追加改修なしで JSON 取得できる。

```bash
cd ~/git-repos && /Users/matsunomasaharu2/selenium_env/venv/bin/python \
  scripts/jarvis_flowforge_share_fetch.py --share tn9-F4fhdIgHVpRl
# または --flow-id flow_M8SvKC1IDTDi496Vw-DgGjpD （share 一覧から解決）
```

## 推奨ロードマップ（最小改修）

| Phase | 内容 | 誰 | FlowForge 本体改修 |
|---|---|---|---|
| **0（済・本調査）** | 既存 `/api/shares` の確認 | Jarvis | 不要 |
| **1（即）** | CLI 取得＋運用コマンド／本 MD | Jarvis | 不要 |
| **2（推奨）** | **読み取り専用プロキシ**（API キー）。URL or shareId → JSON。ChatGPT Actions から呼ぶ | Codex／Cursor | 不要 |
| **3（任意）** | ベンダーへ公式 Agent API（API キー・CORS・レート）を依頼 | 人＋ベンダー | 要 |

Phase 2 の利点: project-GE 側だけで完結。編集権限は持たせず、秘密はマスク方針をプロキシ側で実装可能。

### Phase 2 案（プロキシ）

- 入口例: `GET /api/flowforge/share/{shareId}` または `?url=https://…/share/…`
- 認証: Bearer / ヘッダ API キー（`.env.jarvis_private`。チャット禁止）
- 内部: FlowForge `/api/shares/…` を `Origin` 付きで取得してそのまま／要約して返す
- 置き場候補: `apps/jarvis-dashboard`（自分用）または薄い Cloud Run
- **デプロイ前に松野承認**（対外公開・キー漏洩面）

### ChatGPT 側（Phase 2 後）

1. Custom GPT Actions にプロキシ OpenAPI を登録
2. ユーザーは FlowForge の **share URL**（または flow URL＋registry 解決）を渡す
3. GPT が JSON を読み、問題点・改善案を返す
4. 実装は Codex／Cursor へ TASK.md で渡す

## やらないこと

- 認証なしで社内フローを全世界公開
- `/flows/{id}` 編集 API をエージェントに渡す（書込リスク）
- FlowForge ソースが無いのに「本体に API 追加」を Codex に丸投げ
- 秘密・トークンをフロー JSON／チャットに再掲

## Codex 向け TASK

→ [`docs/AIエージェントチーム/_inbox/TASK_FlowForge読み取りプロキシ_20261106.md`](./_inbox/TASK_FlowForge読み取りプロキシ_20261106.md)

## 関連

- 共有 URL: `config/flowforge_share_urls.json`
- 一覧: [`15_FlowForge全体系_進捗_20261010.md`](./15_FlowForge全体系_進捗_20261010.md)
- CLI: `scripts/jarvis_flowforge_share_fetch.py`
- コマンド: `docs/運用コマンド一覧.md`「FlowForge フロー読取」
