# Jarvis × Cursor Cloud Agent（運用正本）

対話・調査の**本線は Cursor Cloud Agent**。ローカル Agent はフォールバック／Mac 専用。  
ダッシュボード構想の親: `.cursor/plans/トリアージのクラウド寄せ_65bfdb65.plan.md`  
仕様すり合わせ: `.cursor/plans/ダッシュボード仕様確認_b91ee6f9.plan.md`

## プラン認識（誤解防止）

| 点 | 正 |
|---|---|
| Cloud vs Local | **同じ Cursor 有料プラン**（Pro 等）。別契約ではない |
| 超過後 | [公式](https://cursor.com/docs/models-and-pricing) は **on-demand かプラン上げ**。「品質ダウングレードで無料継続」ではない |
| 安い継続感 | 主に **Cursor Models／Auto（ローカル）**。Cloud は選択モデルの **API 単価** |
| 同時実行 | Cloud に上限あり（Pro はコミュニティ回答で約8）。詰まったら [agents](https://cursor.com/agents) で古い run を archive |
| 運用方針 | **基本はクラウド。** 枠切れ・同時上限・MCP 未配線・Mac 専用だけローカル／Mac |

公式: [Cloud Agents help](https://cursor.com/help/ai-features/cloud-agents) / [capabilities（MCP）](https://cursor.com/docs/cloud-agent/capabilities.md)

## データの役割

| 層 | 正 |
|---|---|
| 原本 | OneDrive（215 等）／Gmail／Notion |
| 投影 | Supabase `jarvis-dashboard`（トリアージ・ウォッチ・カード） |
| 見る | https://jarvis-dashboard-amber.vercel.app/ |
| 対話・推敲 | Cloud Agent（本線）。会話で下書きを直す |
| 送信（理想） | **Cloud 上で確認後に送る**（Gmail API／yoritoori 相当。対外送信前確認は維持） |
| 送信（当面・フォールバック） | 未配線や失敗時は **Mac の yoritoori**。**Vercel Web 画面からは送らない** |

## 下書き〜送信の理想フロー（2026-08 追記）

ユーザー方針（確定）:

1. **基本はクラウドで完結** — 下書きを Cloud Agent と会話しながら見直し、その場で送れるなら送る  
2. **送れない／制限で止まったらローカル** — 従来どおり Mac の Cursor／`yoritoori_send.py`  
3. **Web ダッシュボードからのワンクリック送信はしない**（誤送信防止。表示・対応済み操作のみ）

技術メモ: Gmail API＋token（Secrets）があれば Cloud Agent から送信可能。対外送信前確認・`--via` 確認は Mac と同じ。

### Cloud 送信コマンド（実装済み）

```bash
# 1) プレビュー（チャットに出して「これで送っていいですか？」）
python scripts/jarvis_cloud_gmail_send.py --from-triage <triage_items.id> --preview

# 2) ユーザー承認後のみ実送信
python scripts/jarvis_cloud_gmail_send.py --from-triage <triage_items.id> --i-confirm-send
```

Secrets（Cloud My Secrets 推奨）: `GMAIL_CREDENTIALS_B64` ＋ `GMAIL_ESTATE_TOKEN_B64`（なければ `GMAIL_M19M_TOKEN_B64`）。  
生成: `python scripts/jarvis_cloud_secrets_prepare.py --include-gmail-send`  
失敗・未配線時は Mac の `yoritoori_send.py`。**admin token では送らない**（対外 From は estate／m19m）。

## Cloud MCP（ローカル mcp.json は継承されない）

設定場所: [cursor.com/agents](https://cursor.com/agents) → MCP ドロップダウン（個人）／Team なら Integrations & MCP。  
**HTTP 推奨**（認証情報は VM に載らない）。stdio は VM 内実行。

### 1. Notion（必須）

| 項目 | 値 |
|---|---|
| 種別 | HTTP |
| URL | `https://mcp.notion.com/mcp` |
| 認証 | OAuth（画面の指示に従う） |

**登録場所**: [cursor.com/agents](https://cursor.com/agents) の MCP ドロップダウン（または Dashboard → Integrations）。ローカルの Notion プラグインは **継承されない**。

疎通（Cloud 起動後）: 「Notion で『所有物件タスク管理』を検索して1件要約して」  
ローカル疎通済み: `notion-search` で同 DB を確認済み（2026-08-01）。  
切断時: agents の MCP で Re-authenticate。ルール: `notion-mcp-reauth.mdc`

### 2. NotebookLM（Cloud 初回はユーザー操作あり）

| 項目 | 値 |
|---|---|
| 種別 | stdio（現行パッケージ） |
| command | `npx` |
| args | `-y` `notebooklm-mcp@latest` |

**登録場所**: [cursor.com/agents](https://cursor.com/agents) → MCP（ローカル `mcp.json` は継承されない）。

**初回配線（Cloud run 内）**:

1. MCP 追加後、Cloud Agent で「NotebookLM の `get_health` を実行して」
2. `authenticated=false` なら **`setup_auth`**、または Mac で  
   `python scripts/jarvis_notebooklm_mcp_login.py`（`.env.jarvis_private` の `NOTEBOOKLM_EMAIL` / `NOTEBOOKLM_PASSWORD`。アカウントは **admin**）  
   → `browser_state/state.json` を書き、`get_health` で `authenticated=true` を確認
3. `add_notebook` で共有 URL を登録 → `list_notebooks` → `ask_question` で1問
4. 切れたら `re_auth` または再度 `setup_auth`

ソース正本は Drive `200_NoteBookLM`（`jarvis-notebooklm-drive-sources`）。ローカル MCP も同様に `setup_auth` が必要なことがある。

### 3. やらない MCP

- ローカル専用パス前提の stdio を無検証で増やさない
- Service Role / パスワードを MCP env に平文で増やしすぎない（Environment Secrets を優先）

## Cloud Environment Secrets（例）

Environment: リポジトリ `m19mhrts83-cyber/project-GE`（Dashboard に Active な environment あり）。  
値は Dashboard にのみ。Git・チャットに出さない。テンプレ名: [`config/cloud_agent_secrets.example.env`](../config/cloud_agent_secrets.example.env)

| Secret | 用途 |
|---|---|
| `JARVIS_SUPABASE_URL` | 投影 DB |
| `JARVIS_SUPABASE_SERVICE_ROLE_KEY` / `JARVIS_SUPABASE_SECRET_KEY` | 読取／upsert（**`sb_secret_` 新形式**） |
| `GEMINI_API_KEY` | リサーチ（`scripts/jarvis_gemini_research.py`） |
| `GMAIL_CREDENTIALS_B64` / `GMAIL_ADMIN_TOKEN_B64` | admin 取込（既存 GHA と同系） |
| `GMAIL_ESTATE_TOKEN_B64`（または `GMAIL_M19M_TOKEN_B64`） | **Cloud 対外送信**（`jarvis_cloud_gmail_send.py`） |
| `MS_GRAPH_*` | OneDrive レーン収集（GHA／Cloud）。**委任＋REFRESH_TOKEN**（`AUTHORITY=consumers`）

### 登録手順（手動・約1分）

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
python scripts/jarvis_cloud_secrets_prepare.py
# Cloud 送信も載せる場合:
python scripts/jarvis_cloud_secrets_prepare.py --include-gmail-send
# 生成: ~/.jarvis_state/cloud_agent_secrets.env
open https://cursor.com/dashboard/cloud-agents
# → My Secrets → Add Secrets → ファイル内容を貼る → Save（Runtime Secret 推奨）
rm -f ~/.jarvis_state/cloud_agent_secrets.env
```

自動化ブラウザからの貼り付けはフォーカス／クリップボード制約で失敗しやすい。**手元貼り付けを正とする。**

## OneDrive Graph（レーン GHA）

個人用 OneDrive は **委任＋デバイスコード**（アプリ専用は使わない）。正本: [`Jarvis_OneDrive_Graph.md`](Jarvis_OneDrive_Graph.md)

```bash
python scripts/jarvis_ms_graph_setup_check.py
# CLIENT_ID 設定後:
python scripts/jarvis_ms_graph_device_login.py
python scripts/jarvis_onedrive_graph.py --probe
python scripts/jarvis_onedrive_graph.py --path "215_神・大家さん倶楽部/…"
python scripts/jarvis_ms_graph_secrets_to_gha.py
# refresh 回転時:
python scripts/jarvis_ms_graph_sync_refresh.py --push-gha
gh workflow run jarvis-dashboard-lanes.yml
```

配線後は `jarvis-dashboard-lanes.yml` が Graph で materialize → `cards` upsert。Journal（Google Drive）だけ GHA スキップで Mac push 補完。

## admin Gmail と Gemini

| 対象 | やり方 |
|---|---|
| **admin Gmail 差分** | 既に GHA → `triage_items`。Cloud からはダッシュボード or Supabase 読取。詳細は下のクエリ例 |
| **Gemini リサーチ** | `GEMINI_API_KEY` ＋ `python scripts/jarvis_gemini_research.py "質問"` |
| **Workspace Gemini 会話履歴** | **同期しない**（対象外）。必要なら手動で NotebookLM／メモ／メール化 |

### triage_items の参照例（Service Role・ローカル／Cloud シェル）

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
python - <<'PY'
import os
from supabase import create_client
sb = create_client(os.environ["JARVIS_SUPABASE_URL"], os.environ["JARVIS_SUPABASE_SERVICE_ROLE_KEY"])
r = (
    sb.table("triage_items")
    .select("id,subject,from_email,status,lane,updated_at")
    .eq("status", "pending")
    .order("updated_at", desc=True)
    .limit(10)
    .execute()
)
for row in r.data or []:
    print(row.get("updated_at"), row.get("lane"), row.get("subject"))
PY
```

## Mac に残すもの（当面）

CHRLINE／オプチャ、Zaim Playwright、パートナー MD 全文取込、OneDrive ローカル path 依存（Graph 未設定時）。  
**対外送信**は Cloud スクリプト優先。未配線・失敗時は Mac の yoritoori。

## チェックリスト（初回配線）

1. [ ] Cloud environment を project-GE に接続
2. [ ] Secrets を上表どおり登録（`sb_secret_` ＋ 必要なら Gmail send B64）
3. [ ] Notion MCP（HTTP）追加 → OAuth 完了 → 1 検索成功
4. [ ] NotebookLM MCP（stdio）追加 → `setup_auth` → list／1 問成功
5. [ ] Supabase `sync_meta` を Cloud から読めることを確認
6. [ ] （任意）`jarvis_cloud_gmail_send.py --preview` が Cloud で動く
7. [x] `MS_GRAPH_*`（委任）→ lanes GHA 収集（downloadUrl 修正・Secrets 反映後に緑化確認）
8. [ ] on-demand 利用の要否を Dashboard Usage で確認（枠切れ対策）
