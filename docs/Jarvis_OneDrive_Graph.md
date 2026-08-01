# Jarvis × OneDrive（Microsoft Graph）

原本は `OneDrive-個人用`（215 等）。ダッシュボード投影は Supabase。  
GHA レーン要約（`jarvis-dashboard-lanes.yml`）がクラウドから読むときに使う。

## 重要: 個人用 vs 職場

| 種類 | この Mac の用途 | 認証 |
|---|---|---|
| **個人用 OneDrive**（フォルダ名 `OneDrive-個人用`） | 正本（215） | **委任＋デバイスコード＋ refresh_token**（推奨） |
| 職場 Microsoft 365 | 今回は非対象 | アプリ専用（client credentials）も可 |

個人 MSA に「アプリケーションの許可 `Files.Read.All`」だけを付けても、読取が通らないことが多いです。

## あなたがやること（約10分・初回のみ）

### A. Azure アプリ登録

1. [Azure Portal](https://portal.azure.com) → **Microsoft Entra ID** → **アプリの登録** → **新規登録**
2. 名前: `jarvis-onedrive-readonly`
3. サポートされるアカウント:
   - **個人の Microsoft アカウントのみ**、または **組織＋個人**
4. リダイレクト URI: 空でよい（デバイスコードを使う）
5. 登録後 → **認証** → 高度な設定 → **パブリック クライアント フローを許可 = はい**
6. **API のアクセス許可** → Microsoft Graph → **委任されたアクセス許可**:
   - `Files.Read`
   - `Files.Read.All`
   - `offline_access`
   - `User.Read`
7. **概要** の **アプリケーション (クライアント) ID** を控える  
   （クライアント シークレットは公開クライアントなら不要。機密にする場合のみ発行）

### B. ローカルに ID を書く

`.env.jarvis_private` に（チャットに貼らない）:

```bash
MS_GRAPH_CLIENT_ID=（控えた GUID）
MS_GRAPH_AUTHORITY=consumers
```

「保存した」と Jarvis に一声 → 続きのデバイスコードを実行します。  
自分で進める場合:

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
python scripts/jarvis_ms_graph_device_login.py
# 表示 URL を開き、OneDrive と同じ Microsoft アカウントで CODE 承認
# → ~/.jarvis_state/ms_graph_device_login.env を .env.jarvis_private へ追記
python scripts/jarvis_onedrive_graph.py --probe
python scripts/jarvis_ms_graph_secrets_to_gha.py
gh workflow run jarvis-dashboard-lanes.yml
```

### C. 動作確認の目安

```bash
python scripts/jarvis_ms_graph_setup_check.py
python scripts/jarvis_onedrive_graph.py --probe
python scripts/jarvis_onedrive_graph.py --path "215_神・大家さん倶楽部/C2_ルーティン作業/26_パートナー社への相談/000_共通/連絡先一覧.yaml"
```

`probe_ok: true` かつファイルの `bytes` が出れば成功。

## Jarvis / スクリプト側（実装済み）

| スクリプト | 役割 |
|---|---|
| `jarvis_ms_graph_setup_check.py` | 未設定時の手順表示 |
| `jarvis_ms_graph_device_login.py` | 初回デバイスコード |
| `jarvis_onedrive_graph.py` | refresh / app / ローカル読取 |
| `jarvis_ms_graph_secrets_to_gha.py` | GitHub Secrets 反映 |
| `jarvis_gha_lanes.py` | GHA でレーン要約 → `cards` |

## 制限

- Obsidian Journal（Google Drive）は Graph 対象外 → GHA では `journal_recent` をスキップ（Mac push で補完）
- refresh_token が回転したら `~/.jarvis_state/ms_graph_new_refresh.env` を private に反映
- 秘密は `.env.jarvis_private` と GitHub / Cloud Secrets のみ。チャット・Git 禁止

## 関連

- `config/onedrive_graph.example.yaml`
- `docs/運用コマンド一覧.md`（ダッシュボード節）
- `docs/Jarvis_Cloud_Agent.md`
