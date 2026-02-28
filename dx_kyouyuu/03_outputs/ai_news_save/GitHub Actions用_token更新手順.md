# GitHub Actions 用 Gmail token 更新手順

`invalid_grant` / `Token has been expired or revoked` で AI News Save が失敗したときに、順を追って行う手順です。

---

## おすすめの流れ（エラーを起こさないために）

**「やってみたらエラー」を避けたい**場合は、次の 2 段構えがおすすめです。

### 1. 事前にエラーの芽を潰す

- **Google OAuth を「本番」にする**  
  同意画面が「テスト」のままだと refresh token が約 7 日で失効します。「本番」にすると長期間（未使用で約 6 ヶ月、使用していれば実質ずっと）有効になります。  
  → [Google Cloud Console](https://console.cloud.google.com/) → 該当プロジェクト → **API とサービス** → **OAuth 同意画面** → **公開ステータス** を **「本番」** に。本人のみ利用なら「本番（未確認）」で可。
- 変更後、**一度だけ** 手元で `gmail_ai_news_save.py --list` や `refresh_and_prepare_token.sh` を実行し、必要ならブラウザで再認証して新しい refresh token を発行する。

### 2. 自動でトークンを更新する

Mac 上で **3 日ごと** に Gmail token を更新し、**GitHub の GMAIL_TOKEN_B64 も API で自動更新**する仕組みを入れておくと、毎週の AI News Save 実行時に「token 期限切れ」で落ちることを防げます。

- **セットアップ**: `token自動更新_セットアップ手順.md` に従い、GitHub の Personal Access Token（Secrets: Read and write）を用意 → `.github_token` に保存 → `refresh_token_and_update_github_secret.py` を手動で 1 回実行して確認 → launchd に `co.workstyle.ai-news-token-refresh.plist` を入れて 3 日ごとに実行。
- ログは `~/Library/Logs/ai-news-token-refresh.log` と `ai-news-token-refresh-error.log` で確認できます。

### 3. それでもエラーになったとき（手動で更新）

自動更新を入れていない場合や、PAT 切れ・長期スリープで更新が走らなかった場合のフォールバックです。

- **ワンコマンドで準備**: 次を実行すると、token の確認・更新と Base64 の準備までまとめて行えます。あとは GitHub で貼り付けるだけです。

```bash
cd "/Users/matsunomasaharu/Library/CloudStorage/GoogleDrive-m19m.hrts83@gmail.com/マイドライブ/DX互助会_共有フォルダ/03_outputs/ai_news_save"
./refresh_and_prepare_token.sh
```

- やること: token の確認（必要なら更新）→ Base64 をクリップボードにコピー → 同じ内容を `token_for_github_secret_b64.txt` に保存。
- あなたがやること: GitHub の **Settings → Secrets and variables → Actions** で **GMAIL_TOKEN_B64** を開き、**Value に貼り付け (Cmd+V)** → **Update secret**。

---

## Watson が実行済みの場合（今回のように事前に実行した場合）

- **ステップ 1** は Watson が実行済みです（手元の token を更新し、`token.json を保存しました` と出ていれば完了）。
- **ステップ 2** の「方法 B」が済んでいます。同じフォルダ内の **`token_for_github_secret_b64.txt`** に Base64 が入っています。
- **あなたがやること**: 下記 **ステップ 2-2** のみ。`token_for_github_secret_b64.txt` を開き、中身をすべてコピー → GitHub の **GMAIL_TOKEN_B64** に貼り付けて更新 → **ステップ 3** で Run workflow を実行して確認。

---

## 手順一覧

| # | 作業内容 | 誰がやる |
|---|----------|----------|
| 1 | 手元で新しい token を取得する（ブラウザ認証が必要な場合はここで実施） | **あなた**（Watson はブラウザを開けないため） |
| 2 | token.json を Base64 にして、GitHub の Secret **GMAIL_TOKEN_B64** を更新する | **あなた**（または Watson が Base64 をファイルに書き出し、あなたがコピーして登録） |
| 3 | GitHub Actions で「Run workflow」を実行し、成功するか確認する | **あなた** |

---

## ステップ 1: 手元で新しい token を取得する

### 1-1. ターミナルを開く

Mac の「ターミナル」アプリを開きます。

### 1-2. 次のコマンドを実行する

```bash
cd "/Users/matsunomasaharu/Library/CloudStorage/GoogleDrive-m19m.hrts83@gmail.com/マイドライブ/DX互助会_共有フォルダ/03_outputs/ai_news_save"

/Users/matsunomasaharu/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/C1_cursor/1b_Cursorマニュアル/.venv_gmail/bin/python gmail_ai_news_save.py --list
```

### 1-3. 結果に応じて次へ

- **メール一覧が表示された場合**  
  → 手元の token は有効です。**ステップ 2** へ進み、いまの token.json を Base64 にして GitHub に登録すればよいです。

- **ブラウザが開き「Google でログイン」と表示された場合**  
  → 認証を完了してください。完了すると新しい `token.json` が  
  `215_神・大家さん倶楽部/C1_cursor/1b_Cursorマニュアル/token.json` に保存されます。  
  → その後、**ステップ 2** へ進みます。

- **エラー（invalid_grant など）と表示された場合**  
  → ブラウザが開かない環境で実行している可能性があります。  
  **あなたが手元のターミナルで** 上記コマンドを実行し、ブラウザでログインまで完了してから、再度ステップ 2 へ進んでください。

---

## ステップ 2: GitHub の Secret「GMAIL_TOKEN_B64」を更新する

### 2-1. token を Base64 にする（改行なし）

**方法 A: クリップボードにコピーする（推奨）**

ターミナルで実行：

```bash
base64 -i "/Users/matsunomasaharu/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/C1_cursor/1b_Cursorマニュアル/token.json" | tr -d '\n' | pbcopy
```

→ クリップボードに Base64 が入ります。

**方法 B: ファイルに書き出す**

Watson が `03_outputs/ai_news_save/token_for_github_secret_b64.txt` を作成している場合は、そのファイルを開き、**中身をすべて選択してコピー**してください（改行が含まれていれば削除してから使うか、改行なしで登録する）。

### 2-2. GitHub で Secret を更新する

1. リポジトリ **m19mhrts83-cyber/DX-_-**（または該当する DX互助会 用リポジトリ）を開く。
2. **Settings** → **Secrets and variables** → **Actions** を開く。
3. **GMAIL_TOKEN_B64** の行で **Update**（更新）をクリック。
4. **Value** に、ステップ 2-1 でコピーした Base64 文字列を**貼り付け**（既存の値はすべて削除してから貼り付け）。
5. **Update secret** で保存。

---

## ステップ 3: 動作確認

1. GitHub の **Actions** タブを開く。
2. 左の **AI News Save** を選ぶ。
3. 右の **Run workflow** → **Run workflow** を実行。
4. 数秒〜数十秒後、実行結果が **緑の ✓** になれば成功です。  
   **Run AI News Save** が緑になっていれば、token 更新は完了しています。

---

## 注意

- **token.json** は機密情報です。Base64 にしたファイル（`token_for_github_secret_b64.txt` など）は、Secret の登録が終わったら削除するか、少なくとも Git にコミットしないでください（`.gitignore` に含めることを推奨）。
- Gmail の token は一定期間で失効するため、**数ヶ月に一度**は同じ手順で token を更新し、**GMAIL_TOKEN_B64** を更新する必要があります。

## 同じ Gmail 認証を使う他の機能（パートナーとのやりとり）

215 の `C1_cursor/1b_Cursorマニュアル` にある **credentials.json / token.json** は、**パートナーとのやりとり**（gmail_to_yoritoori → 5.やり取り.md への追記）でも同じものを使用しています。  
いけとも用に token を更新すると 215 の token.json も更新されるため、パートナー用は追加の作業は不要です。逆に、パートナー用に token を更新した場合は、その token.json を Base64 にして本手順のステップ 2 に従い **GMAIL_TOKEN_B64** も更新することをおすすめします。  
→ 215: `C1_cursor/1b_Cursorマニュアル/Gmail token 更新時の連携（いけとも・パートナー）.md`
