# Gmail token 自動更新のセットアップ手順

「エラーになってから対処」ではなく、**事前にトークンを更新し、GitHub Secret も自動で更新する**仕組みです。  
いけともAIニュースの GitHub Actions が毎週失敗しないよう、Mac 上で定期実行します。

---

## 仕組みの概要

1. **事前にエラーを防ぐ**: Google OAuth を「本番」にすると refresh token が長く持つ（数ヶ月〜）。
2. **自動でトークンを更新**: Mac の launchd が **3 日ごと** に `refresh_token_and_update_github_secret.py` を実行。
3. スクリプトが **Gmail token を更新** し、同じ内容を **GitHub の GMAIL_TOKEN_B64** に API で反映。  
   → 毎週日曜の AI News Save ワークフロー実行時には、常に新しい token が使われる想定です。

---

## 前提

- 215 の `credentials.json` / `token.json` がすでにあり、いけともAIニュースまたはパートナーやりとりで一度でもブラウザ認証済みであること。
- **GitHub の Personal Access Token（PAT）** を発行し、リポジトリの **Secrets: Read and write** 権限を持つこと。

---

## ステップ 1: Google OAuth を「本番」にする（推奨）

Refresh token の有効期限を延ばします。

1. [Google Cloud Console](https://console.cloud.google.com/) にアクセス
2. 画面上部のプロジェクト選択で **yaritori-gmail-487109**（いけとも・パートナー共通のプロジェクト）を選択
3. 左メニュー **API とサービス** → **OAuth 同意画面**
4. **公開ステータス** を **「本番」** に変更して **保存**。本人のみ利用なら「本番（未確認）」のままで可（Google の審査不要）
5. **一度だけ**、次のいずれかを実行して「本番」用の refresh token を用意する。
   - **5-1. そのまま実行して確認**  
     ターミナルで次を実行する。  
     ```bash
     cd "/Users/matsunomasaharu/Library/CloudStorage/GoogleDrive-m19m.hrts83@gmail.com/マイドライブ/DX互助会_共有フォルダ/03_outputs/ai_news_save"
     /Users/matsunomasaharu/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/C1_cursor/1b_Cursorマニュアル/.venv_gmail/bin/python gmail_ai_news_save.py --list
     ```
     - メール一覧や「該当メールはありませんでした」と出れば **成功**。この時点でステップ 1 は完了。
     - ブラウザが開いて「Google でログイン」と出た場合は、認証を完了すると新しい token が保存され、これも完了。
   - **5-2. 新しい refresh token を確実に取りたい場合（任意）**  
     「本番」にした直後に、長く持つ refresh token を新規発行したいときは、まず 215 の `token.json` をリネームして退避し、**そのあと** 上記のコマンドを**あなたのターミナルで**実行する。ブラウザが開くので **matsuno.estate@gmail.com** でログインして許可すると、新しい `token.json` が保存される。  
     ```bash
     mv "/Users/matsunomasaharu/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/C1_cursor/1b_Cursorマニュアル/token.json" "/Users/matsunomasaharu/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/C1_cursor/1b_Cursorマニュアル/token.json.bak"
     # 続けて上記の gmail_ai_news_save.py --list を実行
     ```

---

## ステップ 2: 215 の venv に PyNaCl を入れる

token を GitHub API で暗号化するために必要です。

```bash
/Users/matsunomasaharu/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/C1_cursor/1b_Cursorマニュアル/.venv_gmail/bin/pip install PyNaCl
```

---

## ステップ 3: GitHub の Personal Access Token（PAT）を用意する

1. GitHub → **Settings**（自分のアカウント）→ **Developer settings** → **Personal access tokens** → **Fine-grained tokens**（または **Tokens (classic)**）
2. **Generate new token**
   - **Fine-grained**: 対象リポジトリを選び、**Repository permissions** で **Secrets** を **Read and write** に設定
   - **Classic**: `repo` スコープにチェック（Secrets の更新に必要）
3. 発行したトークンをコピー（再表示できないので安全な場所に控える）

---

## ステップ 4: PAT をスクリプトから参照できるようにする

**どちらか一方** で構いません。

- **方法 A（ファイル）**: `03_outputs/ai_news_save/.github_token` を作成し、1 行目に PAT を書く。  
  （このファイルは .gitignore 済みなので Git にはコミットされませんが、**フォルダを他メンバーと共有している場合は、.github_token がそのフォルダ内に存在すると見られる可能性がある**ため、方法 B を推奨します。）
- **方法 B（環境変数）**: launchd の plist に `GITHUB_TOKEN` を追加する。  
  **フォルダを共有している場合はこちらを推奨**。plist は **あなたの Mac の** `~/Library/LaunchAgents/` にだけ置くため、他のメンバーには見えません。

### 方法 B の具体的な手順

1. ステップ 6 の「plist を LaunchAgents にコピー」を**先に**実行する。
2. 次のファイルを開いて編集する（テキストエディタで可）。  
   `~/Library/LaunchAgents/co.workstyle.ai-news-token-refresh.plist`
3. **EnvironmentVariables** の `<dict>` の中に、次の 2 行を **GMAIL_TOKEN_PATH の次** などに追加する。  
   （`あなたのPAT` のところに、ステップ 3 でコピーしたトークン文字列を貼り付ける）
   ```xml
   <key>GITHUB_TOKEN</key>
   <string>あなたのPAT</string>
   ```
4. ファイルを保存する。  
   この plist はあなたの Mac 内だけなので、共有フォルダに PAT を置かずに済みます。

リポジトリ名が `m19mhrts83-cyber/DX-_-` 以外の場合は、同じく plist の EnvironmentVariables に `<key>GITHUB_REPO</key><string>owner/repo</string>` を追加してください。

---

## ステップ 5: 手動で 1 回実行して確認

ターミナルで次を実行する。  
**必ず 215 の `.venv_gmail` の Python を使うこと。** `python3` だと `google` モジュールが入っておらず `ModuleNotFoundError` になります。

- **方法 A の人**: 下の「共通」と「Python 実行」の 2 行だけ実行（`.github_token` をスクリプトが読む）。
- **方法 B の人**: 「共通」のあとに **`export GITHUB_TOKEN='...'`** の 1 行を入れ、PAT を貼り付けてから「Python 実行」を実行。  
  （PAT はターミナルに表示されないよう、貼り付けたら Enter で確定してから次の行を実行する）

```bash
cd "/Users/matsunomasaharu/Library/CloudStorage/GoogleDrive-m19m.hrts83@gmail.com/マイドライブ/DX互助会_共有フォルダ/03_outputs/ai_news_save"
# 方法 B の場合のみ: 次の 1 行を追加し、' ' の中にステップ 3 でコピーした PAT を貼り付ける
# export GITHUB_TOKEN='ここにPATを貼る'
/Users/matsunomasaharu/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/C1_cursor/1b_Cursorマニュアル/.venv_gmail/bin/python refresh_token_and_update_github_secret.py
```

- 「Gmail token を更新しました。」「GitHub Secret GMAIL_TOKEN_B64 を更新しました。」と出れば成功です。
- `--refresh-only` を付けると Gmail の更新のみ（GitHub は触らない）。`--dry-run` は書き換えなしの確認だけ。

---

## ステップ 6: launchd で 3 日ごとに自動実行する

1. plist を LaunchAgents にコピー  
   ```bash
   cp "/Users/matsunomasaharu/Library/CloudStorage/GoogleDrive-m19m.hrts83@gmail.com/マイドライブ/DX互助会_共有フォルダ/03_outputs/ai_news_save/co.workstyle.ai-news-token-refresh.plist" ~/Library/LaunchAgents/
   ```
2. **PAT を plist に渡す場合**: plist を編集し、`<dict>` 内の `EnvironmentVariables` に  
   `<key>GITHUB_TOKEN</key><string>あなたのPAT</string>` を追加。
3. 有効化  
   ```bash
   launchctl load ~/Library/LaunchAgents/co.workstyle.ai-news-token-refresh.plist
   ```
4. 確認  
   ```bash
   launchctl list | grep ai-news-token-refresh
   ```

**ログ**: `~/Library/Logs/ai-news-token-refresh.log` と `~/Library/Logs/ai-news-token-refresh-error.log` で成功・失敗を確認できます。定期的にエラーログを見て、失敗していれば手元で再認証や PAT の確認をしてください。

---

## 無効化する場合

```bash
launchctl unload ~/Library/LaunchAgents/co.workstyle.ai-news-token-refresh.plist
```

---

## まとめ

- **事前対策**: OAuth を本番にし、refresh token を長生きさせる。
- **自動更新**: 3 日ごとに Gmail token を更新し、GitHub Secret も更新する。  
これで「やってみたらエラー」を避けつつ、トークンまわりを自動で維持できます。
