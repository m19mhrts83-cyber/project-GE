# Gmail API 活用の取り組み紹介

215 神・大家さん倶楽部および関連運用で、Gmail API をどのように活用しているかをまとめます。

---

## 全体像

| 用途 | 方式 | 認証・設定の場所 | 参照ドキュメント |
|------|------|------------------|-------------------|
| パートナーとのやり取り取得 | Python スクリプト | `1b_Cursorマニュアル/` の credentials.json・token.json | [Gmailやり取り連携_セットアップ手順.md](./Gmailやり取り連携_セットアップ手順.md) |
| パートナー宛メール送信 | Python スクリプト | 同上 | [yoritoori_send.py](./yoritoori_send.py) 冒頭 |
| いけともAIニュース（戸井さんニュース） | GitHub Actions | 同上 token を Base64 化して GMAIL_TOKEN_B64 | [Gmail token 更新時の連携（いけとも・パートナー）.md](./Gmail%20token%20更新時の連携（いけとも・パートナー）.md) |
| **Cursor チャットでメール参照・検索** | **Gmail MCP** | **~/.gmail-mcp/**（別認証） | 本ドキュメント「MCP でメール参照」 |

※ やり取り連携・送信・いけともは **同じ Google プロジェクトの credentials.json / token.json** を共有。MCP は **同じプロジェクトの OAuth キー** を `~/.gmail-mcp/` にコピーして別途認証し、MCP 用の token を `~/.gmail-mcp/credentials.json` に保存しています。

---

## 1. パートナーとのやり取り取得（Gmail → やり取り.md）

- **スクリプト**: `gmail_to_yoritoori.py`
- **動き**: Gmail の未読（必要なら既読も）を取得し、連絡先一覧と照合して該当パートナーフォルダの `5.やり取り.md` に追記。添付は「添付」サブフォルダに保存。
- **認証**: `credentials.json` + `token.json`（このフォルダ）

---

## 2. パートナー宛メール送信

- **スクリプト**: `yoritoori_send.py`
- **動き**: 各パートナーフォルダの `4.送信下書き.txt`（1行目＝件名、2行目以降＝本文）と連絡先一覧を使って Gmail で送信。
- **認証**: 上記と同じ credentials / token

---

## 3. いけともAIニュース（戸井さんニュース）

- **運用**: GitHub Actions で定期実行。Gmail から対象メールを取得して保存。
- **認証**: 上記 `token.json` を Base64 にしたものを GitHub Secret **GMAIL_TOKEN_B64** に登録。  
  token 更新時は [Gmail token 更新時の連携（いけとも・パートナー）.md](./Gmail%20token%20更新時の連携（いけとも・パートナー）.md) の手順で **GMAIL_TOKEN_B64** も更新する。

---

## 4. MCP でメール参照（Cursor チャットから検索・表示）

Cursor のチャットで「〇〇からのメールを探して」「件名に△△が入ったメールを出して」のように依頼すると、AI が Gmail を検索し、結果をチャットに表示できます。

### 4.1 使っている MCP

- **サーバー**: `@gongrzhe/server-gmail-autoauth-mcp`（Gmail AutoAuth MCP Server）
- **推奨ツール（日常的に使うもの）**  
  | ツール | 用途 |
  |--------|------|
  | `search_emails` | 条件に合うメールを検索して一覧を出す |
  | `read_email` | 特定の1通の本文を取得する（検索結果の内容表示や返信元の確認） |
  | `draft_email` | 下書きを作成する（内容確認用） |
  | `send_email` | メールを送信する（新規送信・返信とも。返信時は threadId / inReplyTo を指定） |
- **その他のツール**  
  ラベル操作（`list_email_labels`, `create_label` など）、フィルタ、一括操作（`batch_modify_emails` 等）、`download_attachment` などは、依頼があったときだけ利用する。

### 4.2 設定の流れ（実施済みの例）

1. **OAuth キーの準備**  
   - やり取り連携用の Google プロジェクトの **credentials.json**（デスクトップアプリ）を、MCP 用に `gcp-oauth.keys.json` としてコピー。
   - 保存先: `~/.gmail-mcp/gcp-oauth.keys.json`

2. **初回認証**  
   ```bash
   npx @gongrzhe/server-gmail-autoauth-mcp auth
   ```  
   - ブラウザが開くので、Google アカウントでログインし、権限を許可。
   - 成功すると `~/.gmail-mcp/credentials.json` に MCP 用の認証情報が保存される。

3. **Cursor の MCP 設定**  
   - `~/.cursor/mcp.json` の `mcpServers` に `gmail` を追加（command: `npx`, args: `["-y", "@gongrzhe/server-gmail-autoauth-mcp"]`）。
   - Cursor を再起動すると、Gmail MCP が利用可能になる。

### 4.3 チャットでの使い方

- 例: 「先週 LEAF から来たメールを探して」「件名に『見積もり』が入ったメールを5件出して」
- Gmail の検索演算子（`from:`, `subject:`, `after:`, `has:attachment` など）を MCP の `search_emails` が利用するため、自然な日本語で条件を言うと検索して結果を表示してくれます。

### 4.4 トラブル時

- MCP がエラーになる場合: Cursor の MCP 設定で「Error - Show Output」で内容を確認。
- 認証切れ: 再度 `npx @gongrzhe/server-gmail-autoauth-mcp auth` を実行してから Cursor を再起動。
- 別実装（@shinzolabs/gmail-mcp）を使う場合の手順: [Gmail_MCP_エラー解消手順.md](./Gmail_MCP_エラー解消手順.md) を参照。

---

## 認証まわりの整理

| 用途 | 認証情報の場所 |
|------|----------------|
| やり取り連携・パートナー送信・いけとも | `1b_Cursorマニュアル/credentials.json` + `token.json` |
| Cursor Gmail MCP | `~/.gmail-mcp/gcp-oauth.keys.json` + `~/.gmail-mcp/credentials.json` |

同じ Google プロジェクトの OAuth クライアント（credentials）を使い、**スクリプト用**と**MCP 用**で token の保存先だけ分けています。  
token を更新する場合、やり取り連携用はこのフォルダの `token.json` を更新し、いけとも用は **GMAIL_TOKEN_B64** を更新。MCP 用は `npx @gongrzhe/server-gmail-autoauth-mcp auth` で再認証すれば更新されます。
