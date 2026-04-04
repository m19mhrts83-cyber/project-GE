# NotebookLM MCP の Cursor へのインストール手順

NotebookLM で集めたソースを、Cursor のチャットから「そのノートを前提に質問する」形で連携するための手順です。

---

## 前提

- **利用する MCP**: [notebooklm-mcp](https://www.npmjs.com/package/notebooklm-mcp)（npx で実行、初回のみブラウザで Google ログイン）
- **設定ファイル**: `~/.cursor/mcp.json`（グローバル）または プロジェクトの `.cursor/mcp.json`

---

## ステップ1: mcp.json に NotebookLM を追加

1. Cursor で **Settings → MCP** を開く  
   または **Cmd + Shift + J** でパレットを開き **MCP** タブへ。
2. **「Add new global MCP Server」** を選ぶと `~/.cursor/mcp.json` が開きます。
3. 既存の `mcpServers` に、次の **notebooklm** ブロックを**1つ**追加します（最後のサーバーの後ろにカンマを忘れずに）。

```json
"notebooklm": {
  "command": "npx",
  "args": ["-y", "notebooklm-mcp@latest"]
}
```

### 既存の npx をフルパスで指定している場合

ほかの MCP で `"/Users/matsunomasaharu/.nvm/versions/node/v22.22.0/bin/npx"` のようにフルパスを使っている場合は、合わせて次のようにしてもよいです。

```json
"notebooklm": {
  "command": "/Users/matsunomasaharu/.nvm/versions/node/v22.22.0/bin/npx",
  "args": ["-y", "notebooklm-mcp@latest"]
}
```

### 編集後のイメージ（抜粋）

```json
{
  "mcpServers": {
    "tavily": { ... },
    "notion": { ... },
    "gmail": { ... },
    "GitKraken": { ... },
    "notebooklm": {
      "command": "npx",
      "args": ["-y", "notebooklm-mcp@latest"]
    }
  }
}
```

4. ファイルを保存します。

---

## ステップ2: Cursor を再起動（または MCP の再読み込み）

- Cursor を一度終了して開き直す  
  または  
- **Cmd + Shift + J → MCP** で NotebookLM が一覧に表示されるか確認する（表示されていれば読み込み済み）

---

## ステップ3: 初回だけ「NotebookLM にログイン」

1. Cursor の**チャット**で、次のどちらかを送信します。
   - **「NotebookLM にログインして」**
   - **「Log me in to NotebookLM」**
2. **Chrome が起動**し、Google アカウントのログインが求められます。ログインを完了してください。
3. 認証が終わると、以降は同じマシンでは再ログイン不要です（セッションが保存されます）。

---

## ステップ4: NotebookLM でノートを用意し、リンクを登録

1. [notebooklm.google.com](https://notebooklm.google.com) でノートを作成し、ソース（PDF・Google Docs・Web・YouTube など）を追加します。
2. ノートの **⚙️ Share → Anyone with link → Copy** でリンクをコピーします。
3. Cursor のチャットで、例えば次のように伝えます。
   - **「この NotebookLM をライブラリに追加して：[貼り付けたリンク］」**
   - **「Add [リンク] to library」**
4. 登録後は、「〇〇について NotebookLM のノートで調べて」のように指示すると、そのノートのソースを前提に回答を取得できます。

---

## よく使う指示例（チャットでそのまま使える）

| やりたいこと           | チャットで入力する例 |
|------------------------|----------------------|
| 初回ログイン           | 「NotebookLM にログインして」 |
| ノートを登録           | 「このノートをライブラリに追加して：[リンク］」 |
| 登録済みノート一覧     | 「NotebookLM のノート一覧を表示して」 |
| このノートで調べてから書く | 「この件は NotebookLM で調べてからコードを書いて」 |
| ブラウザで動作確認     | 「NotebookLM のブラウザを表示して」 |
| 認証エラー時           | 「NotebookLM の認証を修復して」 |

---

## トラブルシューティング

- **MCP 一覧に notebooklm が出ない**  
  - `mcp.json` の JSON のカンマ・括弧の付け忘れがないか確認する。  
  - Cursor を完全終了して再起動する。

- **「Log me in」しても Chrome が開かない**  
  - Cursor の **設定 → Tools & MCP** では、ツールの**オン/オフ**の切り替えだけができ、そこで「実行」はできません。認証を始めるには、**チャットで「setup_auth を実行してください」**のように、**ツール名を明示して**依頼してください。AI が setup_auth ツールを呼び出すと Chrome が開きます。  
  - NotebookLM MCP は **Chrome を開く仕様**のため、デフォルトブラウザが Chrome でなくても、**Chrome がインストールされていれば** MCP が Chrome を起動する場合があります。開かない場合は以下も試す。  
  - **デフォルトブラウザが Chrome ではない場合**：  
    - **方法A**：一時的にデフォルトブラウザを Chrome に変更し、「NotebookLM にログインして」を実行。ログイン完了後、デフォルトを元のブラウザに戻してよい（認証は 1 回だけ）。  
    - **方法B**：Chrome をインストールしたうえで、Cursor で「NotebookLM にログインして」を送る。MCP が Chrome を直接起動する場合がある。  
  - ターミナルで `npx -y notebooklm-mcp@latest` を実行し、エラーが出ないか確認する。

- **デフォルトを Chrome にしてもログイン用の Chrome が開かない**  
  - **Chrome をいったんすべて終了**してから試す（MCP が「特別なフラグ」で Chrome を起動するため、既に Chrome が動いていると失敗することがある）。  
  - チャットで**別の言い方**を試す：「Open NotebookLM auth setup」「NotebookLM の認証を修復して」  
  - ターミナルで `npx -y notebooklm-mcp@latest` を実行し、起動メッセージやエラーが出ないか確認する。  
  - Chrome が **/Applications/Google Chrome.app**（Mac の標準の場所）にインストールされているか確認する。

- **NotebookLM をブラウザで使っても、Cursor 経由でログイン用 Chrome が開かない**  
  - **ターミナルで MCP を直接起動**し、起動時エラーが出ないか確認する。  
    ```bash
    npx -y notebooklm-mcp@latest
    ```
    起動後は MCP プロトコルで待機するためそのままでは Chrome は開かないが、**Chrome や patchright の不足でエラーになっていないか**が分かる。  
  - **Cursor の MCP 一覧**（Cmd + Shift + J → MCP）で、**notebooklm が「接続済み」や緑表示になっているか**確認する。接続エラーがあるとチャットからツールが呼ばれない。  
  - Cursor の**再起動**や**アップデート**の有無を確認する。  
  - 上記で解決しない場合は、[notebooklm-mcp の GitHub Issues](https://github.com/PleasePrompto/notebooklm-mcp/issues) で「Cursor」「Chrome が開かない」などで検索し、同様の報告や回避策がないか確認する。

- **ノートの回答が返ってこない**  
  - NotebookLM 側でノートの共有が「リンクを知っている人」になっているか確認する。  
  - チャットで「〇〇について NotebookLM で調べて」と、ノートの対象範囲に沿った質問になっているか確認する。

---

## つないだあとにできること

- **NotebookLMとCursorでできること一覧.md**（同フォルダ）に、認証・ライブラリ管理・質問・セッション・トラブル対応などを初心者向けにまとめてあります。チャットでどう言えばよいかの例も載っています。

## 参考リンク

- [notebooklm-mcp（npm）](https://www.npmjs.com/package/notebooklm-mcp)
- [NotebookLM](https://notebooklm.google.com)
- [Cursor MCP 公式ドキュメント](https://cursor.com/docs/context/mcp)
