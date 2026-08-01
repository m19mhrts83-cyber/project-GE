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
| 対話 | Cloud Agent（下記 MCP＋Secrets） |
| 送信 | Mac の yoritoori（対外送信前確認）。Web から送らない |

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

### 2. NotebookLM

| 項目 | 値 |
|---|---|
| 種別 | stdio（現行パッケージ） |
| command | `npx` |
| args | `-y` `notebooklm-mcp@latest` |

初回は Cloud run 内で Google ログイン／cookie（`setup_auth`）。ローカル現状は `authenticated=false` のことがあり、同じく `setup_auth` が必要。  
ソース正本は Drive `200_NoteBookLM`（`jarvis-notebooklm-drive-sources`）。  
疎通: 「登録ノートを list して1問聞いて」

### 3. やらない MCP

- ローカル専用パス前提の stdio を無検証で増やさない
- Service Role / パスワードを MCP env に平文で増やしすぎない（Environment Secrets を優先）

## Cloud Environment Secrets（例）

Environment: リポジトリ `m19mhrts83-cyber/project-GE`（Dashboard に Active な environment あり）。  
値は Dashboard にのみ。Git・チャットに出さない。テンプレ名: [`config/cloud_agent_secrets.example.env`](../config/cloud_agent_secrets.example.env)

| Secret | 用途 |
|---|---|
| `JARVIS_SUPABASE_URL` | 投影 DB |
| `JARVIS_SUPABASE_SERVICE_ROLE_KEY` | 読取／必要時 upsert（最小権限運用を意識） |
| `GEMINI_API_KEY` | リサーチ（`scripts/jarvis_gemini_research.py`） |
| `GMAIL_CREDENTIALS_B64` / `GMAIL_ADMIN_TOKEN_B64` | admin Gmail（既存 GHA と同系。必要時のみ） |

### 登録手順（手動・約1分）

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
python scripts/jarvis_cloud_secrets_prepare.py
# 生成: ~/.jarvis_state/cloud_agent_secrets.env
open https://cursor.com/dashboard/cloud-agents
# → My Secrets → Add Secrets → ファイル内容を貼る → Save（Runtime Secret 推奨）
rm -f ~/.jarvis_state/cloud_agent_secrets.env
```

自動化ブラウザからの貼り付けはフォーカス／クリップボード制約で失敗しやすい。**手元貼り付けを正とする。**

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

## Mac に残すもの

CHRLINE／オプチャ、Zaim Playwright、パートナー MD 全文取込、対外送信、OneDrive ローカル path 依存ジョブ（Graph 未設定時）。

## チェックリスト（初回配線）

1. [ ] Cloud environment を project-GE に接続
2. [ ] Secrets を上表どおり登録（値は private／Dashboard のみ）
3. [ ] Notion MCP（HTTP）追加 → OAuth 完了 → 1 検索成功
4. [ ] NotebookLM MCP（stdio）追加 → list／1 問成功
5. [ ] Supabase `sync_meta` を Cloud から読めることを確認
6. [ ] on-demand 利用の要否を Dashboard Usage で確認（枠切れ対策）
