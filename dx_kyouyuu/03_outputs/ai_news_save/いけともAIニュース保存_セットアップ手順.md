# いけともAIニュース定期保存 セットアップ手順

## 概要

`gmail_ai_news_save.py` は、Gmail から「注目AIニュース」（ikeda@workstyle-evolution.co.jp）を取得し、指定フォルダ直下に Markdown と画像を保存します。

## 前提

- Gmail API 設定済み（`credentials.json`, `token.json` は 215 フォルダの `C1_cursor/1b_Cursorマニュアル` に配置）
- `gmail_to_yoritoori.py`（パートナーとのやりとり）と同じ credentials を利用。**token を更新したときは、いけとも・パートナー両方の運用を確認**するとよい（215: `Gmail token 更新時の連携（いけとも・パートナー）.md` 参照）

## 手動実行

```bash
cd "03_outputs/ai_news_save"
# 215 フォルダの venv を使用（credentials と同一）
/Users/matsunomasaharu/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/C1_cursor/1b_Cursorマニュアル/.venv_gmail/bin/python gmail_ai_news_save.py
```

- `--output /path` で保存先を指定可能
- `--dry-run` で保存せずに確認のみ

## 定期実行（launchd）

毎週日曜 12:00 に自動実行するには、plist を LaunchAgents に配置します。

### 1. plist をコピー

```bash
cp "03_outputs/ai_news_save/co.workstyle.ai-news-save.plist" ~/Library/LaunchAgents/
```

### 2. 有効化

```bash
launchctl load ~/Library/LaunchAgents/co.workstyle.ai-news-save.plist
```

### 3. 確認

```bash
launchctl list | grep ai-news-save
```

### 無効化する場合

```bash
launchctl unload ~/Library/LaunchAgents/co.workstyle.ai-news-save.plist
```

## ログ

- 標準出力: `~/Library/Logs/ai-news-save.log`
- 標準エラー: `~/Library/Logs/ai-news-save-error.log`

## 保存先

デフォルト: `05_knowledge/いけともAIニュース/`（DX互助会_共有フォルダ内）

環境変数 `AI_NEWS_SAVE_PATH` または `--output` で変更可能。

## 画像テキスト索引（OCR）

集フォルダ内の画像を OCR し、**1フォルダ1ファイル**の索引（`画像テキスト索引.md`）にまとめると、キーワード検索で「どの図解にその語が含まれるか」を探せます。

### 前提

- **Tesseract** をインストール（日本語対応）
  ```bash
  brew install tesseract tesseract-lang
  ```
- Python 用パッケージ（保存用 venv に追加済み）
  ```bash
  pip install Pillow pytesseract
  ```

### 実行（推奨: 同梱の run_image_index.sh）

```bash
cd "03_outputs/ai_news_save"
./run_image_index.sh 20260201
```

- **初回だけ** venv（`.venv_index`）を作成し、Pillow と pytesseract を自動インストールします。
- 引数なし: `./run_image_index.sh` → いけともAIニュース直下の**すべての集フォルダ**を処理
- `./run_image_index.sh 20260201`: 指定した集フォルダのみ処理
- `./run_image_index.sh --dry-run`: 索引を書き出さずに処理内容だけ表示

（Python を直接使う場合: `python3 build_image_index.py 20260201`。その前に `pip install Pillow pytesseract` が必要です。）

### 検索のしかた

- Cursor やエディタで `05_knowledge/いけともAIニュース/20260201/画像テキスト索引.md` を開き、キーワード（例: Cursor、チャットベース）で検索
- ヒットした `## 〇〇/図解N.jpg` のパスが、その語が含まれる画像です

### 定期実行時に一緒に動く

**保存スクリプト（`gmail_ai_news_save.py`）に組み込み済み**です。  
メールを保存した直後に、その集フォルダ向けに `build_image_index.py` を自動実行します。

- **launchd（Mac の定期実行）**: 同じ Python 環境に Tesseract と Pillow / pytesseract を入れておけば、保存のたびに索引も更新されます。
- **GitHub Actions**: 実行環境に Tesseract が入っていないため、索引は作られません。索引が必要な集は手元で `build_image_index.py` を実行するか、Mac の launchd で保存している場合はそちらで自動生成されます。

---

## 定期実行（GitHub Actions）※Mac に依存しない

毎週日曜 12:00（日本時間）に GitHub のサーバーで自動実行。Mac の電源オフ・スリープでも動作。

### 1. Secrets の登録

リポジトリの **Settings → Secrets and variables → Actions** で以下を追加：

| Secret 名 | 値 |
|-----------|-----|
| `GMAIL_CREDENTIALS_B64` | credentials.json の Base64 文字列 |
| `GMAIL_TOKEN_B64` | token.json の Base64 文字列 |

**Base64 の作り方**（ターミナル）:

```bash
base64 -i credentials.json | pbcopy   # クリップボードにコピー、Secrets に貼り付け
base64 -i token.json | pbcopy
```

※ credentials.json と token.json は 215 フォルダの `C1_cursor/1b_Cursorマニュアル` にある

### 2. ワークフローの配置

`.github/workflows/ai-news-save.yml` がリポジトリに含まれていれば OK。  
このフォルダを push するだけで有効になる。

### 3. 実行結果の取得

- 実行後、`05_knowledge/いけともAIニュース/` に保存されたファイルがリポジトリにコミット・push される
- ローカルで `git pull` すると取得できる
- Google Drive と同期している場合は、pull 後に Drive にも反映される

### 4. 手動実行

GitHub の **Actions** タブ → **AI News Save** → **Run workflow** で任意のタイミングで実行可能。

### 5. スケジュール（定期実行）はどこで設定されているか

スケジュールは **ワークフローファイル内** に書かれています。

- **ファイル**: `.github/workflows/ai-news-save.yml`
- **該当箇所**（8〜11行目付近）:
  ```yaml
  on:
    schedule:
      # 日曜 03:00 UTC = 12:00 JST
      - cron: "0 3 * * 0"
    workflow_dispatch:  # 手動実行用
  ```
- **意味**: 毎週日曜 03:00 UTC = **日本時間 12:00** に自動実行
- GitHub の Actions 画面では「Run workflow」が目立ちますが、上記の `schedule` により日曜 12:00 にも自動で実行されます。

---

## GitHub Actions が「All jobs have failed」で失敗するとき

通知メールで「AI News Save: All jobs have failed」と表示された場合、次の順で確認してください。

1. **GitHub でログを開く**  
   メールの **View workflow run** をクリックするか、リポジトリの **Actions** タブ → 失敗した実行（赤い ×）→ **AI News Save / save** ジョブを開く。
2. **どのステップで落ちたか確認**  
   - **Create credentials** で失敗 → Secrets 未設定または Base64 が不正（下記「よくある原因と対処」参照）。
   - **Run AI News Save** で失敗 → スクリプト内エラー。ログ末尾のメッセージを確認。
3. **特に多い原因**
   - **Secrets が空・未設定**  
     `GMAIL_CREDENTIALS_B64` と `GMAIL_TOKEN_B64` がリポジトリの **Settings → Secrets and variables → Actions** に正しく登録されているか確認。値は credentials.json / token.json の **Base64 文字列**（改行なしで1行）。
   - **token の有効期限切れ**  
     Gmail の token は時間で失効します。手元で一度 `gmail_ai_news_save.py` を実行して新しい token.json を取得し、その内容を Base64 にして **GMAIL_TOKEN_B64** を更新する必要があります。

---

## エラーが出たときの確認手順

1. GitHub の **Actions** タブを開く
2. **失敗した実行**（赤い × の行）をクリック
3. 失敗している **ステップ**（赤い ×）をクリックしてログを開く
4. ログの最後のエラーメッセージを確認

### よくある原因と対処

| エラー例 | 原因 | 対処 |
|----------|------|------|
| `base64: invalid input` | Secret の Base64 が不正 | credentials.json / token.json を再度 base64 にして、**改行なし**で Secrets に登録し直す |
| `credentials.json が見つかりません` | Create credentials の失敗 | 上記と同じ。Secret 名が `GMAIL_CREDENTIALS_B64`・`GMAIL_TOKEN_B64` か確認 |
| `Refresh token has expired` / `Token has been expired` | token の有効期限切れ | 手元で一度 `gmail_ai_news_save.py` を実行して新しい token.json を取得し、Base64 を Secrets の `GMAIL_TOKEN_B64` に更新 |
| `run_local_server` やブラウザ認証に関するエラー | CI ではブラウザ認証不可 | token が期限切れのため再認証を求められている。上記と同様に手元で token を更新し `GMAIL_TOKEN_B64` を更新 |
| `Permission denied`（push 時） | リポジトリへの書き込み権限 | ワークフローに `permissions: contents: write` があるか確認（すでに設定済み） |

### 失敗した週のニュースをあとから保存する場合（転送メール）

GitHub Actions が失敗した週など、届いていたのに保存されていない分は、m19m から matsuno.estate に**手動で1通転送**したうえで、`gmail_ai_news_save.py --date 届いた日 --allow-forwarded` で取得できます。手順の詳細は **`いけともAIニュース_転送ルールの作り方.md`** の「既に届いた分を手動転送して保存したい場合」を参照。
