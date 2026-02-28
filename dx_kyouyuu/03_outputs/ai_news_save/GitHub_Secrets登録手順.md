# GitHub Secrets 登録手順（いけともAIニュース用）

GitHub Actions で AI ニュースを定期保存するには、Gmail の認証情報を GitHub の「Secrets」に登録する必要があります。以下、画面ごとに手順を説明します。

---

## 前提

- DX互助会のリポジトリが GitHub に push 済みであること
- `credentials.json` と `token.json` が手元にあること  
  （場所: 215 フォルダ内 `C1_cursor/1b_Cursorマニュアル`）

---

## リポジトリの確認：GitHub に接続されているか

### ターミナルで確認する方法

1. ターミナルを開く
2. 以下を実行（DX互助会フォルダに移動してリモートを確認）:

```bash
cd "/Users/matsunomasaharu/Library/CloudStorage/GoogleDrive-m19m.hrts83@gmail.com/マイドライブ/DX互助会_共有フォルダ"
git remote -v
```

3. **結果の見方**:
   - **何も表示されない** → GitHub に接続されていない（リモート未設定）
   - **URL が表示される**（例: `origin  https://github.com/ユーザー名/リポジトリ名.git`）→ 接続済み

### 接続されていない場合

次の「リポジトリの新規作成と接続」に進んでください。

### 接続されている場合

「手順 1: GitHub でリポジトリを開く」に進んでください。

---

## リポジトリの新規作成と接続

GitHub にまだリポジトリがない場合は、作成してから接続します。

### 1. GitHub で新規リポジトリを作成

1. [https://github.com](https://github.com) にアクセスしてログイン
2. 右上の **「+」** をクリック → **「New repository」** を選択
3. 以下を入力:
   - **Repository name**: `DX互助会_共有フォルダ` など（任意の名前）
   - **Visibility**: Private（非公開）を推奨
   - **「Add a README file」** は **チェックしない**（中の身はすでにあるため）
4. **「Create repository」** をクリック

### 2. 作成後の画面で表示される URL をコピー

- `https://github.com/あなたのユーザー名/リポジトリ名.git` のような URL が表示されます
- この URL をコピーしておく
https://github.com/m19mhrts83-cyber/DX-_-

### 3. ローカルから GitHub に接続

ターミナルで以下を実行（`YOUR_USERNAME` と `YOUR_REPO` は実際の値に置き換える）:

```bash
cd "/Users/matsunomasaharu/Library/CloudStorage/GoogleDrive-m19m.hrts83@gmail.com/マイドライブ/DX互助会_共有フォルダ"
git remote add origin https://github.com/m19mhrts83-cyber/DX-_-
```

例: `https://github.com/m19m-hrts83/DX互助会.git` の場合

```bash
git remote add origin https://github.com/m19m-hrts83/DX互助会.git
```

### 4. 初回 push

```bash
git add .
git commit -m "初回コミット"
git push -u origin main
```

※ ブランチ名が `master` の場合は `git push -u origin master` に読み替え

以上で GitHub に接続され、以降は「手順 1」から GitHub Secrets の登録に進めます。

---

## 手順 1: GitHub でリポジトリを開く

1. ブラウザで [https://github.com](https://github.com) にアクセス
2. ログインする
3. 画面上部の検索バー、または左側の **Repositories** から、**DX互助会のリポジトリ**を探してクリック

   - 例: `m19m-hrts83/DX互助会_共有フォルダ` のような名前

---

## 手順 2: Settings（設定）を開く

1. リポジトリのトップページで、上部メニューの **「Code」** の右側にある **「Issues」「Pull requests」** などのタブを確認
2. 右端の **「Settings」** タブをクリック

   ```
   [Code] [Issues] [Pull requests] ... [Settings]
   ```

3. **注意**: 「Settings」が表示されない場合は、そのリポジトリのオーナー（管理者）権限が必要です。権限がない場合はリポジトリのオーナーに依頼してください。

---

## 手順 3: Secrets and variables → Actions を開く

1. 左側のサイドバーが表示されます
2. **「Secrets and variables」** の項目をクリック
3. さらに **「Actions」** をクリック

   ```
   左サイドバー:
   ─────────────────
   General
   Access
   ...
   Secrets and variables  ← ここをクリック
     └ Actions           ← この中で「Actions」をクリック
   ```

4. 画面に「Repository secrets」というセクションが表示されます

---

## 手順 4: credentials.json の Base64 を作成する

ターミナル（Mac の「ターミナル」アプリ）で以下を実行します。

### 4-1. フォルダに移動

```bash
cd "/Users/matsunomasaharu/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/C1_cursor/1b_Cursorマニュアル"
```

### 4-2. Base64 を作成してクリップボードにコピー

```bash
base64 -i credentials.json | pbcopy
```

- これで `credentials.json` の内容が Base64 変換され、クリップボードにコピーされました
- 画面には何も表示されませんが、正常にコピーされています

---

## 手順 5: GMAIL_CREDENTIALS_B64 を登録する

1. GitHub の「Actions」 secrets 画面に戻る
2. **「New repository secret」** ボタンをクリック
3. **Name（名前）** の欄に以下を入力（半角で、コピー＆ペースト推奨）:

   ```
   GMAIL_CREDENTIALS_B64
   ```

4. **Secret（値）** の欄に、クリップボードの内容を貼り付け
   - Mac: `command + V`
   - 長い文字列が 1 行で貼り付けられます

5. **「Add secret」** ボタンをクリック

6. 「Repository secrets」の一覧に `GMAIL_CREDENTIALS_B64` が追加されていることを確認

---

## 手順 6: token.json の Base64 を作成する

ターミナルで以下を実行します。

```bash
base64 -i token.json | pbcopy
```

- 同じフォルダにいる前提です（手順 4-1 の `cd` のまま）

---

## 手順 7: GMAIL_TOKEN_B64 を登録する

1. GitHub の「Actions」 secrets 画面で、再度 **「New repository secret」** をクリック
2. **Name（名前）** に以下を入力:

   ```
   GMAIL_TOKEN_B64
   ```

3. **Secret（値）** に、クリップボードの内容を貼り付け（`command + V`）
4. **「Add secret」** をクリック

5. 「Repository secrets」の一覧に次の 2 つが表示されていれば完了です:

   - `GMAIL_CREDENTIALS_B64`
   - `GMAIL_TOKEN_B64`

---

## 確認

- Secrets は値の内容を再表示できません（「●●●●●●」のようにマスクされます）
- 名前（`GMAIL_CREDENTIALS_B64` と `GMAIL_TOKEN_B64`）が正しく登録されていれば問題ありません

---

## トラブルシューティング

### 「Settings」が見つからない

- リポジトリのオーナーか、管理者権限を持つアカウントでログインしているか確認してください
- フォークしたリポジトリの場合、元のリポジトリの Settings は編集できません

### Base64 の作成でエラーが出る

- `credentials.json` や `token.json` が存在するか確認してください
- 手順 4-1 の `cd` コマンドで正しいフォルダに移動しているか確認してください

### Secret を間違えて登録した

- 「Repository secrets」一覧で該当 Secret の右側の **「Update」** をクリックして、正しい値を再登録できます

---

## エラー: "refusing to allow an OAuth App to create or update workflow"

`git push` 時にこのエラーが出る場合は、**workflow ファイル（`.github/workflows/*.yml`）を変更する権限**が現在の認証に含まれていません。

### 対処法 A: GitHub CLI で権限を追加（推奨）

GitHub CLI（`gh`）を使っている場合:

```bash
gh auth refresh -s workflow
```

ブラウザが開き、workflow 権限の付与を求められます。承認後、もう一度 `git push` を試してください。

### 対処法 B: Personal Access Token（PAT）を更新

1. [https://github.com/settings/tokens](https://github.com/settings/tokens) を開く
2. 既存のトークンがあれば **「Edit」** をクリックし、**workflow** にチェックを入れて保存
3. 新規作成する場合は **「Generate new token (classic)」** を選択し、**repo** と **workflow** にチェック
4. 生成されたトークン（`ghp_` で始まる文字列）をコピー

**Mac の Keychain を更新する場合:**

- 「キーチェーンアクセス」アプリを開く
- 検索で `github.com` を入力
- `github.com` の「インターネットパスワード」をダブルクリック
- 「パスワードを表示」にチェックを入れ、既存のパスワードを新しい PAT に差し替え

### 対処法 C: SSH を使う

HTTPS の代わりに SSH を使うと、このエラーを避けられる場合があります。

1. SSH キーがなければ作成: `ssh-keygen -t ed25519 -C "your_email@example.com"`
2. 公開鍵を GitHub に登録（Settings → SSH and GPG keys）
3. リモートを SSH に変更:

```bash
git remote set-url origin git@github.com:ユーザー名/DX-_-.git
```

4. 再度 `git push`
