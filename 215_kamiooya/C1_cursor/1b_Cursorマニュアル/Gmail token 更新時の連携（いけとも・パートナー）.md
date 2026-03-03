# Gmail token 更新時の連携（いけともAIニュース・パートナーとのやりとり）

**credentials.json** と **token.json** は、このフォルダ（`215_神・大家さん倶楽部/C1_cursor/1b_Cursorマニュアル/`）に **1 組だけ** 置き、次の 2 系統で **共通利用** しています。

---

## API とトークンは別物（「やってみたら期限切れ」を防ぐために）

| 種類 | 役割 | 期限 | 対策 |
|------|------|------|------|
| **Gmail API** | Google Cloud で有効化する機能。credentials.json の OAuth クライアント ID/シークレット | **期限なし** | 特になし |
| **token.json** | ユーザー認可の結果（access token + refresh token）。Gmail にアクセスするための「鍵」 | **期限あり** | 下記の事前対策を実施 |

**今回の「Token has been expired or revoked」は token.json の refresh token が失効したためです。** API の有効期限ではありません。

### 事前対策チェックリスト（「やってみたら期限切れでした」を防ぐ）

1. **OAuth 同意画面を「本番」にする**（最優先）  
   「テスト」のままだと refresh token が約 7 日で失効します。  
   → [Google Cloud Console](https://console.cloud.google.com/) → 該当プロジェクト（yaritori-gmail-487109）→ **API とサービス** → **OAuth 同意画面** → 公開ステータスを **「本番」** に。本人のみ利用なら「本番（未確認）」で可。

2. **3 日ごとの自動更新を入れる**  
   いけとも・パートナーは同じ token.json を共有しているため、**いけとも用の自動更新が動けばパートナー用も自動で更新**されます。  
   → DX互助会 `03_outputs/ai_news_save/token自動更新_セットアップ手順.md` に従い、launchd で `refresh_token_and_update_github_secret.py` を 3 日ごとに実行。

3. **定期的にログを確認する**  
   自動更新の成否は `~/Library/Logs/ai-news-token-refresh-error.log` で確認。失敗していれば手元で再認証が必要。

---

| 用途 | 使うスクリプト・仕組み | token の置き場所 |
|------|------------------------|------------------|
| **パートナーとのやりとり** | `gmail_to_yoritoori.py`（215 内） | このフォルダの `token.json` をそのまま使用 |
| **いけともAIニュース（戸井さんニュース）** | `gmail_ai_news_save.py`（DX互助会）＋ GitHub Actions | ローカル実行時はこのフォルダの `token.json`。GitHub Actions では **GMAIL_TOKEN_B64**（token.json の Base64）を Secret に登録して使用 |

そのため、**どちらか一方で Gmail token の更新（期限切れ対応）をしたときは、もう一方もあわせて確認・更新する**と、両方で同じエラーを防げます。

---

## いけともAIニュース（戸井さんニュース）で token を更新したとき

- 手元で `gmail_ai_news_save.py` を実行して token を更新すると、**このフォルダの token.json が上書き**されます。
- **パートナーとのやりとり**は同じ token.json を参照するので、**追加の作業は不要**です。
- **GitHub Actions** 用には、更新した token.json を Base64 にして **GMAIL_TOKEN_B64** を更新してください。  
  → 手順: DX互助会フォルダの `03_outputs/ai_news_save/GitHub Actions用_token更新手順.md` のステップ 2

---

## パートナーとのやりとりで token を更新したとき

- `gmail_to_yoritoori.py` を実行してブラウザ認証すると、**このフォルダの token.json が更新**されます。
- **いけともAIニュース**の **GitHub Actions** は、この token.json を参照していないため、**GMAIL_TOKEN_B64** を更新しないと古い token のままになります。
- **推奨**: パートナー用に token を更新したら、同じ token.json を Base64 にして、GitHub の **GMAIL_TOKEN_B64** も更新する。  
  → 手順: DX互助会フォルダの `03_outputs/ai_news_save/GitHub Actions用_token更新手順.md` のステップ 2（token はすでにこのフォルダに保存済みなので、Base64 化と Secret 更新のみ）

---

## トラブルシューティング時に Watson が提案する内容

Gmail の token 期限切れや **GMAIL_TOKEN_B64** の更新を扱うとき、Watson は次のように案内します。

- **いけともAIニュース（戸井さんニュース）** の token 更新を案内するとき  
  → 「同じ Gmail 認証を使っているパートナーとのやりとりは、215 の token.json を共有しているため、手元で token を更新すればパートナー用はそのままで問題ありません。あわせて GitHub の GMAIL_TOKEN_B64 を更新すればいけとも用の定期実行も動きます。」
- **パートナーとのやりとり** の token 更新を案内するとき  
  → 「同じ Gmail 認証を使っているいけともAIニュース（戸井さんニュース）の GitHub Actions 用には、215 の token.json を Base64 にしたものを GitHub の Secret **GMAIL_TOKEN_B64** に登録する必要があります。パートナー用に token を更新したら、DX互助会の `03_outputs/ai_news_save/GitHub Actions用_token更新手順.md` のステップ 2 に従って GMAIL_TOKEN_B64 も更新することをおすすめします。」

この方針は `.cursor/rules/gmail-token-troubleshooting.mdc` に記載し、トラブルシューティング時に参照されます。

---

## Cursor Gmail MCP とポート競合（EADDRINUSE）

**現在は Gmail MCP は使用していません**（いけとも・パートナー・空室対策で Gmail は足りているため、ツール数削減のため無効化済み）。以下は参考用です。

**Cursor の Gmail MCP**（チャットから Gmail を触る機能）は、**このフォルダの token.json とは別系統**です。MCP は `~/.cursor/mcp.json` の **GMAIL_CLIENT_ID / GMAIL_CLIENT_SECRET / GMAIL_REFRESH_TOKEN** を参照しており、215 の token 自動更新の対象には含まれません。

- **EADDRINUSE（ポート 3000 使用中）**  
  Gmail MCP が起動時にポート 3000 を使おうとして、既に別プロセスが使用していると発生します。  
  **恒久対策**: `~/.cursor/mcp.json` の Gmail の `env` に **`"PORT": "3010"`** と **`"AUTH_SERVER_PORT": "3010"`** を追加して、3000 を避けています。再発した場合は Cursor を再起動するか、`lsof -i :3000` で 3000 を使っているプロセスを確認してください。
- **トークンとの関係**  
  - このエラーが起きても、**パートナー・いけとも・空室対策・GMAIL_TOKEN_B64 のトークン更新には影響しません**（別の認証系統のため）。  
  - 逆に、215 の token.json を更新しても **Gmail MCP の mcp.json の GMAIL_REFRESH_TOKEN は自動では更新されません**。MCP で Gmail に触りたい場合は、MCP 用に別途トークンを取得するか、手動で mcp.json の REFRESH_TOKEN を差し替える必要があります。

---

## token の失効を減らす・更新作業を楽にする

上記「事前対策チェックリスト」を参照。要点は次のとおりです。

- **失効頻度を下げる**: OAuth 同意画面を「本番」にする。
- **自動で更新する**: いけとも用の 3 日ごと自動更新が、パートナー用の token.json も同時に更新する。
- **手動で更新する場合**: DX互助会の `03_outputs/ai_news_save/refresh_and_prepare_token.sh` を実行すると、token の確認・更新と Base64 準備までまとめて行えます。  
  → 詳しくは `GitHub Actions用_token更新手順.md` の「効率化のヒント」を参照。
